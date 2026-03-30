"""Local technical indicator calculations using pandas-ta."""

import pandas as pd
import pandas_ta as ta
from app.services.market_data import fetch_klines
from app.models.schemas import TechnicalIndicators


async def calculate_indicators(symbol: str, interval: str = "4h") -> TechnicalIndicators:
    """Fetch klines and compute technical indicators locally."""
    raw = await fetch_klines(symbol, interval=interval, limit=100)

    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    # RSI
    rsi = ta.rsi(df["close"], length=14)
    rsi_val = round(float(rsi.iloc[-1]), 2) if rsi is not None and not rsi.empty else None

    # MACD
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    macd_val = macd_signal = macd_hist = None
    if macd is not None and not macd.empty:
        macd_val = round(float(macd.iloc[-1, 0]), 2)
        macd_signal = round(float(macd.iloc[-1, 1]), 2)
        macd_hist = round(float(macd.iloc[-1, 2]), 2)

    # EMA
    ema21 = ta.ema(df["close"], length=21)
    ema55 = ta.ema(df["close"], length=55)

    ema21_val = round(float(ema21.iloc[-1]), 2) if ema21 is not None and not ema21.empty else None
    ema55_val = round(float(ema55.iloc[-1]), 2) if ema55 is not None and not ema55.empty else None

    # Bollinger Bands
    bb = ta.bbands(df["close"], length=20, std=2)
    bb_upper = bb_mid = bb_lower = None
    if bb is not None and not bb.empty:
        bb_lower = round(float(bb.iloc[-1, 0]), 2)
        bb_mid = round(float(bb.iloc[-1, 1]), 2)
        bb_upper = round(float(bb.iloc[-1, 2]), 2)

    # ATR
    atr = ta.atr(df["high"], df["low"], df["close"], length=14)
    atr_val = round(float(atr.iloc[-1]), 2) if atr is not None and not atr.empty else None

    # Volume SMA
    vol_sma = ta.sma(df["volume"], length=20)
    vol_sma_val = round(float(vol_sma.iloc[-1]), 2) if vol_sma is not None and not vol_sma.empty else None

    return TechnicalIndicators(
        symbol=symbol,
        timeframe=interval,
        rsi=rsi_val,
        macd=macd_val,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
        ema_21=ema21_val,
        ema_55=ema55_val,
        bb_upper=bb_upper,
        bb_middle=bb_mid,
        bb_lower=bb_lower,
        atr=atr_val,
        volume_sma_20=vol_sma_val,
    )


def empty_indicators(symbol: str, interval: str = "4h") -> TechnicalIndicators:
    """Return empty indicators when kline data is unavailable."""
    return TechnicalIndicators(
        symbol=symbol,
        timeframe=interval,
    )


def format_indicators_for_prompt(ind: TechnicalIndicators) -> str:
    """Format indicators into readable text for Gemini prompt."""
    lines = [
        f"=== {ind.symbol} Technical Indicators ({ind.timeframe}) ===",
        f"RSI(14): {ind.rsi}",
        f"MACD: {ind.macd} | Signal: {ind.macd_signal} | Histogram: {ind.macd_hist}",
        f"EMA21: {ind.ema_21} | EMA55: {ind.ema_55}",
        f"Bollinger Bands: Upper={ind.bb_upper} | Mid={ind.bb_middle} | Lower={ind.bb_lower}",
        f"ATR(14): {ind.atr}",
        f"Volume SMA(20): {ind.volume_sma_20}",
    ]
    return "\n".join(lines)

