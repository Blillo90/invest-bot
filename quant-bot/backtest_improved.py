"""
Estrategia mejorada: Momentum relativo + Filtro de régimen de mercado

MEJORAS vs. versión base:
  1. Filtro de régimen (SPY > SMA200) — si el mercado está en bear, ir a cash
  2. Momentum relativo (ret stock - ret SPY) — buscamos stocks que superen al mercado
  3. Trend filter: cada stock debe estar sobre su SMA50 para ser comprable
  4. Vol filter: excluir stocks con volatilidad z-score muy alta (>1.5σ)

Objetivo: superar los ~13% CAGR de SPY con alpha positivo consistente
"""

import yfinance as yf, pandas as pd, numpy as np, math, datetime as dt

SP100 = [
    "AAPL","ABBV","ABT","ACN","ADBE","AIG","AMD","AMGN","AMT","AMZN",
    "AVGO","AXP","BA","BAC","BK","BKNG","BLK","BMY","BRK-B","C",
    "CAT","CHTR","CL","CMCSA","COF","COP","COST","CRM","CSCO","CVS",
    "CVX","DE","DHR","DIS","DOW","DUK","EMR","EXC","F","FDX",
    "GD","GE","GILD","GM","GOOGL","GS","HD","HON","IBM","INTC",
    "INTU","ISRG","JNJ","JPM","KHC","KO","LIN","LLY","LMT","LOW",
    "MA","MCD","MDLZ","MDT","MET","META","MMM","MO","MRK","MS",
    "MSFT","NEE","NFLX","NKE","NOW","NVDA","ORCL","PEP","PFE","PG",
    "PM","PYPL","QCOM","RTX","SBUX","SCHW","SO","SPG","T","TGT",
    "TMO","TMUS","TXN","UNH","UNP","UPS","USB","V","VZ","WFC",
    "WMT","XOM",
]

DOWNLOAD_START = "2013-01-01"   # más warmup para SMA200
BACKTEST_START = dt.date(2015, 1, 1)
BACKTEST_END   = dt.date(2026, 3, 7)

# ── Descarga de datos ─────────────────────────────────────────────────────────
print(f"Descargando {len(SP100)} símbolos + SPY desde {DOWNLOAD_START}...")
raw = yf.download(SP100 + ["SPY"], start=DOWNLOAD_START, end=str(BACKTEST_END),
                  auto_adjust=True, progress=False, group_by="ticker")

rows = []
for sym in SP100:
    try:
        sub = raw[sym][["Open","High","Low","Close","Volume"]].copy()
    except KeyError:
        continue
    sub = sub.dropna(subset=["Close"])
    sub.index = pd.to_datetime(sub.index).date
    sub.columns = ["open","high","low","close","volume"]
    sub["symbol"] = sym
    rows.append(sub[["symbol","open","high","low","close","volume"]])

bars = pd.concat(rows)
bars.index.name = "date"
bars = bars.reset_index()
bars["date"] = pd.to_datetime(bars["date"]).dt.date

# SPY como régimen de mercado
spy_raw = raw["SPY"]["Close"].squeeze()
spy_raw.index = pd.to_datetime(spy_raw.index).date

print(f"Bars: {len(bars):,} | Símbolos: {bars['symbol'].nunique()}")

# ── Features ──────────────────────────────────────────────────────────────────
def compute_features(df, spy_dict):
    df = df.sort_values("date").reset_index(drop=True)
    c = df["close"]
    out = df[["symbol","date"]].copy()

    # Momentum absoluto
    out["ret_20"]  = c.pct_change(20)
    out["ret_60"]  = c.pct_change(60)

    # Momentum relativo vs SPY (stock supera al mercado)
    spy_20  = df["date"].map(lambda d: spy_dict.get(d, np.nan))
    spy_ser = pd.Series(spy_20.values, index=df.index)
    out["rel_20"] = out["ret_20"] - spy_ser.pct_change(20)   # alpha puro
    out["rel_60"] = out["ret_60"] - spy_ser.pct_change(60)

    # Trend: precio vs SMA50
    out["sma50"]  = c.rolling(50).mean()
    out["above_sma50"] = (c > out["sma50"]).astype(int)

    # Volatilidad
    v20 = c.pct_change().rolling(20).std()
    out["vol_z_20"] = (v20 - v20.rolling(60).mean()) / (v20.rolling(60).std() + 1e-9)

    out["dollar_vol_20"] = (c * df["volume"]).rolling(20).mean()

    return out.dropna(subset=["ret_20","rel_20","vol_z_20","dollar_vol_20"])

spy_dict = spy_raw.to_dict()
feat = pd.concat([compute_features(g.copy(), spy_dict)
                  for _, g in bars.groupby("symbol")], ignore_index=True)

# Régimen de mercado: SPY > SMA200
spy_s = pd.Series(spy_dict).sort_index()
spy_sma200 = spy_s.rolling(200).mean()
regime = (spy_s > spy_sma200).to_dict()   # True = bull, False = bear/cash

bars_bt = bars[bars["date"] >= BACKTEST_START]
feat_bt = feat[feat["date"] >= BACKTEST_START]

# ── Motor de backtest ─────────────────────────────────────────────────────────
def rp(s):
    return s.rank(pct=True)

def run_bt(bars_df, feat_df, cfg, regime_map=None):
    FEE  = 20 / 10_000.0
    days = sorted(feat_df["date"].unique())
    cash = 100_000; pos = {}; log = []; peak = 100_000

    for day in days:
        db = bars_df[bars_df["date"] == day].set_index("symbol")["close"].to_dict()
        if not db:
            continue
        f = feat_df[feat_df["date"] == day].copy()
        if f.empty:
            continue

        # ── Filtro de régimen ──────────────────────────────────────────────
        in_bull = regime_map.get(day, True) if regime_map else True

        if not in_bull:
            # Vender todo y quedarse en cash
            for sym in list(pos.keys()):
                if sym in db:
                    cash += pos[sym]["sh"] * db[sym] * (1 - FEE)
                    del pos[sym]
            exp = 0
            eq  = cash
        else:
            # ── Filtros de universo ────────────────────────────────────────
            f = f.sort_values("dollar_vol_20", ascending=False).head(2000)
            # Solo stocks sobre SMA50
            if cfg.get("TREND_FILTER"):
                f = f[f["above_sma50"] == 1]
            # Excluir alta volatilidad
            if cfg.get("VOL_FILTER"):
                f = f[f["vol_z_20"] < 1.5]

            # ── Score compuesto ────────────────────────────────────────────
            score = pd.Series(0.0, index=f.index)
            if cfg.get("USE_REL"):                       # momentum relativo
                score += rp(f["rel_20"].fillna(0)) * 0.5
                score += rp(f["rel_60"].fillna(0)) * 0.3
            else:
                score += rp(f["ret_20"].fillna(0)) * 0.8
            score += rp(-f["vol_z_20"].fillna(0)) * 0.2  # premia baja volatilidad relativa
            f["score"] = score
            f = f.sort_values("score", ascending=False).reset_index(drop=True)

            n        = len(f)
            buy_set  = set(f.head(max(1, int(cfg["BT"] * n)))["symbol"])
            hold_set = set(f.head(max(1, int(cfg["ST"] * n)))["symbol"])
            cur      = set(pos.keys())
            to_sell  = sorted(cur - hold_set)[:cfg["MR"]]
            to_buy   = sorted(buy_set - cur)[:cfg["MR"]]

            exp = sum(pos[s]["sh"] * db.get(s, 0) for s in pos)
            tgt = (cash + exp) * 0.99 / cfg["MP"]

            for sym in to_sell:
                if sym not in db:
                    continue
                cash += pos[sym]["sh"] * db[sym] * (1 - FEE)
                del pos[sym]

            if tgt >= 1000:
                sl = max(0, cfg["MP"] - len(pos))
                for sym in to_buy[:sl]:
                    if sym not in db or tgt > cash:
                        continue
                    pos[sym] = {"sh": tgt / (db[sym] * (1 + FEE))}
                    cash -= tgt

            exp = sum(pos[s]["sh"] * db.get(s, 0) for s in pos)
            eq  = cash + exp

        peak = max(peak, eq)
        log.append({"date": day, "equity": eq, "dd": eq / peak - 1,
                    "n_pos": len(pos), "in_bull": in_bull})

    df_log = pd.DataFrame(log).set_index("date")
    df_log.index = pd.to_datetime(df_log.index)
    return df_log


# ── Benchmarks y estrategias ──────────────────────────────────────────────────
spy_s_bt = spy_s[spy_s.index >= BACKTEST_START]
spy_monthly = pd.Series({k: v for k, v in spy_dict.items() if k >= BACKTEST_START})
spy_monthly.index = pd.to_datetime(spy_monthly.index)
spy_monthly = spy_monthly.resample("ME").last()
spy_mret  = spy_monthly.pct_change().dropna()
spy_ny    = (spy_monthly.index[-1] - spy_monthly.index[0]).days / 365.25
spy_final = spy_monthly.iloc[-1] / spy_monthly.iloc[0] * 100_000
spy_cagr  = ((spy_final / 100_000) ** (1 / spy_ny) - 1) * 100
spy_exc   = spy_mret - 0.045 / 12
spy_sh    = spy_exc.mean() / spy_exc.std() * math.sqrt(12)

CFGS = {
    "BASE (ret_20 abs)": dict(BT=0.10, ST=0.30, MR=10, MP=10,
                              USE_REL=False, TREND_FILTER=False, VOL_FILTER=False),
    "IMPROVED v1 (régimen)": dict(BT=0.10, ST=0.30, MR=10, MP=10,
                                  USE_REL=False, TREND_FILTER=False, VOL_FILTER=False,
                                  REGIME=True),
    "IMPROVED v2 (+momentum rel)": dict(BT=0.10, ST=0.30, MR=10, MP=10,
                                        USE_REL=True, TREND_FILTER=False, VOL_FILTER=False,
                                        REGIME=True),
    "IMPROVED v3 (+trend+vol)": dict(BT=0.10, ST=0.30, MR=10, MP=10,
                                     USE_REL=True, TREND_FILTER=True, VOL_FILTER=True,
                                     REGIME=True),
    "IMPROVED v4 (más posiciones)": dict(BT=0.15, ST=0.35, MR=15, MP=15,
                                         USE_REL=True, TREND_FILTER=True, VOL_FILTER=True,
                                         REGIME=True),
}

results = {}
for name, cfg in CFGS.items():
    regime_map = regime if cfg.get("REGIME") else None
    df = run_bt(bars_bt, feat_bt, cfg, regime_map=regime_map)
    monthly = df["equity"].resample("ME").last()
    mret    = monthly.pct_change().dropna()
    ny      = (df.index[-1] - df.index[0]).days / 365.25
    final   = df["equity"].iloc[-1]
    cagr    = ((final / 100_000) ** (1 / ny) - 1) * 100
    exc     = mret - 0.045 / 12
    sh      = exc.mean() / exc.std() * math.sqrt(12) if exc.std() > 0 else 0
    pct_bull = df["in_bull"].mean() * 100 if "in_bull" in df.columns else 100
    results[name] = dict(
        final=final, cagr=cagr, max_dd=df["dd"].min() * 100,
        sharpe=sh, wins=(mret > 0).sum(), n=len(mret),
        pct_bull=pct_bull, monthly=monthly,
    )
    print(f"  {name[:40]:<40} CAGR {cagr:+.2f}% | SPY {spy_cagr:+.2f}% | "
          f"Alpha {cagr-spy_cagr:+.2f}% | Sharpe {sh:.2f} | MaxDD {df['dd'].min()*100:+.2f}%")

results["SPY (benchmark)"] = dict(
    final=spy_final, cagr=spy_cagr, max_dd=float("nan"),
    sharpe=spy_sh, wins=(spy_mret > 0).sum(), n=len(spy_mret),
    pct_bull=100, monthly=spy_monthly / spy_monthly.iloc[0] * 100_000,
)

# ── Tabla resumen ─────────────────────────────────────────────────────────────
names = list(results.keys())
W = 28
ny = (BACKTEST_END - BACKTEST_START).days / 365.25
print()
print("=" * (22 + (W + 2) * len(names)))
print(f"  BACKTEST MEJORADO {BACKTEST_START.year}–{BACKTEST_END.year} ({ny:.1f} años) | $100,000 inicial")
print(f"  Mejoras: régimen SPY>SMA200 | momentum relativo | SMA50 trend | vol filter")
print("=" * (22 + (W + 2) * len(names)))

print(f"\n{'Métrica':<22}", end="")
for n in names:
    print(f"  {n[:W]:<{W}}", end="")
print()
print("-" * (22 + (W + 2) * len(names)))

for lbl, key, fmt in [
    ("Capital final",    "final",    "${:>12,.0f}"),
    ("CAGR",             "cagr",     "{:>+9.2f}%"),
    ("Alpha vs SPY",     None,       None),
    ("Max Drawdown",     "max_dd",   "{:>+9.2f}%"),
    ("Sharpe",           "sharpe",   "{:>9.2f}"),
    ("Meses positivos",  "wins",     None),
    ("% tiempo bull",    "pct_bull", "{:>9.1f}%"),
]:
    print(f"{lbl:<22}", end="")
    for n in names:
        if key is None:  # alpha
            v = results[n]["cagr"] - spy_cagr
            s = f"{'+' if v>=0 else ''}{v:.2f}%"
            print(f"  {s:<{W}}", end="")
        elif key == "wins":
            s = f"{results[n]['wins']}/{results[n]['n']}"
            print(f"  {s:<{W}}", end="")
        elif math.isnan(results[n][key]):
            print(f"  {'N/A':<{W}}", end="")
        else:
            print(f"  {fmt.format(results[n][key]):<{W}}", end="")
    print()

# ── Retorno anual ─────────────────────────────────────────────────────────────
print("\n--- Retorno anual ---")
print(f"{'Año':<6}", end="")
for n in names:
    print(f"  {n[:W]:<{W}}", end="")
print()
print("-" * (6 + (W + 2) * len(names)))

all_yrs = range(BACKTEST_START.year, BACKTEST_END.year + 1)
for yr in all_yrs:
    print(f"{yr:<6}", end="")
    for n in names:
        m = results[n]["monthly"]
        ym = m[m.index.year == yr]
        if len(ym) < 2:
            print(f"  {'N/A':<{W}}", end="")
            continue
        ret = (ym.iloc[-1] / ym.iloc[0] - 1) * 100
        spy_yr = spy_monthly[spy_monthly.index.year == yr]
        spy_ret = (spy_yr.iloc[-1] / spy_yr.iloc[0] - 1) * 100 if len(spy_yr) >= 2 else 0
        alpha = ret - spy_ret
        tag = f" ({'+' if alpha>=0 else ''}{alpha:.1f}α)"
        s = f"{'+' if ret>=0 else ''}{ret:.1f}%{tag}"
        print(f"  {s:<{W}}", end="")
    print()

print()
print("--- Interpretación del alpha anual: positivo=supera a SPY ese año ---")
print("=" * (22 + (W + 2) * len(names)))
