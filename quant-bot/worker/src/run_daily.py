#!/usr/bin/env python3
import os
import math
import pathlib
import datetime as dt
from dataclasses import dataclass
from typing import List, Tuple, Dict

import numpy as np
import pandas as pd
import duckdb
import yfinance as yf


# -----------------------------
# Config
# -----------------------------
def getenv(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v if v is not None and v != "" else default

def getenv_float(name: str, default: float) -> float:
    return float(getenv(name, str(default)))

def getenv_int(name: str, default: int) -> int:
    return int(getenv(name, str(default)))

@dataclass
class Config:
    tickers_file: str
    db_path: str
    reports_dir: str

    start_cash: float
    max_positions: int
    max_exposure_pct: float
    min_position_usd: float

    fee_bps: float
    slippage_bps: float

    buy_top_pct: float
    sell_out_pct: float
    max_replacements_per_day: int

    history_years: int


def load_config() -> Config:
    return Config(
        tickers_file=getenv("TICKERS_FILE", "/home/ubuntu/quant-bot/data/tickers.txt"),
        db_path=getenv("DB_PATH", "/home/ubuntu/quant-bot/data/market.duckdb"),
        reports_dir=getenv("REPORTS_DIR", "/home/ubuntu/quant-bot/reports"),

        start_cash=getenv_float("START_CASH", 100000),
        max_positions=getenv_int("MAX_POSITIONS", 20),
        max_exposure_pct=getenv_float("MAX_EXPOSURE_PCT", 0.95),
        min_position_usd=getenv_float("MIN_POSITION_USD", 1000),

        fee_bps=getenv_float("FEE_BPS", 10),
        slippage_bps=getenv_float("SLIPPAGE_BPS", 10),

        buy_top_pct=getenv_float("BUY_TOP_PCT", 0.10),
        sell_out_pct=getenv_float("SELL_OUT_PCT", 0.30),
        max_replacements_per_day=getenv_int("MAX_REPLACEMENTS_PER_DAY", 5),

        history_years=getenv_int("HISTORY_YEARS", 3),
    )


# -----------------------------
# DB schema
# -----------------------------
def get_db(db_path: str) -> duckdb.DuckDBPyConnection:
    pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    con.execute("PRAGMA threads=2;")
    return con

def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
    CREATE TABLE IF NOT EXISTS bars (
      symbol TEXT,
      date DATE,
      open DOUBLE,
      high DOUBLE,
      low DOUBLE,
      close DOUBLE,
      volume DOUBLE,
      PRIMARY KEY(symbol, date)
    );
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS features (
      symbol TEXT,
      date DATE,
      ret_5 DOUBLE,
      ret_10 DOUBLE,
      ret_20 DOUBLE,
      vol_20 DOUBLE,
      atr_14 DOUBLE,
      vol_z_20 DOUBLE,
      dollar_vol_20 DOUBLE,
      PRIMARY KEY(symbol, date)
    );
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS positions (
      symbol TEXT PRIMARY KEY,
      shares DOUBLE,
      avg_price DOUBLE,
      entry_date DATE
    );
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS equity (
      date DATE PRIMARY KEY,
      equity DOUBLE,
      cash DOUBLE,
      exposure DOUBLE,
      drawdown DOUBLE,
      num_positions INTEGER
    );
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS meta (
      key TEXT PRIMARY KEY,
      value TEXT
    );
    """)

def meta_get(con, key: str, default: str = "") -> str:
    row = con.execute("SELECT value FROM meta WHERE key = ?", [key]).fetchone()
    return row[0] if row else default

def meta_set(con, key: str, value: str) -> None:
    con.execute("""
    INSERT INTO meta(key, value) VALUES(?, ?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, [key, value])


# -----------------------------
# Helpers
# -----------------------------
def read_tickers(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        tickers = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    seen = set()
    out = []
    for t in tickers:
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out

def today_utc_date() -> dt.date:
    return dt.datetime.utcnow().date()

def yfinance_download_daily(tickers: List[str], start: dt.date) -> pd.DataFrame:
    # auto_adjust=True ajusta por splits/dividendos
    df = yf.download(
        tickers=tickers,
        start=start.isoformat(),
        interval="1d",
        auto_adjust=True,
        group_by="ticker",
        threads=True,
        progress=False
    )
    return df


# -----------------------------
# Step 1: Fetch bars
# -----------------------------
def upsert_bars(con, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    con.register("tmp_bars", df)
    con.execute("""
      INSERT INTO bars
      SELECT symbol, date, open, high, low, close, volume
      FROM tmp_bars
      ON CONFLICT(symbol, date) DO UPDATE SET
        open=excluded.open,
        high=excluded.high,
        low=excluded.low,
        close=excluded.close,
        volume=excluded.volume
    """)
    return len(df)

def fetch_daily(con, tickers: List[str], history_years: int) -> Tuple[int, dt.date, dt.date]:
    last_date_str = meta_get(con, "last_bars_date", "")
    if last_date_str:
        start = dt.date.fromisoformat(last_date_str) + dt.timedelta(days=1)
    else:
        start = today_utc_date() - dt.timedelta(days=365 * history_years)

    end = today_utc_date()
    if start > end:
        return (0, start, end)

    raw = yfinance_download_daily(tickers, start=start)

    rows = []
    if isinstance(raw.columns, pd.MultiIndex):
        for sym in tickers:
            if sym not in raw.columns.get_level_values(0):
                continue
            sub = raw[sym].copy()
            sub = sub.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
            sub = sub.dropna(subset=["close"])
            sub["symbol"] = sym
            sub["date"] = pd.to_datetime(sub.index).date
            rows.append(sub[["symbol", "date", "open", "high", "low", "close", "volume"]])
        long_df = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    else:
        sym = tickers[0]
        sub = raw.copy()
        sub = sub.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        sub = sub.dropna(subset=["close"])
        sub["symbol"] = sym
        sub["date"] = pd.to_datetime(sub.index).date
        long_df = sub[["symbol", "date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)

    inserted = upsert_bars(con, long_df)
    if inserted > 0:
        meta_set(con, "last_bars_date", end.isoformat())
    return (inserted, start, end)


# -----------------------------
# Step 2: Compute features
# -----------------------------
def compute_features(con, tickers: List[str]) -> int:
    total = 0
    for sym in tickers:
        df = con.execute("""
          SELECT date, open, high, low, close, volume
          FROM bars
          WHERE symbol = ?
          ORDER BY date
        """, [sym]).df()

        if len(df) < 60:
            continue

        df["date"] = pd.to_datetime(df["date"])
        df["ret_1"] = df["close"].pct_change()
        df["ret_5"] = df["close"].pct_change(5)
        df["ret_10"] = df["close"].pct_change(10)
        df["ret_20"] = df["close"].pct_change(20)
        df["vol_20"] = df["ret_1"].rolling(20).std()

        prev_close = df["close"].shift(1)
        tr = pd.concat([
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ], axis=1).max(axis=1)
        df["atr_14"] = tr.rolling(14).mean()

        vol_mean = df["volume"].rolling(20).mean()
        vol_std = df["volume"].rolling(20).std()
        df["vol_z_20"] = (df["volume"] - vol_mean) / vol_std.replace(0, np.nan)

        dollar_vol = df["close"] * df["volume"]
        df["dollar_vol_20"] = dollar_vol.rolling(20).mean()

        out = df.dropna(subset=["ret_20", "vol_20", "atr_14", "vol_z_20", "dollar_vol_20"]).copy()
        out["symbol"] = sym
        out["date"] = out["date"].dt.date
        out = out[["symbol", "date", "ret_5", "ret_10", "ret_20", "vol_20", "atr_14", "vol_z_20", "dollar_vol_20"]]

        if out.empty:
            continue

        con.register("tmp_feat", out)
        con.execute("""
          INSERT INTO features
          SELECT * FROM tmp_feat
          ON CONFLICT(symbol, date) DO UPDATE SET
            ret_5=excluded.ret_5,
            ret_10=excluded.ret_10,
            ret_20=excluded.ret_20,
            vol_20=excluded.vol_20,
            atr_14=excluded.atr_14,
            vol_z_20=excluded.vol_z_20,
            dollar_vol_20=excluded.dollar_vol_20
        """)
        total += len(out)
    return total


# -----------------------------
# Step 3: Signals (ranking)
# -----------------------------
def rank_pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True)

def generate_signals(con, cfg: Config, asof: dt.date) -> pd.DataFrame:
    feat = con.execute("""
      SELECT symbol, date, ret_20, vol_20, vol_z_20, dollar_vol_20
      FROM features
      WHERE date = ?
    """, [asof]).df()

    if feat.empty:
        return pd.DataFrame(columns=["symbol", "action", "score", "reason"])

    feat = feat.sort_values("dollar_vol_20", ascending=False).head(1000).copy()
    feat["score"] = (
        rank_pct(feat["ret_20"].fillna(0)) +
        rank_pct(feat["vol_z_20"].fillna(0)) -
        rank_pct(feat["vol_20"].fillna(feat["vol_20"].median()))
    )
    feat = feat.sort_values("score", ascending=False).reset_index(drop=True)
    n = len(feat)
    if n == 0:
        return pd.DataFrame(columns=["symbol", "action", "score", "reason"])

    buy_cut = max(1, int(math.floor(cfg.buy_top_pct * n)))
    sell_out = max(1, int(math.floor(cfg.sell_out_pct * n)))

    buy_set = set(feat.head(buy_cut)["symbol"].tolist())
    hold_set = set(feat.head(sell_out)["symbol"].tolist())

    pos = con.execute("SELECT symbol FROM positions").df()
    current = set(pos["symbol"].tolist()) if not pos.empty else set()

    to_buy = sorted(list(buy_set - current))
    to_sell = sorted(list(current - hold_set))

    if to_sell:
        cur_scores = feat[feat["symbol"].isin(to_sell)][["symbol", "score"]].sort_values("score", ascending=True)
        to_sell = cur_scores["symbol"].tolist()

    max_rep = cfg.max_replacements_per_day
    to_sell = to_sell[:max_rep]
    to_buy = to_buy[:max_rep]

    sig = []
    for sym in to_sell:
        sc = feat.loc[feat["symbol"] == sym, "score"]
        sig.append({"symbol": sym, "action": "SELL", "score": float(sc.iloc[0]) if len(sc) else float("nan"), "reason": "Salió del top (ranking)"})
    for sym in to_buy:
        sc = feat.loc[feat["symbol"] == sym, "score"]
        sig.append({"symbol": sym, "action": "BUY", "score": float(sc.iloc[0]) if len(sc) else float("nan"), "reason": "Entró en top (ranking)"})

    return pd.DataFrame(sig)


# -----------------------------
# Step 4: Simulación (compounding + exposure + min position)
# -----------------------------
def get_last_cash(con, cfg: Config) -> float:
    row = con.execute("SELECT cash FROM equity ORDER BY date DESC LIMIT 1").fetchone()
    return float(row[0]) if row else cfg.start_cash

def simulate(con, cfg: Config, signals: pd.DataFrame, asof: dt.date) -> Dict:
    fee = (cfg.fee_bps + cfg.slippage_bps) / 10000.0

    cash = get_last_cash(con, cfg)
    pos = con.execute("SELECT symbol, shares, avg_price, entry_date FROM positions").df()

    prices = con.execute("SELECT symbol, close FROM bars WHERE date = ?", [asof]).df()
    px = dict(zip(prices["symbol"], prices["close"]))

    exposure = 0.0
    if not pos.empty:
        for _, r in pos.iterrows():
            sym = r["symbol"]
            sh = float(r["shares"])
            if sym in px:
                exposure += sh * float(px[sym])

    equity_pre = cash + exposure

    investable = equity_pre * cfg.max_exposure_pct
    target_value = investable / cfg.max_positions if cfg.max_positions > 0 else 0.0
    can_open_new = target_value >= cfg.min_position_usd

    trades = []

    # SELL primero
    if not signals.empty:
        sells = signals[signals["action"] == "SELL"]
        for _, s in sells.iterrows():
            sym = s["symbol"]
            if pos.empty or sym not in set(pos["symbol"]) or sym not in px:
                continue
            close = float(px[sym])
            row = pos[pos["symbol"] == sym].iloc[0]
            sh = float(row["shares"])
            eff = close * (1.0 - fee)
            proceeds = sh * eff
            cash += proceeds
            trades.append({"date": str(asof), "symbol": sym, "side": "SELL", "shares": sh, "price_close": close, "price_effective": eff, "reason": s.get("reason", "")})
            con.execute("DELETE FROM positions WHERE symbol = ?", [sym])

    # refrescar posiciones
    pos = con.execute("SELECT symbol, shares, avg_price, entry_date FROM positions").df()

    # BUY
    if can_open_new and not signals.empty:
        cur_n = 0 if pos.empty else len(pos)
        slots = max(0, cfg.max_positions - cur_n)
        buys = signals[signals["action"] == "BUY"].head(slots)
        for _, s in buys.iterrows():
            sym = s["symbol"]
            if sym not in px:
                continue
            close = float(px[sym])
            eff = close * (1.0 + fee)
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
            trades.append({"date": str(asof), "symbol": sym, "side": "BUY", "shares": shares, "price_close": close, "price_effective": eff, "reason": s.get("reason", "")})

    # equity post
    pos2 = con.execute("SELECT symbol, shares, avg_price FROM positions").df()
    exposure2 = 0.0
    if not pos2.empty:
        for _, r in pos2.iterrows():
            sym = r["symbol"]
            sh = float(r["shares"])
            if sym in px:
                exposure2 += sh * float(px[sym])

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


# -----------------------------
# Step 5: Report
# -----------------------------
def write_report(cfg: Config, con, asof: dt.date, fetch_inserted: int, fetch_start: dt.date, fetch_end: dt.date, sim: Dict) -> str:
    pathlib.Path(cfg.reports_dir).mkdir(parents=True, exist_ok=True)
    report_path = os.path.join(cfg.reports_dir, f"{asof.isoformat()}.md")
    latest_path = os.path.join(cfg.reports_dir, "latest.md")

    pos = con.execute("SELECT symbol, shares, avg_price, entry_date FROM positions ORDER BY symbol").df()
    prices = con.execute("SELECT symbol, close FROM bars WHERE date = ?", [asof]).df()
    px = dict(zip(prices["symbol"], prices["close"]))

    pos_lines = []
    if pos.empty:
        pos_lines.append("- (sin posiciones)")
    else:
        for _, r in pos.iterrows():
            sym = r["symbol"]
            sh = float(r["shares"])
            ap = float(r["avg_price"])
            close = float(px.get(sym, float("nan")))
            mv = sh * close if not math.isnan(close) else float("nan")
            pnl = (close / ap - 1.0) if (ap > 0 and not math.isnan(close)) else float("nan")
            pos_lines.append(f"- **{sym}**: {sh:.4f} sh | avg {ap:.2f} | close {close:.2f} | mv {mv:.2f} | pnl {pnl*100:.2f}%")

    trade_lines = []
    if not sim["trades"]:
        trade_lines.append("- (sin trades hoy)")
    else:
        for t in sim["trades"]:
            trade_lines.append(f"- **{t['side']} {t['symbol']}** | shares {t['shares']:.4f} | close {t['price_close']:.2f} | eff {t['price_effective']:.2f} | {t['reason']}")

    warnings = []
    if not sim["can_open_new"]:
        warnings.append(f"- ⚠️ No se abren nuevas posiciones: target_value={sim['target_value']:.2f} < MIN_POSITION_USD={cfg.min_position_usd}")
    if fetch_inserted == 0:
        warnings.append("- ⚠️ No se insertaron barras nuevas (finde/holiday o sin datos).")

    txt = f"""# Reporte diario — {asof.isoformat()}

## Resumen
- Barras nuevas insertadas: **{fetch_inserted}** (desde {fetch_start} hasta {fetch_end})
- Equity (pre): **{sim['equity_pre']:.2f}**
- Equity (post): **{sim['equity_end']:.2f}**
- Cash: **{sim['cash_end']:.2f}**
- Exposición: **{sim['exposure_pct_end']*100:.2f}%**
- Drawdown (vs pico): **{sim['drawdown']*100:.2f}%**
- Target por posición (aprox): **{sim['target_value']:.2f}**

## Trades de hoy
{chr(10).join(trade_lines)}

## Posiciones actuales
{chr(10).join(pos_lines)}

## Alertas / avisos
{chr(10).join(warnings) if warnings else "- (sin avisos)"}

## Parámetros clave
- MAX_POSITIONS={cfg.max_positions}
- MAX_EXPOSURE_PCT={cfg.max_exposure_pct}
- MIN_POSITION_USD={cfg.min_position_usd}
- FEE_BPS={cfg.fee_bps}
- SLIPPAGE_BPS={cfg.slippage_bps}
- BUY_TOP_PCT={cfg.buy_top_pct}
- SELL_OUT_PCT={cfg.sell_out_pct}
- MAX_REPLACEMENTS_PER_DAY={cfg.max_replacements_per_day}
"""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(txt)
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(txt)
    return report_path


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    cfg = load_config()
    con = get_db(cfg.db_path)
    init_schema(con)

    tickers = read_tickers(cfg.tickers_file)
    if not tickers:
        raise SystemExit("No hay tickers en TICKERS_FILE.")

    inserted, start, end = fetch_daily(con, tickers, cfg.history_years)
    _ = compute_features(con, tickers)

    asof_row = con.execute("SELECT MAX(date) FROM bars").fetchone()
    if not asof_row or asof_row[0] is None:
        raise SystemExit("No hay datos en bars. Revisa tickers o yfinance.")
    asof = dt.date.fromisoformat(str(asof_row[0]))

    signals = generate_signals(con, cfg, asof=asof)
    sim = simulate(con, cfg, signals, asof=asof)

    report_path = write_report(cfg, con, asof, inserted, start, end, sim)
    print(f"OK. Reporte generado: {report_path}")
