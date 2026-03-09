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

DOWNLOAD_START = "2014-01-01"   # warmup para features (ret_20, vol_z_20 necesitan ~80 días)
BACKTEST_START = dt.date(2015, 1, 1)
BACKTEST_END   = dt.date(2026, 3, 7)

print(f"Descargando {len(SP100)} símbolos desde {DOWNLOAD_START}...")
raw = yf.download(SP100, start=DOWNLOAD_START, end=str(BACKTEST_END),
                  auto_adjust=True, progress=False, group_by="ticker")
print(f"Descarga completa. MultiIndex: {isinstance(raw.columns, pd.MultiIndex)}")

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
print(f"Features calculadas: {len(feat)} filas")

# Recortar al período real de backtest
bars_bt = bars[bars["date"] >= BACKTEST_START]
feat_bt = feat[feat["date"] >= BACKTEST_START]
print(f"Período backtest: {feat_bt['date'].min()} → {feat_bt['date'].max()}\n")


def rp(s):
    return s.rank(pct=True)


def run_bt(bars_df, feat_df, cfg):
    FEE = 20 / 10_000.0
    days = sorted(feat_df["date"].unique())
    cash = 100_000; pos = {}; log = []; peak = 100_000
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
    df = pd.DataFrame(log).set_index("date")
    df.index = pd.to_datetime(df.index)
    return df


# También descargamos SPY como benchmark
print("Descargando SPY (benchmark S&P500)...")
spy_raw = yf.download("SPY", start=str(BACKTEST_START), end=str(BACKTEST_END),
                      auto_adjust=True, progress=False)
spy = spy_raw["Close"].squeeze()
spy.index = pd.to_datetime(spy.index)
spy_monthly = spy.resample("ME").last()
spy_mret = spy_monthly.pct_change().dropna()
spy_final = spy_monthly.iloc[-1] / spy_monthly.iloc[0] * 100_000
spy_ny = (spy_monthly.index[-1] - spy_monthly.index[0]).days / 365.25
spy_cagr = ((spy_final / 100_000) ** (1 / spy_ny) - 1) * 100
spy_exc = spy_mret - 0.045 / 12
spy_sharpe = spy_exc.mean() / spy_exc.std() * math.sqrt(12)
print(f"SPY benchmark: CAGR {spy_cagr:+.2f}% | Sharpe {spy_sharpe:.2f} | Final ${spy_final:,.0f}\n")

CFGS = {
    "SP100 rot.total ret_10": dict(BT=0.25, ST=0.60, MR=20, MP=30, SIG="ret_10"),
    "SP100 top-10 ret_20":    dict(BT=0.10, ST=0.30, MR=10, MP=10, SIG="ret_20"),
    "SP100 ret_5 momentum":   dict(BT=0.20, ST=0.50, MR=15, MP=20, SIG="ret_5"),
    "SP100 top-5 MAXIMO":     dict(BT=0.05, ST=0.15, MR=5,  MP=5,  SIG="ret_10"),
}

results = {}
for name, cfg in CFGS.items():
    df = run_bt(bars_bt, feat_bt, cfg)
    monthly = df["equity"].resample("ME").last()
    mret = monthly.pct_change().dropna()
    ny = (df.index[-1] - df.index[0]).days / 365.25
    final = df["equity"].iloc[-1]
    cagr = ((final / 100_000) ** (1 / ny) - 1) * 100
    exc = mret - 0.045 / 12
    sh = exc.mean() / exc.std() * math.sqrt(12) if exc.std() > 0 else 0
    results[name] = dict(
        final=final, cagr=cagr, max_dd=df["dd"].min() * 100,
        sharpe=sh, wins=(mret > 0).sum(), n=len(mret),
        best=mret.max() * 100, worst=mret.min() * 100, monthly=monthly,
    )

# Añadir SPY como fila de referencia
results["SPY (benchmark)"] = dict(
    final=spy_final, cagr=spy_cagr, max_dd=float("nan"),
    sharpe=spy_sharpe, wins=(spy_mret > 0).sum(), n=len(spy_mret),
    best=spy_mret.max() * 100, worst=spy_mret.min() * 100, monthly=spy_monthly / spy_monthly.iloc[0] * 100_000,
)

n_years = round((BACKTEST_END - BACKTEST_START).days / 365.25, 1)
print("=" * 115)
print(f"  S&P100 BACKTEST {BACKTEST_START.year}–{BACKTEST_END.year} ({n_years} años) | $100,000 inicial")
print("=" * 115)
names = list(results.keys())
W = 26

print(f"\n{'Métrica':<20}", end="")
for n in names:
    print(f"  {n[:W-2]:<{W}}", end="")
print()
print("-" * (20 + (W + 2) * len(names)))

for lbl, key, fmt in [
    ("Capital final",   "final",   "${:>13,.0f}"),
    ("CAGR",            "cagr",    "{:>+10.2f}%"),
    ("Max Drawdown",    "max_dd",  "{:>+10.2f}%"),
    ("Sharpe",          "sharpe",  "{:>10.2f}"),
    ("Meses positivos", "wins",    None),
    ("Mejor mes",       "best",    "{:>+10.2f}%"),
    ("Peor mes",        "worst",   "{:>+10.2f}%"),
]:
    print(f"{lbl:<20}", end="")
    for n in names:
        v = results[n][key]
        if key == "wins":
            s = f"{v}/{results[n]['n']}"
            print(f"  {s:<{W}}", end="")
        elif math.isnan(v):
            print(f"  {'N/A':<{W}}", end="")
        else:
            print(f"  {fmt.format(v):<{W}}", end="")
    print()

# Detalle anual (más limpio que mensual para 11 años)
print("\n--- Retorno por año ---")
print(f"{'Año':<6}", end="")
for n in names:
    print(f"  {n[:W-2]:<{W}}", end="")
print()
print("-" * (6 + (W + 2) * len(names)))

for yr in range(BACKTEST_START.year, BACKTEST_END.year + 1):
    print(f"{yr:<6}", end="")
    for n in names:
        m = results[n]["monthly"]
        yr_m = m[m.index.year == yr]
        if len(yr_m) < 2:
            print(f"  {'N/A':<{W}}", end="")
            continue
        ret = (yr_m.iloc[-1] / yr_m.iloc[0] - 1) * 100
        print(f"  {'+' if ret>=0 else ''}{ret:.2f}%{'':<{W-9}}", end="")
    print()

print("\n--- Detalle mensual ---")
print(f"{'Mes':<10}", end="")
for n in names:
    print(f"  {n[:W-2]:<{W}}", end="")
print()
print("-" * (10 + (W + 2) * len(names)))

prev = {n: 100_000.0 for n in names}
for m in sorted(set(m for n in names for m in results[n]["monthly"].index)):
    print(f"{m.strftime('%Y-%m'):<10}", end="")
    for n in names:
        eq = results[n]["monthly"].get(m)
        if eq is not None:
            ret = (eq / prev[n] - 1) * 100
            s = f"{'+' if ret >= 0 else ''}{ret:.2f}% (${eq:>9,.0f})"
            print(f"  {s:<{W}}", end="")
            prev[n] = eq
        else:
            print(f"  {'N/A':<{W}}", end="")
    print()
print("=" * 115)
