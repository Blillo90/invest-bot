#!/usr/bin/env python3
"""
Backtest de la estrategia del bot usando los datos históricos almacenados en DuckDB.
Simula la estrategia día a día y reporta rendimiento mensual.
"""
import math
import datetime as dt
import duckdb
import pandas as pd
import numpy as np

DB_PATH = "/home/user/invest-bot/quant-bot/data/market.duckdb"

# Parámetros (igual que bot.env)
START_CASH         = 100_000.0
MAX_POSITIONS      = 20
MAX_EXPOSURE_PCT   = 0.95
MIN_POSITION_USD   = 1_000.0
FEE_BPS            = 10
SLIPPAGE_BPS       = 10
BUY_TOP_PCT        = 0.10
SELL_OUT_PCT       = 0.30
MAX_REPLACEMENTS   = 5

FEE = (FEE_BPS + SLIPPAGE_BPS) / 10_000.0  # 0.002

def rank_pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True)

def run_backtest():
    src = duckdb.connect(DB_PATH, read_only=True)

    # Cargar todo en memoria para velocidad
    bars_df    = src.execute("SELECT symbol, date, close FROM bars ORDER BY date, symbol").df()
    feat_df    = src.execute("SELECT symbol, date, ret_20, vol_20, vol_z_20, dollar_vol_20 FROM features ORDER BY date, symbol").df()
    src.close()

    bars_df["date"] = pd.to_datetime(bars_df["date"]).dt.date
    feat_df["date"] = pd.to_datetime(feat_df["date"]).dt.date

    # Obtener días de trading donde hay features
    trading_days = sorted(feat_df["date"].unique())

    # Estado del portfolio
    cash = START_CASH
    positions = {}   # symbol -> {shares, avg_price}
    equity_log = []  # (date, equity, cash, exposure_pct, num_pos)

    peak_equity = START_CASH

    for day in trading_days:
        day_bars = bars_df[bars_df["date"] == day].set_index("symbol")["close"].to_dict()
        if not day_bars:
            continue

        # --- Signals ---
        feat = feat_df[feat_df["date"] == day].copy()
        feat = feat.sort_values("dollar_vol_20", ascending=False).head(1000)
        if feat.empty:
            continue

        feat["score"] = (
            rank_pct(feat["ret_20"].fillna(0)) +
            rank_pct(feat["vol_z_20"].fillna(0)) -
            rank_pct(feat["vol_20"].fillna(feat["vol_20"].median()))
        )
        feat = feat.sort_values("score", ascending=False).reset_index(drop=True)
        n = len(feat)

        buy_cut  = max(1, int(math.floor(BUY_TOP_PCT * n)))
        sell_cut = max(1, int(math.floor(SELL_OUT_PCT * n)))

        buy_set  = set(feat.head(buy_cut)["symbol"])
        hold_set = set(feat.head(sell_cut)["symbol"])
        current  = set(positions.keys())

        to_sell = sorted(current - hold_set)[:MAX_REPLACEMENTS]
        to_buy  = sorted(buy_set - current)[:MAX_REPLACEMENTS]

        # Equity pre-trade (mark to market)
        exposure = sum(positions[s]["shares"] * day_bars.get(s, 0) for s in positions)
        equity_pre = cash + exposure
        investable = equity_pre * MAX_EXPOSURE_PCT
        target_value = investable / MAX_POSITIONS if MAX_POSITIONS > 0 else 0

        # SELL
        for sym in to_sell:
            if sym not in day_bars:
                continue
            close = day_bars[sym]
            eff   = close * (1.0 - FEE)
            sh    = positions[sym]["shares"]
            cash += sh * eff
            del positions[sym]

        # BUY
        can_open = target_value >= MIN_POSITION_USD
        if can_open:
            slots = max(0, MAX_POSITIONS - len(positions))
            for sym in to_buy[:slots]:
                if sym not in day_bars:
                    continue
                close = day_bars[sym]
                eff   = close * (1.0 + FEE)
                shares = target_value / eff
                cost   = shares * eff
                if cost > cash:
                    continue
                cash -= cost
                positions[sym] = {"shares": shares, "avg_price": eff}

        # Equity post-trade
        exposure2 = sum(positions[s]["shares"] * day_bars.get(s, 0) for s in positions)
        equity_end = cash + exposure2
        exposure_pct = exposure2 / equity_end if equity_end > 0 else 0.0
        peak_equity = max(peak_equity, equity_end)
        drawdown = (equity_end / peak_equity - 1.0)

        equity_log.append({
            "date": day,
            "equity": equity_end,
            "cash": cash,
            "exposure_pct": exposure_pct,
            "num_positions": len(positions),
            "drawdown": drawdown,
        })

    df = pd.DataFrame(equity_log)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    # --- Rendimiento mensual ---
    monthly = df["equity"].resample("ME").last()
    monthly_ret = monthly.pct_change().dropna()

    print("\n" + "="*60)
    print("  BACKTEST — Estrategia Momentum + Volume (2023–2026)")
    print("="*60)
    print(f"\nCapital inicial:     ${START_CASH:>12,.2f}")
    print(f"Capital final:       ${df['equity'].iloc[-1]:>12,.2f}")

    total_ret = (df["equity"].iloc[-1] / START_CASH - 1) * 100
    n_years = (df.index[-1] - df.index[0]).days / 365.25
    cagr = ((df["equity"].iloc[-1] / START_CASH) ** (1 / n_years) - 1) * 100
    max_dd = df["drawdown"].min() * 100
    avg_exp = df["exposure_pct"].mean() * 100
    avg_pos = df["num_positions"].mean()

    print(f"Retorno total:       {total_ret:>+11.2f}%")
    print(f"CAGR (~{n_years:.1f} años):    {cagr:>+11.2f}%")
    print(f"Max Drawdown:        {max_dd:>+11.2f}%")
    print(f"Exposición media:    {avg_exp:>11.2f}%")
    print(f"Posiciones medias:   {avg_pos:>11.1f}")

    # Estadísticas mensuales
    print(f"\nRetorno mensual promedio:  {monthly_ret.mean()*100:>+.2f}%")
    print(f"Retorno mensual mediana:   {monthly_ret.median()*100:>+.2f}%")
    print(f"Desv. estándar mensual:    {monthly_ret.std()*100:>.2f}%")
    print(f"Mejor mes:                 {monthly_ret.max()*100:>+.2f}%")
    print(f"Peor mes:                  {monthly_ret.min()*100:>+.2f}%")
    wins = (monthly_ret > 0).sum()
    total_m = len(monthly_ret)
    print(f"Meses positivos:           {wins}/{total_m} ({wins/total_m*100:.0f}%)")

    # Sharpe mensual aproximado
    rf_monthly = 0.045 / 12  # 4.5% anual libre de riesgo
    excess = monthly_ret - rf_monthly
    sharpe = excess.mean() / excess.std() * math.sqrt(12) if excess.std() > 0 else 0
    print(f"Sharpe ratio (anual):      {sharpe:>.2f}")

    print("\n--- Detalle mensual ---")
    print(f"{'Mes':<12} {'Equity':>12} {'Ret. mes':>10} {'Posiciones':>12} {'Exposición':>12}")
    print("-"*60)

    monthly_equity = df["equity"].resample("ME").last()
    monthly_npos   = df["num_positions"].resample("ME").mean()
    monthly_exp    = df["exposure_pct"].resample("ME").mean() * 100

    prev_eq = START_CASH
    for month_date in monthly_equity.index:
        eq  = monthly_equity[month_date]
        ret = (eq / prev_eq - 1) * 100
        npos = monthly_npos[month_date]
        exp  = monthly_exp[month_date]
        label = month_date.strftime("%Y-%m")
        sign = "+" if ret >= 0 else ""
        print(f"{label:<12} ${eq:>11,.0f} {sign}{ret:>8.2f}%   {npos:>8.1f} pos   {exp:>7.1f}%")
        prev_eq = eq

    print("\n" + "="*60)

if __name__ == "__main__":
    run_backtest()
