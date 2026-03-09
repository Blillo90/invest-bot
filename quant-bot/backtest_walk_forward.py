"""
Walk-forward backtest para detectar sesgo in-sample.

Metodología:
  - IN-SAMPLE  : 2015-01-01 → 2019-12-31  (5 años — "diseño" de la estrategia)
  - OUT-OF-SAMPLE: 2020-01-01 → 2026-03-07 (6 años — validación real)

Si los resultados se degradan mucho en OOS, hay overfitting/survivorship bias.
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

DOWNLOAD_START = "2014-01-01"
BACKTEST_END   = dt.date(2026, 3, 7)

IS_START  = dt.date(2015, 1,  1)   # In-Sample start
IS_END    = dt.date(2019, 12, 31)  # In-Sample end
OOS_START = dt.date(2020, 1,  1)   # Out-of-Sample start

print(f"Descargando {len(SP100)} símbolos desde {DOWNLOAD_START}...")
raw = yf.download(SP100, start=DOWNLOAD_START, end=str(BACKTEST_END),
                  auto_adjust=True, progress=False, group_by="ticker")

rows = []
for sym in SP100:
    try:
        sub = raw[sym][["Open", "High", "Low", "Close", "Volume"]].copy()
    except KeyError:
        continue
    sub = sub.dropna(subset=["Close"])
    sub.index = pd.to_datetime(sub.index).date
    sub.columns = ["open", "high", "low", "close", "volume"]
    sub["symbol"] = sym
    sub["date"] = sub.index
    rows.append(sub[["symbol", "date", "open", "high", "low", "close", "volume"]])

bars = pd.concat(rows, ignore_index=True)
bars["date"] = pd.to_datetime(bars["date"]).dt.date
print(f"Bars: {len(bars)} filas | {bars['symbol'].nunique()} símbolos")


def compute_features(df):
    df = df.sort_values("date").reset_index(drop=True)
    c = df["close"]
    out = df[["symbol", "date"]].copy()
    out["ret_5"]  = c.pct_change(5)
    out["ret_10"] = c.pct_change(10)
    out["ret_20"] = c.pct_change(20)
    v20 = c.pct_change().rolling(20).std()
    out["vol_20"]        = v20
    out["vol_z_20"]      = (v20 - v20.rolling(60).mean()) / (v20.rolling(60).std() + 1e-9)
    out["dollar_vol_20"] = (c * df["volume"]).rolling(20).mean()
    return out.dropna(subset=["ret_20", "vol_20", "dollar_vol_20"])


feat = pd.concat([compute_features(g.copy()) for _, g in bars.groupby("symbol")],
                 ignore_index=True)

# SPY benchmark
spy_raw = yf.download("SPY", start=str(IS_START), end=str(BACKTEST_END),
                      auto_adjust=True, progress=False)
spy = spy_raw["Close"].squeeze()
spy.index = pd.to_datetime(spy.index)


def rp(s):
    return s.rank(pct=True)


def run_bt(bars_df, feat_df, cfg, start_capital=100_000):
    FEE = 20 / 10_000.0
    days = sorted(feat_df["date"].unique())
    cash = start_capital; pos = {}; log = []; peak = start_capital
    for day in days:
        db = bars_df[bars_df["date"] == day].set_index("symbol")["close"].to_dict()
        if not db:
            continue
        f = feat_df[feat_df["date"] == day].copy()
        if f.empty:
            continue
        f = f.sort_values("dollar_vol_20", ascending=False).head(2000)
        col = {"ret_5": "ret_5", "ret_10": "ret_10"}.get(cfg["SIG"], "ret_20")
        f["score"] = rp(f[col].fillna(0)) + rp(f["vol_z_20"].fillna(0))
        f = f.sort_values("score", ascending=False).reset_index(drop=True)
        n = len(f)
        buy_set  = set(f.head(max(1, int(cfg["BT"] * n)))["symbol"])
        hold_set = set(f.head(max(1, int(cfg["ST"] * n)))["symbol"])
        cur = set(pos.keys())
        to_sell = sorted(cur - hold_set)[:cfg["MR"]]
        to_buy  = sorted(buy_set - cur)[:cfg["MR"]]
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
        exp2 = sum(pos[s]["sh"] * db.get(s, 0) for s in pos)
        eq = cash + exp2; peak = max(peak, eq)
        log.append({"date": day, "equity": eq, "dd": eq / peak - 1})
    df_log = pd.DataFrame(log).set_index("date")
    df_log.index = pd.to_datetime(df_log.index)
    return df_log


def summarize(df, spy_series, period_name, start_cap=100_000):
    monthly = df["equity"].resample("ME").last()
    mret    = monthly.pct_change().dropna()
    ny      = (df.index[-1] - df.index[0]).days / 365.25
    final   = df["equity"].iloc[-1]
    cagr    = ((final / start_cap) ** (1 / ny) - 1) * 100
    exc     = mret - 0.045 / 12
    sh      = exc.mean() / exc.std() * math.sqrt(12) if exc.std() > 0 else 0
    max_dd  = df["dd"].min() * 100

    # SPY para el mismo período
    spy_p = spy_series[spy_series.index >= df.index[0]]
    spy_p = spy_p[spy_p.index <= df.index[-1]]
    spy_m = spy_p.resample("ME").last()
    spy_mr = spy_m.pct_change().dropna()
    spy_ny = (spy_m.index[-1] - spy_m.index[0]).days / 365.25
    spy_cagr = ((spy_m.iloc[-1] / spy_m.iloc[0]) ** (1 / spy_ny) - 1) * 100
    spy_exc  = spy_mr - 0.045 / 12
    spy_sh   = spy_exc.mean() / spy_exc.std() * math.sqrt(12)

    return {
        "period": period_name,
        "final": final, "cagr": cagr, "max_dd": max_dd, "sharpe": sh,
        "wins": (mret > 0).sum(), "n": len(mret),
        "spy_cagr": spy_cagr, "spy_sharpe": spy_sh,
        "alpha": cagr - spy_cagr,
        "monthly": monthly,
    }


# Configuración "mejor" del backtest anterior
CFG = dict(BT=0.10, ST=0.30, MR=10, MP=10, SIG="ret_20")

periods = {
    "FULL (2015–2026)":       (IS_START,  BACKTEST_END),
    "IN-SAMPLE (2015–2019)":  (IS_START,  IS_END),
    "OUT-OF-SAMPLE (2020–2026)": (OOS_START, BACKTEST_END),
}

results = {}
for name, (s, e) in periods.items():
    b = bars[bars["date"].between(s, e)]
    f = feat[feat["date"].between(s, e)]
    df = run_bt(b, f, CFG)
    results[name] = summarize(df, spy, name)
    print(f"  {name}: CAGR {results[name]['cagr']:+.2f}% | SPY {results[name]['spy_cagr']:+.2f}% | Alpha {results[name]['alpha']:+.2f}%")

print()
print("=" * 90)
print("  ANÁLISIS IN-SAMPLE vs OUT-OF-SAMPLE — SP100 top-10 ret_20 | $100,000")
print("  Objetivo: detectar si los buenos resultados son reales o fruto del overfitting")
print("=" * 90)

W = 22
names = list(results.keys())
print(f"\n{'Métrica':<22}", end="")
for n in names:
    print(f"  {n[:W]:<{W}}", end="")
print()
print("-" * (22 + (W + 2) * len(names)))

for lbl, key, fmt, extra in [
    ("Capital final",    "final",     "${:>12,.0f}", ""),
    ("CAGR estrategia",  "cagr",      "{:>+9.2f}%",  ""),
    ("CAGR SPY (ref.)",  "spy_cagr",  "{:>+9.2f}%",  ""),
    ("Alpha (vs SPY)",   "alpha",     "{:>+9.2f}%",  " ← clave"),
    ("Max Drawdown",     "max_dd",    "{:>+9.2f}%",  ""),
    ("Sharpe",           "sharpe",    "{:>9.2f}",    ""),
    ("SPY Sharpe",       "spy_sharpe","{:>9.2f}",    ""),
    ("Meses positivos",  "wins",      None,           ""),
]:
    print(f"{lbl+extra:<22}", end="")
    for n in names:
        v = results[n][key]
        if key == "wins":
            s = f"{v}/{results[n]['n']}"
            print(f"  {s:<{W}}", end="")
        else:
            print(f"  {fmt.format(v):<{W}}", end="")
    print()

print()
print("--- Retorno anual ---")
print(f"{'Año':<6}", end="")
for n in names:
    print(f"  {n[:W]:<{W}}", end="")
print()
print("-" * (6 + (W + 2) * len(names)))

all_years = sorted({yr for n in names
                    for yr in results[n]["monthly"].index.year.unique()})
for yr in all_years:
    print(f"{yr:<6}", end="")
    for n in names:
        m = results[n]["monthly"]
        yr_m = m[m.index.year == yr]
        if len(yr_m) < 2:
            tag = "  (IS)" if yr <= 2019 else "  (OOS)"
            print(f"  {'N/A':<{W}}", end="")
            continue
        ret = (yr_m.iloc[-1] / yr_m.iloc[0] - 1) * 100
        tag = " [IS]" if yr <= 2019 else " [OOS]"
        s = f"{'+' if ret>=0 else ''}{ret:.2f}%{tag}"
        print(f"  {s:<{W}}", end="")
    print()

# Veredicto
is_alpha  = results["IN-SAMPLE (2015–2019)"]["alpha"]
oos_alpha = results["OUT-OF-SAMPLE (2020–2026)"]["alpha"]
full_alpha = results["FULL (2015–2026)"]["alpha"]

print()
print("=" * 90)
print("  VEREDICTO")
print("=" * 90)
print(f"  Alpha IN-SAMPLE   : {is_alpha:+.2f}%  (resultado 'conocido' — puede estar inflado)")
print(f"  Alpha OUT-OF-SAMPLE: {oos_alpha:+.2f}%  (resultado real — el que importa)")
print(f"  Alpha FULL        : {full_alpha:+.2f}%")
print()
degradation = is_alpha - oos_alpha
if abs(degradation) < 3:
    verdict = "ROBUSTO — poca degradación OOS, el sesgo in-sample es bajo."
elif oos_alpha > 0:
    verdict = f"PARCIALMENTE SESGADO — alpha cae {degradation:.1f}pp OOS pero sigue positivo."
else:
    verdict = f"SESGADO — alpha cae {degradation:.1f}pp OOS y se vuelve negativo. Overfitting probable."
print(f"  → {verdict}")
print()
if oos_alpha < is_alpha:
    print("  Causas probables del sesgo:")
    print("  1. Survivorship bias: el S&P100 de 2026 excluye empresas que quebaron/salieron")
    print("  2. Parameter fitting: los parámetros BT/ST/MP se eligieron viendo el período completo")
    print("  3. El momentum funcionó especialmente bien en 2015-2019 (bull market suave)")
print("=" * 90)
