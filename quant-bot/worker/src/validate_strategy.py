#!/usr/bin/env python3
"""
validate_strategy.py — Strategy consistency validator.

Verifies that the backtest pipeline and direct calls to strategy.core
produce IDENTICAL signals and feature values for the same input data.

This catches regressions where a code change accidentally diverges
the live-bot logic from the backtest logic.

Usage:
    python src/validate_strategy.py

Exit 0 = all checks passed.
Exit 1 = divergence detected or unexpected error.
"""

import sys
import math
import datetime as dt

import pandas as pd
import yfinance as yf

# ── Canonical functions (what we're testing against) ──────────────────────
from strategy.core import (
    compute_features_df,
    compute_momentum_score,
    is_trend_ok_strict,
    is_trend_ok_relaxed,
    check_atr_stop,
    target_position_size,
    ATR_STOP_MULT,
    ATR_TRAIL_MULT,
)

# ── Backtest pipeline (must match strategy.core) ──────────────────────────
from backtest import (
    build_features_panel,
    build_daily_lookup,
    score_universe,
    get_liquid_universe,
    BENCHMARKS,
)

# ── Test configuration ────────────────────────────────────────────────────
TOLERANCE      = 1e-9   # max allowed absolute difference in any metric
TEST_TICKERS   = [
    "SPY", "AAPL", "MSFT", "NVDA", "GOOGL",
    "META", "AMZN", "JPM", "V",    "HD",
]
PERIOD_START   = "2024-01-01"
PERIOD_END     = "2024-06-30"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _download(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    raw = yf.download(
        tickers=tickers, start=start, end=end,
        interval="1d", auto_adjust=True,
        group_by="ticker", threads=True, progress=False,
    )
    prices: dict[str, pd.DataFrame] = {}
    if isinstance(raw.columns, pd.MultiIndex):
        for sym in tickers:
            if sym in raw.columns.get_level_values(0):
                sub = raw[sym].copy().rename(columns=str.lower).dropna(subset=["close"])
                sub.index = pd.to_datetime(sub.index)
                if len(sub) >= 30:
                    prices[sym] = sub
    else:
        sym = tickers[0]
        sub = raw.copy().rename(columns=str.lower).dropna(subset=["close"])
        sub.index = pd.to_datetime(sub.index)
        if len(sub) >= 30:
            prices[sym] = sub
    return prices


def _check(label: str, ok: bool, detail: str = "") -> bool:
    status = PASS if ok else FAIL
    suffix = f" — {detail}" if detail else ""
    print(f"  {status}  {label}{suffix}")
    return ok


# ─────────────────────────────────────────────────────────────────────────────
# Check 1 — Feature computation consistency
# ─────────────────────────────────────────────────────────────────────────────

def check_features(prices: dict) -> bool:
    """
    Verify that build_features_panel() and direct compute_features_df()
    produce identical results for every ticker and feature column.
    """
    print("\n[1/4] Feature computation consistency")

    features_direct = {}
    for sym, df in prices.items():
        ft = compute_features_df(df)
        if not ft.empty:
            features_direct[sym] = ft

    features_pipeline = build_features_panel(prices)

    if not _check("Same tickers present",
                  set(features_direct) == set(features_pipeline),
                  f"direct={sorted(features_direct)}, pipeline={sorted(features_pipeline)}"):
        return False

    max_diff_overall = 0.0
    for sym in features_direct:
        fa = features_direct[sym]
        fb = features_pipeline[sym]
        common = fa.index.intersection(fb.index)
        for col in ["ret_20", "vol_20", "atr_14", "sma_50", "sma_100", "vol_z_20", "dollar_vol_20"]:
            if col not in fa.columns or col not in fb.columns:
                continue
            diff = (fa.loc[common, col] - fb.loc[common, col]).abs().max()
            if not math.isnan(diff):
                max_diff_overall = max(max_diff_overall, diff)
            if diff > TOLERANCE:
                _check(f"{sym}.{col}", False, f"max diff = {diff:.2e}")
                return False

    return _check("All feature values identical",
                  max_diff_overall <= TOLERANCE,
                  f"max diff = {max_diff_overall:.2e}")


# ─────────────────────────────────────────────────────────────────────────────
# Check 2 — Momentum score consistency
# ─────────────────────────────────────────────────────────────────────────────

def check_scores(prices: dict) -> bool:
    """
    Verify that score_universe() and direct compute_momentum_score()
    produce identical scores for the same cross-section.
    """
    print("\n[2/4] Momentum score consistency")

    features_pipeline = build_features_panel(prices)
    trading_dates = features_pipeline.get("SPY", next(iter(features_pipeline.values()))).index
    trading_dates = trading_dates[-20:]   # last 20 days of the period

    lookup = build_daily_lookup(features_pipeline, trading_dates)

    max_diff = 0.0
    for date, day_data in lookup.items():
        liquid = [sym for sym in day_data if sym not in BENCHMARKS]
        if len(liquid) < 3:
            continue

        # Path A: via backtest pipeline
        scored_bt = score_universe(day_data, liquid)
        if scored_bt.empty:
            continue
        score_map_bt = dict(zip(scored_bt["symbol"], scored_bt["score"]))

        # Path B: direct via strategy.core
        rows = []
        for sym in liquid:
            d = day_data[sym]
            rows.append({
                "symbol":   sym,
                "ret_5":    d.get("ret_5",    0.0),
                "ret_10":   d.get("ret_10",   0.0),
                "ret_20":   d.get("ret_20",   0.0),
                "vol_20":   max(d.get("vol_20",  0.01), 1e-8),
                "vol_z_20": d.get("vol_z_20", 0.0),
            })
        df_cross = pd.DataFrame(rows)
        scores_direct = compute_momentum_score(df_cross)
        score_map_direct = dict(zip(df_cross["symbol"], scores_direct))

        for sym in score_map_direct:
            if sym in score_map_bt:
                diff = abs(score_map_direct[sym] - score_map_bt[sym])
                if diff > TOLERANCE:
                    print(f"    FAIL: {date.date()} {sym}: diff={diff:.2e}")
                    return False
                max_diff = max(max_diff, diff)

    return _check("Momentum scores identical across all dates",
                  max_diff <= TOLERANCE,
                  f"max diff = {max_diff:.2e}")


# ─────────────────────────────────────────────────────────────────────────────
# Check 3 — ATR stop logic
# ─────────────────────────────────────────────────────────────────────────────

def check_atr_stops() -> bool:
    """
    Verify ATR stop logic with known inputs.
    """
    print("\n[3/4] ATR stop logic")

    cases = [
        # (close, avg_price, highest, atr, stop_mult, trail_mult, expect_triggered)
        (95.0,  100.0, 110.0, 2.0,  2.5, 3.0, True),   # initial stop: 100 - 2.5×2 = 95.0 → triggered
        (95.1,  100.0, 110.0, 2.0,  2.5, 3.0, False),  # just above initial stop
        (104.0, 100.0, 110.0, 2.0,  2.5, 3.0, True),   # trailing: 110 - 3×2 = 104.0 → triggered
        (104.1, 100.0, 110.0, 2.0,  2.5, 3.0, False),  # just above trailing stop
        (120.0, 100.0, 120.0, 2.0,  2.5, 3.0, False),  # at new high, no stop
    ]

    all_ok = True
    for i, (c, avg, hi, atr, sm, tm, expect) in enumerate(cases):
        triggered, reason = check_atr_stop(c, avg, hi, atr, sm, tm)
        ok = triggered == expect
        detail = f"close={c}, avg={avg}, hi={hi}, atr={atr} → {'triggered' if triggered else 'ok'}"
        if not _check(f"Case {i+1}", ok, detail):
            all_ok = False

    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Check 4 — Position sizing
# ─────────────────────────────────────────────────────────────────────────────

def check_sizing() -> bool:
    """Verify target_position_size matches the expected formula."""
    print("\n[4/4] Position sizing")

    cases = [
        (100_000, 0.95, 12, 100_000 * 0.95 / 12),
        (50_000,  0.50, 10, 50_000  * 0.50 / 10),
        (100_000, 0.95, 0,  0.0),   # guard: zero positions
    ]
    all_ok = True
    for eq, exp, n, expected in cases:
        result = target_position_size(eq, exp, n)
        ok = abs(result - expected) < 1e-6
        if not _check(f"equity={eq}, exp={exp}, n={n} → {expected:.2f}", ok,
                      f"got {result:.2f}"):
            all_ok = False
    return all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> bool:
    print("=" * 60)
    print("validate_strategy.py — Strategy consistency check")
    print(f"Period: {PERIOD_START} → {PERIOD_END}")
    print(f"Tickers: {TEST_TICKERS}")
    print(f"Tolerance: {TOLERANCE:.0e}")
    print("=" * 60)

    print("\n[0/4] Downloading test data...")
    prices = _download(TEST_TICKERS, PERIOD_START, PERIOD_END)
    if len(prices) < 3:
        print(f"ERROR: only {len(prices)} tickers downloaded. Need at least 3.")
        return False
    print(f"   -> {len(prices)} tickers downloaded.")

    results = [
        check_features(prices),
        check_scores(prices),
        check_atr_stops(),
        check_sizing(),
    ]

    print()
    if all(results):
        print("=" * 60)
        print(f"{PASS}  ALL CHECKS PASSED — strategy logic is consistent.")
        print("=" * 60)
        return True
    else:
        failed = sum(1 for r in results if not r)
        print("=" * 60)
        print(f"{FAIL}  {failed}/{len(results)} CHECKS FAILED — review output above.")
        print("=" * 60)
        return False


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
