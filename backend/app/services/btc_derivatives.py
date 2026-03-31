"""BTC Derivatives Dashboard — Core + Technical + Advanced metrics.

Core:    Funding Rate, Open Interest, Liquidations
Technical: EMA Trend (21/55/200), RSI Divergence, ATR Stop-Loss
Advanced:  CVD (Cumulative Volume Delta), Volume Profile
"""

import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone
from app.services.market_data import _okx_get, fetch_klines, _OKX_SYMBOL_MAP

SYMBOL = "BTCUSDT"
SWAP_INST = "BTC-USDT-SWAP"
ULY = "BTC-USDT"

# ── Cache ──
_cache: dict = {"data": None, "ts": None}
CACHE_TTL = 60  # seconds


async def get_btc_derivatives() -> dict:
    """Return full BTC derivatives dashboard data."""
    import time
    now = time.time()
    if _cache["data"] and _cache["ts"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    core = await _fetch_core()
    tech = await _fetch_technical()
    adv = await _fetch_advanced()

    result = {
        "core": core,
        "technical": tech,
        "advanced": adv,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _cache["data"] = result
    _cache["ts"] = now
    return result


# ═══════════════════════════════════════════
#  CORE: Funding Rate + OI + Liquidations
# ═══════════════════════════════════════════

async def _fetch_core() -> dict:
    funding_rate = None
    next_funding_rate = None
    oi_coin = None
    oi_usd = None
    oi_change_pct = None
    liq_long_usd = 0.0
    liq_short_usd = 0.0
    liq_count = 0
    current_price = 0.0

    # Price
    try:
        body = await _okx_get("/api/v5/market/ticker", {"instId": SWAP_INST})
        if body and body["data"]:
            current_price = float(body["data"][0].get("last", 0))
    except Exception:
        pass

    # Funding rate
    try:
        body = await _okx_get("/api/v5/public/funding-rate", {"instId": SWAP_INST})
        if body and body["data"]:
            funding_rate = float(body["data"][0].get("fundingRate", 0))
            next_funding_rate = float(body["data"][0].get("nextFundingRate", 0)) if body["data"][0].get("nextFundingRate") else None
    except Exception:
        pass

    # Open Interest
    try:
        body = await _okx_get("/api/v5/public/open-interest", {"instType": "SWAP", "instId": SWAP_INST})
        if body and body["data"]:
            oi_coin = float(body["data"][0].get("oiCcy", 0))
            oi_usd = oi_coin * current_price if current_price else None
    except Exception:
        pass

    # OI history (24h change) — use 2 data points
    try:
        body = await _okx_get("/api/v5/rubik/stat/contracts/open-interest-volume",
                              {"ccy": "BTC", "period": "1D"})
        if body and body["data"] and len(body["data"]) >= 2:
            latest_oi = float(body["data"][0][1])  # oi field
            prev_oi = float(body["data"][1][1])
            if prev_oi > 0:
                oi_change_pct = round((latest_oi - prev_oi) / prev_oi * 100, 2)
    except Exception:
        pass

    # Recent liquidations
    try:
        body = await _okx_get("/api/v5/public/liquidation-orders",
                              {"instType": "SWAP", "uly": ULY, "state": "filled", "limit": "100"})
        if body and body["data"]:
            ct_val = 0.01  # BTC contract value
            for batch in body["data"]:
                for d in batch.get("details", []):
                    sz = float(d.get("sz", 0))
                    bk_px = float(d.get("bkPx", 0))
                    usd = sz * ct_val * bk_px
                    side = d.get("posSide", "long")
                    if side == "long":
                        liq_long_usd += usd
                    else:
                        liq_short_usd += usd
                    liq_count += 1
    except Exception:
        pass

    return {
        "price": round(current_price, 2),
        "funding_rate": funding_rate,
        "next_funding_rate": next_funding_rate,
        "oi_coin": round(oi_coin, 2) if oi_coin else None,
        "oi_usd": round(oi_usd, 0) if oi_usd else None,
        "oi_change_pct": oi_change_pct,
        "liq_long_usd": round(liq_long_usd, 0),
        "liq_short_usd": round(liq_short_usd, 0),
        "liq_count": liq_count,
        "liq_ratio": round(liq_long_usd / liq_short_usd, 2) if liq_short_usd > 0 else None,
    }


# ═══════════════════════════════════════════
#  TECHNICAL: EMA Trend + RSI Divergence + ATR Stop
# ═══════════════════════════════════════════

async def _fetch_technical() -> dict:
    try:
        raw = await fetch_klines(SYMBOL, interval="4h", limit=250)
    except Exception:
        return {"error": "K线数据获取失败"}

    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    price = float(df["close"].iloc[-1])

    # EMA 21/55/200
    ema21 = ta.ema(df["close"], length=21)
    ema55 = ta.ema(df["close"], length=55)
    ema200 = ta.ema(df["close"], length=200)

    e21 = round(float(ema21.iloc[-1]), 2) if ema21 is not None and not ema21.empty else None
    e55 = round(float(ema55.iloc[-1]), 2) if ema55 is not None and not ema55.empty else None
    e200 = round(float(ema200.iloc[-1]), 2) if ema200 is not None and not ema200.empty else None

    # EMA trend determination
    ema_trend = "neutral"
    if e21 and e55 and e200:
        if price > e21 > e55 > e200:
            ema_trend = "strong_bull"
        elif price > e21 and price > e55:
            ema_trend = "bull"
        elif price < e21 < e55 < e200:
            ema_trend = "strong_bear"
        elif price < e21 and price < e55:
            ema_trend = "bear"

    # RSI + divergence detection
    rsi_series = ta.rsi(df["close"], length=14)
    rsi_val = round(float(rsi_series.iloc[-1]), 2) if rsi_series is not None and not rsi_series.empty else None
    rsi_divergence = None

    if rsi_series is not None and len(rsi_series) >= 20:
        # Check last 20 bars for divergence
        closes_tail = df["close"].iloc[-20:].values
        rsi_tail = rsi_series.iloc[-20:].values
        # Bullish divergence: price makes lower low, RSI makes higher low
        price_ll = closes_tail[-1] < min(closes_tail[:10])
        rsi_hl = rsi_tail[-1] > min(rsi_tail[:10])
        # Bearish divergence: price makes higher high, RSI makes lower high
        price_hh = closes_tail[-1] > max(closes_tail[:10])
        rsi_lh = rsi_tail[-1] < max(rsi_tail[:10])
        if price_ll and rsi_hl:
            rsi_divergence = "bullish"
        elif price_hh and rsi_lh:
            rsi_divergence = "bearish"

    # ATR stop-loss levels
    atr_series = ta.atr(df["high"], df["low"], df["close"], length=14)
    atr_val = round(float(atr_series.iloc[-1]), 2) if atr_series is not None and not atr_series.empty else None

    long_sl = round(price - atr_val * 1.5, 2) if atr_val else None
    short_sl = round(price + atr_val * 1.5, 2) if atr_val else None
    long_tp = round(price + atr_val * 3, 2) if atr_val else None
    short_tp = round(price - atr_val * 3, 2) if atr_val else None

    return {
        "price": price,
        "ema_21": e21,
        "ema_55": e55,
        "ema_200": e200,
        "ema_trend": ema_trend,
        "rsi": rsi_val,
        "rsi_divergence": rsi_divergence,
        "atr": atr_val,
        "long_stop_loss": long_sl,
        "short_stop_loss": short_sl,
        "long_take_profit": long_tp,
        "short_take_profit": short_tp,
    }


# ═══════════════════════════════════════════
#  ADVANCED: CVD + Volume Profile
# ═══════════════════════════════════════════

async def _fetch_advanced() -> dict:
    try:
        raw = await fetch_klines(SYMBOL, interval="1h", limit=200)
    except Exception:
        return {"error": "K线数据获取失败"}

    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore",
    ])
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df[col] = df[col].astype(float)
    df["taker_buy_base"] = df["taker_buy_base"].astype(float)

    # CVD approximation: buy_vol - sell_vol per bar
    # OKX doesn't give taker buy directly, approximate:
    #   buy_vol ≈ volume * (close - low) / (high - low)
    df["range"] = df["high"] - df["low"]
    df["buy_pct"] = df.apply(
        lambda r: (r["close"] - r["low"]) / r["range"] if r["range"] > 0 else 0.5, axis=1
    )
    df["buy_vol"] = df["volume"] * df["buy_pct"]
    df["sell_vol"] = df["volume"] * (1 - df["buy_pct"])
    df["delta"] = df["buy_vol"] - df["sell_vol"]
    df["cvd"] = df["delta"].cumsum()

    cvd_current = round(float(df["cvd"].iloc[-1]), 2)
    cvd_24h_ago = round(float(df["cvd"].iloc[-24]), 2) if len(df) >= 24 else 0
    cvd_trend = "accumulation" if cvd_current > cvd_24h_ago else "distribution"

    # Volume Profile — last 200 hours grouped into 15 price levels
    price_min = float(df["low"].min())
    price_max = float(df["high"].max())
    n_levels = 15
    step = (price_max - price_min) / n_levels if n_levels > 0 else 1

    vp_levels = []
    for i in range(n_levels):
        lo = price_min + i * step
        hi = lo + step
        mid = round((lo + hi) / 2, 2)
        # Volume that traded within this price range
        mask = (df["low"] <= hi) & (df["high"] >= lo)
        vol = float(df.loc[mask, "quote_volume"].sum())
        vp_levels.append({"price": mid, "volume": round(vol, 0)})

    # Find POC (Point of Control) — highest volume level
    poc = max(vp_levels, key=lambda x: x["volume"]) if vp_levels else None

    # Value Area (70% of total volume)
    total_vol = sum(l["volume"] for l in vp_levels)
    sorted_levels = sorted(vp_levels, key=lambda x: x["volume"], reverse=True)
    cumul = 0.0
    va_levels = []
    for lv in sorted_levels:
        cumul += lv["volume"]
        va_levels.append(lv["price"])
        if cumul >= total_vol * 0.7:
            break
    vah = round(max(va_levels), 2) if va_levels else None
    val_ = round(min(va_levels), 2) if va_levels else None

    return {
        "cvd_current": cvd_current,
        "cvd_24h_change": round(cvd_current - cvd_24h_ago, 2),
        "cvd_trend": cvd_trend,
        "volume_profile": vp_levels,
        "poc_price": poc["price"] if poc else None,
        "poc_volume": poc["volume"] if poc else None,
        "value_area_high": vah,
        "value_area_low": val_,
    }

