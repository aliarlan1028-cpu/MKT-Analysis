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


def _compute_verdict(core: dict, tech: dict, adv: dict) -> dict:
    """Pure code logic: score each signal and produce overall BTC verdict."""

    score = 0  # positive = bullish, negative = bearish
    signals = []

    # 1. Funding Rate
    fr = core.get("funding_rate")
    if fr is not None:
        if fr < -0.0003:
            score += 2
            signals.append("负费率(空头拥挤,利多)")
        elif fr < 0:
            score += 1
            signals.append("微负费率(偏多)")
        elif fr > 0.001:
            score -= 2
            signals.append("极高费率(多头拥挤,利空)")
        elif fr > 0.0003:
            score -= 1
            signals.append("高费率(偏空)")
        else:
            signals.append("费率中性")

    # 2. OI Change
    oi_chg = core.get("oi_change_pct")
    if oi_chg is not None:
        if oi_chg > 5:
            score += 1
            signals.append(f"OI↑{oi_chg}%(资金涌入)")
        elif oi_chg < -5:
            score -= 1
            signals.append(f"OI↓{oi_chg}%(资金撤离)")

    # 3. Liquidation ratio
    liq_long = core.get("liq_long_usd", 0)
    liq_short = core.get("liq_short_usd", 0)
    total_liq = liq_long + liq_short
    if total_liq > 0:
        if liq_long > liq_short * 3:
            score += 1
            signals.append("大量多头清算(可能筑底)")
        elif liq_short > liq_long * 3:
            score -= 1
            signals.append("大量空头清算(可能见顶)")

    # 4. EMA Trend
    ema_trend = tech.get("ema_trend", "neutral")
    if ema_trend == "strong_bull":
        score += 2
        signals.append("EMA强多头排列")
    elif ema_trend == "bull":
        score += 1
        signals.append("EMA偏多")
    elif ema_trend == "strong_bear":
        score -= 2
        signals.append("EMA强空头排列")
    elif ema_trend == "bear":
        score -= 1
        signals.append("EMA偏空")

    # 5. RSI Divergence
    rsi = tech.get("rsi")
    rsi_div = tech.get("rsi_divergence")
    if rsi_div == "bullish":
        score += 2
        signals.append("RSI看涨背离")
    elif rsi_div == "bearish":
        score -= 2
        signals.append("RSI看跌背离")
    elif rsi is not None:
        if rsi > 75:
            score -= 1
            signals.append(f"RSI={rsi}超买")
        elif rsi < 25:
            score += 1
            signals.append(f"RSI={rsi}超卖")

    # 6. CVD
    cvd_trend = adv.get("cvd_trend")
    if cvd_trend == "accumulation":
        score += 1
        signals.append("CVD吸筹")
    elif cvd_trend == "distribution":
        score -= 1
        signals.append("CVD派发")

    # Determine direction
    if score >= 3:
        direction = "bullish"
        direction_cn = "🟢 偏多"
        strength = "strong" if score >= 5 else "moderate"
    elif score <= -3:
        direction = "bearish"
        direction_cn = "🔴 偏空"
        strength = "strong" if score <= -5 else "moderate"
    else:
        direction = "neutral"
        direction_cn = "⚪ 震荡观望"
        strength = "weak"

    # Key levels
    price = tech.get("price") or core.get("price", 0)
    levels = []
    poc = adv.get("poc_price")
    vah = adv.get("value_area_high")
    val_ = adv.get("value_area_low")
    long_sl = tech.get("long_stop_loss")
    short_sl = tech.get("short_stop_loss")
    long_tp = tech.get("long_take_profit")
    short_tp = tech.get("short_take_profit")

    if poc:
        levels.append({"label": "POC(强支撑/阻力)", "price": poc})
    if vah:
        levels.append({"label": "VAH(上方阻力)", "price": vah})
    if val_:
        levels.append({"label": "VAL(下方支撑)", "price": val_})
    if direction != "bearish" and long_sl:
        levels.append({"label": "做多止损", "price": long_sl})
    if direction != "bearish" and long_tp:
        levels.append({"label": "做多止盈", "price": long_tp})
    if direction != "bullish" and short_sl:
        levels.append({"label": "做空止损", "price": short_sl})
    if direction != "bullish" and short_tp:
        levels.append({"label": "做空止盈", "price": short_tp})

    # One-line summary
    signal_text = "、".join(signals[:4])
    if direction == "bullish":
        summary = f"综合{len(signals)}项指标偏多({signal_text})，关注POC ${poc:,.0f}支撑" if poc else f"综合偏多({signal_text})"
    elif direction == "bearish":
        summary = f"综合{len(signals)}项指标偏空({signal_text})，关注POC ${poc:,.0f}阻力" if poc else f"综合偏空({signal_text})"
    else:
        summary = f"多空信号交织({signal_text})，建议观望等待明确方向"

    return {
        "direction": direction,
        "direction_cn": direction_cn,
        "strength": strength,
        "score": score,
        "signals": signals,
        "key_levels": levels,
        "summary": summary,
        "price": price,
    }


async def get_btc_derivatives() -> dict:
    """Return full BTC derivatives dashboard data."""
    import time
    now = time.time()
    if _cache["data"] and _cache["ts"] and (now - _cache["ts"]) < CACHE_TTL:
        return _cache["data"]

    core = await _fetch_core()
    tech = await _fetch_technical()
    adv = await _fetch_advanced()

    verdict = _compute_verdict(core, tech, adv)

    result = {
        "core": core,
        "technical": tech,
        "advanced": adv,
        "verdict": verdict,
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

