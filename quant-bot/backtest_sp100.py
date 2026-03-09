import yfinance as yf, pandas as pd, numpy as np, math, datetime as dt, duckdb

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

print(f"Descargando {len(SP100)} símbolos del S&P 100...")
raw = yf.download(SP100, start="2022-12-01", end="2026-03-07",
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
print(f"Features calculadas: {len(feat)} filas\n")


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


# Load 30-symbol data for reference
src = duckdb.connect("/home/user/invest-bot/quant-bot/data/market.duckdb", read_only=True)
b30 = src.execute("SELECT symbol,date,close FROM bars").df()
f30 = src.execute("SELECT symbol,date,ret_5,ret_10,ret_20,vol_20,vol_z_20,dollar_vol_20 FROM features").df()
src.close()
b30["date"] = pd.to_datetime(b30["date"]).dt.date
f30["date"] = pd.to_datetime(f30["date"]).dt.date

START = dt.date(2023, 3, 1)
bars_sp = bars[bars["date"] >= START]
feat_sp = feat[feat["date"] >= START]
bars_30 = b30[b30["date"] >= START]
feat_30 = f30[f30["date"] >= START]

CFGS = {
    "30sym Agres-B (referencia)":  dict(BT=0.25, ST=0.60, MR=15, MP=30, SIG="ret_10", USE_SP=False),
    "SP100 rot.total ret_10 30p":  dict(BT=0.25, ST=0.60, MR=20, MP=30, SIG="ret_10", USE_SP=True),
    "SP100 top-10 concentrado":    dict(BT=0.10, ST=0.30, MR=10, MP=10, SIG="ret_20", USE_SP=True),
    "SP100 ret_5 momentum 20p":    dict(BT=0.20, ST=0.50, MR=15, MP=20, SIG="ret_5",  USE_SP=True),
    "SP100 top-5 MAXIMO":          dict(BT=0.05, ST=0.15, MR=5,  MP=5,  SIG="ret_10", USE_SP=True),
}

results = {}
for name, cfg in CFGS.items():
    bd = bars_sp if cfg["USE_SP"] else bars_30
    fd = feat_sp if cfg["USE_SP"] else feat_30
    df = run_bt(bd, fd, cfg)
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

print("=" * 110)
print("  COMPARATIVA: 30 sym vs S&P100 — varios escenarios | 2023–2026 | $100,000")
print("=" * 110)
names = list(results.keys())
W = 24

print(f"\n{'Métrica':<20}", end="")
for n in names:
    print(f"  {n[:W-2]:<{W}}", end="")
print()
print("-" * (20 + (W + 2) * len(names)))

for lbl, key, fmt in [
    ("Capital final",   "final",   "${:>11,.0f}"),
    ("CAGR",            "cagr",    "{:>+9.2f}%"),
    ("Max Drawdown",    "max_dd",  "{:>+9.2f}%"),
    ("Sharpe",          "sharpe",  "{:>9.2f}"),
    ("Meses positivos", "wins",    None),
    ("Mejor mes",       "best",    "{:>+9.2f}%"),
    ("Peor mes",        "worst",   "{:>+9.2f}%"),
]:
    print(f"{lbl:<20}", end="")
    for n in names:
        v = results[n][key]
        if key == "wins":
            s = f"{v}/{results[n]['n']}"
            print(f"  {s:<{W}}", end="")
        else:
            print(f"  {fmt.format(v):<{W}}", end="")
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
            s = f"{'+' if ret >= 0 else ''}{ret:.2f}% (${eq:>8,.0f})"
            print(f"  {s:<{W}}", end="")
            prev[n] = eq
        else:
            print(f"  {'N/A':<{W}}", end="")
    print()
print("=" * 110)
