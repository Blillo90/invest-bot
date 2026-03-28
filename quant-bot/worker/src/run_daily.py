#!/usr/bin/env python3
"""
run_daily.py — Estrategia momentum diaria (versión agresiva con stops ATR).

LOOK-AHEAD BIAS (documentado):
  Las señales y la ejecución usan precios de cierre del mismo día 'asof'.
  En producción se asume ejecución al cierre (orden MOC) o en la apertura
  del día siguiente con el cierre anterior como referencia de precio.
  El parámetro SLIPPAGE_BPS intenta compensar este deslizamiento.

ORDEN DE EJECUCIÓN (siempre):
  1. Actualizar highest_price_since_entry para todas las posiciones
  2. Evaluar stops (ATR stop + trailing stop) → SELL
  3. Ventas por ranking → SELL
  4. Recalcular cash/equity
  5. Compras (solo activos con ranking + tendencia válidos) → BUY
"""
import os
import json
import math
import pathlib
import datetime as dt
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import duckdb
import yfinance as yf

# ── Shared strategy logic (canonical implementation) ──────────────────────
# Any change to scoring / features / stops must be made in strategy/core.py
# so that both live trading and backtest stay in sync automatically.
from strategy.core import (
    compute_features_df,
    rank_pct,                       # re-exported for legacy callers
    compute_momentum_score,
    trend_ok_strict_vectorized,
    check_atr_stop,
    target_position_size,
)


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
def getenv(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return v if v is not None and v != "" else default

def getenv_float(name: str, default: float) -> float:
    return float(getenv(name, str(default)))

def getenv_int(name: str, default: int) -> int:
    return int(getenv(name, str(default)))

def getenv_bool(name: str, default: bool) -> bool:
    v = getenv(name, "").lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    return default


@dataclass
class Config:
    tickers_file: str
    db_path: str
    reports_dir: str

    start_cash: float
    max_positions: int              # número máximo de posiciones simultáneas
    max_exposure_pct: float         # exposición máxima total (bull)
    min_position_usd: float         # tamaño mínimo por posición
    target_cash_buffer_pct: float   # objetivo: no superar este % en cash

    fee_bps: float
    slippage_bps: float

    buy_top_pct: float              # comprar si está en el top X% del ranking
    sell_out_pct: float             # vender por ranking si cae por debajo del top X%
    max_replacements_per_day: int   # máximo de rotaciones diarias

    atr_stop_mult: float            # stop inicial  = avg_price - mult × ATR_at_entry
    atr_trail_mult: float           # trailing stop = highest_price - mult × ATR_at_entry

    # Si True, después de las compras primarias rellena la cartera hasta MAX_POSITIONS
    # usando el ranking completo (no solo top BUY_TOP_PCT), respetando el filtro de tendencia.
    fill_to_target: bool

    history_years: int


def load_config() -> Config:
    return Config(
        tickers_file=getenv("TICKERS_FILE", "/home/ubuntu/quant-bot/data/tickers.txt"),
        db_path=getenv("DB_PATH", "/home/ubuntu/quant-bot/data/market.duckdb"),
        reports_dir=getenv("REPORTS_DIR", "/home/ubuntu/quant-bot/reports"),

        start_cash=getenv_float("START_CASH", 100000),
        # Más concentrado: 12 posiciones vs 20 anteriores
        max_positions=getenv_int("MAX_POSITIONS", 12),
        max_exposure_pct=getenv_float("MAX_EXPOSURE_PCT", 0.95),
        min_position_usd=getenv_float("MIN_POSITION_USD", 1000),
        # Objetivo: no más del 20% en cash en condiciones normales
        target_cash_buffer_pct=getenv_float("TARGET_CASH_BUFFER_PCT", 0.20),

        fee_bps=getenv_float("FEE_BPS", 10),
        slippage_bps=getenv_float("SLIPPAGE_BPS", 10),

        # Más agresivo: comprar top 7% (antes 10%), rotar antes (antes 30%)
        buy_top_pct=getenv_float("BUY_TOP_PCT", 0.07),
        sell_out_pct=getenv_float("SELL_OUT_PCT", 0.20),
        max_replacements_per_day=getenv_int("MAX_REPLACEMENTS_PER_DAY", 6),

        # Protección con ATR
        atr_stop_mult=getenv_float("ATR_STOP_MULT", 2.5),
        atr_trail_mult=getenv_float("ATR_TRAIL_MULT", 3.0),

        # Rellenar cartera hasta MAX_POSITIONS usando ranking completo (default: activo)
        fill_to_target=getenv_bool("FILL_TO_TARGET", True),

        history_years=getenv_int("HISTORY_YEARS", 3),
    )


# ─────────────────────────────────────────────
# DB schema
# ─────────────────────────────────────────────
def get_db(db_path: str) -> duckdb.DuckDBPyConnection:
    pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)
    con.execute("PRAGMA threads=2;")
    return con


def _add_column_safe(con: duckdb.DuckDBPyConnection, table: str, col: str, dtype: str) -> None:
    """Añade columna solo si no existe. Seguro para migraciones hacia atrás."""
    try:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {dtype}")
    except Exception:
        pass  # la columna ya existe


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
    # Migración segura: añadir columnas de tendencia a features
    _add_column_safe(con, "features", "sma_50", "DOUBLE")
    _add_column_safe(con, "features", "sma_100", "DOUBLE")

    con.execute("""
    CREATE TABLE IF NOT EXISTS positions (
      symbol TEXT PRIMARY KEY,
      shares DOUBLE,
      avg_price DOUBLE,
      entry_date DATE
    );
    """)
    # Migración segura: añadir columnas para stops ATR
    _add_column_safe(con, "positions", "highest_price_since_entry", "DOUBLE")
    _add_column_safe(con, "positions", "atr_at_entry", "DOUBLE")

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
    con.execute("""
    CREATE TABLE IF NOT EXISTS trades_log (
      id INTEGER,
      date DATE,
      symbol TEXT,
      side TEXT,
      shares DOUBLE,
      price_close DOUBLE,
      price_effective DOUBLE,
      value DOUBLE,
      reason TEXT
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


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
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

def _safe_float(v, fallback: Optional[float] = None) -> Optional[float]:
    """Convierte a float ignorando None y NaN. Retorna fallback si no es válido."""
    if v is None:
        return fallback
    try:
        f = float(v)
        return fallback if math.isnan(f) else f
    except (TypeError, ValueError):
        return fallback

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


# ─────────────────────────────────────────────
# Step 1: Fetch bars
# ─────────────────────────────────────────────
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


# ─────────────────────────────────────────────
# Step 2: Compute features
# ─────────────────────────────────────────────
def compute_features(con, tickers: List[str]) -> int:
    total = 0
    for sym in tickers:
        df = con.execute("""
          SELECT date, open, high, low, close, volume
          FROM bars
          WHERE symbol = ?
          ORDER BY date
        """, [sym]).df()

        # Necesitamos 100+ días para sma_100 + margen
        if len(df) < 110:
            continue

        # ── Delegate to strategy.core (canonical feature computation) ──────
        df["date"] = pd.to_datetime(df["date"])
        ft = compute_features_df(df.set_index("date"))  # DatetimeIndex
        out = ft.reset_index()                           # "date" → plain column
        out["symbol"] = sym
        out["date"] = pd.to_datetime(out["date"]).dt.date
        out = out[[
            "symbol", "date", "ret_5", "ret_10", "ret_20",
            "vol_20", "atr_14", "vol_z_20", "dollar_vol_20",
            "sma_50", "sma_100"
        ]]

        if out.empty:
            continue

        con.register("tmp_feat", out)
        con.execute("""
          INSERT INTO features(
            symbol, date, ret_5, ret_10, ret_20, vol_20, atr_14,
            vol_z_20, dollar_vol_20, sma_50, sma_100
          )
          SELECT
            symbol, date, ret_5, ret_10, ret_20, vol_20, atr_14,
            vol_z_20, dollar_vol_20, sma_50, sma_100
          FROM tmp_feat
          ON CONFLICT(symbol, date) DO UPDATE SET
            ret_5=excluded.ret_5,
            ret_10=excluded.ret_10,
            ret_20=excluded.ret_20,
            vol_20=excluded.vol_20,
            atr_14=excluded.atr_14,
            vol_z_20=excluded.vol_z_20,
            dollar_vol_20=excluded.dollar_vol_20,
            sma_50=excluded.sma_50,
            sma_100=excluded.sma_100
        """)
        total += len(out)
    return total


# ─────────────────────────────────────────────
# Step 3: Signals (ranking)
# ─────────────────────────────────────────────
def get_spy_regime(con) -> bool:
    """True = bull (SPY ≥ MA200), False = bear. Fallback a yfinance si DB insuficiente."""
    df = con.execute("""
      SELECT close FROM bars
      WHERE symbol = 'SPY'
      ORDER BY date DESC
      LIMIT 200
    """).df()
    if len(df) < 200:
        try:
            start = today_utc_date() - dt.timedelta(days=365)
            raw = yf.download("SPY", start=start.isoformat(), interval="1d",
                              auto_adjust=True, progress=False)
            if len(raw) < 200:
                return True
            closes = raw["Close"].dropna().values
            return float(closes[-1]) >= float(closes[-200:].mean())
        except Exception:
            return True  # asumir bull si falla
    ma200 = float(df["close"].mean())
    current = float(df.iloc[0]["close"])
    return current >= ma200


def generate_signals(con, cfg: Config, asof: dt.date) -> pd.DataFrame:
    """
    Genera señales BUY/SELL basadas en ranking de momentum.

    Score (más agresivo):
      - Mayor peso a momentum de medio plazo (ret_20)
      - Menos penalización a volatilidad
      - Volumen como confirmación (vol_z_20)
      - Calidad (Sharpe implícito) como factor secundario

    Filtro de tendencia para BUY:
      - close > sma_50  (precio sobre media de 50 días)
      - sma_50 > sma_100 (tendencia alcista confirmada)
    """
    # Obtener features + close del día para filtro de tendencia
    feat = con.execute("""
      SELECT f.symbol,
             f.ret_5, f.ret_10, f.ret_20, f.vol_20,
             f.vol_z_20, f.dollar_vol_20,
             f.sma_50, f.sma_100,
             b.close
      FROM features f
      JOIN bars b ON f.symbol = b.symbol AND f.date = b.date
      WHERE f.date = ?
    """, [asof]).df()

    if feat.empty:
        return pd.DataFrame(columns=["symbol", "action", "score", "reason"])

    # Filtrar por liquidez (top 1000 por dólar-volumen)
    feat = feat.sort_values("dollar_vol_20", ascending=False).head(1000).copy()

    # ── Score momentum (canonical — via strategy.core) ────────────────────
    feat["score"] = compute_momentum_score(feat)
    feat = feat.sort_values("score", ascending=False).reset_index(drop=True)
    n = len(feat)
    if n == 0:
        return pd.DataFrame(columns=["symbol", "action", "score", "reason"])

    # Umbrales de ranking
    buy_cut = max(1, int(math.floor(cfg.buy_top_pct * n)))
    sell_out = max(1, int(math.floor(cfg.sell_out_pct * n)))

    buy_set = set(feat.head(buy_cut)["symbol"].tolist())
    hold_set = set(feat.head(sell_out)["symbol"].tolist())

    # ── Filtro de tendencia para BUY (canonical — via strategy.core) ───────
    # close > sma_50 AND sma_50 > sma_100
    trend_ok = set(feat[trend_ok_strict_vectorized(feat)]["symbol"].tolist())
    buy_set = buy_set & trend_ok  # intersección: ranking top + tendencia alcista

    pos = con.execute("SELECT symbol FROM positions").df()
    current = set(pos["symbol"].tolist()) if not pos.empty else set()

    # Candidatos primarios: top BUY_TOP_PCT + tendencia, sin posición actual
    to_buy_primary = feat[feat["symbol"].isin(buy_set - current)].sort_values("score", ascending=False)["symbol"].tolist()
    to_sell = sorted(list(current - hold_set))

    # Ordenar ventas por ranking (primero los peores)
    if to_sell:
        cur_scores = feat[feat["symbol"].isin(to_sell)][["symbol", "score"]].sort_values("score", ascending=True)
        to_sell = cur_scores["symbol"].tolist()

    max_rep = cfg.max_replacements_per_day
    to_sell = to_sell[:max_rep]
    to_buy_primary = to_buy_primary[:max_rep]  # rotaciones primarias capped at max_rep

    sig = []
    for sym in to_sell:
        sc = feat.loc[feat["symbol"] == sym, "score"]
        sig.append({
            "symbol": sym, "action": "SELL",
            "score": float(sc.iloc[0]) if len(sc) else float("nan"),
            "reason": "Salió del ranking",
            "is_fill": False,
        })
    for sym in to_buy_primary:
        sc = feat.loc[feat["symbol"] == sym, "score"]
        sig.append({
            "symbol": sym, "action": "BUY",
            "score": float(sc.iloc[0]) if len(sc) else float("nan"),
            "reason": "Entró en top (ranking + tendencia)",
            "is_fill": False,
        })

    # ── Candidatos de relleno (fill_to_target) ────────────────────────────
    # Todos los activos con filtro de tendencia válido, ordenados por score,
    # excluyendo los que ya están en cartera y los candidatos primarios.
    # Usados en simulate() para rellenar slots hasta MAX_POSITIONS.
    if cfg.fill_to_target:
        primary_syms = set(to_buy_primary)
        fill_candidates = feat[
            feat["symbol"].isin(trend_ok) &   # filtro de tendencia obligatorio
            ~feat["symbol"].isin(current) &    # no en cartera ya
            ~feat["symbol"].isin(primary_syms) # no duplicar primarios
        ]  # feat ya está ordenado por score desc
        for _, row in fill_candidates.iterrows():
            sig.append({
                "symbol": row["symbol"],
                "action": "BUY",
                "score": float(row["score"]),
                "reason": "Relleno de cartera (fill_to_target)",
                "is_fill": True,
            })

    return pd.DataFrame(sig)


# ─────────────────────────────────────────────
# Step 4: Simulación
# ─────────────────────────────────────────────
def get_last_cash(con, cfg: Config) -> float:
    row = con.execute("SELECT cash FROM equity ORDER BY date DESC LIMIT 1").fetchone()
    return float(row[0]) if row else cfg.start_cash


def simulate(con, cfg: Config, signals: pd.DataFrame, asof: dt.date) -> Dict:
    """
    Ejecuta la simulación diaria en este orden estricto:
      1. Actualizar highest_price_since_entry
      2. Evaluar stops ATR + trailing
      3. Ventas por ranking
      4. Recalcular exposición/cash
      5. Compras (sizing equal-weight del capital invertible)
    """
    fee = (cfg.fee_bps + cfg.slippage_bps) / 10000.0

    # Régimen del mercado (bull/bear)
    bull_regime = get_spy_regime(con)
    effective_max_exposure = cfg.max_exposure_pct if bull_regime else min(cfg.max_exposure_pct, 0.50)

    cash = get_last_cash(con, cfg)

    # Cargar posiciones (incluye columnas de stop si ya existen)
    pos = con.execute("""
        SELECT symbol, shares, avg_price, entry_date,
               highest_price_since_entry, atr_at_entry
        FROM positions
    """).df()

    # Precios de cierre del día
    prices = con.execute("SELECT symbol, close FROM bars WHERE date = ?", [asof]).df()
    px = dict(zip(prices["symbol"], prices["close"]))

    # ATR del día actual (para nuevas posiciones que no tienen atr_at_entry)
    atr_df = con.execute("SELECT symbol, atr_14 FROM features WHERE date = ?", [asof]).df()
    atr_px: Dict[str, float] = dict(zip(atr_df["symbol"], atr_df["atr_14"])) if not atr_df.empty else {}

    # Equity de partida (antes de cualquier operación)
    exposure_pre = 0.0
    if not pos.empty:
        for _, r in pos.iterrows():
            sym = r["symbol"]
            if sym in px:
                exposure_pre += float(r["shares"]) * float(px[sym])
    equity_pre = cash + exposure_pre

    trades: List[Dict] = []
    stop_sell_syms: List[str] = set()

    # ── 1. Actualizar highest_price_since_entry ────────────────────────────
    if not pos.empty:
        for _, r in pos.iterrows():
            sym = r["symbol"]
            if sym not in px:
                continue
            close = float(px[sym])
            current_highest = _safe_float(r["highest_price_since_entry"], fallback=float(r["avg_price"]))
            new_highest = max(current_highest, close)
            if new_highest != current_highest:
                con.execute(
                    "UPDATE positions SET highest_price_since_entry = ? WHERE symbol = ?",
                    [new_highest, sym]
                )

    # Refrescar posiciones con highest_price actualizado
    pos = con.execute("""
        SELECT symbol, shares, avg_price, entry_date,
               highest_price_since_entry, atr_at_entry
        FROM positions
    """).df()

    # ── 2. Evaluar stops (ATR stop + trailing stop) ────────────────────────
    if not pos.empty:
        for _, r in pos.iterrows():
            sym = r["symbol"]
            if sym not in px:
                continue

            close = float(px[sym])
            avg_price = float(r["avg_price"])
            sh = float(r["shares"])

            # ── ATR stops (canonical — via strategy.core) ─────────────────
            atr = _safe_float(r["atr_at_entry"]) or _safe_float(atr_px.get(sym))
            if atr is None:
                continue  # sin ATR no podemos calcular stop

            highest = _safe_float(r["highest_price_since_entry"], fallback=avg_price)
            triggered, stop_reason = check_atr_stop(
                close, avg_price, highest, atr, cfg.atr_stop_mult, cfg.atr_trail_mult
            )

            if triggered:
                eff = close * (1.0 - fee)
                cash += sh * eff
                trades.append({
                    "date": str(asof), "symbol": sym, "side": "SELL",
                    "shares": sh, "price_close": close, "price_effective": eff,
                    "reason": stop_reason, "is_stop": True
                })
                stop_sell_syms.add(sym)
                con.execute("DELETE FROM positions WHERE symbol = ?", [sym])

    # ── 3. Ventas por ranking ──────────────────────────────────────────────
    if not signals.empty:
        sells = signals[signals["action"] == "SELL"]
        for _, s in sells.iterrows():
            sym = s["symbol"]
            if sym in stop_sell_syms:
                continue  # ya vendido por stop
            pos_row = con.execute(
                "SELECT shares FROM positions WHERE symbol = ?", [sym]
            ).fetchone()
            if pos_row is None or sym not in px:
                continue
            close = float(px[sym])
            sh = float(pos_row[0])
            eff = close * (1.0 - fee)
            cash += sh * eff
            trades.append({
                "date": str(asof), "symbol": sym, "side": "SELL",
                "shares": sh, "price_close": close, "price_effective": eff,
                "reason": s.get("reason", "Salió del ranking"), "is_stop": False
            })
            con.execute("DELETE FROM positions WHERE symbol = ?", [sym])

    # ── 4. Recalcular exposición y equity tras ventas ─────────────────────
    pos_now = con.execute("SELECT symbol, shares FROM positions").df()
    exposure_now = 0.0
    if not pos_now.empty:
        for _, r in pos_now.iterrows():
            sym = r["symbol"]
            if sym in px:
                exposure_now += float(r["shares"]) * float(px[sym])
    equity_now = cash + exposure_now
    cur_n = 0 if pos_now.empty else len(pos_now)

    # ── 5. Compras ─────────────────────────────────────────────────────────
    # Sizing: equal-weight sobre el capital total investible (canonical).
    target_per_pos = target_position_size(equity_now, effective_max_exposure, cfg.max_positions)
    can_open_new = target_per_pos >= cfg.min_position_usd

    # Helper interno para ejecutar una compra y registrarla
    def _execute_buy(sym: str, reason: str) -> bool:
        """Compra sym a precio de cierre del día. Actualiza cash y positions en DB.
        Retorna True si la compra se ejecutó, False si no fue posible."""
        nonlocal cash
        if sym not in px:
            return False
        already = con.execute("SELECT 1 FROM positions WHERE symbol = ?", [sym]).fetchone()
        if already:
            return False
        # Recalcular target con el equity/cash actual para reflejar compras previas
        pos_cur = con.execute("SELECT symbol, shares FROM positions").df()
        exp_cur = sum(
            float(r["shares"]) * px[r["symbol"]]
            for _, r in pos_cur.iterrows() if r["symbol"] in px
        ) if not pos_cur.empty else 0.0
        equity_cur = cash + exp_cur
        target = target_position_size(equity_cur, effective_max_exposure, cfg.max_positions)
        if target < cfg.min_position_usd:
            return False
        close = float(px[sym])
        eff = close * (1.0 + fee)
        shares = target / eff
        cost = shares * eff
        if cost > cash:
            return False  # efectivo insuficiente
        cash -= cost
        atr_entry = _safe_float(atr_px.get(sym))
        con.execute("""
          INSERT INTO positions(
            symbol, shares, avg_price, entry_date,
            highest_price_since_entry, atr_at_entry
          )
          VALUES(?, ?, ?, ?, ?, ?)
          ON CONFLICT(symbol) DO UPDATE SET
            shares=excluded.shares,
            avg_price=excluded.avg_price,
            entry_date=excluded.entry_date,
            highest_price_since_entry=excluded.highest_price_since_entry,
            atr_at_entry=excluded.atr_at_entry
        """, [sym, shares, eff, asof, close, atr_entry])
        trades.append({
            "date": str(asof), "symbol": sym, "side": "BUY",
            "shares": shares, "price_close": close, "price_effective": eff,
            "reason": reason, "is_stop": False
        })
        return True

    has_fill_col = not signals.empty and "is_fill" in signals.columns
    bought_syms: set = set()
    fill_skipped_reason: str = ""

    if can_open_new and not signals.empty:
        # ── 5a. Compras primarias (top BUY_TOP_PCT + tendencia) ───────────
        # Máx max_replacements_per_day rotaciones con los mejores del ranking.
        slots = max(0, cfg.max_positions - cur_n)
        primary_mask = signals["action"] == "BUY"
        if has_fill_col:
            primary_mask = primary_mask & (~signals["is_fill"].fillna(False))
        primary_buys = signals[primary_mask].head(slots)

        for _, s in primary_buys.iterrows():
            sym = s["symbol"]
            if _execute_buy(sym, s.get("reason", "Entró en top (ranking + tendencia)")):
                bought_syms.add(sym)

        # ── 5b. Fill de cartera (fill_to_target) ──────────────────────────
        # Si quedan slots libres y exposición < objetivo, usar candidatos adicionales
        # del ranking (con filtro de tendencia) para llegar a MAX_POSITIONS.
        # Esto evita el cash muerto cuando BUY_TOP_PCT es pequeño con universos cortos.
        if cfg.fill_to_target and has_fill_col:
            pos_fill = con.execute("SELECT symbol, shares FROM positions").df()
            cur_n_fill = 0 if pos_fill.empty else len(pos_fill)
            slots_fill = max(0, cfg.max_positions - cur_n_fill)

            exp_fill = sum(
                float(r["shares"]) * px[r["symbol"]]
                for _, r in pos_fill.iterrows() if r["symbol"] in px
            ) if not pos_fill.empty else 0.0
            equity_fill = cash + exp_fill
            exp_pct_fill = exp_fill / equity_fill if equity_fill > 0 else 0.0

            if slots_fill <= 0:
                fill_skipped_reason = "cartera llena"
            elif exp_pct_fill >= effective_max_exposure:
                fill_skipped_reason = f"exposición objetivo alcanzada ({exp_pct_fill*100:.1f}%)"
            else:
                fill_signals = signals[
                    (signals["action"] == "BUY") &
                    (signals["is_fill"].fillna(False))
                ]
                for _, s in fill_signals.iterrows():
                    if slots_fill <= 0 or exp_pct_fill >= effective_max_exposure:
                        break
                    sym = s["symbol"]
                    if sym in bought_syms:
                        continue
                    if _execute_buy(sym, s.get("reason", "Relleno de cartera")):
                        bought_syms.add(sym)
                        slots_fill -= 1
                        # Actualizar contadores de exposición para el siguiente ciclo
                        pos_updated = con.execute("SELECT symbol, shares FROM positions").df()
                        exp_fill = sum(
                            float(r["shares"]) * px[r["symbol"]]
                            for _, r in pos_updated.iterrows() if r["symbol"] in px
                        ) if not pos_updated.empty else 0.0
                        equity_fill = cash + exp_fill
                        exp_pct_fill = exp_fill / equity_fill if equity_fill > 0 else 0.0

    # ── 6. Equity final ───────────────────────────────────────────────────
    pos_final = con.execute("SELECT symbol, shares FROM positions").df()
    exposure_end = 0.0
    if not pos_final.empty:
        for _, r in pos_final.iterrows():
            sym = r["symbol"]
            if sym in px:
                exposure_end += float(r["shares"]) * float(px[sym])

    equity_end = cash + exposure_end
    exposure_pct = (exposure_end / equity_end) if equity_end > 0 else 0.0
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
    """, [asof, equity_end, cash, exposure_pct, drawdown,
          int(0 if pos_final.empty else len(pos_final))])

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
        "fill_skipped_reason": fill_skipped_reason,  # "" si fill no fue necesario o se ejecutó
    }


# ─────────────────────────────────────────────
# Step 5: Report
# ─────────────────────────────────────────────
def write_report(
    cfg: Config,
    con,
    asof: dt.date,
    fetch_inserted: int,
    fetch_start: dt.date,
    fetch_end: dt.date,
    sim: Dict,
) -> str:
    pathlib.Path(cfg.reports_dir).mkdir(parents=True, exist_ok=True)
    report_path = os.path.join(cfg.reports_dir, f"{asof.isoformat()}.md")
    latest_path = os.path.join(cfg.reports_dir, "latest.md")

    pos = con.execute(
        "SELECT symbol, shares, avg_price, entry_date FROM positions ORDER BY symbol"
    ).df()
    prices = con.execute("SELECT symbol, close FROM bars WHERE date = ?", [asof]).df()
    px = dict(zip(prices["symbol"], prices["close"]))

    # Posiciones actuales
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
            pos_lines.append(
                f"- **{sym}**: {sh:.4f} sh | avg {ap:.2f} | close {close:.2f} | mv {mv:.2f} | pnl {pnl*100:.2f}%"
            )

    # Trades del día — separados por tipo para mayor claridad
    def fmt_trade(t: Dict) -> str:
        side = t.get("side", "N/A")
        symbol = t.get("symbol", "N/A")
        shares = float(t.get("shares", 0.0))
        price_close = float(t.get("price_close", t.get("close", 0.0)))
        price_effective = float(t.get("price_effective", price_close))
        reason = t.get("reason", "N/A")
        value = shares * price_effective
        return (
            f"- **{side} {symbol}** | shares {shares:.4f} | close {price_close:.2f} "
            f"| eff {price_effective:.2f} | val {value:.2f} | {reason}"
        )

    stop_trades = [t for t in sim["trades"] if t.get("is_stop", False)]
    rank_sells = [t for t in sim["trades"] if t["side"] == "SELL" and not t.get("is_stop", False)]
    buys = [t for t in sim["trades"] if t["side"] == "BUY"]

    trade_blocks = []
    if stop_trades:
        trade_blocks.append(
            "### Ventas por stop\n" + "\n".join(fmt_trade(t) for t in stop_trades)
        )
    if rank_sells:
        trade_blocks.append(
            "### Ventas por ranking\n" + "\n".join(fmt_trade(t) for t in rank_sells)
        )
    if buys:
        trade_blocks.append(
            "### Compras\n" + "\n".join(fmt_trade(t) for t in buys)
        )

    trade_section = "\n\n".join(trade_blocks) if trade_blocks else "- (sin trades hoy)"

    # Alertas
    regime_label = "BULL (SPY ≥ MA200)" if sim["bull_regime"] else "BEAR (SPY < MA200)"
    warnings = []
    if not sim["bull_regime"]:
        warnings.append(
            f"- ⚠️ Régimen BEAR: exposición máxima reducida a {sim['effective_max_exposure']*100:.0f}%"
        )
    if not sim["can_open_new"]:
        warnings.append(
            f"- ⚠️ No se abren nuevas posiciones: target_per_pos={sim['target_per_pos']:.2f} < MIN_POSITION_USD={cfg.min_position_usd}"
        )
    # Avisar si el cash está muy por encima del objetivo, con razón detallada
    cash_pct = sim.get("cash_pct", 0.0)
    if cash_pct > cfg.target_cash_buffer_pct:
        fill_reason = sim.get("fill_skipped_reason", "")
        if fill_reason:
            detail = f"fill detenido: {fill_reason}"
        elif not cfg.fill_to_target:
            detail = "FILL_TO_TARGET=False"
        else:
            detail = "no hay candidatos válidos con filtro de tendencia activo"
        warnings.append(
            f"- ℹ️ Cash elevado: {cash_pct*100:.1f}% > objetivo {cfg.target_cash_buffer_pct*100:.0f}%"
            f" — {detail}"
        )
    if fetch_inserted == 0:
        warnings.append("- ⚠️ No se insertaron barras nuevas (finde/holiday o sin datos).")

    date_range = (
        f"desde {fetch_start} hasta {fetch_end}"
        if fetch_start <= fetch_end
        else "sin nuevas barras"
    )

    txt = f"""# Reporte diario — {asof.isoformat()}

## Resumen
- Barras nuevas insertadas: **{fetch_inserted}** ({date_range})
- Régimen SPY: **{regime_label}**
- Equity (pre): **{sim['equity_pre']:.2f}**
- Equity (post): **{sim['equity_end']:.2f}**
- Cash: **{sim['cash_end']:.2f}** ({cash_pct*100:.1f}%)
- Exposición real: **{sim['exposure_pct_end']*100:.2f}%** (objetivo: {sim['effective_max_exposure']*100:.0f}%)
- Drawdown (vs pico): **{sim['drawdown']*100:.2f}%**
- Target por posición (aprox): **{sim['target_per_pos']:.2f}**

## Trades de hoy
{trade_section}

## Posiciones actuales
{chr(10).join(pos_lines)}

## Alertas / avisos
{chr(10).join(warnings) if warnings else "- (sin avisos)"}

## Parámetros clave
- MAX_POSITIONS={cfg.max_positions}
- MAX_EXPOSURE_PCT={cfg.max_exposure_pct}
- TARGET_CASH_BUFFER_PCT={cfg.target_cash_buffer_pct}
- MIN_POSITION_USD={cfg.min_position_usd}
- FEE_BPS={cfg.fee_bps}
- SLIPPAGE_BPS={cfg.slippage_bps}
- BUY_TOP_PCT={cfg.buy_top_pct}
- SELL_OUT_PCT={cfg.sell_out_pct}
- MAX_REPLACEMENTS_PER_DAY={cfg.max_replacements_per_day}
- ATR_STOP_MULT={cfg.atr_stop_mult}
- ATR_TRAIL_MULT={cfg.atr_trail_mult}
- FILL_TO_TARGET={cfg.fill_to_target}
"""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(txt)
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(txt)

    # Guardar trades en DB
    if sim["trades"]:
        next_id_row = con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM trades_log").fetchone()
        next_id = int(next_id_row[0]) if next_id_row else 1
        for i, t in enumerate(sim["trades"]):
            price_close = float(t.get("price_close", t.get("close", 0.0)))
            price_eff = float(t.get("price_effective", price_close))
            shares = float(t.get("shares", 0.0))
            con.execute("""
              INSERT INTO trades_log(id, date, symbol, side, shares, price_close, price_effective, value, reason)
              VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                next_id + i, asof, t["symbol"], t["side"], shares,
                price_close, price_eff, shares * price_eff, t.get("reason", "")
            ])

    # Exportar histórico de trades a JSON para el dashboard
    trades_json_path = os.path.join(pathlib.Path(cfg.reports_dir).parent, "trades.json")
    all_trades = con.execute("""
      SELECT id, date, symbol, side, shares, price_close, price_effective, value, reason
      FROM trades_log ORDER BY date DESC, id DESC
    """).df()
    all_trades["date"] = all_trades["date"].astype(str)
    with open(trades_json_path, "w", encoding="utf-8") as f:
        json.dump(all_trades.to_dict(orient="records"), f, ensure_ascii=False)

    return report_path


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # ── MODE routing ──────────────────────────────────────────────────────
    # MODE=backtest → run historical simulation with current bot.env params.
    # MODE=live|paper (default) → normal live/intraday execution.
    _mode = os.getenv("MODE", "live").lower()
    if _mode == "backtest":
        import backtest as _bt
        _bt.main()
        raise SystemExit(0)

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
