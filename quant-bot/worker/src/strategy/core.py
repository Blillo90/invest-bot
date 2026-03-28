#!/usr/bin/env python3
"""
strategy/core.py — Canonical strategy logic.

All functions here are PURE (no DB, no yfinance). They operate on plain
DataFrames and plain Python values.

  Same inputs  →  same outputs

Used by:
  - run_daily.py   (live / paper trading)
  - backtest.py    (historical simulation)
  - validate_strategy.py (consistency checks)

Any change to scoring, feature computation, ATR stops, or position sizing
must be made HERE ONLY so both live and backtest are always in sync.
"""

import math
from typing import Optional

import numpy as np
import pandas as pd


# ── Canonical score weights ────────────────────────────────────────────────
# Weights apply to cross-sectional percentile ranks (0–1).
# Positive = reward, negative = penalise.
SCORE_W_RET20   = +0.60   # 20-day momentum (primary driver)
SCORE_W_RET10   = +0.25   # 10-day momentum
SCORE_W_RET5    = +0.15   # 5-day momentum
SCORE_W_VOL20   = -0.15   # realised volatility (penalise noisy stocks)
SCORE_W_QUALITY = +0.15   # Sharpe-like ratio: ret_20 / vol_20
SCORE_W_VOLZ20  = +0.10   # volume z-score (volume confirmation)

# ── ATR stop multipliers ───────────────────────────────────────────────────
ATR_STOP_MULT  = 2.5   # initial stop  = avg_price  - ATR_STOP_MULT  × ATR_at_entry
ATR_TRAIL_MULT = 3.0   # trailing stop = highest    - ATR_TRAIL_MULT × ATR_at_entry

# ── Risk-free rate (annual) ────────────────────────────────────────────────
RISK_FREE_RATE = 0.04


# ────────────────────────────────────────────────────────────────────────────
# Feature computation (pure pandas, no DB, no network)
# ────────────────────────────────────────────────────────────────────────────

def compute_features_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all technical features from an OHLCV DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must have columns: open, high, low, close, volume.
        Index must be a DatetimeIndex (dates, ascending).

    Returns
    -------
    pd.DataFrame
        Same rows as input plus columns:
            ret_1, ret_5, ret_10, ret_20, vol_20,
            atr_14, vol_z_20, dollar_vol_20,
            sma_50, sma_100, sma_200
        Rows with NaN in key columns are dropped.
    """
    d = df.copy().sort_index()

    # ── Momentum (returns) ──────────────────────────────────────────────────
    d["ret_1"]  = d["close"].pct_change()
    d["ret_5"]  = d["close"].pct_change(5)
    d["ret_10"] = d["close"].pct_change(10)
    d["ret_20"] = d["close"].pct_change(20)

    # ── Realised volatility ─────────────────────────────────────────────────
    d["vol_20"] = d["ret_1"].rolling(20).std()

    # ── ATR 14 ──────────────────────────────────────────────────────────────
    pc = d["close"].shift(1)
    tr = pd.concat([
        (d["high"] - d["low"]).abs(),
        (d["high"] - pc).abs(),
        (d["low"]  - pc).abs(),
    ], axis=1).max(axis=1)
    d["atr_14"] = tr.rolling(14).mean()

    # ── Volume signals ──────────────────────────────────────────────────────
    vol_m = d["volume"].rolling(20).mean()
    vol_s = d["volume"].rolling(20).std().replace(0, np.nan)
    d["vol_z_20"]      = (d["volume"] - vol_m) / vol_s
    d["dollar_vol_20"] = (d["close"] * d["volume"]).rolling(20).mean()

    # ── Trend filters ───────────────────────────────────────────────────────
    d["sma_50"]  = d["close"].rolling(50).mean()
    d["sma_100"] = d["close"].rolling(100).mean()
    d["sma_200"] = d["close"].rolling(200).mean()

    return d.dropna(subset=[
        "ret_20", "vol_20", "atr_14", "vol_z_20", "dollar_vol_20",
        "sma_50", "sma_100",
    ])


# ────────────────────────────────────────────────────────────────────────────
# Momentum scoring
# ────────────────────────────────────────────────────────────────────────────

def rank_pct(s: pd.Series) -> pd.Series:
    """Cross-sectional percentile rank (0–1). Higher is better."""
    return s.rank(pct=True)


def compute_momentum_score(df: pd.DataFrame) -> pd.Series:
    """
    Compute composite momentum score for a cross-section of tickers.

    Parameters
    ----------
    df : pd.DataFrame
        One row per ticker. Must have columns:
            ret_5, ret_10, ret_20, vol_20, vol_z_20

    Returns
    -------
    pd.Series of float scores (higher = stronger momentum).
    """
    quality = df["ret_20"] / df["vol_20"].replace(0, np.nan)
    return (
        SCORE_W_RET20   * rank_pct(df["ret_20"].fillna(0))
      + SCORE_W_RET10   * rank_pct(df["ret_10"].fillna(0))
      + SCORE_W_RET5    * rank_pct(df["ret_5"].fillna(0))
      + SCORE_W_VOL20   * rank_pct(df["vol_20"].fillna(df["vol_20"].median()))
      + SCORE_W_QUALITY * rank_pct(quality.fillna(0))
      + SCORE_W_VOLZ20  * rank_pct(df["vol_z_20"].fillna(0))
    )


def compute_momentum_score_v2(df: pd.DataFrame) -> pd.Series:
    """
    BotTest2 scoring: quality-adjusted momentum.

    Shifts emphasis from raw short-term returns toward risk-adjusted quality
    (Sharpe-like) and applies a stronger volatility penalty.  The idea is to
    prefer names that earn their returns efficiently rather than just moving fast.

    Weights vs v1:
        ret_20   : 0.45  (was 0.60)  – still primary signal, less dominant
        ret_10   : 0.20  (was 0.25)  – medium-term confirmation
        ret_5    : 0.05  (was 0.15)  – noise-reduction: minimal short-term weight
        quality  : 0.30  (was 0.15)  – doubled: reward Sharpe, not raw momentum
        vol_z_20 : 0.10  (was 0.10)  – unchanged volume confirmation
        vol_20   : -0.20 (was -0.15) – stronger vol penalty

    Parameters
    ----------
    df : pd.DataFrame
        One row per ticker. Must have columns:
            ret_5, ret_10, ret_20, vol_20, vol_z_20

    Returns
    -------
    pd.Series of float scores (higher = better quality-adjusted momentum).
    """
    quality = df["ret_20"] / df["vol_20"].replace(0, np.nan)
    return (
        0.45 * rank_pct(df["ret_20"].fillna(0))
      + 0.20 * rank_pct(df["ret_10"].fillna(0))
      + 0.05 * rank_pct(df["ret_5"].fillna(0))
      + 0.30 * rank_pct(quality.fillna(0))          # quality is the key differentiator
      + 0.10 * rank_pct(df["vol_z_20"].fillna(0))
      - 0.20 * rank_pct(df["vol_20"].fillna(df["vol_20"].median()))
    )


# ────────────────────────────────────────────────────────────────────────────
# Trend filters (per-element and vectorized)
# ────────────────────────────────────────────────────────────────────────────

def is_trend_ok_strict(close: float, sma_50: float, sma_100: float) -> bool:
    """
    Strict uptrend: close > SMA50 AND SMA50 > SMA100.
    Returns False if any value is NaN.
    """
    if math.isnan(close) or math.isnan(sma_50) or math.isnan(sma_100):
        return False
    return close > sma_50 and sma_50 > sma_100


def is_trend_ok_relaxed(close: float, sma_100: float) -> bool:
    """
    Relaxed uptrend: close > SMA100.
    Returns False if any value is NaN.
    """
    if math.isnan(close) or math.isnan(sma_100):
        return False
    return close > sma_100


def trend_ok_strict_vectorized(df: pd.DataFrame) -> pd.Series:
    """
    Vectorized version of is_trend_ok_strict. Returns a boolean Series.
    df must have columns: close, sma_50, sma_100.
    Equivalent to applying is_trend_ok_strict row-by-row.
    """
    return (
        df["close"].notna()
        & df["sma_50"].notna()
        & df["sma_100"].notna()
        & (df["close"]  > df["sma_50"])
        & (df["sma_50"] > df["sma_100"])
    )


# ────────────────────────────────────────────────────────────────────────────
# ATR stop checks
# ────────────────────────────────────────────────────────────────────────────

def check_atr_stop(
    close:      float,
    avg_price:  float,
    highest:    float,
    atr:        float,
    stop_mult:  float = ATR_STOP_MULT,
    trail_mult: float = ATR_TRAIL_MULT,
) -> tuple[bool, str]:
    """
    Check whether a position should be stopped out by ATR rules.

    Parameters
    ----------
    close     : current price
    avg_price : average entry price
    highest   : highest close since entry
    atr       : ATR value at entry
    stop_mult : initial stop multiplier  (default ATR_STOP_MULT)
    trail_mult: trailing stop multiplier (default ATR_TRAIL_MULT)

    Returns
    -------
    (triggered: bool, reason: str)
    reason is "" when not triggered.
    """
    if atr <= 0 or math.isnan(atr):
        return False, ""

    initial_stop = avg_price - stop_mult  * atr
    trail_stop   = highest   - trail_mult * atr

    if close <= initial_stop:
        return True, f"Stop ATR ({stop_mult}×ATR, stop={initial_stop:.2f})"
    if close <= trail_stop:
        return True, f"Trailing stop ATR ({trail_mult}×ATR, max={highest:.2f}, stop={trail_stop:.2f})"
    return False, ""


# ────────────────────────────────────────────────────────────────────────────
# Position sizing
# ────────────────────────────────────────────────────────────────────────────

def target_position_size(
    equity:        float,
    max_exposure:  float,
    max_positions: int,
) -> float:
    """
    Equal-weight target dollar size per position.

    target = equity × max_exposure / max_positions
    """
    if max_positions <= 0:
        return 0.0
    return (equity * max_exposure) / max_positions


def effective_exposure_cap(
    base_exposure: float,
    spy_close:     float,
    spy_sma200:    float,
) -> float:
    """
    Return effective max-exposure cap based on market regime.

    Bull (SPY ≥ SMA200): full base_exposure.
    Bear (SPY <  SMA200): min(base_exposure, 0.50).
    Falls back to base_exposure if either value is NaN.
    """
    if math.isnan(spy_close) or math.isnan(spy_sma200):
        return base_exposure
    return base_exposure if spy_close >= spy_sma200 else min(base_exposure, 0.50)


# ────────────────────────────────────────────────────────────────────────────
# Performance metrics
# ────────────────────────────────────────────────────────────────────────────

def _safe(v: float, fallback: float = 0.0) -> float:
    return round(v, 6) if math.isfinite(v) else fallback


def compute_metrics(
    equity_curve:   list[dict],
    drawdown_curve: list[dict],
    exposure_curve: list[dict],
    trades_log:     list[dict],
) -> dict:
    """
    Compute standard performance metrics from time-series data.

    Parameters
    ----------
    equity_curve   : [{"date": str, "value": float}, ...]
    drawdown_curve : [{"date": str, "value": float}, ...]  values in % (e.g. -15.3)
    exposure_curve : [{"date": str, "value": float}, ...]  values in %
    trades_log     : [{"side": "BUY"|"SELL", ...}, ...]

    Returns
    -------
    dict with: cagr, total_return, volatility, sharpe, sortino,
               max_drawdown, calmar, avg_exposure, num_trades, win_rate
    """
    zeros = {k: 0.0 for k in [
        "cagr", "total_return", "volatility", "sharpe",
        "sortino", "max_drawdown", "calmar", "avg_exposure",
        "num_trades", "win_rate",
    ]}
    if len(equity_curve) < 2:
        return zeros

    values  = [r["value"] for r in equity_curve]
    returns = pd.Series(values).pct_change().dropna()
    n_days  = len(equity_curve)
    years   = n_days / 252.0
    fv, lv  = values[0], values[-1]

    total_r = (lv / fv - 1.0) if fv > 0 else 0.0
    cagr    = (lv / fv) ** (1.0 / max(years, 0.01)) - 1.0 if fv > 0 else 0.0
    vol     = float(returns.std() * math.sqrt(252)) if len(returns) > 1 else 0.0

    rf_daily = RISK_FREE_RATE / 252
    excess   = returns - rf_daily
    sharpe   = float(excess.mean() / excess.std() * math.sqrt(252)) if excess.std() > 0 else 0.0
    down_ret = returns[returns < 0]
    s_denom  = float(down_ret.std() * math.sqrt(252)) if len(down_ret) > 1 else 0.0
    sortino  = float(excess.mean() * 252 / s_denom) if s_denom > 0 else 0.0

    max_dd  = min(r["value"] for r in drawdown_curve) / 100.0 if drawdown_curve else 0.0
    calmar  = abs(cagr / max_dd) if max_dd < 0 else 0.0
    avg_exp = (
        float(sum(r["value"] for r in exposure_curve) / len(exposure_curve)) / 100.0
        if exposure_curve else 0.0
    )

    return {
        "cagr":         _safe(cagr),
        "total_return": _safe(total_r),
        "volatility":   _safe(vol),
        "sharpe":       _safe(sharpe),
        "sortino":      _safe(sortino),
        "max_drawdown": _safe(max_dd),
        "calmar":       _safe(calmar),
        "avg_exposure": _safe(avg_exp),
        "num_trades":   len(trades_log),
        "win_rate":     0.0,
    }


def compute_annual_returns(equity_curve: list[dict]) -> list[dict]:
    """
    Compute calendar-year returns from an equity curve.

    Parameters
    ----------
    equity_curve : [{"date": str, "value": float}, ...]

    Returns
    -------
    [{"year": int, "return": float}, ...]
    """
    if not equity_curve:
        return []
    df = pd.DataFrame(equity_curve)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    result = []
    for year in range(df.index[0].year, df.index[-1].year + 1):
        yr = df[df.index.year == year]
        if len(yr) < 2:
            continue
        sv, ev = float(yr.iloc[0]["value"]), float(yr.iloc[-1]["value"])
        result.append({
            "year":   year,
            "return": round((ev / sv - 1.0) if sv > 0 else 0.0, 6),
        })
    return result


# ────────────────────────────────────────────────────────────────────────────
# JSON utilities
# ────────────────────────────────────────────────────────────────────────────

def sanitize(obj):
    """
    Recursively replace non-finite floats (NaN, ±Inf) with None
    so the result can be serialised to JSON without errors.
    """
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


# ────────────────────────────────────────────────────────────────────────────
# EMA / SMA / Bollinger helpers (used by EMA_SMA_Bollinger variant)
# ────────────────────────────────────────────────────────────────────────────

def compute_ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()


def compute_bollinger(series: pd.Series, length: int = 20, stddev: float = 2.0):
    """
    Returns (upper, middle, lower) Bollinger Band Series.
    middle = SMA(length), bands = middle ± stddev * rolling_std(length).
    """
    mid = series.rolling(length).mean()
    std = series.rolling(length).std()
    return mid + stddev * std, mid, mid - stddev * std


def compute_ema_sma_bollinger_features(df: pd.DataFrame,
                                        ema_len: int = 9,
                                        sma_len: int = 21,
                                        bb_len: int = 20,
                                        bb_std: float = 2.0) -> pd.DataFrame:
    """
    Compute EMA, SMA, and Bollinger Band columns on a per-ticker OHLCV DataFrame.

    Adds columns:
        ema_9, sma_21, bb_upper, bb_mid, bb_lower
    Drops rows with NaN in those columns.
    """
    d = df.copy().sort_index()
    d["ema_9"]    = compute_ema(d["close"], ema_len)
    d["sma_21"]   = d["close"].rolling(sma_len).mean()
    upper, mid, lower = compute_bollinger(d["close"], bb_len, bb_std)
    d["bb_upper"] = upper
    d["bb_mid"]   = mid
    d["bb_lower"] = lower
    return d.dropna(subset=["ema_9", "sma_21", "bb_upper", "bb_lower"])


def ema_sma_bollinger_buy_signal(
    closes: pd.Series,
    emas: pd.Series,
    smas: pd.Series,
    bb_uppers: pd.Series,
    bb_lowers: pd.Series,
    opens: pd.Series,
    crossover_window: int = 5,
    belly_window: int = 3,
    slope_lookback: int = 3,
) -> bool:
    """
    Returns True when ALL buy conditions are met at the last bar.

    Conditions:
      A. Recent bullish EMA/SMA crossover within last `crossover_window` bars.
         - crossover bar: ema[i-1] <= sma[i-1] AND ema[i] > sma[i]
         - EMA still above SMA on the current bar.
      B. Post-crossover belly:
         - spread = ema - sma
         - spread > 0 on current bar
         - spread now > spread at crossover bar
         - spread growth over last 2 bars < spread growth immediately after crossover
         - current close < max close of last 3 bars (mild pause)
         - current close > sma (structurally healthy)
      C. Bollinger compression:
         - upper_band[now] < upper_band[slope_lookback bars ago]
         - lower_band[now] > lower_band[slope_lookback bars ago]
         - band width now < band width slope_lookback bars ago
      D. Previous candle is red: closes[-2] < opens[-2]

    All arrays must be aligned; the last element is the decision bar.
    Returns False if there is insufficient history.
    """
    min_bars = crossover_window + slope_lookback + belly_window + 2
    if len(closes) < min_bars:
        return False

    # ── A. Recent bullish crossover ──────────────────────────────────────────
    crossover_bar = None
    # search back through crossover_window bars (not including the current bar)
    for k in range(1, crossover_window + 1):
        idx_prev = -(k + 1)
        idx_cur  = -k
        try:
            e_prev, s_prev = emas.iloc[idx_prev], smas.iloc[idx_prev]
            e_cur,  s_cur  = emas.iloc[idx_cur],  smas.iloc[idx_cur]
        except IndexError:
            break
        if math.isnan(e_prev) or math.isnan(s_prev) or math.isnan(e_cur) or math.isnan(s_cur):
            continue
        if e_prev <= s_prev and e_cur > s_cur:
            crossover_bar = idx_cur
            break

    if crossover_bar is None:
        return False
    # EMA still above SMA on the current (decision) bar
    if emas.iloc[-1] <= smas.iloc[-1]:
        return False

    # ── B. Belly pattern ─────────────────────────────────────────────────────
    spread_now      = emas.iloc[-1]  - smas.iloc[-1]
    spread_xover    = emas.iloc[crossover_bar] - smas.iloc[crossover_bar]
    if spread_now <= 0 or spread_now <= spread_xover:
        return False

    # Growth deceleration: spread change over last 2 bars vs first bar after crossover
    spread_2_ago    = emas.iloc[-3] - smas.iloc[-3]
    spread_1_ago    = emas.iloc[-2] - smas.iloc[-2]
    growth_recent   = spread_now - spread_2_ago          # last 2 bars
    spread_xover_p1 = emas.iloc[crossover_bar + 1] - smas.iloc[crossover_bar + 1] if crossover_bar + 1 < 0 else (
        emas.iloc[-1 + (crossover_bar + 1 - (-1))] - smas.iloc[-1 + (crossover_bar + 1 - (-1))]
        if crossover_bar != -1 else spread_now
    )
    growth_initial  = spread_xover_p1 - spread_xover
    # Recent growth must be smaller than initial burst (deceleration)
    if growth_recent >= growth_initial and growth_initial > 0:
        return False

    # Price pause: close not the highest of last 3 bars
    recent_high = closes.iloc[-3:].max()
    if closes.iloc[-1] >= recent_high:
        return False
    # Structurally healthy: close above SMA
    if closes.iloc[-1] <= smas.iloc[-1]:
        return False

    # ── C. Bollinger compression ──────────────────────────────────────────────
    ub_now  = bb_uppers.iloc[-1]
    ub_ago  = bb_uppers.iloc[-1 - slope_lookback]
    lb_now  = bb_lowers.iloc[-1]
    lb_ago  = bb_lowers.iloc[-1 - slope_lookback]
    if math.isnan(ub_now) or math.isnan(ub_ago) or math.isnan(lb_now) or math.isnan(lb_ago):
        return False
    if ub_now >= ub_ago:    # upper band must be falling
        return False
    if lb_now <= lb_ago:    # lower band must be rising
        return False
    width_now = ub_now - lb_now
    width_ago = ub_ago - lb_ago
    if width_now >= width_ago:  # overall width must narrow
        return False

    # ── D. Previous candle red ────────────────────────────────────────────────
    if closes.iloc[-2] >= opens.iloc[-2]:
        return False

    return True


def ema_sma_bollinger_sell_signal(
    closes: pd.Series,
    emas: pd.Series,
    smas: pd.Series,
    bb_uppers: pd.Series,
    bb_lowers: pd.Series,
) -> tuple[bool, str]:
    """
    Returns (triggered, reason) for sell conditions.

    Sell when ANY of:
      A. Bearish EMA/SMA crossover: ema[-2] >= sma[-2] AND ema[-1] < sma[-1]
      B. Structure failure: close < both EMA and SMA
      C. Pattern invalidation: Bollinger expanding (compression gone) AND close < EMA
    """
    if len(closes) < 3:
        return False, ""

    e_now, s_now = emas.iloc[-1], smas.iloc[-1]
    e_prev, s_prev = emas.iloc[-2], smas.iloc[-2]
    c_now = closes.iloc[-1]

    # A. Bearish crossover
    if not (math.isnan(e_prev) or math.isnan(s_prev) or math.isnan(e_now) or math.isnan(s_now)):
        if e_prev >= s_prev and e_now < s_now:
            return True, "EMA crossed below SMA"

    # B. Structure failure
    if not (math.isnan(e_now) or math.isnan(s_now)):
        if c_now < e_now and c_now < s_now:
            return True, "Close below both EMA and SMA"

    # C. Pattern invalidation: Bollinger expanding AND close < EMA
    if len(bb_uppers) >= 4 and len(bb_lowers) >= 4:
        ub_now = bb_uppers.iloc[-1]; ub_ago = bb_uppers.iloc[-4]
        lb_now = bb_lowers.iloc[-1]; lb_ago = bb_lowers.iloc[-4]
        if not any(math.isnan(x) for x in [ub_now, ub_ago, lb_now, lb_ago]):
            bb_expanding = (ub_now > ub_ago) and (lb_now < lb_ago)
            if bb_expanding and c_now < e_now:
                return True, "BB expanding and close below EMA"

    return False, ""
