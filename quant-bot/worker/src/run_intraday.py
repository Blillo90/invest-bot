#!/usr/bin/env python3
import os
import math
import datetime as dt

import pandas as pd
import yfinance as yf
import duckdb

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

    cash = core.get_last_cash(con, cfg)
    pos = con.execute("SELECT symbol, shares, avg_price, entry_date FROM positions").df()

    # close diario por si falta intradía
    prices_eod = con.execute("SELECT symbol, close FROM bars WHERE date = ?", [asof]).df()
    px_eod = dict(zip(prices_eod["symbol"], prices_eod["close"]))

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

    investable = equity_pre * cfg.max_exposure_pct
    target_value = investable / cfg.max_positions if cfg.max_positions > 0 else 0.0
    can_open_new = target_value >= cfg.min_position_usd

    trades = []

    # SELL
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
            trades.append({"date": str(asof), "symbol": sym, "side": "SELL", "shares": sh, "price": float(p), "price_effective": eff, "reason": s.get("reason", "")})
            con.execute("DELETE FROM positions WHERE symbol = ?", [sym])

    pos = con.execute("SELECT symbol, shares, avg_price, entry_date FROM positions").df()

    # BUY
    if can_open_new and not signals.empty:
        cur_n = 0 if pos.empty else len(pos)
        slots = max(0, cfg.max_positions - cur_n)
        buys = signals[signals["action"] == "BUY"].head(slots)

        for _, s in buys.iterrows():
            sym = s["symbol"]
            p = price(sym)
            if p is None:
                continue
            eff = float(p) * (1.0 + fee)
            shares = target_value / eff
            cost = shares * eff
            if cost > cash:
                continue
            cash -= cost
            con.execute("""
              INSERT INTO positions(symbol, shares, avg_price, entry_date)
              VALUES(?, ?, ?, ?)
              ON CONFLICT(symbol) DO UPDATE SET
                shares=excluded.shares,
                avg_price=excluded.avg_price,
                entry_date=excluded.entry_date
            """, [sym, shares, eff, asof])
            trades.append({"date": str(asof), "symbol": sym, "side": "BUY", "shares": shares, "price": float(p), "price_effective": eff, "reason": s.get("reason", "")})

    # equity post
    pos2 = con.execute("SELECT symbol, shares, avg_price FROM positions").df()
    exposure2 = 0.0
    if not pos2.empty:
        for _, r in pos2.iterrows():
            sym = r["symbol"]
            sh = float(r["shares"])
            p = price(sym)
            if p is not None:
                exposure2 += sh * p

    equity_end = cash + exposure2
    exposure_pct = (exposure2 / equity_end) if equity_end > 0 else 0.0

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
        "exposure_pct_end": exposure_pct,
        "drawdown": drawdown,
        "target_value": target_value,
        "can_open_new": can_open_new,
        "trades": trades,
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
    print("TIPO DE inserted:", type(inserted))
    print("NUM TRADES INSERTED:", len(inserted) if inserted is not None else "None")

    if inserted:
        print("PRIMER TRADE:", inserted[0])
        print("CLAVES PRIMER TRADE:", list(inserted[0].keys()))
    report_path = core.write_report(cfg, con, asof, inserted, start, end, sim)
    print(f"OK ({mode}). Reporte generado: {report_path}")
