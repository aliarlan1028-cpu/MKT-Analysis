"""Local technical indicator calculations using pandas-ta.

Supports multi-timeframe analysis (1h/4h/1D), advanced indicators
(StochRSI, ADX, OBV, VWAP), and real key level computation
(Swing High/Low + Fibonacci retracements).
"""

import pandas as pd
import numpy as np
import pandas_ta as ta
from app.services.market_data import fetch_klines
from app.models.schemas import TechnicalIndicators


def _safe_float(series, idx=-1, decimals=2):
    """Safely extract a float from a pandas Series."""
    if series is None or series.empty:
        return None
    val = series.iloc[idx]
    if pd.isna(val):
        return None
    return round(float(val), decimals)


def _compute_from_df(df: pd.DataFrame, symbol: str, interval: str) -> TechnicalIndicators:
    """Compute all indicators from a prepared DataFrame."""
    # RSI
    rsi_val = _safe_float(ta.rsi(df["close"], length=14))

    # MACD
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    macd_val = macd_signal = macd_hist = None
    if macd is not None and not macd.empty:
        macd_val = _safe_float(macd.iloc[:, 0])
        macd_signal = _safe_float(macd.iloc[:, 1])
        macd_hist = _safe_float(macd.iloc[:, 2])

    # EMA
    ema21_val = _safe_float(ta.ema(df["close"], length=21))
    ema55_val = _safe_float(ta.ema(df["close"], length=55))

    # Bollinger Bands
    bb = ta.bbands(df["close"], length=20, std=2)
    bb_upper = bb_mid = bb_lower = None
    if bb is not None and not bb.empty:
        bb_lower = _safe_float(bb.iloc[:, 0])
        bb_mid = _safe_float(bb.iloc[:, 1])
        bb_upper = _safe_float(bb.iloc[:, 2])

    # ATR
    atr_val = _safe_float(ta.atr(df["high"], df["low"], df["close"], length=14))

    # Volume SMA
    vol_sma_val = _safe_float(ta.sma(df["volume"], length=20))

    # ── New indicators ──
    # Stochastic RSI
    stoch_rsi = ta.stochrsi(df["close"], length=14, rsi_length=14, k=3, d=3)
    stoch_k = stoch_d = None
    if stoch_rsi is not None and not stoch_rsi.empty:
        stoch_k = _safe_float(stoch_rsi.iloc[:, 0])
        stoch_d = _safe_float(stoch_rsi.iloc[:, 1])

    # ADX (trend strength)
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    adx_val = None
    if adx_df is not None and not adx_df.empty:
        adx_val = _safe_float(adx_df.iloc[:, 0])

    # OBV (On-Balance Volume) + slope
    obv_series = ta.obv(df["close"], df["volume"])
    obv_val = obv_slope = None
    if obv_series is not None and not obv_series.empty:
        obv_val = round(float(obv_series.iloc[-1]), 0)
        # OBV slope over last 10 periods (positive = accumulation)
        if len(obv_series) >= 10:
            recent = obv_series.iloc[-10:]
            slope = (recent.iloc[-1] - recent.iloc[0]) / max(abs(recent.iloc[0]), 1)
            obv_slope = round(float(slope) * 100, 2)  # percentage change

    # VWAP (Volume-Weighted Average Price) - approximate from available data
    vwap_val = None
    if len(df) >= 20:
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        cumvol = df["volume"].cumsum()
        cumtp = (typical_price * df["volume"]).cumsum()
        vwap_series = cumtp / cumvol
        vwap_val = _safe_float(vwap_series)

    return TechnicalIndicators(
        symbol=symbol, timeframe=interval,
        rsi=rsi_val, macd=macd_val, macd_signal=macd_signal, macd_hist=macd_hist,
        ema_21=ema21_val, ema_55=ema55_val,
        bb_upper=bb_upper, bb_middle=bb_mid, bb_lower=bb_lower,
        atr=atr_val, volume_sma_20=vol_sma_val,
        stoch_rsi_k=stoch_k, stoch_rsi_d=stoch_d,
        adx=adx_val, obv=obv_val, obv_slope=obv_slope, vwap=vwap_val,
    )


def _build_df(raw: list[list]) -> pd.DataFrame:
    """Build a clean DataFrame from raw kline data."""
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df


async def calculate_indicators(symbol: str, interval: str = "4h") -> TechnicalIndicators:
    """Fetch klines and compute technical indicators locally."""
    raw = await fetch_klines(symbol, interval=interval, limit=100)
    df = _build_df(raw)
    return _compute_from_df(df, symbol, interval)


async def calculate_multi_tf(symbol: str) -> dict[str, TechnicalIndicators]:
    """Calculate indicators for 1h, 4h, and 1D timeframes."""
    import asyncio
    results = {}
    tasks = []
    timeframes = ["1h", "4h", "1d"]
    for tf in timeframes:
        tasks.append(fetch_klines(symbol, interval=tf, limit=100))
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    for tf, raw in zip(timeframes, raw_results):
        if isinstance(raw, Exception) or not raw:
            results[tf] = empty_indicators(symbol, tf)
        else:
            try:
                df = _build_df(raw)
                results[tf] = _compute_from_df(df, symbol, tf)
            except Exception:
                results[tf] = empty_indicators(symbol, tf)
    return results



async def calculate_key_levels(symbol: str) -> dict:
    """Calculate real support/resistance levels from daily klines.

    Uses Swing High/Low detection + Fibonacci retracement.
    Returns dict with swing_highs, swing_lows, fib_levels, recent_range.
    """
    try:
        raw = await fetch_klines(symbol, interval="1d", limit=90)
        df = _build_df(raw)
    except Exception:
        return {"swing_highs": [], "swing_lows": [], "fib_levels": {}, "recent_range": {}}

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    # Swing High/Low detection (5-bar pivot)
    swing_highs = []
    swing_lows = []
    lookback = 5
    for i in range(lookback, len(df) - lookback):
        # Swing high: highest in window
        if highs[i] == max(highs[i - lookback:i + lookback + 1]):
            swing_highs.append(round(float(highs[i]), 2))
        # Swing low: lowest in window
        if lows[i] == min(lows[i - lookback:i + lookback + 1]):
            swing_lows.append(round(float(lows[i]), 2))

    # Keep most recent and significant levels (deduplicate within 1%)
    def _dedup(levels, current_price, max_count=4):
        if not levels:
            return []
        unique = [levels[0]]
        for lv in levels[1:]:
            if all(abs(lv - u) / max(u, 1) > 0.01 for u in unique):
                unique.append(lv)
        # Sort by distance to current price, take nearest
        unique.sort(key=lambda x: abs(x - current_price))
        return unique[:max_count]

    current = float(closes[-1])
    swing_highs = _dedup(sorted(swing_highs, reverse=True), current)
    swing_lows = _dedup(sorted(swing_lows), current)

    # Fibonacci retracement from 90-day range
    period_high = float(max(highs))
    period_low = float(min(lows))
    diff = period_high - period_low
    fib_levels = {
        "0.0": round(period_high, 2),
        "0.236": round(period_high - diff * 0.236, 2),
        "0.382": round(period_high - diff * 0.382, 2),
        "0.5": round(period_high - diff * 0.5, 2),
        "0.618": round(period_high - diff * 0.618, 2),
        "0.786": round(period_high - diff * 0.786, 2),
        "1.0": round(period_low, 2),
    }

    # Price position in range
    price_position = round((current - period_low) / max(diff, 0.01) * 100, 1)

    return {
        "swing_highs": swing_highs,
        "swing_lows": swing_lows,
        "fib_levels": fib_levels,
        "recent_range": {
            "high_90d": round(period_high, 2),
            "low_90d": round(period_low, 2),
            "current": round(current, 2),
            "position_pct": price_position,  # 0=at low, 100=at high
        },
    }


def empty_indicators(symbol: str, interval: str = "4h") -> TechnicalIndicators:
    """Return empty indicators when kline data is unavailable."""
    return TechnicalIndicators(symbol=symbol, timeframe=interval)


def format_indicators_for_prompt(ind: TechnicalIndicators) -> str:
    """Format single-TF indicators into readable text."""
    lines = [
        f"=== {ind.symbol} Technical Indicators ({ind.timeframe}) ===",
        f"RSI(14): {ind.rsi}",
        f"MACD: {ind.macd} | Signal: {ind.macd_signal} | Histogram: {ind.macd_hist}",
        f"EMA21: {ind.ema_21} | EMA55: {ind.ema_55}",
        f"Bollinger Bands: Upper={ind.bb_upper} | Mid={ind.bb_middle} | Lower={ind.bb_lower}",
        f"ATR(14): {ind.atr}",
        f"Volume SMA(20): {ind.volume_sma_20}",
    ]
    # Add new indicators if present
    if ind.stoch_rsi_k is not None:
        lines.append(f"StochRSI: K={ind.stoch_rsi_k} | D={ind.stoch_rsi_d}")
    if ind.adx is not None:
        lines.append(f"ADX(14): {ind.adx} ({'强趋势' if ind.adx > 25 else '震荡'})")
    if ind.obv_slope is not None:
        lines.append(f"OBV斜率: {ind.obv_slope}% ({'资金流入' if ind.obv_slope > 0 else '资金流出'})")
    if ind.vwap is not None:
        lines.append(f"VWAP: ${ind.vwap:,.2f}")
    return "\n".join(lines)


def format_multi_tf_for_prompt(multi_tf: dict[str, TechnicalIndicators]) -> str:
    """Format multi-timeframe indicators into a combined prompt section."""
    sections = []
    tf_labels = {"1h": "1小时(短线结构)", "4h": "4小时(波段趋势)", "1d": "日线(大方向)"}
    for tf in ["1d", "4h", "1h"]:
        ind = multi_tf.get(tf)
        if not ind or ind.rsi is None:
            continue
        label = tf_labels.get(tf, tf)
        trend = "多头" if (ind.ema_21 and ind.ema_55 and ind.ema_21 > ind.ema_55) else "空头" if (ind.ema_21 and ind.ema_55) else "未知"
        bb_pos = ""
        if ind.bb_upper and ind.bb_lower and ind.bb_middle:
            price = ind.vwap or ind.ema_21 or ind.bb_middle
            if price > ind.bb_upper:
                bb_pos = "超买区(布林上轨上方)"
            elif price < ind.bb_lower:
                bb_pos = "超卖区(布林下轨下方)"
            else:
                bb_pos = "中轨附近"

        lines = [
            f"\n--- {label} ---",
            f"  RSI: {ind.rsi} | MACD柱: {ind.macd_hist} | EMA趋势: {trend}",
            f"  BB: [{ind.bb_lower} - {ind.bb_middle} - {ind.bb_upper}] {bb_pos}",
            f"  ATR: {ind.atr}",
        ]
        if ind.stoch_rsi_k is not None:
            lines.append(f"  StochRSI: K={ind.stoch_rsi_k} D={ind.stoch_rsi_d}")
        if ind.adx is not None:
            lines.append(f"  ADX: {ind.adx} ({'趋势行情' if ind.adx > 25 else '震荡行情'})")
        if ind.obv_slope is not None:
            lines.append(f"  OBV趋势: {ind.obv_slope}% ({'持续买入' if ind.obv_slope > 5 else '持续卖出' if ind.obv_slope < -5 else '平衡'})")
        if ind.vwap is not None:
            lines.append(f"  VWAP: ${ind.vwap:,.2f}")
        sections.append("\n".join(lines))

    return "\n".join(sections)


def format_key_levels_for_prompt(levels: dict) -> str:
    """Format key levels into prompt text."""
    if not levels or not levels.get("swing_highs"):
        return "关键价位数据不可用"
    r = levels["recent_range"]
    lines = [
        f"=== 真实关键价位 (90日K线计算) ===",
        f"90日范围: ${r['low_90d']:,.2f} - ${r['high_90d']:,.2f} | 当前位置: {r['position_pct']}%",
        f"摆动高点(阻力): {', '.join(f'${h:,.2f}' for h in levels['swing_highs'])}",
        f"摆动低点(支撑): {', '.join(f'${l:,.2f}' for l in levels['swing_lows'])}",
        f"Fibonacci回撤:",
    ]
    for fib_key, fib_val in levels["fib_levels"].items():
        lines.append(f"  {fib_key}: ${fib_val:,.2f}")
    return "\n".join(lines)