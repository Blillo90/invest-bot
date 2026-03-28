#!/usr/bin/env python3
"""
backtest.py - Vectorized momentum strategy backtest (~300 tickers).

Variants:
  1. current_bot    - buy_top_pct=0.07, fill=False
  2. fill_to_target - buy_top_pct=0.07, fill=True (strict trend)
  3. improved       - buy_top_pct=0.15, fill=True, relaxed fill trend
  4. equal_weight   - monthly rebalanced equal-weight top-150 by liquidity
  5. spy            - buy-and-hold SPY
  6. acwi           - buy-and-hold ACWI

Output: dashboard/invest-dashboard/public/backtest-results.json
"""

import sys, os, json, math, datetime as dt
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Any

import numpy as np
import pandas as pd
import yfinance as yf

# ── Shared strategy logic (canonical) ─────────────────────────────────────
# All feature computation, scoring, and stop logic lives here.
from strategy.core import (
    compute_features_df,
    rank_pct,
    compute_momentum_score,
    compute_momentum_score_v2,
    is_trend_ok_strict,
    is_trend_ok_relaxed,
    check_atr_stop,
    target_position_size,
    compute_metrics,
    compute_annual_returns,
    sanitize,
    compute_ema_sma_bollinger_features,
    ema_sma_bollinger_buy_signal,
    ema_sma_bollinger_sell_signal,
    ema_sma_bollinger_v2_buy_signal,
    ema_sma_bollinger_v2_sell_signal,
    ema_sma_bollinger_v3_buy_signal,
    ema_sma_bollinger_v3_sell_signal,
)

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
REPO_ROOT   = SCRIPT_DIR.parent.parent.parent
OUTPUT_PATH = REPO_ROOT / "dashboard" / "invest-dashboard" / "public" / "backtest-results.json"

# ─── Universe ─────────────────────────────────────────────────────────────────
UNIVERSE = [
    # Mega-cap tech
    "AAPL","MSFT","AMZN","GOOGL","META","NVDA","TSLA","AVGO",
    "AMD","QCOM","INTC","TXN","ADBE","CRM","INTU","CSCO",
    "IBM","ORCL","AMAT","KLAC","LRCX","SNPS","CDNS","MU",
    # Cyber / cloud
    "PANW","CRWD","FTNT","OKTA","TEAM","DDOG","NET","ZS",
    "SNOW","MDB","PLTR",
    # Consumer tech / growth
    "NFLX","SHOP","SQ","PYPL","UBER","LYFT","ABNB","COIN",
    "DOCU","ZM","ROKU","TWLO","RIVN","LCID",
    # Healthcare
    "UNH","JNJ","PFE","MRK","ABBV","TMO","DHR","ABT",
    "MDT","AMGN","GILD","REGN","ISRG","SYK","HCA","HUM",
    "CVS","CI","ZTS","NVO","AZN","NVS","BSX","EW",
    "BDX","IDXX","VRTX","BIIB",
    # Financials
    "JPM","BAC","GS","MS","BLK","SPGI","V","MA",
    "SCHW","ICE","CME","AXP","CB","MMC","AON","EQIX",
    "USB","BRK-B","BBVA","WFC","C","TFC","FITB","MTB",
    "MCO","MSCI","NTRS","AFL","MET","PRU",
    # Consumer staples
    "PG","KO","PEP","WMT","COST","MCD","MDLZ","PM",
    "MO","CL","EL","GIS","K","KHC","SBUX","YUM",
    "DPZ","KR","DG","DLTR","WBA","SYY",
    # Consumer discretionary
    "HD","NKE","TJX","LOW","BKNG","MAR","TGT",
    "DIS","CMCSA","EA","UL","EXPE","HLT","WYNN","MGM",
    "ROST","BBY","PHM","DHI","LEN",
    # Industrials
    "CAT","DE","HON","GE","RTX","LMT","BA","UPS",
    "GD","ITW","EMR","ETN","NSC","WM","SHW","MMM",
    "ROP","ORLY","MSI","ADP","FDX",
    "CARR","OTIS","TDG","CTAS","VRSK","ROK","AME",
    # Airlines
    "DAL","AAL","LUV","UAL",
    # Telecom
    "VZ","T",
    # Energy
    "XOM","CVX","COP","SLB","OXY","DVN","APA","HAL",
    "KMI","WMB","PSX","EOG","FCX",
    # Materials
    "LIN","APD","NEM","ECL","ALB","CF",
    # Real estate
    "PLD","CCI","AMT","SPG","PSA","O",
    # Utilities
    "NEE","AEP","EXC","SRE","XEL","ED","PCG","PEG","DUK","SO",
    # International US-listed
    "ASML","SAP","SHEL","BABA","TSM","TM","SONY","DB","ENI",
    # Other large-caps
    "ACN","MCK","FISV","ANET","TTD","NOW","CHTR",
    "NXPI","MCHP","ADI","SWKS",
    # ETFs - broad
    "SPY","QQQ","VTI","VT","ACWI",
    # ETFs - factor
    "MTUM","VLUE","QUAL","USMV","SIZE",
    # ETFs - sector
    "XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLB","XLRE","XLU",
    # ETFs - international
    "VEA","VWO","EEM","IEFA","IEMG",
    # ETFs - thematic
    "ARKK","SMH","SOXX","IGV",
    # ETFs - commodities
    "GLD","SLV","DBC","USO",
    # ETFs - bonds
    "TLT","IEF","TIP",
]
# Dedup preserving order
UNIVERSE = list(dict.fromkeys(UNIVERSE))

BENCHMARKS      = ["SPY", "ACWI"]
ALL_DOWNLOAD    = list(dict.fromkeys(UNIVERSE + BENCHMARKS))

# ─── Global parameters (env-aware — read from bot.env when MODE=backtest) ────
# These defaults mirror the run_daily.py Config defaults so both stay in sync.
def _envf(k: str, d: float) -> float:
    try:    return float(os.getenv(k, str(d)))
    except: return d

def _envi(k: str, d: int) -> int:
    try:    return int(os.getenv(k, str(d)))
    except: return d

DOWNLOAD_START       = "2022-07-01"
BACKTEST_START       = "2023-01-03"
BACKTEST_END         = "2026-03-27"
START_CASH           = _envf("START_CASH",        100_000.0)
FEE_TOTAL            = (_envf("FEE_BPS", 10) + _envf("SLIPPAGE_BPS", 10)) / 10_000.0
MAX_POSITIONS        = _envi("MAX_POSITIONS",     12)
MAX_EXPOSURE         = _envf("MAX_EXPOSURE_PCT",  0.95)
BEAR_MAX_EXPOSURE    = 0.50                 # fixed risk rule, not configurable
MIN_POSITION_USD     = _envf("MIN_POSITION_USD",  1_000.0)
MAX_REPLACEMENTS     = _envi("MAX_REPLACEMENTS_PER_DAY", 6)
ATR_STOP_MULT        = _envf("ATR_STOP_MULT",     2.5)
ATR_TRAIL_MULT       = _envf("ATR_TRAIL_MULT",    3.0)
MIN_HISTORY_DAYS     = 252
MIN_DOLLAR_VOL       = 5_000_000.0
TOP_N_LIQUIDITY      = 150


# ─── Variant configs ──────────────────────────────────────────────────────────
@dataclass
class VariantConfig:
    id:                 str
    label:              str
    color:              str
    buy_top_pct:        float = 0.07
    sell_out_pct:       float = 0.20
    fill_to_target:     bool  = False
    fill_relaxed_trend: bool  = False
    # ── BotTest2 extensions ────────────────────────────────────────────────
    use_score_v2:       bool  = False  # quality-adjusted scoring (v2 formula)
    trend_exit:         bool  = False  # exit held position if close < SMA50
    vol_weighted_size:  bool  = False  # scale position size inversely with vol_20
    use_ema_sma_bb:     bool  = False  # EMA_SMA_Bollinger strategy
    use_ema_sma_bb_v2:  bool  = False  # EMA_SMA_Bollinger_v2 strategy
    use_ema_sma_bb_v3:  bool  = False  # EMA_SMA_Bollinger_v3 strategy

STRATEGY_VARIANTS = [
    # current_bot: exact live-bot parameters from env (or defaults matching run_daily.py)
    VariantConfig("current_bot",    "Current Bot",    "#6366f1",
                  buy_top_pct=_envf("BUY_TOP_PCT",  0.07),
                  sell_out_pct=_envf("SELL_OUT_PCT", 0.20),
                  fill_to_target=False),
    VariantConfig("fill_to_target", "Fill-to-Target", "#f59e0b",
                  buy_top_pct=_envf("BUY_TOP_PCT",  0.07),
                  sell_out_pct=_envf("SELL_OUT_PCT", 0.20),
                  fill_to_target=True, fill_relaxed_trend=False),
    VariantConfig("improved",       "Improved",       "#10b981",
                  buy_top_pct=0.15, sell_out_pct=0.30,
                  fill_to_target=True, fill_relaxed_trend=True),
    # ── BotTest2 ───────────────────────────────────────────────────────────
    # Quality-adjusted momentum with trend exit and vol-weighted sizing.
    # Wider buy/hold universe than current_bot, fills to target,
    # but only enters names with strict uptrend.
    VariantConfig("bottest2",       "BotTest2",       "#ec4899",
                  buy_top_pct=0.10, sell_out_pct=0.25,
                  fill_to_target=True, fill_relaxed_trend=False,
                  use_score_v2=True, trend_exit=True, vol_weighted_size=True),
    VariantConfig("ema_sma_bollinger", "EMA_SMA_Bollinger", "#f59e0b",
                  buy_top_pct=0.10, sell_out_pct=0.25,
                  fill_to_target=True, fill_relaxed_trend=True,
                  use_score_v2=False, trend_exit=False, vol_weighted_size=False,
                  use_ema_sma_bb=True),
    VariantConfig("ema_sma_bollinger_v2", "EMA_SMA_Bollinger_v2", "#10b981",
                  buy_top_pct=0.10, sell_out_pct=0.25,
                  fill_to_target=True, fill_relaxed_trend=True,
                  use_score_v2=False, trend_exit=False, vol_weighted_size=False,
                  use_ema_sma_bb=False, use_ema_sma_bb_v2=True),
    VariantConfig("ema_sma_bollinger_v3", "EMA_SMA_Bollinger_v3", "#3b82f6",
                  buy_top_pct=0.10, sell_out_pct=0.25,
                  fill_to_target=True, fill_relaxed_trend=True,
                  use_score_v2=False, trend_exit=False, vol_weighted_size=False,
                  use_ema_sma_bb=False, use_ema_sma_bb_v2=False, use_ema_sma_bb_v3=True),
]


# ─── 1. Download ──────────────────────────────────────────────────────────────
def download_prices(tickers: List[str]) -> Dict[str, pd.DataFrame]:
    print(f"[1/5] Downloading {len(tickers)} tickers from {DOWNLOAD_START}...")
    raw = yf.download(
        tickers=tickers, start=DOWNLOAD_START, end=BACKTEST_END,
        interval="1d", auto_adjust=True, group_by="ticker",
        threads=True, progress=True,
    )
    result: Dict[str, pd.DataFrame] = {}
    if isinstance(raw.columns, pd.MultiIndex):
        for sym in tickers:
            if sym not in raw.columns.get_level_values(0):
                continue
            sub = raw[sym].copy().rename(columns=str.lower)
            sub = sub.dropna(subset=["close"])
            sub.index = pd.to_datetime(sub.index)
            if len(sub) >= MIN_HISTORY_DAYS + 50:
                result[sym] = sub
    else:
        sym = tickers[0]
        sub = raw.copy().rename(columns=str.lower).dropna(subset=["close"])
        sub.index = pd.to_datetime(sub.index)
        if len(sub) >= MIN_HISTORY_DAYS + 50:
            result[sym] = sub
    print(f"   -> {len(result)} tickers with sufficient data.")
    return result


# ─── 2. Features ─────────────────────────────────────────────────────────────
def build_features_panel(prices: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Compute features for all tickers using the canonical strategy.core function."""
    print("[2/5] Computing features...")
    out: Dict[str, pd.DataFrame] = {}
    for sym, df in prices.items():
        try:
            ft = compute_features_df(df)   # canonical — from strategy.core
            if not ft.empty:
                out[sym] = ft
        except Exception:
            pass
    print(f"   -> Features for {len(out)} tickers.")
    return out


# ─── 3. Fast daily lookup ─────────────────────────────────────────────────────
FEATURE_KEYS = ["close","ret_5","ret_10","ret_20","vol_20","atr_14",
                "vol_z_20","dollar_vol_20","sma_50","sma_100","sma_200"]

DayLookup = Dict[str, Dict[str, float]]   # date_str -> {sym: {field: val}}

def build_daily_lookup(
    features: Dict[str, pd.DataFrame],
    trading_dates: pd.DatetimeIndex,
) -> Dict[pd.Timestamp, DayLookup]:
    """Pre-build O(1) date -> sym -> field lookup."""
    print("[3/5] Building daily lookup tables...")
    lookup: Dict[pd.Timestamp, DayLookup] = {}

    for sym, df in features.items():
        df_bt = df[df.index.isin(trading_dates)]
        for date, row in df_bt.iterrows():
            if date not in lookup:
                lookup[date] = {}
            entry: Dict[str, float] = {}
            for k in FEATURE_KEYS:
                v = row.get(k, float("nan"))
                entry[k] = float(v) if not pd.isna(v) else float("nan")
            lookup[date][sym] = entry

    print(f"   -> Lookup built for {len(lookup)} trading days.")
    return lookup


def get_trading_dates(features: Dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    ref = features.get("SPY")
    if ref is None:
        ref = next(iter(features.values()))
    idx = ref.index
    return idx[(idx >= pd.Timestamp(BACKTEST_START)) & (idx <= pd.Timestamp(BACKTEST_END))]


# ─── 4. Signals (vectorized per day) ─────────────────────────────────────────
def get_liquid_universe(
    day_data: DayLookup,
    top_n: int = TOP_N_LIQUIDITY,
) -> List[str]:
    """Top-N tickers by dollar_vol_20, excluding benchmarks, with min liquidity."""
    candidates = [
        (sym, d["dollar_vol_20"])
        for sym, d in day_data.items()
        if sym not in BENCHMARKS
        and not math.isnan(d.get("dollar_vol_20", float("nan")))
        and d["dollar_vol_20"] >= MIN_DOLLAR_VOL
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in candidates[:top_n]]


def spy_bull_regime(day_data: DayLookup) -> bool:
    spy = day_data.get("SPY", {})
    sma200 = spy.get("sma_200", float("nan"))
    close  = spy.get("close",   float("nan"))
    if math.isnan(sma200) or math.isnan(close):
        return True
    return close >= sma200


def score_universe(
    day_data:    DayLookup,
    liquid_syms: List[str],
    use_v2:      bool = False,
) -> pd.DataFrame:
    """
    Compute momentum score for the liquid universe on a given day.

    use_v2=True selects the quality-adjusted BotTest2 formula.
    use_v2=False (default) keeps the original formula for existing variants.
    """
    rows = []
    for sym in liquid_syms:
        d = day_data[sym]
        vol20 = d["vol_20"] if not math.isnan(d["vol_20"]) and d["vol_20"] > 0 else 0.01
        rows.append({
            "symbol":  sym,
            "ret_5":   d["ret_5"]    if not math.isnan(d["ret_5"])    else 0.0,
            "ret_10":  d["ret_10"]   if not math.isnan(d["ret_10"])   else 0.0,
            "ret_20":  d["ret_20"]   if not math.isnan(d["ret_20"])   else 0.0,
            "vol_20":  vol20,
            "vol_z_20": d["vol_z_20"] if not math.isnan(d["vol_z_20"]) else 0.0,
            "sma_50":  d["sma_50"],
            "sma_100": d["sma_100"],
            "close":   d["close"],
        })
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    score_fn = compute_momentum_score_v2 if use_v2 else compute_momentum_score
    df["score"] = score_fn(df)
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def generate_signals(
    day_data:    DayLookup,
    liquid_syms: List[str],
    cfg:         VariantConfig,
    portfolio:   Set[str],
    eff_max_exp: float,
    date:        Optional[pd.Timestamp] = None,
    ema_bb_ts:   Optional[Dict[str, pd.DataFrame]] = None,
) -> Tuple[List[str], List[str], List[str]]:

    # ── EMA_SMA_Bollinger path ──────────────────────────────────────────────
    if cfg.use_ema_sma_bb and ema_bb_ts is not None and date is not None:
        buy_primary: List[str] = []
        to_sell: List[str] = []

        for sym in liquid_syms:
            ts = ema_bb_ts.get(sym)
            if ts is None or ts.empty:
                continue
            # slice history up to and including current date
            hist = ts[ts.index <= date]
            if len(hist) < 15:
                continue

            if sym not in portfolio:
                try:
                    triggered = ema_sma_bollinger_buy_signal(
                        closes=hist["close"],
                        emas=hist["ema_9"],
                        smas=hist["sma_21"],
                        bb_uppers=hist["bb_upper"],
                        bb_lowers=hist["bb_lower"],
                        opens=hist["open"],
                    )
                except Exception:
                    triggered = False
                if triggered:
                    buy_primary.append(sym)
            else:
                try:
                    sell_triggered, _ = ema_sma_bollinger_sell_signal(
                        closes=hist["close"],
                        emas=hist["ema_9"],
                        smas=hist["sma_21"],
                        bb_uppers=hist["bb_upper"],
                        bb_lowers=hist["bb_lower"],
                    )
                except Exception:
                    sell_triggered = False
                if sell_triggered:
                    to_sell.append(sym)

        buy_primary = buy_primary[:MAX_REPLACEMENTS]
        to_sell     = to_sell[:MAX_REPLACEMENTS]

        buy_fill: List[str] = []
        if cfg.fill_to_target:
            # Additional fill candidates: liquid symbols with buy signal not already buying
            already_buying = set(buy_primary)
            for sym in liquid_syms:
                if sym in portfolio or sym in already_buying:
                    continue
                ts = ema_bb_ts.get(sym)
                if ts is None or ts.empty:
                    continue
                hist = ts[ts.index <= date]
                if len(hist) < 15:
                    continue
                try:
                    triggered = ema_sma_bollinger_buy_signal(
                        closes=hist["close"],
                        emas=hist["ema_9"],
                        smas=hist["sma_21"],
                        bb_uppers=hist["bb_upper"],
                        bb_lowers=hist["bb_lower"],
                        opens=hist["open"],
                    )
                except Exception:
                    triggered = False
                if triggered:
                    buy_fill.append(sym)

        return buy_primary, buy_fill, to_sell

    # ── EMA_SMA_Bollinger_v2 path ───────────────────────────────────────────
    if cfg.use_ema_sma_bb_v2 and ema_bb_ts is not None and date is not None:
        buy_primary: List[str] = []
        to_sell: List[str] = []

        for sym in liquid_syms:
            ts = ema_bb_ts.get(sym)
            if ts is None or ts.empty:
                continue
            # slice history up to and including current date
            hist = ts[ts.index <= date]
            if len(hist) < 15:
                continue

            if sym not in portfolio:
                try:
                    triggered = ema_sma_bollinger_v2_buy_signal(
                        closes=hist["close"],
                        opens=hist["open"],
                        emas=hist["ema_9"],
                        smas=hist["sma_21"],
                        bb_uppers=hist["bb_upper"],
                        bb_lowers=hist["bb_lower"],
                    )
                except Exception:
                    triggered = False
                if triggered:
                    buy_primary.append(sym)
            else:
                try:
                    sell_triggered, _ = ema_sma_bollinger_v2_sell_signal(
                        closes=hist["close"],
                        emas=hist["ema_9"],
                        smas=hist["sma_21"],
                        bb_uppers=hist["bb_upper"],
                        bb_lowers=hist["bb_lower"],
                    )
                except Exception:
                    sell_triggered = False
                if sell_triggered:
                    to_sell.append(sym)

        buy_primary = buy_primary[:MAX_REPLACEMENTS]
        to_sell     = to_sell[:MAX_REPLACEMENTS]

        buy_fill: List[str] = []
        if cfg.fill_to_target:
            # Additional fill candidates: liquid symbols with buy signal not already buying
            already_buying = set(buy_primary)
            for sym in liquid_syms:
                if sym in portfolio or sym in already_buying:
                    continue
                ts = ema_bb_ts.get(sym)
                if ts is None or ts.empty:
                    continue
                hist = ts[ts.index <= date]
                if len(hist) < 15:
                    continue
                try:
                    triggered = ema_sma_bollinger_v2_buy_signal(
                        closes=hist["close"],
                        opens=hist["open"],
                        emas=hist["ema_9"],
                        smas=hist["sma_21"],
                        bb_uppers=hist["bb_upper"],
                        bb_lowers=hist["bb_lower"],
                    )
                except Exception:
                    triggered = False
                if triggered:
                    buy_fill.append(sym)

        return buy_primary, buy_fill, to_sell

    # ── EMA_SMA_Bollinger_v3 path ───────────────────────────────────────────
    if cfg.use_ema_sma_bb_v3 and ema_bb_ts is not None and date is not None:
        buy_primary: List[str] = []
        to_sell: List[str] = []

        for sym in liquid_syms:
            ts = ema_bb_ts.get(sym)
            if ts is None or ts.empty:
                continue
            # slice history up to and including current date
            hist = ts[ts.index <= date]
            if len(hist) < 15:
                continue

            if sym not in portfolio:
                try:
                    triggered = ema_sma_bollinger_v3_buy_signal(
                        closes=hist["close"],
                        opens=hist["open"],
                        highs=hist["high"],
                        emas=hist["ema_9"],
                        smas=hist["sma_21"],
                        bb_uppers=hist["bb_upper"],
                        bb_lowers=hist["bb_lower"],
                    )
                except Exception:
                    triggered = False
                if triggered:
                    buy_primary.append(sym)
            else:
                try:
                    sell_triggered, _ = ema_sma_bollinger_v3_sell_signal(
                        closes=hist["close"],
                        emas=hist["ema_9"],
                        smas=hist["sma_21"],
                        bb_uppers=hist["bb_upper"],
                        bb_lowers=hist["bb_lower"],
                    )
                except Exception:
                    sell_triggered = False
                if sell_triggered:
                    to_sell.append(sym)

        buy_primary = buy_primary[:MAX_REPLACEMENTS]
        to_sell     = to_sell[:MAX_REPLACEMENTS]

        buy_fill: List[str] = []
        if cfg.fill_to_target:
            # Additional fill candidates: liquid symbols with buy signal not already buying
            already_buying = set(buy_primary)
            for sym in liquid_syms:
                if sym in portfolio or sym in already_buying:
                    continue
                ts = ema_bb_ts.get(sym)
                if ts is None or ts.empty:
                    continue
                hist = ts[ts.index <= date]
                if len(hist) < 15:
                    continue
                try:
                    triggered = ema_sma_bollinger_v3_buy_signal(
                        closes=hist["close"],
                        opens=hist["open"],
                        highs=hist["high"],
                        emas=hist["ema_9"],
                        smas=hist["sma_21"],
                        bb_uppers=hist["bb_upper"],
                        bb_lowers=hist["bb_lower"],
                    )
                except Exception:
                    triggered = False
                if triggered:
                    buy_fill.append(sym)

        return buy_primary, buy_fill, to_sell

    # ── Standard momentum path ──────────────────────────────────────────────
    # Score universe with the formula selected by cfg (v1 or v2)
    df = score_universe(day_data, liquid_syms, use_v2=cfg.use_score_v2)
    if df.empty:
        return [], [], []

    n = len(df)
    buy_cut  = max(1, int(math.floor(cfg.buy_top_pct  * n)))
    sell_cut = max(1, int(math.floor(cfg.sell_out_pct * n)))

    buy_set  = set(df.head(buy_cut)["symbol"])
    hold_set = set(df.head(sell_cut)["symbol"])

    # Trend filters — canonical from strategy.core
    def strict_trend(sym: str) -> bool:
        d = day_data.get(sym, {})
        return is_trend_ok_strict(
            d.get("close", float("nan")),
            d.get("sma_50", float("nan")),
            d.get("sma_100", float("nan")),
        )

    def relaxed_trend(sym: str) -> bool:
        d = day_data.get(sym, {})
        return is_trend_ok_relaxed(
            d.get("close", float("nan")),
            d.get("sma_100", float("nan")),
        )

    trend_strict_set  = {s for s in df["symbol"] if strict_trend(s)}
    trend_relaxed_set = {s for s in df["symbol"] if relaxed_trend(s)}

    buy_primary_std = (
        df[df["symbol"].isin((buy_set & trend_strict_set) - portfolio)]
        .head(MAX_REPLACEMENTS)["symbol"].tolist()
    )

    # Rank-based sells: positions that dropped out of hold_set
    to_sell_std = (
        df[df["symbol"].isin(portfolio - hold_set)]
        .sort_values("score", ascending=True)["symbol"].tolist()
    )

    # BotTest2 — trend exit: sell held positions that have broken their uptrend
    # (close < SMA50), even if still inside the hold_set ranking threshold.
    if cfg.trend_exit:
        already_selling = set(to_sell_std)
        for sym in portfolio:
            if sym in already_selling:
                continue
            d = day_data.get(sym, {})
            c   = d.get("close",  float("nan"))
            s50 = d.get("sma_50", float("nan"))
            if not math.isnan(c) and not math.isnan(s50) and c < s50:
                to_sell_std.append(sym)

    to_sell_std = to_sell_std[:MAX_REPLACEMENTS]

    buy_fill_std: List[str] = []
    if cfg.fill_to_target:
        trend_for_fill = trend_relaxed_set if cfg.fill_relaxed_trend else trend_strict_set
        fill_pool = trend_for_fill - portfolio - set(buy_primary_std)
        buy_fill_std = df[df["symbol"].isin(fill_pool)]["symbol"].tolist()

    return buy_primary_std, buy_fill_std, to_sell_std


# ─── 5. Simulation ────────────────────────────────────────────────────────────
@dataclass
class Position:
    shares:    float
    avg_price: float
    entry_atr: Optional[float]
    highest:   float


def portfolio_value(
    portfolio: Dict[str, Position],
    day_data:  DayLookup,
    cash:      float,
) -> float:
    v = cash
    for sym, pos in portfolio.items():
        p = day_data.get(sym, {}).get("close", float("nan"))
        v += pos.shares * (p if not math.isnan(p) else pos.avg_price)
    return v


def simulate_variant(
    cfg:           VariantConfig,
    lookup:        Dict[pd.Timestamp, DayLookup],
    trading_dates: pd.DatetimeIndex,
    prices:        Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict:
    print(f"   -> Simulating '{cfg.label}'...")
    cash: float = START_CASH
    portfolio: Dict[str, Position] = {}
    equity_curve, drawdown_curve, exposure_curve = [], [], []
    trades_log: List[dict] = []
    peak = START_CASH

    # ── Precompute EMA/SMA/Bollinger time series (EMA_SMA_Bollinger variants) ─
    ema_bb_ts: Optional[Dict[str, pd.DataFrame]] = None
    if (cfg.use_ema_sma_bb or cfg.use_ema_sma_bb_v2 or cfg.use_ema_sma_bb_v3) and prices is not None:
        print(f"      Precomputing EMA/SMA/Bollinger features for {len(prices)} tickers...")
        ema_bb_ts = {}
        for sym, df_ohlcv in prices.items():
            try:
                feat = compute_ema_sma_bollinger_features(df_ohlcv)
                if not feat.empty:
                    if cfg.use_ema_sma_bb_v3:
                        ema_bb_ts[sym] = feat[["open", "high", "close", "ema_9", "sma_21", "bb_upper", "bb_lower"]]
                    else:
                        ema_bb_ts[sym] = feat[["open", "close", "ema_9", "sma_21", "bb_upper", "bb_lower"]]
            except Exception:
                pass
        print(f"      EMA/SMA/BB precomputed for {len(ema_bb_ts)} tickers.")

    for date in trading_dates:
        day_data = lookup.get(date, {})
        if not day_data:
            # carry forward
            if equity_curve:
                equity_curve.append({**equity_curve[-1], "date": date.date().isoformat()})
                drawdown_curve.append({**drawdown_curve[-1], "date": date.date().isoformat()})
                exposure_curve.append({**exposure_curve[-1], "date": date.date().isoformat()})
            continue

        # 1. Update highest prices
        for sym, pos in portfolio.items():
            p = day_data.get(sym, {}).get("close", float("nan"))
            if not math.isnan(p) and p > pos.highest:
                pos.highest = p

        # 2. ATR stops (canonical — via strategy.core.check_atr_stop)
        to_stop: List[str] = []
        for sym, pos in portfolio.items():
            d = day_data.get(sym, {})
            p = d.get("close", float("nan"))
            if math.isnan(p) or pos.entry_atr is None:
                continue
            triggered, _ = check_atr_stop(
                p, pos.avg_price, pos.highest, pos.entry_atr,
                ATR_STOP_MULT, ATR_TRAIL_MULT,
            )
            if triggered:
                to_stop.append(sym)

        for sym in to_stop:
            pos = portfolio.pop(sym)
            p = day_data.get(sym, {}).get("close", float("nan"))
            if math.isnan(p):
                p = pos.avg_price
            cash += pos.shares * p * (1.0 - FEE_TOTAL)
            trades_log.append({"side": "SELL", "symbol": sym})

        # 3. Regime
        bull         = spy_bull_regime(day_data)
        eff_max_exp  = MAX_EXPOSURE if bull else BEAR_MAX_EXPOSURE
        liquid_syms  = get_liquid_universe(day_data)

        # 4. Signals
        buy_primary, buy_fill, to_sell = generate_signals(
            day_data, liquid_syms, cfg, set(portfolio.keys()), eff_max_exp,
            date=date, ema_bb_ts=ema_bb_ts,
        )

        # 5. Sell by ranking
        for sym in to_sell:
            if sym not in portfolio:
                continue
            pos = portfolio.pop(sym)
            p = day_data.get(sym, {}).get("close", float("nan"))
            if math.isnan(p):
                p = pos.avg_price
            cash += pos.shares * p * (1.0 - FEE_TOTAL)
            trades_log.append({"side": "SELL", "symbol": sym})

        # 6. Buy helper
        def do_buy(sym: str) -> bool:
            nonlocal cash
            if sym in portfolio:
                return False
            p = day_data.get(sym, {}).get("close", float("nan"))
            if math.isnan(p) or p <= 0:
                return False
            eq     = portfolio_value(portfolio, day_data, cash)
            target = target_position_size(eq, eff_max_exp, MAX_POSITIONS)

            # BotTest2 — vol-weighted sizing:
            # Scale position down for high-volatility names (and slightly up
            # for low-vol), bounded within [0.5×, 1.5×] of equal weight.
            # Reference daily vol ~1.5% (≈ 24% annualised, a broad market proxy).
            if cfg.vol_weighted_size:
                sym_vol = day_data.get(sym, {}).get("vol_20", float("nan"))
                if not math.isnan(sym_vol) and sym_vol > 0:
                    REF_VOL = 0.015
                    scale   = min(1.5, max(0.5, REF_VOL / sym_vol))
                    target  = target * scale

            if target < MIN_POSITION_USD:
                return False
            eff   = p * (1.0 + FEE_TOTAL)
            cost  = (target / eff) * eff
            if cost > cash * 1.001:
                return False
            atr = day_data.get(sym, {}).get("atr_14", float("nan"))
            portfolio[sym] = Position(
                shares=target / eff,
                avg_price=eff,
                entry_atr=atr if not math.isnan(atr) else None,
                highest=p,
            )
            cash -= cost
            trades_log.append({"side": "BUY", "symbol": sym})
            return True

        # 7. Primary buys
        for sym in buy_primary:
            if len(portfolio) >= MAX_POSITIONS:
                break
            do_buy(sym)

        # 8. Fill
        if cfg.fill_to_target:
            for sym in buy_fill:
                if len(portfolio) >= MAX_POSITIONS:
                    break
                eq = portfolio_value(portfolio, day_data, cash)
                exp_pct = (eq - cash) / eq if eq > 0 else 0
                if exp_pct >= eff_max_exp:
                    break
                do_buy(sym)

        # 9. Record
        eq  = portfolio_value(portfolio, day_data, cash)
        if eq > peak:
            peak = eq
        dd       = (eq / peak - 1.0) if peak > 0 else 0.0
        exp_pct  = (eq - cash) / eq if eq > 0 else 0.0

        equity_curve.append({"date": date.date().isoformat(), "value": round(eq, 2)})
        drawdown_curve.append({"date": date.date().isoformat(), "value": round(dd * 100, 4)})
        exposure_curve.append({"date": date.date().isoformat(), "value": round(exp_pct * 100, 2)})

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
        "trades":         trades_log,   # included for audit / dashboard
    }


# ─── Equal-weight benchmark ────────────────────────────────────────────────────
def simulate_equal_weight(
    lookup:        Dict[pd.Timestamp, DayLookup],
    trading_dates: pd.DatetimeIndex,
) -> Dict:
    """Monthly rebalanced equal-weight portfolio, top-150 by dollar_vol."""
    print("   -> Simulating 'Equal Weight'...")
    cash  = START_CASH
    portfolio: Dict[str, float] = {}   # sym -> shares
    equity_curve, drawdown_curve = [], []
    peak = START_CASH
    last_rebal_month = -1

    for date in trading_dates:
        day_data = lookup.get(date, {})
        if not day_data:
            if equity_curve:
                equity_curve.append({**equity_curve[-1], "date": date.date().isoformat()})
                drawdown_curve.append({**drawdown_curve[-1], "date": date.date().isoformat()})
            continue

        # Monthly rebalance
        if date.month != last_rebal_month:
            last_rebal_month = date.month
            liquid = get_liquid_universe(day_data, TOP_N_LIQUIDITY)

            if liquid:
                # Equity before rebal
                eq_pre = cash + sum(
                    portfolio.get(sym, 0) * day_data.get(sym, {}).get("close", 0)
                    for sym in portfolio
                )
                target = eq_pre / len(liquid)   # equal weight target per position
                new_set = set(liquid)

                # Sell exiting positions
                for sym in list(portfolio.keys()):
                    if sym not in new_set:
                        p = day_data.get(sym, {}).get("close", float("nan"))
                        if not math.isnan(p) and p > 0:
                            cash += portfolio.pop(sym) * p * (1.0 - FEE_TOTAL)

                # Buy / adjust to target
                for sym in liquid:
                    p = day_data.get(sym, {}).get("close", float("nan"))
                    if math.isnan(p) or p <= 0:
                        continue
                    current_val = portfolio.get(sym, 0) * p
                    diff = target - current_val
                    if diff > p:          # need to buy more
                        cost = diff * (1.0 + FEE_TOTAL)
                        if cost <= cash:
                            portfolio[sym] = portfolio.get(sym, 0) + diff / p
                            cash -= cost
                    elif diff < -p:       # need to trim
                        trim_shares = abs(diff) / p
                        portfolio[sym] = max(0, portfolio.get(sym, 0) - trim_shares)
                        cash += trim_shares * p * (1.0 - FEE_TOTAL)

        # Daily equity
        eq = cash + sum(
            portfolio.get(sym, 0) * day_data.get(sym, {}).get("close", 0)
            for sym in portfolio
            if day_data.get(sym, {}).get("close", 0) > 0
        )
        if eq > peak:
            peak = eq
        dd = (eq / peak - 1.0) if peak > 0 else 0.0
        equity_curve.append({"date": date.date().isoformat(), "value": round(eq, 2)})
        drawdown_curve.append({"date": date.date().isoformat(), "value": round(dd * 100, 4)})

    exposure_curve = [{"date": r["date"], "value": 100.0} for r in equity_curve]
    metrics = compute_metrics(equity_curve, drawdown_curve, exposure_curve, [])
    return {
        "id": "equal_weight", "label": "Equal Weight", "color": "#f43f5e",
        "metrics": metrics,
        "annual_returns": compute_annual_returns(equity_curve),
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "exposure_curve": exposure_curve,
    }


# ─── Buy-and-hold benchmark ────────────────────────────────────────────────────
def simulate_benchmark(
    sym: str, label: str, color: str, vid: str,
    features: Dict[str, pd.DataFrame],
    trading_dates: pd.DatetimeIndex,
) -> Dict:
    print(f"   -> Simulating benchmark '{label}'...")
    ft = features.get(sym)
    if ft is None:
        eq = [{"date": d.date().isoformat(), "value": START_CASH} for d in trading_dates]
        dd = [{"date": d.date().isoformat(), "value": 0.0} for d in trading_dates]
        ex = [{"date": d.date().isoformat(), "value": 100.0} for d in trading_dates]
        return {"id": vid, "label": label, "color": color,
                "metrics": compute_metrics(eq, dd, ex, []),
                "annual_returns": [], "equity_curve": eq,
                "drawdown_curve": dd, "exposure_curve": ex}

    shares, equity_curve, drawdown_curve = 0.0, [], []
    first_price, peak = None, START_CASH

    for date in trading_dates:
        row = ft[ft.index == date]
        if row.empty:
            if equity_curve:
                equity_curve.append({**equity_curve[-1], "date": date.date().isoformat()})
                drawdown_curve.append({**drawdown_curve[-1], "date": date.date().isoformat()})
            continue
        p = float(row.iloc[0]["close"])
        if pd.isna(p):
            continue
        if first_price is None:
            first_price = p
            shares = START_CASH / (p * (1.0 + FEE_TOTAL))
        eq = shares * p
        if eq > peak:
            peak = eq
        dd = (eq / peak - 1.0) if peak > 0 else 0.0
        equity_curve.append({"date": date.date().isoformat(), "value": round(eq, 2)})
        drawdown_curve.append({"date": date.date().isoformat(), "value": round(dd * 100, 4)})

    exposure_curve = [{"date": r["date"], "value": 100.0} for r in equity_curve]
    metrics = compute_metrics(equity_curve, drawdown_curve, exposure_curve, [])
    return {
        "id": vid, "label": label, "color": color,
        "metrics": metrics,
        "annual_returns": compute_annual_returns(equity_curve),
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "exposure_curve": exposure_curve,
    }


# ─── Markdown summary ─────────────────────────────────────────────────────────
def _generate_summary_md(results: List[dict]) -> str:
    """Generate a human-readable backtest summary report."""
    by_id = {r["id"]: r for r in results}
    spy   = by_id.get("spy",  {}).get("metrics", {})
    acwi  = by_id.get("acwi", {}).get("metrics", {})

    lines = [
        "# Backtest Summary",
        f"\n_Generated: {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        f"_Period: {BACKTEST_START} → {BACKTEST_END}_\n",
        "## Key metrics",
        "",
        f"| Strategy | CAGR | Sharpe | Sortino | Max DD | Avg Exp | Trades |",
        f"|----------|-----:|-------:|--------:|-------:|--------:|-------:|",
    ]
    for r in results:
        m = r["metrics"]
        lines.append(
            f"| {r['label']:<22} "
            f"| {m['cagr']*100:>5.1f}% "
            f"| {m['sharpe']:>6.2f} "
            f"| {m['sortino']:>7.2f} "
            f"| {m['max_drawdown']*100:>6.1f}% "
            f"| {m['avg_exposure']*100:>6.1f}% "
            f"| {m['num_trades']:>6} |"
        )

    lines += [
        "",
        "## vs Benchmarks (SPY / ACWI buy-and-hold)",
        "",
        f"| Benchmark | CAGR | Sharpe | Max DD |",
        f"|-----------|-----:|-------:|-------:|",
        f"| SPY  B&H  | {spy.get('cagr', 0)*100:>5.1f}%"
        f" | {spy.get('sharpe', 0):>6.2f}"
        f" | {spy.get('max_drawdown', 0)*100:>6.1f}% |",
        f"| ACWI B&H  | {acwi.get('cagr', 0)*100:>5.1f}%"
        f" | {acwi.get('sharpe', 0):>6.2f}"
        f" | {acwi.get('max_drawdown', 0)*100:>6.1f}% |",
        "",
        "## Annual returns",
        "",
        "| Year |" + "".join(f" {r['label'][:12]:>12} |" for r in results),
        "|------|" + "".join(f"{'---':>13}:|" for _ in results),
    ]

    # Collect all years
    all_years: Set[int] = set()
    for r in results:
        for ar in r.get("annual_returns", []):
            all_years.add(ar["year"])
    for year in sorted(all_years):
        row = f"| {year} |"
        for r in results:
            ar_map = {x["year"]: x["return"] for x in r.get("annual_returns", [])}
            v = ar_map.get(year)
            row += f" {v*100:>11.1f}% |" if v is not None else f" {'N/A':>12} |"
        lines.append(row)

    lines += [
        "",
        "---",
        "_Universe: ~300 US equities + ETFs. "
        "Strategy: daily momentum with ATR stops. "
        "Execution: signal at close T, fill at close T (MOC)._",
    ]
    return "\n".join(lines) + "\n"


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Backtest momentum strategy - invest-bot (300-ticker universe)")
    print(f"Period: {BACKTEST_START} -> {BACKTEST_END}")
    print(f"Universe: {len(UNIVERSE)} tickers to download")
    print("=" * 60)

    prices        = download_prices(ALL_DOWNLOAD)
    features      = build_features_panel(prices)
    trading_dates = get_trading_dates(features)
    print(f"   -> Trading days in backtest: {len(trading_dates)}")

    if len(trading_dates) < 10:
        print("ERROR: Not enough trading days.")
        sys.exit(1)

    lookup = build_daily_lookup(features, trading_dates)

    print("[4/5] Running simulations...")
    results = []

    for cfg in STRATEGY_VARIANTS:
        results.append(simulate_variant(cfg, lookup, trading_dates, prices=prices))

    results.append(simulate_equal_weight(lookup, trading_dates))
    results.append(simulate_benchmark("SPY",  "SPY (B&H)",  "#0ea5e9", "spy",  features, trading_dates))
    results.append(simulate_benchmark("ACWI", "ACWI (B&H)", "#a78bfa", "acwi", features, trading_dates))

    output = {
        "generated_at":  dt.datetime.now(dt.timezone.utc).isoformat(),
        "universe_size": len([s for s in features if s not in BENCHMARKS]),
        "period": {
            "start":        str(trading_dates[0].date()),
            "end":          str(trading_dates[-1].date()),
            "trading_days": len(trading_dates),
        },
        "variants": results,
    }
    output = sanitize(output)

    # ── Write JSON (pretty-printed, human-readable) ─────────────────────────
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(output, ensure_ascii=False, indent=2)
    json.loads(json_str)   # validate round-trip

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(json_str)

    # ── Write Markdown summary ───────────────────────────────────────────────
    SUMMARY_PATH = REPO_ROOT / "quant-bot" / "reports" / "backtest_summary.md"
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        f.write(_generate_summary_md(results))

    print()
    print("[5/5] Results saved to:")
    print(f"      JSON:     {OUTPUT_PATH}")
    print(f"      Summary:  {SUMMARY_PATH}")
    print()
    print(f"{'Variant':<22} {'CAGR':>7} {'Sharpe':>7} {'Sortino':>8} {'MaxDD':>8} {'Exp%':>7}")
    print("-" * 58)
    for r in results:
        m = r["metrics"]
        print(f"{r['label']:<22} {m['cagr']*100:>6.1f}%"
              f" {m['sharpe']:>7.2f} {m['sortino']:>8.2f}"
              f" {m['max_drawdown']*100:>7.1f}% {m['avg_exposure']*100:>6.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
