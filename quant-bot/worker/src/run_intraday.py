#!/usr/bin/env python3
import os
import math
import datetime as dt

import pandas as pd
import yfinance as yf
import duckdb
import shutil

# Reutiliza todo lo de run_daily.py importándolo como módulo
# Truco: asegúrate de estar en el mismo directorio y que run_daily.py existe.
import run_daily as core


def get_mode() -> str:
    mode = os.getenv("MODE", "close").strip().lower()
    if mode not in ("open", "mid", "close"):
        mode = "close"
    return mode


def get_intraday_prices(tickers: list[str]) -> dict[str, float]:
    """
    Obtiene el último precio disponible para cada ticker usando yfinance intradía.
    Para pruebas: interval 1m, period 1d.
    """
    # yfinance devuelve MultiIndex cuando son varios tickers
    raw = yf.download(
        tickers=tickers,
        period="1d",
        interval="1m",
        group_by="ticker",
        threads=True,
        progress=False,
        auto_adjust=True
    )

    prices: dict[str, float] = {}
    if raw.empty:
        return prices

    if isinstance(raw.columns, pd.MultiIndex):
        for sym in tickers:
            if sym not in raw.columns.get_level_values(0):
                continue
            sub = raw[sym].dropna()
            if sub.empty:
                continue
            # último "Close" del minuto más reciente
            prices[sym] = float(sub["Close"].iloc[-1])
    else:
        # un ticker
        sym = tickers[0]
        sub = raw.dropna()
        if not sub.empty:
            prices[sym] = float(sub["Close"].iloc[-1])

    return prices


def simulate_with_prices(con: duckdb.DuckDBPyConnection, cfg: core.Config, signals: pd.DataFrame, asof: dt.date, px_now: dict[str, float]) -> dict:
    """
    Igual que core.simulate, pero usa px_now en vez del close diario para ejecutar trades.
    El mark-to-market y exposición se hace con px_now si existe, si no, cae al close diario.
    """
    fee = (cfg.fee_bps + cfg.slippage_bps) / 10000.0

    bull_regime = core.get_spy_regime(con)
    effective_max_exposure = cfg.max_exposure_pct if bull_regime else min(cfg.max_exposure_pct, 0.50)

    cash = core.get_last_cash(con, cfg)
    pos = con.execute("""
        SELECT symbol, shares, avg_price, entry_date,
               highest_price_since_entry, atr_at_entry
        FROM positions
    """).df()

    # close diario por si falta intradía
    prices_eod = con.execute("SELECT symbol, close FROM bars WHERE date = ?", [asof]).df()
    px_eod = dict(zip(prices_eod["symbol"], prices_eod["close"]))

    # ATR del día actual para nuevas posiciones
    atr_df = con.execute("SELECT symbol, atr_14 FROM features WHERE date = ?", [asof]).df()
    atr_px = dict(zip(atr_df["symbol"], atr_df["atr_14"])) if not atr_df.empty else {}

    def price(sym: str) -> float | None:
        if sym in px_now:
            return float(px_now[sym])
        if sym in px_eod:
            return float(px_eod[sym])
        return None

    # equity pre
    exposure = 0.0
    if not pos.empty:
        for _, r in pos.iterrows():
            sym = r["symbol"]
            sh = float(r["shares"])
            p = price(sym)
            if p is not None:
                exposure += sh * p

    equity_pre = cash + exposure

    trades = []

    # SELL (solo por ranking — los stops ATR se ejecutan en run_daily al cierre)
    if not signals.empty:
        sells = signals[signals["action"] == "SELL"]
        for _, s in sells.iterrows():
            sym = s["symbol"]
            if pos.empty or sym not in set(pos["symbol"]):
                continue
            p = price(sym)
            if p is None:
                continue
            row = pos[pos["symbol"] == sym].iloc[0]
            sh = float(row["shares"])
            eff = float(p) * (1.0 - fee)
            cash += sh * eff
            trades.append({
                "date": str(asof), "symbol": sym, "side": "SELL",
                "shares": sh, "price_close": float(p), "price_effective": eff,
                "reason": s.get("reason", ""), "is_stop": False
            })
            con.execute("DELETE FROM positions WHERE symbol = ?", [sym])

    # Recalcular equity/exposición tras ventas para sizing correcto
    pos_now = con.execute("SELECT symbol, shares FROM positions").df()
    exposure_now = 0.0
    if not pos_now.empty:
        for _, r in pos_now.iterrows():
            p = price(r["symbol"])
            if p is not None:
                exposure_now += float(r["shares"]) * p
    equity_now = cash + exposure_now
    cur_n = 0 if pos_now.empty else len(pos_now)

    # Sizing igual que run_daily: equal-weight sobre capital invertible
    target_per_pos = (equity_now * effective_max_exposure) / cfg.max_positions if cfg.max_positions > 0 else 0.0
    can_open_new = target_per_pos >= cfg.min_position_usd

    # BUY
    if can_open_new and not signals.empty:
        slots = max(0, cfg.max_positions - cur_n)
        buys = signals[signals["action"] == "BUY"].head(slots)

        for _, s in buys.iterrows():
            sym = s["symbol"]
            p = price(sym)
            if p is None:
                continue
            already = con.execute("SELECT 1 FROM positions WHERE symbol = ?", [sym]).fetchone()
            if already:
                continue
            eff = float(p) * (1.0 + fee)
            shares = target_per_pos / eff
            cost = shares * eff
            if cost > cash:
                continue
            cash -= cost
            atr_entry = core._safe_float(atr_px.get(sym))
            con.execute("""
              INSERT INTO positions(symbol, shares, avg_price, entry_date,
                                   highest_price_since_entry, atr_at_entry)
              VALUES(?, ?, ?, ?, ?, ?)
              ON CONFLICT(symbol) DO UPDATE SET
                shares=excluded.shares,
                avg_price=excluded.avg_price,
                entry_date=excluded.entry_date,
                highest_price_since_entry=excluded.highest_price_since_entry,
                atr_at_entry=excluded.atr_at_entry
            """, [sym, shares, eff, asof, float(p), atr_entry])
            trades.append({
                "date": str(asof), "symbol": sym, "side": "BUY",
                "shares": shares, "price_close": float(p), "price_effective": eff,
                "reason": s.get("reason", ""), "is_stop": False
            })

    # equity post
    pos2 = con.execute("SELECT symbol, shares FROM positions").df()
    exposure2 = 0.0
    if not pos2.empty:
        for _, r in pos2.iterrows():
            p = price(r["symbol"])
            if p is not None:
                exposure2 += float(r["shares"]) * p

    equity_end = cash + exposure2
    exposure_pct = (exposure2 / equity_end) if equity_end > 0 else 0.0
    cash_pct = (cash / equity_end) if equity_end > 0 else 1.0

    peak = con.execute("SELECT MAX(equity) FROM equity").fetchone()[0]
    peak = float(peak) if peak is not None else equity_end
    peak = max(peak, equity_end)
    drawdown = (equity_end / peak - 1.0) if peak > 0 else 0.0

    con.execute("""
      INSERT INTO equity(date, equity, cash, exposure, drawdown, num_positions)
      VALUES(?, ?, ?, ?, ?, ?)
      ON CONFLICT(date) DO UPDATE SET
        equity=excluded.equity,
        cash=excluded.cash,
        exposure=excluded.exposure,
        drawdown=excluded.drawdown,
        num_positions=excluded.num_positions
    """, [asof, equity_end, cash, exposure_pct, drawdown, int(0 if pos2.empty else len(pos2))])

    return {
        "equity_pre": equity_pre,
        "equity_end": equity_end,
        "cash_end": cash,
        "cash_pct": cash_pct,
        "exposure_pct_end": exposure_pct,
        "drawdown": drawdown,
        "target_per_pos": target_per_pos,
        "can_open_new": can_open_new,
        "trades": trades,
        "bull_regime": bull_regime,
        "effective_max_exposure": effective_max_exposure,
    }


if __name__ == "__main__":
    mode = get_mode()
    cfg = core.load_config()
    con = core.get_db(cfg.db_path)
    core.init_schema(con)

    tickers = core.read_tickers(cfg.tickers_file)

    # 1) Actualiza barras diarias (si hay día nuevo)
    inserted, start, end = core.fetch_daily(con, tickers, cfg.history_years)
    _ = core.compute_features(con, tickers)

    # 2) asof = último día disponible en la DB (EOD)
    asof_row = con.execute("SELECT MAX(date) FROM bars").fetchone()
    if not asof_row or asof_row[0] is None:
        raise SystemExit("No hay datos en bars.")
    asof = dt.date.fromisoformat(str(asof_row[0]))

    # 3) Señales basadas en features del día asof
    signals = core.generate_signals(con, cfg, asof=asof)

    # 4) Precios intradía actuales para ejecutar trades ahora
    px_now = get_intraday_prices(tickers)

    sim = simulate_with_prices(con, cfg, signals, asof=asof, px_now=px_now)

    # 5) Reporte “latest.md”, pero añade el modo al título (para que sepas cuándo corrió)
    # Reutilizamos writer, pero podrías hacer uno propio. Aquí lo simple:
    
    report_path = core.write_report(cfg, con, asof, inserted, start, end, sim)

    src = report_path
    dst = "/home/ubuntu/n8n-files/reports/latest.md"
    shutil.copy(src, dst)
    
    print(f"OK ({mode}). Reporte generado: {report_path}")
