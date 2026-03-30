"""Multi-timeframe technical analysis service."""

from datetime import datetime, timezone
from app.models.schemas import MultiTimeframe, TimeframeSignal, TechnicalIndicators
from app.services.technical import calculate_indicators, empty_indicators
from app.services.market_data import fetch_cmc_batch
from app.core.config import settings

TIMEFRAMES = ["1h", "4h", "1d"]


def _analyze_timeframe(ind: TechnicalIndicators) -> TimeframeSignal:
    """Determine signal direction and strength from indicators."""
    score = 0
    signals = 0

    # RSI analysis
    if ind.rsi is not None:
        signals += 1
        if ind.rsi < 30:
            score += 2  # oversold = bullish
        elif ind.rsi < 45:
            score += 1
        elif ind.rsi > 70:
            score -= 2  # overbought = bearish
        elif ind.rsi > 55:
            score -= 1

    # MACD analysis
    if ind.macd_hist is not None:
        signals += 1
        if ind.macd_hist > 0:
            score += 1
            if ind.macd is not None and ind.macd_signal is not None and ind.macd > ind.macd_signal:
                score += 1
        else:
            score -= 1
            if ind.macd is not None and ind.macd_signal is not None and ind.macd < ind.macd_signal:
                score -= 1

    # EMA trend
    ema_trend = "neutral"
    if ind.ema_21 is not None and ind.ema_55 is not None:
        signals += 1
        if ind.ema_21 > ind.ema_55:
            score += 1
            ema_trend = "bullish"
        else:
            score -= 1
            ema_trend = "bearish"

    # Bollinger Band position
    bb_position = "middle"
    if ind.bb_upper is not None and ind.bb_lower is not None and ind.bb_middle is not None:
        signals += 1
        # We don't have the current price in indicators, so use bb_middle as reference
        mid = ind.bb_middle
        band_width = ind.bb_upper - ind.bb_lower
        if band_width > 0:
            if ind.ema_21 and ind.ema_21 > ind.bb_upper:
                bb_position = "above_upper"
                score -= 1  # overbought
            elif ind.ema_21 and ind.ema_21 < ind.bb_lower:
                bb_position = "below_lower"
                score += 1  # oversold

    # Determine direction
    if signals == 0:
        direction = "NEUTRAL"
        strength = 0
    else:
        max_score = signals * 2
        normalized = score / max_score if max_score > 0 else 0
        strength = min(100, max(0, int(abs(normalized) * 100)))
        if normalized > 0.15:
            direction = "LONG"
        elif normalized < -0.15:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

    return TimeframeSignal(
        timeframe=ind.timeframe,
        direction=direction,
        strength=strength,
        rsi=ind.rsi,
        macd_hist=ind.macd_hist,
        ema_trend=ema_trend,
        bb_position=bb_position,
    )


def _determine_consensus(signals: list[TimeframeSignal]) -> str:
    """Determine overall consensus from multiple timeframe signals."""
    long_count = sum(1 for s in signals if s.direction == "LONG")
    short_count = sum(1 for s in signals if s.direction == "SHORT")
    total = len(signals)

    if long_count == total:
        return "STRONG_LONG"
    elif short_count == total:
        return "STRONG_SHORT"
    elif long_count > short_count:
        return "LONG"
    elif short_count > long_count:
        return "SHORT"
    return "NEUTRAL"


async def get_multi_timeframe(symbol: str) -> MultiTimeframe:
    """Calculate multi-timeframe analysis for a symbol."""
    tf_signals = []

    for tf in TIMEFRAMES:
        try:
            ind = await calculate_indicators(symbol, interval=tf)
            signal = _analyze_timeframe(ind)
            tf_signals.append(signal)
        except Exception as e:
            print(f"  ⚠ {symbol} {tf} indicators unavailable: {e}")
            empty = empty_indicators(symbol, interval=tf)
            tf_signals.append(TimeframeSignal(
                timeframe=tf,
                direction="NEUTRAL",
                strength=0,
                ema_trend="neutral",
                bb_position="middle",
            ))

    # Get current price
    price = 0.0
    try:
        cmc = await fetch_cmc_batch()
        if symbol in cmc:
            price = cmc[symbol].price
    except Exception:
        pass

    consensus = _determine_consensus(tf_signals)

    return MultiTimeframe(
        symbol=symbol,
        name=settings.SYMBOL_NAMES.get(symbol, symbol),
        price=price,
        timeframes=tf_signals,
        consensus=consensus,
        timestamp=datetime.now(timezone.utc),
    )


async def get_all_multi_timeframe() -> list[MultiTimeframe]:
    """Get multi-timeframe for all symbols."""
    results = []
    for symbol in settings.SYMBOLS:
        try:
            mt = await get_multi_timeframe(symbol)
            results.append(mt)
        except Exception as e:
            print(f"  ✗ Multi-timeframe failed for {symbol}: {e}")
    return results

