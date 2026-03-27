#!/usr/bin/env python3
"""
backtest.py – Vectorized momentum strategy backtest.

Compares 5 variants:
  1. current_bot    – buy_top_pct=0.07, fill=False
  2. fill_to_target – buy_top_pct=0.07, fill=True (strict trend on fill)
  3. improved       – buy_top_pct=0.15, fill=True, relaxed fill trend, sell_out_pct=0.30
  4. spy            – buy-and-hold SPY
  5. acwi           – buy-and-hold ACWI

Output: dashboard/invest-dashboard/public/backtest-results.json

Usage:
  python backtest.py
"""

import sys, os, json, math, datetime as dt
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# ─── Output path ────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
REPO_ROOT  = SCRIPT_DIR.parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "dashboard" / "invest-dashboard" / "public"
OUTPUT_PATH = OUTPUT_DIR / "backtest-results.json"

# ─── Universe ────────────────────────────────────────────────────────────────
# 150 large/mega-cap líquidos EE.UU. – misma lista que quant-bot/data/tickers.txt
# Con 150 tickers:  buy_top_pct=0.07 → ~10 candidatos  |  0.15 → ~22 candidatos
# sell_out_pct=0.20 → 30 en zona venta  |  0.30 → 45    |  MAX_POSITIONS=12 ✓
UNIVERSE = [
    # Tecnología (30)
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","AMD","INTC","NFLX",
    "CRM","ADBE","CSCO","ORCL","SNOW","PLTR","ANET","PANW","FTNT","NOW",
    "TTD","QCOM","AVGO","MU","TXN","KLAC","LRCX","CRWD","MRVL","ADSK",
    # Salud (16)
    "UNH","LLY","JNJ","ABT","MRK","PFE","AMGN","ISRG","TMO","MDT",
    "BMY","CVS","CI","ELV","VRTX","ABBV",
    # Finanzas (18)
    "JPM","BAC","GS","MS","BLK","SPGI","AXP","CB","V","MA",
    "WFC","C","USB","TFC","PGR","MET","ALL","SCHW",
    # Consumo discrecional (14)
    "HD","COST","WMT","NKE","SBUX","MCD","TJX","LOW","BKNG","CMG",
    "ROST","GM","F","YUM",
    # Consumo básico (10)
    "PG","KO","PEP","PM","MO","CL","MDLZ","EL","KMB","STZ",
    # Industriales (15)
    "CAT","DE","HON","GE","RTX","LMT","UPS","BA","FDX","MMM",
    "NOC","ITW","EMR","ETN","PH",
    # Energía (10)
    "XOM","CVX","COP","SLB","EOG","PSX","MPC","VLO","OXY","HAL",
    # Materiales (8)
    "LIN","FCX","NEM","APD","ECL","DD","PPG","NUE",
    # Comunicaciones (7)
    "DIS","T","VZ","CMCSA","CHTR","EA","TTWO",
    # Utilities (6)
    "NEE","DUK","SO","AEP","EXC","D",
    # Real Estate (5)
    "PLD","AMT","EQIX","SPG","CCI",
    # Otros large-caps (11)
    "BRK-B","ZS","NET","SHOP","UBER","PYPL","ICE","DXCM","BIIB","GLD","CDNS",
    # SPY para filtro de régimen (no se rankea como candidato de compra)
    "SPY",
]
BENCHMARKS = ["SPY", "ACWI"]

# Todos los tickers a descargar (deduplicados)
ALL_DOWNLOAD = list(dict.fromkeys(UNIVERSE + BENCHMARKS))

# ─── Parámetros globales de simulación ──────────────────────────────────────
DOWNLOAD_START  = "2022-07-01"   # descarga extra para warmup de features (110+ bars)
BACKTEST_START  = "2023-01-03"
BACKTEST_END    = "2026-03-27"
START_CASH      = 100_000.0
FEE_BPS         = 10.0
SLIPPAGE_BPS    = 10.0
FEE_TOTAL       = (FEE_BPS + SLIPPAGE_BPS) / 10_000.0  # 0.20%

MAX_POSITIONS       = 12
MAX_EXPOSURE        = 0.95
BEAR_MAX_EXPOSURE   = 0.50
MIN_POSITION_USD    = 1_000.0
MAX_REPLACEMENTS    = 6

ATR_STOP_MULT  = 2.5
ATR_TRAIL_MULT = 3.0


# ─── Variantes ───────────────────────────────────────────────────────────────
@dataclass
class VariantConfig:
    id:                  str
    label:               str
    color:               str
    buy_top_pct:         float = 0.07
    sell_out_pct:        float = 0.20
    fill_to_target:      bool  = False
    fill_relaxed_trend:  bool  = False   # fill solo necesita close > sma_100

VARIANTS = [
    VariantConfig("current_bot",    "Current Bot",    "#6366f1",
                  buy_top_pct=0.07, sell_out_pct=0.20, fill_to_target=False),
    VariantConfig("fill_to_target", "Fill-to-Target", "#f59e0b",
                  buy_top_pct=0.07, sell_out_pct=0.20, fill_to_target=True,  fill_relaxed_trend=False),
    VariantConfig("improved",       "Improved",       "#10b981",
                  buy_top_pct=0.15, sell_out_pct=0.30, fill_to_target=True,  fill_relaxed_trend=True),
    VariantConfig("spy",  "SPY (B&H)",  "#0ea5e9"),
    VariantConfig("acwi", "ACWI (B&H)", "#a78bfa"),
]


# ─── Step 1: Descarga datos ───────────────────────────────────────────────────
def download_prices(tickers: List[str]) -> Dict[str, pd.DataFrame]:
    """Descarga datos OHLCV para todos los tickers. Retorna dict {sym: df}."""
    print(f"[1/4] Descargando {len(tickers)} tickers desde {DOWNLOAD_START}...")

    raw = yf.download(
        tickers=tickers,
        start=DOWNLOAD_START,
        end=BACKTEST_END,
        interval="1d",
        auto_adjust=True,
        group_by="ticker",
        threads=True,
        progress=True,
    )

    result: Dict[str, pd.DataFrame] = {}

    if isinstance(raw.columns, pd.MultiIndex):
        for sym in tickers:
            if sym not in raw.columns.get_level_values(0):
                continue
            sub = raw[sym].copy()
            sub = sub.rename(columns=str.lower)
            sub = sub.dropna(subset=["close"])
            sub.index = pd.to_datetime(sub.index)
            if len(sub) >= 110:
                result[sym] = sub
    else:
        # Un solo ticker
        sym = tickers[0]
        sub = raw.copy().rename(columns=str.lower).dropna(subset=["close"])
        sub.index = pd.to_datetime(sub.index)
        if len(sub) >= 110:
            result[sym] = sub

    print(f"   -> {len(result)} tickers con datos suficientes.")
    return result


# ─── Step 2: Calcular features ───────────────────────────────────────────────
def compute_features_for_ticker(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula todas las features para un ticker. Retorna df indexado por fecha."""
    d = df.copy().sort_index()

    d["ret_1"]  = d["close"].pct_change()
    d["ret_5"]  = d["close"].pct_change(5)
    d["ret_10"] = d["close"].pct_change(10)
    d["ret_20"] = d["close"].pct_change(20)

    d["vol_20"] = d["ret_1"].rolling(20).std()

    # ATR 14
    pc  = d["close"].shift(1)
    tr  = pd.concat([
        (d["high"] - d["low"]).abs(),
        (d["high"] - pc).abs(),
        (d["low"]  - pc).abs(),
    ], axis=1).max(axis=1)
    d["atr_14"] = tr.rolling(14).mean()

    # Volume z-score
    vm = d["volume"].rolling(20).mean()
    vs = d["volume"].rolling(20).std().replace(0, np.nan)
    d["vol_z_20"] = (d["volume"] - vm) / vs

    d["dollar_vol_20"] = (d["close"] * d["volume"]).rolling(20).mean()

    # SMAs
    d["sma_50"]  = d["close"].rolling(50).mean()
    d["sma_100"] = d["close"].rolling(100).mean()
    d["sma_200"] = d["close"].rolling(200).mean()

    return d.dropna(subset=["ret_20","vol_20","atr_14","sma_50","sma_100"])


def build_features_panel(prices: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Para cada ticker, calcula features. Retorna dict {sym: df_features}."""
    print("[2/4] Calculando features...")
    features: Dict[str, pd.DataFrame] = {}
    for sym, df in prices.items():
        try:
            ft = compute_features_for_ticker(df)
            if not ft.empty:
                features[sym] = ft
        except Exception as e:
            print(f"   ! Error en {sym}: {e}")
    print(f"   -> Features calculadas para {len(features)} tickers.")
    return features


# ─── Step 3: Índice de fechas de backtest ────────────────────────────────────
def get_trading_dates(features: Dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """Fechas de trading en el rango del backtest."""
    # SPY como referencia del calendario
    ref = features.get("SPY")
    if ref is None:
        ref = next(iter(features.values()))

    idx = ref.index
    mask = (idx >= pd.Timestamp(BACKTEST_START)) & (idx <= pd.Timestamp(BACKTEST_END))
    return idx[mask]


# ─── Step 4: Señal momentum ───────────────────────────────────────────────────
def rank_pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True)


def spy_bull_regime(features: Dict[str, pd.DataFrame], date: pd.Timestamp) -> bool:
    """True = mercado alcista (SPY ≥ SMA200). Fallback = True."""
    spy_ft = features.get("SPY")
    if spy_ft is None:
        return True
    rows = spy_ft[spy_ft.index <= date]
    if len(rows) < 1:
        return True
    last = rows.iloc[-1]
    if pd.isna(last.get("sma_200", float("nan"))):
        return True
    return float(last["close"]) >= float(last["sma_200"])


def generate_signals(
    features: Dict[str, pd.DataFrame],
    date: pd.Timestamp,
    cfg: VariantConfig,
    current_portfolio: Set[str],
) -> Tuple[List[str], List[str], List[str]]:
    """
    Retorna (to_buy_primary, to_buy_fill, to_sell).
    to_buy_primary: candidatos top ranking + tendencia estricta
    to_buy_fill:    candidatos de relleno (tendencia más laxa si cfg.fill_relaxed_trend)
    to_sell:        posiciones actuales fuera del ranking
    """
    rows = []
    for sym in UNIVERSE:
        ft = features.get(sym)
        if ft is None:
            continue
        row = ft[ft.index == date]
        if row.empty:
            continue
        r = row.iloc[0]
        rows.append({
            "symbol":        sym,
            "ret_5":         float(r["ret_5"])  if not pd.isna(r["ret_5"])  else 0.0,
            "ret_10":        float(r["ret_10"]) if not pd.isna(r["ret_10"]) else 0.0,
            "ret_20":        float(r["ret_20"]) if not pd.isna(r["ret_20"]) else 0.0,
            "vol_20":        float(r["vol_20"]) if not pd.isna(r["vol_20"]) and r["vol_20"] > 0 else 0.01,
            "vol_z_20":      float(r["vol_z_20"]) if not pd.isna(r["vol_z_20"]) else 0.0,
            "dollar_vol_20": float(r["dollar_vol_20"]) if not pd.isna(r["dollar_vol_20"]) else 0.0,
            "sma_50":        float(r["sma_50"])  if not pd.isna(r["sma_50"])  else float("nan"),
            "sma_100":       float(r["sma_100"]) if not pd.isna(r["sma_100"]) else float("nan"),
            "close":         float(r["close"])   if not pd.isna(r["close"])   else 0.0,
        })

    if not rows:
        return [], [], []

    df = pd.DataFrame(rows)

    # Filtro de liquidez: top 1000 por dollar_vol (en la práctica todos pasan con 88 tickers)
    df = df.nlargest(1000, "dollar_vol_20").copy()
    n = len(df)
    if n == 0:
        return [], [], []

    # Score momentum
    quality = df["ret_20"] / df["vol_20"].replace(0, np.nan)
    df["score"] = (
        0.60 * rank_pct(df["ret_20"].fillna(0))
      + 0.25 * rank_pct(df["ret_10"].fillna(0))
      + 0.15 * rank_pct(df["ret_5"].fillna(0))
      - 0.15 * rank_pct(df["vol_20"])
      + 0.15 * rank_pct(quality.fillna(0))
      + 0.10 * rank_pct(df["vol_z_20"].fillna(0))
    )
    df = df.sort_values("score", ascending=False).reset_index(drop=True)

    buy_cut  = max(1, int(math.floor(cfg.buy_top_pct * n)))
    sell_cut = max(1, int(math.floor(cfg.sell_out_pct * n)))

    buy_set  = set(df.head(buy_cut)["symbol"].tolist())
    hold_set = set(df.head(sell_cut)["symbol"].tolist())

    # Filtro de tendencia ESTRICTO (para candidatos primarios)
    def strict_trend(row: dict) -> bool:
        sma50, sma100, close = row["sma_50"], row["sma_100"], row["close"]
        if math.isnan(sma50) or math.isnan(sma100):
            return False
        return close > sma50 and sma50 > sma100

    # Filtro de tendencia RELAJADO (para fill candidates)
    def relaxed_trend(row: dict) -> bool:
        sma100, close = row["sma_100"], row["close"]
        if math.isnan(sma100):
            return False
        return close > sma100

    df_dict = df.set_index("symbol").to_dict("index")

    trend_ok_strict = {sym for sym, r in df_dict.items() if strict_trend(r)}
    trend_ok_relaxed = {sym for sym, r in df_dict.items() if relaxed_trend(r)}

    # Candidatos primarios: top buy_top_pct + tendencia estricta + sin posición
    buy_set_with_trend = buy_set & trend_ok_strict
    to_buy_primary = (
        df[df["symbol"].isin(buy_set_with_trend - current_portfolio)]
        .head(MAX_REPLACEMENTS)["symbol"].tolist()
    )

    # Ventas por ranking
    to_sell_set = current_portfolio - hold_set
    to_sell = (
        df[df["symbol"].isin(to_sell_set)]
        .sort_values("score", ascending=True)["symbol"].tolist()[:MAX_REPLACEMENTS]
    )

    # Candidatos de relleno
    to_buy_fill: List[str] = []
    if cfg.fill_to_target:
        trend_for_fill = trend_ok_relaxed if cfg.fill_relaxed_trend else trend_ok_strict
        fill_eligible = trend_for_fill - current_portfolio - set(to_buy_primary)
        to_buy_fill = (
            df[df["symbol"].isin(fill_eligible)]
            .sort_values("score", ascending=False)["symbol"].tolist()
        )

    return to_buy_primary, to_buy_fill, to_sell


# ─── Step 5: Simulación de una variante ──────────────────────────────────────
@dataclass
class Position:
    shares:      float
    avg_price:   float
    entry_atr:   Optional[float]
    highest:     float

PortfolioT = Dict[str, Position]


def get_price(features: Dict[str, pd.DataFrame], sym: str, date: pd.Timestamp) -> Optional[float]:
    ft = features.get(sym)
    if ft is None:
        return None
    row = ft[ft.index == date]
    if row.empty:
        return None
    v = row.iloc[0]["close"]
    return float(v) if not pd.isna(v) else None


def get_atr(features: Dict[str, pd.DataFrame], sym: str, date: pd.Timestamp) -> Optional[float]:
    ft = features.get(sym)
    if ft is None:
        return None
    row = ft[ft.index == date]
    if row.empty:
        return None
    v = row.iloc[0]["atr_14"]
    return float(v) if not pd.isna(v) else None


def simulate_variant(
    cfg: VariantConfig,
    features: Dict[str, pd.DataFrame],
    trading_dates: pd.DatetimeIndex,
) -> Dict:
    """Simula la estrategia para una variante. Retorna diccionario con curvas y métricas."""
    print(f"   -> Simulando '{cfg.label}'...")

    cash: float = START_CASH
    portfolio: PortfolioT = {}

    equity_curve:   List[dict] = []
    drawdown_curve: List[dict] = []
    exposure_curve: List[dict] = []
    trades_log:     List[dict] = []

    peak_equity = START_CASH

    for date in trading_dates:
        # ── Actualizar highest prices ──────────────────────────────────────
        for sym, pos in portfolio.items():
            p = get_price(features, sym, date)
            if p is not None and p > pos.highest:
                pos.highest = p

        # ── ATR stops ─────────────────────────────────────────────────────
        to_stop: List[str] = []
        for sym, pos in portfolio.items():
            p = get_price(features, sym, date)
            if p is None:
                continue
            atr = pos.entry_atr
            if atr is None or atr <= 0:
                continue
            atr_stop   = pos.avg_price - ATR_STOP_MULT  * atr
            trail_stop = pos.highest   - ATR_TRAIL_MULT * atr
            if p <= atr_stop or p <= trail_stop:
                to_stop.append(sym)

        for sym in to_stop:
            pos = portfolio.pop(sym)
            p = get_price(features, sym, date)
            if p is None:
                p = pos.avg_price
            eff = p * (1.0 - FEE_TOTAL)
            cash += pos.shares * eff
            trades_log.append({"date": date.date().isoformat(), "side": "SELL",
                                "symbol": sym, "reason": "stop"})

        # ── Señales ────────────────────────────────────────────────────────
        bull = spy_bull_regime(features, date)
        eff_max_exp = MAX_EXPOSURE if bull else BEAR_MAX_EXPOSURE

        to_buy_primary, to_buy_fill, to_sell = generate_signals(
            features, date, cfg, set(portfolio.keys())
        )

        # ── Ventas por ranking ─────────────────────────────────────────────
        for sym in to_sell:
            if sym not in portfolio:
                continue
            pos = portfolio.pop(sym)
            p = get_price(features, sym, date)
            if p is None:
                p = pos.avg_price
            eff = p * (1.0 - FEE_TOTAL)
            cash += pos.shares * eff
            trades_log.append({"date": date.date().isoformat(), "side": "SELL",
                                "symbol": sym, "reason": "ranking"})

        # ── Equity tras ventas ─────────────────────────────────────────────
        def portfolio_value() -> float:
            v = cash
            for sym, pos in portfolio.items():
                p = get_price(features, sym, date)
                v += pos.shares * (p if p is not None else pos.avg_price)
            return v

        equity_now = portfolio_value()
        cur_n = len(portfolio)

        # ── Función de compra ──────────────────────────────────────────────
        def do_buy(sym: str) -> bool:
            nonlocal cash
            if sym in portfolio:
                return False
            p = get_price(features, sym, date)
            if p is None or p <= 0:
                return False
            eq = portfolio_value()
            target = (eq * eff_max_exp) / MAX_POSITIONS
            if target < MIN_POSITION_USD:
                return False
            eff_price = p * (1.0 + FEE_TOTAL)
            cost = target / eff_price * eff_price
            if cost > cash * 1.001:  # pequeño margen numérico
                return False
            shares = target / eff_price
            atr = get_atr(features, sym, date)
            portfolio[sym] = Position(
                shares=shares, avg_price=eff_price,
                entry_atr=atr, highest=p
            )
            cash -= cost
            trades_log.append({"date": date.date().isoformat(), "side": "BUY",
                                "symbol": sym, "reason": "primary"})
            return True

        # ── Compras primarias ──────────────────────────────────────────────
        for sym in to_buy_primary:
            if len(portfolio) >= MAX_POSITIONS:
                break
            do_buy(sym)

        # ── Fill-to-target ─────────────────────────────────────────────────
        if cfg.fill_to_target and to_buy_fill:
            for sym in to_buy_fill:
                if len(portfolio) >= MAX_POSITIONS:
                    break
                eq = portfolio_value()
                exp = eq - cash
                exp_pct = exp / eq if eq > 0 else 0
                if exp_pct >= eff_max_exp:
                    break
                do_buy(sym)

        # ── Equity final del día ───────────────────────────────────────────
        equity_end = portfolio_value()
        if equity_end > peak_equity:
            peak_equity = equity_end

        dd = (equity_end / peak_equity - 1.0) if peak_equity > 0 else 0.0

        exp_value = equity_end - cash
        exp_pct   = exp_value / equity_end if equity_end > 0 else 0.0

        equity_curve.append({
            "date":  date.date().isoformat(),
            "value": round(equity_end, 2),
        })
        drawdown_curve.append({
            "date":  date.date().isoformat(),
            "value": round(dd * 100, 4),
        })
        exposure_curve.append({
            "date":  date.date().isoformat(),
            "value": round(exp_pct * 100, 2),
        })

    metrics = compute_metrics(equity_curve, drawdown_curve, exposure_curve, trades_log)
    return {
        "id":             cfg.id,
        "label":          cfg.label,
        "color":          cfg.color,
        "metrics":        metrics,
        "annual_returns": compute_annual_returns(equity_curve),
        "equity_curve":   equity_curve,
        "drawdown_curve": drawdown_curve,
        "exposure_curve": exposure_curve,
    }


def simulate_benchmark(
    sym: str,
    label: str,
    color: str,
    vid: str,
    features: Dict[str, pd.DataFrame],
    trading_dates: pd.DatetimeIndex,
) -> Dict:
    """Buy-and-hold benchmark."""
    print(f"   -> Simulando benchmark '{label}'...")

    ft = features.get(sym)
    if ft is None:
        print(f"   ! No hay datos para {sym}, usando curva plana.")
        eq = [{"date": d.date().isoformat(), "value": START_CASH} for d in trading_dates]
        dd = [{"date": d.date().isoformat(), "value": 0.0} for d in trading_dates]
        ex = [{"date": d.date().isoformat(), "value": 100.0} for d in trading_dates]
        metrics = compute_metrics(eq, dd, ex, [])
        return {"id": vid, "label": label, "color": color,
                "metrics": metrics, "annual_returns": [], "equity_curve": eq,
                "drawdown_curve": dd, "exposure_curve": ex}

    equity_curve:   List[dict] = []
    drawdown_curve: List[dict] = []

    first_price: Optional[float] = None
    shares: float = 0.0
    peak = START_CASH

    for date in trading_dates:
        row = ft[ft.index == date]
        if row.empty:
            # Usa último valor conocido
            if equity_curve:
                equity_curve.append({**equity_curve[-1], "date": date.date().isoformat()})
                drawdown_curve.append({**drawdown_curve[-1], "date": date.date().isoformat()})
            continue
        p = float(row.iloc[0]["close"])
        if pd.isna(p):
            continue

        if first_price is None:
            first_price = p
            # Compra al precio de cierre del primer día (con coste)
            eff = p * (1.0 + FEE_TOTAL)
            shares = START_CASH / eff

        equity = shares * p
        if equity > peak:
            peak = equity
        dd = (equity / peak - 1.0) if peak > 0 else 0.0

        equity_curve.append({"date": date.date().isoformat(), "value": round(equity, 2)})
        drawdown_curve.append({"date": date.date().isoformat(), "value": round(dd * 100, 4)})

    exposure_curve = [{"date": r["date"], "value": 100.0} for r in equity_curve]
    metrics = compute_metrics(equity_curve, drawdown_curve, exposure_curve, [])
    return {
        "id": vid, "label": label, "color": color,
        "metrics": metrics,
        "annual_returns": compute_annual_returns(equity_curve),
        "equity_curve":   equity_curve,
        "drawdown_curve": drawdown_curve,
        "exposure_curve": exposure_curve,
    }


# ─── Métricas ─────────────────────────────────────────────────────────────────
def _safe(v: float, fallback: float = 0.0) -> float:
    """Convierte NaN/Inf a fallback."""
    if v is None or not math.isfinite(v):
        return fallback
    return round(v, 6)


def compute_metrics(
    equity_curve:   List[dict],
    drawdown_curve: List[dict],
    exposure_curve: List[dict],
    trades_log:     List[dict],
) -> dict:
    if len(equity_curve) < 2:
        return {k: 0.0 for k in ["cagr","total_return","volatility","sharpe",
                                   "sortino","max_drawdown","calmar","avg_exposure",
                                   "num_trades","win_rate"]}

    values = [r["value"] for r in equity_curve]
    returns = pd.Series(values).pct_change().dropna()

    n_days = len(equity_curve)
    years  = n_days / 252.0

    first_v = values[0]
    last_v  = values[-1]
    total_return = (last_v / first_v - 1.0) if first_v > 0 else 0.0
    cagr = (last_v / first_v) ** (1.0 / max(years, 0.01)) - 1.0 if first_v > 0 else 0.0

    vol = float(returns.std() * math.sqrt(252)) if len(returns) > 1 else 0.0

    rf = 0.04 / 252  # risk-free rate diaria (4% anual)
    excess = returns - rf
    sharpe = float(excess.mean() / excess.std() * math.sqrt(252)) if excess.std() > 0 else 0.0

    downside = returns[returns < 0]
    sortino_denom = float(downside.std() * math.sqrt(252)) if len(downside) > 1 else 0.0
    sortino = float(excess.mean() * 252 / sortino_denom) if sortino_denom > 0 else 0.0

    max_dd = min(r["value"] for r in drawdown_curve) / 100.0 if drawdown_curve else 0.0
    calmar = abs(cagr / max_dd) if max_dd < 0 else 0.0

    avg_exposure = float(
        sum(r["value"] for r in exposure_curve) / len(exposure_curve)
    ) / 100.0 if exposure_curve else 0.0

    num_buys  = sum(1 for t in trades_log if t["side"] == "BUY")
    num_sells = sum(1 for t in trades_log if t["side"] == "SELL")
    num_trades = num_buys + num_sells
    win_rate = 0.0  # sin registro de PnL por trade en este backtest simplificado

    return {
        "cagr":         _safe(cagr),
        "total_return": _safe(total_return),
        "volatility":   _safe(vol),
        "sharpe":       _safe(sharpe),
        "sortino":      _safe(sortino),
        "max_drawdown": _safe(max_dd),
        "calmar":       _safe(calmar),
        "avg_exposure": _safe(avg_exposure),
        "num_trades":   num_trades,
        "win_rate":     _safe(win_rate),
    }


def compute_annual_returns(equity_curve: List[dict]) -> List[dict]:
    if not equity_curve:
        return []

    df = pd.DataFrame(equity_curve)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    result = []
    for year in range(
        int(df.index[0].year),
        int(df.index[-1].year) + 1
    ):
        yr_data = df[df.index.year == year]
        if len(yr_data) < 2:
            continue
        start_v = float(yr_data.iloc[0]["value"])
        end_v   = float(yr_data.iloc[-1]["value"])
        ret = (end_v / start_v - 1.0) if start_v > 0 else 0.0
        result.append({"year": year, "return": round(ret, 6)})

    return result


# ─── JSON seguro ──────────────────────────────────────────────────────────────
class SafeEncoder(json.JSONEncoder):
    """Reemplaza NaN/Inf con null para JSON estricto."""
    def default(self, obj):
        if isinstance(obj, float):
            if not math.isfinite(obj):
                return None
        return super().default(obj)

    def encode(self, obj):
        # Post-process para reemplazar nan/inf inline
        return super().encode(self._sanitize(obj))

    def _sanitize(self, obj):
        if isinstance(obj, float):
            if not math.isfinite(obj):
                return None
            return obj
        if isinstance(obj, dict):
            return {k: self._sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize(v) for v in obj]
        return obj


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Backtest momentum strategy – invest-bot")
    print(f"Periodo: {BACKTEST_START} -> {BACKTEST_END}")
    print("=" * 60)

    # 1. Descarga
    prices = download_prices(ALL_DOWNLOAD)

    # 2. Features
    features = build_features_panel(prices)

    # 3. Fechas de backtest
    trading_dates = get_trading_dates(features)
    print(f"[3/4] Días de trading en el backtest: {len(trading_dates)}")

    if len(trading_dates) < 10:
        print("ERROR: Fechas de backtest insuficientes. Revisa los datos.")
        sys.exit(1)

    # 4. Simulación
    print("[4/4] Ejecutando simulaciones...")
    results = []

    for cfg in VARIANTS:
        if cfg.id in ("spy", "acwi"):
            continue
        r = simulate_variant(cfg, features, trading_dates)
        results.append(r)

    # Benchmarks
    results.append(simulate_benchmark(
        "SPY", "SPY (B&H)", "#0ea5e9", "spy", features, trading_dates
    ))
    results.append(simulate_benchmark(
        "ACWI", "ACWI (B&H)", "#a78bfa", "acwi", features, trading_dates
    ))

    # 5. Output
    output = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "period": {
            "start":        str(trading_dates[0].date()),
            "end":          str(trading_dates[-1].date()),
            "trading_days": len(trading_dates),
        },
        "variants": results,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    enc = SafeEncoder()
    json_str = enc.encode(output)

    # Validar que es JSON válido antes de guardar
    try:
        json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON inválido generado: {e}")
        sys.exit(1)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(json_str)

    print()
    print("=" * 60)
    print(f"Resultados guardados en: {OUTPUT_PATH}")
    print()
    print("Resumen de métricas:")
    print(f"{'Variante':<20} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>8} {'Exp%':>7}")
    print("-" * 50)
    for r in results:
        m = r["metrics"]
        print(f"{r['label']:<20} {m['cagr']*100:>6.1f}% {m['sharpe']:>7.2f}"
              f" {m['max_drawdown']*100:>7.1f}% {m['avg_exposure']*100:>6.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
