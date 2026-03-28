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

# ─── Global parameters ────────────────────────────────────────────────────────
DOWNLOAD_START       = "2022-07-01"
BACKTEST_START       = "2023-01-03"
BACKTEST_END         = "2026-03-27"
START_CASH           = 100_000.0
FEE_TOTAL            = 20 / 10_000.0       # 20 bps (fee + slippage)
MAX_POSITIONS        = 12
MAX_EXPOSURE         = 0.95
BEAR_MAX_EXPOSURE    = 0.50
MIN_POSITION_USD     = 1_000.0
MAX_REPLACEMENTS     = 6
ATR_STOP_MULT        = 2.5
ATR_TRAIL_MULT       = 3.0
MIN_HISTORY_DAYS     = 252                  # minimo historial antes de operar
MIN_DOLLAR_VOL       = 5_000_000.0          # $5M daily avg vol minimo
TOP_N_LIQUIDITY      = 150                  # top N por liquidez para el ranking activo


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

STRATEGY_VARIANTS = [
    VariantConfig("current_bot",    "Current Bot",    "#6366f1",
                  buy_top_pct=0.07, sell_out_pct=0.20, fill_to_target=False),
    VariantConfig("fill_to_target", "Fill-to-Target", "#f59e0b",
                  buy_top_pct=0.07, sell_out_pct=0.20, fill_to_target=True,  fill_relaxed_trend=False),
    VariantConfig("improved",       "Improved",       "#10b981",
                  buy_top_pct=0.15, sell_out_pct=0.30, fill_to_target=True,  fill_relaxed_trend=True),
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
def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy().sort_index()
    d["ret_1"]  = d["close"].pct_change()
    d["ret_5"]  = d["close"].pct_change(5)
    d["ret_10"] = d["close"].pct_change(10)
    d["ret_20"] = d["close"].pct_change(20)
    d["vol_20"] = d["ret_1"].rolling(20).std()

    pc  = d["close"].shift(1)
    tr  = pd.concat([
        (d["high"] - d["low"]).abs(),
        (d["high"] - pc).abs(),
        (d["low"]  - pc).abs(),
    ], axis=1).max(axis=1)
    d["atr_14"]       = tr.rolling(14).mean()
    vm                = d["volume"].rolling(20).mean()
    vs                = d["volume"].rolling(20).std().replace(0, np.nan)
    d["vol_z_20"]     = (d["volume"] - vm) / vs
    d["dollar_vol_20"]= (d["close"] * d["volume"]).rolling(20).mean()
    d["sma_50"]       = d["close"].rolling(50).mean()
    d["sma_100"]      = d["close"].rolling(100).mean()
    d["sma_200"]      = d["close"].rolling(200).mean()

    return d.dropna(subset=["ret_20","vol_20","atr_14","sma_50","sma_100"])


def build_features_panel(prices: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    print("[2/5] Computing features...")
    out: Dict[str, pd.DataFrame] = {}
    for sym, df in prices.items():
        try:
            ft = compute_features(df)
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
def rank_pct(s: pd.Series) -> pd.Series:
    return s.rank(pct=True)


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
    day_data: DayLookup,
    liquid_syms: List[str],
) -> pd.DataFrame:
    """Compute momentum score for the liquid universe on a given day."""
    rows = []
    for sym in liquid_syms:
        d = day_data[sym]
        vol20 = d["vol_20"] if not math.isnan(d["vol_20"]) and d["vol_20"] > 0 else 0.01
        rows.append({
            "symbol":  sym,
            "ret_5":   d["ret_5"]   if not math.isnan(d["ret_5"])   else 0.0,
            "ret_10":  d["ret_10"]  if not math.isnan(d["ret_10"])  else 0.0,
            "ret_20":  d["ret_20"]  if not math.isnan(d["ret_20"])  else 0.0,
            "vol_20":  vol20,
            "vol_z_20": d["vol_z_20"] if not math.isnan(d["vol_z_20"]) else 0.0,
            "sma_50":  d["sma_50"],
            "sma_100": d["sma_100"],
            "close":   d["close"],
        })
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    quality = df["ret_20"] / df["vol_20"].replace(0, np.nan)
    df["score"] = (
        0.60 * rank_pct(df["ret_20"].fillna(0))
      + 0.25 * rank_pct(df["ret_10"].fillna(0))
      + 0.15 * rank_pct(df["ret_5"].fillna(0))
      - 0.15 * rank_pct(df["vol_20"])
      + 0.15 * rank_pct(quality.fillna(0))
      + 0.10 * rank_pct(df["vol_z_20"].fillna(0))
    )
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def generate_signals(
    day_data:   DayLookup,
    liquid_syms: List[str],
    cfg:        VariantConfig,
    portfolio:  Set[str],
    eff_max_exp: float,
) -> Tuple[List[str], List[str], List[str]]:
    df = score_universe(day_data, liquid_syms)
    if df.empty:
        return [], [], []

    n = len(df)
    buy_cut  = max(1, int(math.floor(cfg.buy_top_pct  * n)))
    sell_cut = max(1, int(math.floor(cfg.sell_out_pct * n)))

    buy_set  = set(df.head(buy_cut)["symbol"])
    hold_set = set(df.head(sell_cut)["symbol"])

    def strict_trend(sym: str) -> bool:
        d = day_data.get(sym, {})
        s50, s100, c = d.get("sma_50", float("nan")), d.get("sma_100", float("nan")), d.get("close", float("nan"))
        if math.isnan(s50) or math.isnan(s100) or math.isnan(c):
            return False
        return c > s50 and s50 > s100

    def relaxed_trend(sym: str) -> bool:
        d = day_data.get(sym, {})
        s100, c = d.get("sma_100", float("nan")), d.get("close", float("nan"))
        if math.isnan(s100) or math.isnan(c):
            return False
        return c > s100

    trend_strict  = {s for s in df["symbol"] if strict_trend(s)}
    trend_relaxed = {s for s in df["symbol"] if relaxed_trend(s)}

    buy_primary = (
        df[df["symbol"].isin((buy_set & trend_strict) - portfolio)]
        .head(MAX_REPLACEMENTS)["symbol"].tolist()
    )

    to_sell = (
        df[df["symbol"].isin(portfolio - hold_set)]
        .sort_values("score", ascending=True)["symbol"].tolist()[:MAX_REPLACEMENTS]
    )

    buy_fill: List[str] = []
    if cfg.fill_to_target:
        trend_for_fill = trend_relaxed if cfg.fill_relaxed_trend else trend_strict
        fill_pool = trend_for_fill - portfolio - set(buy_primary)
        buy_fill = df[df["symbol"].isin(fill_pool)]["symbol"].tolist()

    return buy_primary, buy_fill, to_sell


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
) -> Dict:
    print(f"   -> Simulating '{cfg.label}'...")
    cash: float = START_CASH
    portfolio: Dict[str, Position] = {}
    equity_curve, drawdown_curve, exposure_curve = [], [], []
    trades_log: List[dict] = []
    peak = START_CASH

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

        # 2. ATR stops
        to_stop: List[str] = []
        for sym, pos in portfolio.items():
            d = day_data.get(sym, {})
            p = d.get("close", float("nan"))
            if math.isnan(p):
                continue
            atr = pos.entry_atr
            if atr is None or atr <= 0:
                continue
            if p <= pos.avg_price - ATR_STOP_MULT * atr:
                to_stop.append(sym)
            elif p <= pos.highest - ATR_TRAIL_MULT * atr:
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
            day_data, liquid_syms, cfg, set(portfolio.keys()), eff_max_exp
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
            eq    = portfolio_value(portfolio, day_data, cash)
            target = (eq * eff_max_exp) / MAX_POSITIONS
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
        "id": cfg.id, "label": cfg.label, "color": cfg.color,
        "metrics": metrics,
        "annual_returns": compute_annual_returns(equity_curve),
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "exposure_curve": exposure_curve,
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


# ─── Metrics ──────────────────────────────────────────────────────────────────
def _safe(v: float, fallback: float = 0.0) -> float:
    return round(v, 6) if math.isfinite(v) else fallback


def compute_metrics(
    equity_curve: List[dict], drawdown_curve: List[dict],
    exposure_curve: List[dict], trades_log: List[dict],
) -> dict:
    if len(equity_curve) < 2:
        return {k: 0.0 for k in ["cagr","total_return","volatility","sharpe",
                                   "sortino","max_drawdown","calmar","avg_exposure","num_trades","win_rate"]}
    values   = [r["value"] for r in equity_curve]
    returns  = pd.Series(values).pct_change().dropna()
    n_days   = len(equity_curve)
    years    = n_days / 252.0
    first_v, last_v = values[0], values[-1]
    total_r  = (last_v / first_v - 1.0) if first_v > 0 else 0.0
    cagr     = (last_v / first_v) ** (1.0 / max(years, 0.01)) - 1.0 if first_v > 0 else 0.0
    vol      = float(returns.std() * math.sqrt(252)) if len(returns) > 1 else 0.0
    rf       = 0.04 / 252
    excess   = returns - rf
    sharpe   = float(excess.mean() / excess.std() * math.sqrt(252)) if excess.std() > 0 else 0.0
    down     = returns[returns < 0]
    s_denom  = float(down.std() * math.sqrt(252)) if len(down) > 1 else 0.0
    sortino  = float(excess.mean() * 252 / s_denom) if s_denom > 0 else 0.0
    max_dd   = min(r["value"] for r in drawdown_curve) / 100.0 if drawdown_curve else 0.0
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    avg_exp  = float(sum(r["value"] for r in exposure_curve) / len(exposure_curve)) / 100.0 if exposure_curve else 0.0
    n_trades = len(trades_log)
    return {
        "cagr":         _safe(cagr),
        "total_return": _safe(total_r),
        "volatility":   _safe(vol),
        "sharpe":       _safe(sharpe),
        "sortino":      _safe(sortino),
        "max_drawdown": _safe(max_dd),
        "calmar":       _safe(calmar),
        "avg_exposure": _safe(avg_exp),
        "num_trades":   n_trades,
        "win_rate":     0.0,
    }


def compute_annual_returns(equity_curve: List[dict]) -> List[dict]:
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
        start_v, end_v = float(yr.iloc[0]["value"]), float(yr.iloc[-1]["value"])
        result.append({"year": year, "return": round((end_v / start_v - 1.0) if start_v > 0 else 0.0, 6)})
    return result


# ─── JSON sanitisation ────────────────────────────────────────────────────────
def sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


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
        results.append(simulate_variant(cfg, lookup, trading_dates))

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

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(output, ensure_ascii=False)
    json.loads(json_str)   # validate

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(json_str)

    print()
    print("[5/5] Results saved to:", OUTPUT_PATH)
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
