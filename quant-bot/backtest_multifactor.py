"""
Multi-Factor Backtest — S&P100 + 4 factores académicos

UNIVERSO : S&P100 (102 acciones más líquidas del mercado)
REBALANCEO: Mensual (menos costes de transacción)
RÉGIMEN   : SPY > SMA200 → invertido | SPY < SMA200 → 100% cash

FACTORES (todos basados en precios, sin look-ahead bias):
  1. MOM_12_1  : Retorno de 12 meses saltando el último mes
                 (factor momentum estándar Jegadeesh-Titman 1993)
  2. REL_MOM   : Retorno 3 meses vs SPY (outperformance relativa)
  3. LOW_VOL   : Inverso de la vol anualizada 252 días
                 (anomalía low-volatility — CAPM invertido)
  4. TREND_Q   : % días en que el precio > SMA50 en últimos 60 días
                 (proxy de calidad/tendencia persistente)

CONSTRUCCIÓN: Top N stocks por score compuesto, igual ponderación
"""

import yfinance as yf, pandas as pd, numpy as np, math, datetime as dt

DOWNLOAD_START = "2013-01-01"
BACKTEST_START = dt.date(2015, 1, 1)
BACKTEST_END   = dt.date(2026, 3, 7)
CAPITAL        = 100_000

# ── Universo S&P100 ───────────────────────────────────────────────────────────
UNIVERSE = [
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
print(f"Universo: {len(UNIVERSE)} símbolos (S&P100)")

# ── Descarga ──────────────────────────────────────────────────────────────────
print(f"Descargando {len(UNIVERSE)} acciones + SPY (puede tardar 3-5 min)...")
raw = yf.download(
    UNIVERSE + ["SPY"],
    start=DOWNLOAD_START,
    end=str(BACKTEST_END),
    auto_adjust=True,
    progress=True,
    group_by="ticker",
)

# Extraer close prices en un único DataFrame (fecha × símbolo)
close_dict = {}
vol_dict   = {}
for sym in UNIVERSE + ["SPY"]:
    try:
        s = raw[sym]["Close"].dropna()
        if len(s) > 200:
            close_dict[sym] = s
            vol_dict[sym]   = raw[sym]["Volume"].reindex(s.index).fillna(0)
    except KeyError:
        pass

closes = pd.DataFrame(close_dict)
closes.index = pd.to_datetime(closes.index)
volumes = pd.DataFrame(vol_dict)
volumes.index = pd.to_datetime(volumes.index)

# Solo stocks (excluir SPY del universo)
spy_close = closes["SPY"]
stock_syms = [s for s in UNIVERSE if s in closes.columns]
closes_stk = closes[stock_syms]
volumes_stk = volumes[stock_syms]

print(f"Símbolos válidos: {len(stock_syms)} | Fechas: {closes.index[0].date()} → {closes.index[-1].date()}")

# ── Factores mensuales (sin look-ahead bias) ──────────────────────────────────
# Resample a fin de mes
monthly_close = closes_stk.resample("ME").last()
monthly_spy   = spy_close.resample("ME").last()

# 1. MOM_12_1: retorno 12m − retorno 1m (skip-last-month momentum)
mom_12 = monthly_close.pct_change(12)   # 12-month return
mom_1  = monthly_close.pct_change(1)    # 1-month return (el que se salta)
mom_12_1 = mom_12 - mom_1              # momentum "puro" sin reversal a 1m

# 2. REL_MOM: retorno 3m del stock relativo a SPY
mom_3m_stock = monthly_close.pct_change(3)
mom_3m_spy   = monthly_spy.pct_change(3)
rel_mom = mom_3m_stock.sub(mom_3m_spy, axis=0)

# 3. LOW_VOL: usando datos diarios → std anualizada rolling 252 días
#    luego resampleamos a fin de mes
daily_ret = closes_stk.pct_change()
vol_252d  = daily_ret.rolling(252).std() * np.sqrt(252)
low_vol   = -vol_252d.resample("ME").last()   # negativo: menor vol = mejor score

# 4. TREND_Q: fracción de días en que close > SMA50 (en últimas 60 sesiones)
sma50      = closes_stk.rolling(50).mean()
above_sma  = (closes_stk > sma50).astype(float)
trend_q    = above_sma.rolling(60).mean()
trend_q_m  = trend_q.resample("ME").last()

# ── Régimen SPY ────────────────────────────────────────────────────────────────
spy_sma200 = spy_close.rolling(200).mean()
regime_daily = (spy_close > spy_sma200)
regime_monthly = regime_daily.resample("ME").last()   # True = bull

# Liquidez mínima: dollar volume > $50M diario (promedio 20d, resampled mensual)
dv20 = (closes_stk * volumes_stk).rolling(20).mean()
liq_m = dv20.resample("ME").last()
LIQ_MIN = 50e6

# ── Backtest mensual ──────────────────────────────────────────────────────────
FEE      = 15 / 10_000   # 0.15% por operación (más realista para mkt cap grandes)
N_STOCKS = 25             # número de posiciones

months = sorted(set(monthly_close.index) & set(mom_12_1.index)
                & set(rel_mom.index) & set(low_vol.index) & set(trend_q_m.index))
months = [m for m in months if m.date() >= BACKTEST_START]

cash = CAPITAL
pos  = {}    # sym → shares
log  = []
peak = CAPITAL

for m_idx, month in enumerate(months):
    # Precios de cierre del mes
    prices = monthly_close.loc[month].dropna()
    in_bull = bool(regime_monthly.get(month, True))

    # Mark-to-market
    exp = sum(pos[s] * prices.get(s, 0) for s in pos if s in prices.index)
    eq  = cash + exp
    peak = max(peak, eq)

    # ── Liquidar si régimen bajista ────────────────────────────────────────
    if not in_bull:
        for sym in list(pos.keys()):
            p = prices.get(sym, 0)
            if p > 0:
                cash += pos[sym] * p * (1 - FEE)
        pos = {}
        log.append({"date": month, "equity": eq, "dd": eq/peak-1,
                    "n_pos": 0, "in_bull": False})
        continue

    # ── Score compuesto multi-factor ───────────────────────────────────────
    def rk(s):
        return s.rank(pct=True)

    # Unir factores disponibles para este mes
    f = pd.DataFrame({
        "mom_12_1": mom_12_1.loc[month],
        "rel_mom":  rel_mom.loc[month],
        "low_vol":  low_vol.loc[month],
        "trend_q":  trend_q_m.loc[month],
        "liq":      liq_m.loc[month],
        "price":    prices,
    }).dropna()

    # Filtro liquidez mínima
    f = f[f["liq"] >= LIQ_MIN]

    if len(f) < N_STOCKS:
        log.append({"date": month, "equity": eq, "dd": eq/peak-1,
                    "n_pos": len(pos), "in_bull": True})
        continue

    # Score: 4 factores con pesos académicos
    f["score"] = (
        rk(f["mom_12_1"]) * 0.35 +
        rk(f["rel_mom"])  * 0.35 +
        rk(f["low_vol"])  * 0.20 +
        rk(f["trend_q"])  * 0.10
    )

    target_stocks = set(f.nlargest(N_STOCKS, "score").index)
    current_stocks = set(pos.keys())

    # Vender los que salen del portafolio
    to_sell = current_stocks - target_stocks
    for sym in to_sell:
        p = prices.get(sym, 0)
        if p > 0:
            cash += pos[sym] * p * (1 - FEE)
            del pos[sym]

    # Recalcular equity y target por posición
    exp2 = sum(pos[s] * prices.get(s, 0) for s in pos if s in prices.index)
    total = cash + exp2
    tgt_per_pos = total / N_STOCKS

    # Comprar los nuevos y rebalancear existentes
    to_buy = target_stocks
    for sym in to_buy:
        p = f.loc[sym, "price"]
        if p <= 0:
            continue
        new_sh = tgt_per_pos / (p * (1 + FEE))
        old_sh = pos.get(sym, 0)
        diff = new_sh - old_sh
        if diff > 0:
            cost = diff * p * (1 + FEE)
            if cash >= cost:
                pos[sym] = new_sh
                cash -= cost
        elif diff < -0.01:   # vender exceso en rebalanceo
            cash += (-diff) * p * (1 - FEE)
            pos[sym] = new_sh

    exp3 = sum(pos[s] * prices.get(s, 0) for s in pos if s in prices.index)
    eq3  = cash + exp3
    peak = max(peak, eq3)
    log.append({"date": month, "equity": eq3, "dd": eq3/peak-1,
                "n_pos": len(pos), "in_bull": True})

df_log = pd.DataFrame(log).set_index("date")
df_log.index = pd.to_datetime(df_log.index)

# ── Estadísticas ──────────────────────────────────────────────────────────────
def stats(equity_series, label):
    mret = equity_series.pct_change().dropna()
    ny   = (equity_series.index[-1] - equity_series.index[0]).days / 365.25
    fin  = equity_series.iloc[-1]
    cagr = ((fin / CAPITAL) ** (1 / ny) - 1) * 100
    exc  = mret - 0.045 / 12
    sh   = exc.mean() / exc.std() * math.sqrt(12) if exc.std() > 0 else 0
    dd   = ((equity_series / equity_series.cummax()) - 1).min() * 100
    return dict(label=label, final=fin, cagr=cagr, sharpe=sh, max_dd=dd,
                wins=(mret > 0).sum(), n=len(mret), monthly=equity_series)

strat = stats(df_log["equity"], "Multi-Factor S&P500")

# SPY benchmark (mismo período)
spy_m = monthly_spy.reindex(df_log.index).dropna()
spy_base = spy_m.iloc[0]
spy_eq = spy_m / spy_base * CAPITAL
spy_st = stats(spy_eq, "SPY (benchmark)")

# ── Tabla comparativa ─────────────────────────────────────────────────────────
ny = (BACKTEST_END - BACKTEST_START).days / 365.25
print()
print("=" * 70)
print(f"  MULTI-FACTOR S&P500 — {BACKTEST_START.year}–{BACKTEST_END.year} ({ny:.1f} años) | ${CAPITAL:,}")
print(f"  Factores: MOM_12_1 (35%) · REL_MOM (35%) · LOW_VOL (20%) · TREND_Q (10%)")
print(f"  Régimen: SPY > SMA200 | Rebalanceo: mensual | N={N_STOCKS} posiciones")
print("=" * 70)

for lbl, key, fmt in [
    ("Capital final",   "final",   "${:>13,.0f}"),
    ("CAGR",            "cagr",    "{:>+10.2f}%"),
    ("Alpha vs SPY",    None,      None),
    ("Max Drawdown",    "max_dd",  "{:>+10.2f}%"),
    ("Sharpe Ratio",    "sharpe",  "{:>10.2f}"),
    ("Meses positivos", "wins",    None),
]:
    print(f"  {lbl:<18}", end="")
    for st in [strat, spy_st]:
        if key is None:
            v = strat["cagr"] - spy_st["cagr"]
            s = f"{'+' if v>=0 else ''}{v:.2f}%"
            if st is strat:
                print(f"  {'Multi-Factor':>18}: {s:<12}", end="")
            else:
                print(f"  {'SPY':>18}: {'—':<12}", end="")
        elif key == "wins":
            s = f"{st['wins']}/{st['n']}"
            print(f"  {st['label']:>18}: {s:<12}", end="")
        else:
            v = st[key]
            print(f"  {st['label']:>18}: {fmt.format(v):<12}", end="")
    print()

# ── Retorno anual con alpha ────────────────────────────────────────────────────
print()
print(f"  {'Año':<6} {'Multi-Factor':>14} {'SPY':>10} {'Alpha':>8}")
print(f"  {'-'*42}")
for yr in range(BACKTEST_START.year, BACKTEST_END.year + 1):
    def yr_ret(s):
        ym = s[s.index.year == yr]
        return (ym.iloc[-1] / ym.iloc[0] - 1) * 100 if len(ym) >= 2 else None
    mf  = yr_ret(df_log["equity"])
    spy = yr_ret(spy_eq)
    if mf is None or spy is None:
        continue
    alp = mf - spy
    mark = " ✓" if alp > 0 else ""
    print(f"  {yr:<6} {mf:>+13.2f}%  {spy:>+8.2f}%  {alp:>+7.2f}%{mark}")

# ── Exposición mensual ────────────────────────────────────────────────────────
print()
pct_invested = df_log["in_bull"].mean() * 100
print(f"  Tiempo invertido en bolsa : {pct_invested:.1f}%")
print(f"  Tiempo en cash (bear)     : {100-pct_invested:.1f}%")
print(f"  Posiciones promedio activas: {df_log['n_pos'].mean():.1f}")
print("=" * 70)

# ── Detalle mensual (últimos 24 meses) ────────────────────────────────────────
print("\n  Últimos 24 meses:")
print(f"  {'Mes':<10} {'Multi-Factor':>14} {'SPY':>10} {'Alpha':>8} {'#Pos':>6}")
print(f"  {'-'*52}")
mf_m  = df_log["equity"]
recent = df_log.tail(25)
prev_mf = mf_m.iloc[-25] if len(mf_m) >= 25 else mf_m.iloc[0]
prev_spy = spy_eq.iloc[-25] if len(spy_eq) >= 25 else spy_eq.iloc[0]
for i, (d, row) in enumerate(recent.iterrows()):
    if i == 0:
        prev_mf  = row["equity"]
        prev_spy = spy_eq.get(d, np.nan)
        continue
    mf_ret  = (row["equity"] / prev_mf  - 1) * 100
    spy_val = spy_eq.get(d, np.nan)
    spy_ret = (spy_val / prev_spy - 1) * 100 if not np.isnan(spy_val) else float("nan")
    alp     = mf_ret - spy_ret
    npos    = int(row["n_pos"])
    mark = " ✓" if alp > 0 else ""
    print(f"  {d.strftime('%Y-%m'):<10} {mf_ret:>+13.2f}%  {spy_ret:>+8.2f}%  {alp:>+7.2f}%{mark}  {npos:>4}")
    prev_mf  = row["equity"]
    prev_spy = spy_val
print("=" * 70)
