"""Pump & Dump Scanner — scans ALL OKX USDT perpetual contracts.

Identifies:
  🟢 Pre-Pump: coins in accumulation phase (volume surge + low volatility + OI growth)
  🔴 Dump-Risk: coins at risk of crash (extreme funding + overbought + overextended)
"""

import asyncio
import httpx
import math
from datetime import datetime, timezone
from app.services.market_data import _okx_get, _OKX_ENDPOINTS

# ── Cache ──
_scanner_cache: dict = {"result": None, "updated_at": None}
CACHE_TTL_SECONDS = 300  # 5 minutes


async def _fetch_all_swap_tickers() -> list[dict]:
    """Fetch ALL swap tickers from OKX in one call."""
    body = await _okx_get("/api/v5/market/tickers", {"instType": "SWAP"})
    if body and body.get("data"):
        return body["data"]
    return []


async def _fetch_all_open_interest() -> dict[str, float]:
    """Fetch open interest for all SWAP contracts."""
    body = await _okx_get("/api/v5/public/open-interest", {"instType": "SWAP"})
    oi_map: dict[str, float] = {}
    if body and body.get("data"):
        for item in body["data"]:
            inst_id = item.get("instId", "")
            oi_usd = float(item.get("oiCcy", 0))
            oi_map[inst_id] = oi_usd
    return oi_map


async def _fetch_funding_rate(inst_id: str) -> float | None:
    """Fetch current funding rate for a single instrument."""
    body = await _okx_get("/api/v5/public/funding-rate", {"instId": inst_id})
    if body and body.get("data"):
        return float(body["data"][0].get("fundingRate", 0))
    return None


async def _fetch_klines_7d(inst_id: str) -> list[list] | None:
    """Fetch 7-day daily klines for an instrument."""
    body = await _okx_get("/api/v5/market/candles", {
        "instId": inst_id, "bar": "1D", "limit": "7"
    })
    if body and body.get("data"):
        return body["data"][::-1]  # reverse to ascending order
    return None


def _calc_rsi(closes: list[float], period: int = 14) -> float | None:
    """Calculate RSI from close prices. Uses 6-period for short data."""
    if len(closes) < 3:
        return None
    p = min(period, len(closes) - 1)
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    if not gains:
        return 50.0
    avg_gain = sum(gains[-p:]) / p
    avg_loss = sum(losses[-p:]) / p
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _calc_bb_width(closes: list[float], period: int = 7) -> float | None:
    """Calculate Bollinger Band width (narrower = potential breakout)."""
    if len(closes) < period:
        return None
    recent = closes[-period:]
    mean = sum(recent) / len(recent)
    if mean == 0:
        return None
    variance = sum((x - mean) ** 2 for x in recent) / len(recent)
    std = math.sqrt(variance)
    return round((std / mean) * 100, 4)  # as percentage


def _calc_volume_ratio(volumes: list[float]) -> float | None:
    """Ratio of latest volume to average of prior volumes."""
    if len(volumes) < 3:
        return None
    avg_prior = sum(volumes[:-1]) / (len(volumes) - 1)
    if avg_prior == 0:
        return None
    return round(volumes[-1] / avg_prior, 2)


def _calc_consecutive_up_days(closes: list[float]) -> int:
    """Count consecutive up days from most recent."""
    count = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            count += 1
        else:
            break
    return count


def _calc_cumulative_return(closes: list[float], days: int = 7) -> float:
    """Cumulative % return over the period."""
    if len(closes) < 2:
        return 0.0
    start = closes[max(0, len(closes) - days)]
    end = closes[-1]
    if start == 0:
        return 0.0
    return round((end - start) / start * 100, 2)


def _calc_ema(closes: list[float], period: int) -> float | None:
    """Simple EMA calculation."""
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = price * k + ema * (1 - k)
    return ema


async def _analyze_coin(ticker: dict, oi_map: dict[str, float]) -> dict | None:
    """Analyze a single coin and return scores."""
    inst_id = ticker.get("instId", "")
    if not inst_id.endswith("-USDT-SWAP"):
        return None

    # Extract basic ticker data
    last = float(ticker.get("last", 0))
    if last == 0:
        return None
    open24h = float(ticker.get("open24h", 0))
    high24h = float(ticker.get("high24h", 0))
    low24h = float(ticker.get("low24h", 0))
    vol24h = float(ticker.get("volCcy24h", 0))  # volume in quote currency
    change_pct = ((last - open24h) / open24h * 100) if open24h > 0 else 0

    # Minimum volume filter (at least $500K daily volume)
    if vol24h < 500_000:
        return None

    # Get OI
    oi = oi_map.get(inst_id, 0)

    # Extract coin name
    coin = inst_id.replace("-USDT-SWAP", "")

    return {
        "inst_id": inst_id,
        "coin": coin,
        "price": last,
        "change_pct_24h": round(change_pct, 2),
        "volume_24h": vol24h,
        "high_24h": high24h,
        "low_24h": low24h,
        "open_interest": oi,
    }


async def _enrich_with_klines(coin_data: dict) -> dict:
    """Fetch klines and funding rate, compute advanced indicators."""
    inst_id = coin_data["inst_id"]

    # Fetch klines and funding in parallel
    klines_task = _fetch_klines_7d(inst_id)
    funding_task = _fetch_funding_rate(inst_id)
    klines, funding = await asyncio.gather(klines_task, funding_task)

    coin_data["funding_rate"] = funding

    if klines and len(klines) >= 3:
        closes = [float(k[4]) for k in klines]
        volumes = [float(k[7]) for k in klines]  # volCcyQuote

        coin_data["rsi"] = _calc_rsi(closes, 6)
        coin_data["bb_width"] = _calc_bb_width(closes)
        coin_data["volume_ratio"] = _calc_volume_ratio(volumes)
        coin_data["consecutive_up_days"] = _calc_consecutive_up_days(closes)
        coin_data["cumulative_return_7d"] = _calc_cumulative_return(closes, 7)

        ema21 = _calc_ema(closes, min(5, len(closes)))
        if ema21 and ema21 > 0:
            coin_data["ema_deviation_pct"] = round(
                (closes[-1] - ema21) / ema21 * 100, 2
            )
        else:
            coin_data["ema_deviation_pct"] = 0

        # Volume trend: is volume increasing while price stable?
        if len(volumes) >= 3:
            vol_recent = sum(volumes[-2:]) / 2
            vol_older = sum(volumes[:-2]) / max(len(volumes) - 2, 1)
            coin_data["volume_trend"] = round(
                (vol_recent / vol_older) if vol_older > 0 else 1, 2
            )
        else:
            coin_data["volume_trend"] = 1.0
    else:
        coin_data.update({
            "rsi": None, "bb_width": None, "volume_ratio": None,
            "consecutive_up_days": 0, "cumulative_return_7d": 0,
            "ema_deviation_pct": 0, "volume_trend": 1.0,
        })

    return coin_data


def _score_pre_pump(c: dict) -> float:
    """Score 0-100 for pre-pump (accumulation) potential.

    High score = volume surge + OI growth + low price volatility (BB squeeze).
    """
    score = 0.0

    # 1. Volume surge (30% weight) — volume increasing vs historical
    vol_ratio = c.get("volume_ratio") or 1.0
    if vol_ratio > 3.0:
        score += 30
    elif vol_ratio > 2.0:
        score += 22
    elif vol_ratio > 1.5:
        score += 15
    elif vol_ratio > 1.2:
        score += 8

    # 2. OI growth signal (25% weight) — high OI relative to volume = positions building
    oi = c.get("open_interest", 0)
    vol = c.get("volume_24h", 1)
    if oi > 0 and vol > 0:
        oi_vol_ratio = oi / vol
        if oi_vol_ratio > 0.5:
            score += 25
        elif oi_vol_ratio > 0.3:
            score += 18
        elif oi_vol_ratio > 0.15:
            score += 10

    # 3. BB squeeze / low volatility (20% weight)
    bb = c.get("bb_width")
    if bb is not None:
        if bb < 1.0:
            score += 20  # very tight
        elif bb < 2.0:
            score += 14
        elif bb < 3.0:
            score += 8

    # 4. Funding rate shift (15% weight) — slightly positive = longs building
    fr = c.get("funding_rate")
    if fr is not None:
        if 0.0001 < fr < 0.0005:
            score += 15  # mild positive = accumulation
        elif 0 < fr <= 0.0001:
            score += 10
        elif -0.0001 < fr <= 0:
            score += 5  # neutral

    # 5. Price near breakout (10% weight) — small positive change, not yet pumped
    change = abs(c.get("change_pct_24h", 0))
    if 1.0 < change < 5.0:
        score += 10  # starting to move
    elif 0.5 < change <= 1.0:
        score += 6

    # Penalty: if already pumped hard, reduce score
    cum_ret = c.get("cumulative_return_7d", 0)
    if cum_ret > 20:
        score *= 0.5  # already pumped, not pre-pump
    elif cum_ret > 10:
        score *= 0.7

    return min(round(score, 1), 100)


def _score_dump_risk(c: dict) -> float:
    """Score 0-100 for dump risk (post-pump exhaustion).

    High score = extreme funding + overbought RSI + overextended price.
    """
    score = 0.0

    # 1. Extreme funding rate (25% weight)
    fr = c.get("funding_rate")
    if fr is not None:
        if fr > 0.001:
            score += 25  # extremely high
        elif fr > 0.0005:
            score += 18
        elif fr > 0.0003:
            score += 12
        elif fr > 0.0001:
            score += 6

    # 2. Price-volume divergence (20% weight) — price up but volume dropping
    vol_ratio = c.get("volume_ratio") or 1.0
    change = c.get("change_pct_24h", 0)
    if change > 5 and vol_ratio < 0.8:
        score += 20  # price pumping, volume dying
    elif change > 3 and vol_ratio < 0.9:
        score += 12

    # 3. OI at extreme (15% weight) — very high OI = crowded trade
    oi = c.get("open_interest", 0)
    vol = c.get("volume_24h", 1)
    if oi > 0 and vol > 0:
        oi_vol = oi / vol
        if oi_vol > 1.0:
            score += 15  # extremely crowded
        elif oi_vol > 0.6:
            score += 10

    # 4. RSI overbought (15% weight)
    rsi = c.get("rsi")
    if rsi is not None:
        if rsi > 85:
            score += 15
        elif rsi > 75:
            score += 10
        elif rsi > 70:
            score += 5

    # 5. Overextension from EMA (15% weight)
    dev = c.get("ema_deviation_pct", 0)
    if dev > 20:
        score += 15
    elif dev > 12:
        score += 10
    elif dev > 8:
        score += 6

    # 6. Pump magnitude (10% weight)
    cum_ret = c.get("cumulative_return_7d", 0)
    up_days = c.get("consecutive_up_days", 0)
    if cum_ret > 30 and up_days >= 4:
        score += 10
    elif cum_ret > 20 and up_days >= 3:
        score += 7
    elif cum_ret > 10:
        score += 4

    return min(round(score, 1), 100)


async def scan_all_coins() -> dict:
    """Main scanner: fetch all OKX USDT perps and score them."""
    global _scanner_cache

    # Check cache
    if (_scanner_cache["result"] and _scanner_cache["updated_at"]
            and (datetime.now(timezone.utc) - _scanner_cache["updated_at"]).seconds < CACHE_TTL_SECONDS):
        return _scanner_cache["result"]

    print("🔍 Pump & Dump Scanner: scanning all OKX USDT perpetuals...")

    # Step 1: Fetch all tickers and OI in parallel
    tickers, oi_map = await asyncio.gather(
        _fetch_all_swap_tickers(),
        _fetch_all_open_interest(),
    )

    if not tickers:
        print("  ⚠ No tickers received from OKX")
        return {"pre_pump": [], "dump_risk": [], "total_scanned": 0, "timestamp": datetime.now(timezone.utc).isoformat()}

    # Step 2: Basic filtering — USDT pairs with minimum volume
    candidates = []
    for t in tickers:
        c = await _analyze_coin(t, oi_map)
        if c:
            candidates.append(c)

    print(f"  ✓ {len(candidates)} USDT pairs passed volume filter (from {len(tickers)} total)")

    # Step 3: Sort by absolute change + volume to find interesting coins, take top 60
    candidates.sort(key=lambda x: x["volume_24h"], reverse=True)
    top_candidates = candidates[:80]

    # Step 4: Enrich with klines + funding (batch with concurrency limit)
    semaphore = asyncio.Semaphore(10)  # max 10 concurrent OKX requests

    async def _enrich_limited(c):
        async with semaphore:
            return await _enrich_with_klines(c)

    enriched = await asyncio.gather(*[_enrich_limited(c) for c in top_candidates])

    # Step 5: Score all
    for c in enriched:
        c["pre_pump_score"] = _score_pre_pump(c)
        c["dump_risk_score"] = _score_dump_risk(c)

    # Step 6: Sort and return top 10 for each
    pre_pump = sorted(enriched, key=lambda x: x["pre_pump_score"], reverse=True)[:10]
    dump_risk = sorted(enriched, key=lambda x: x["dump_risk_score"], reverse=True)[:10]

    # Format output
    def _fmt(c: dict, score_key: str) -> dict:
        return {
            "coin": c["coin"],
            "inst_id": c["inst_id"],
            "price": c["price"],
            "change_pct_24h": c["change_pct_24h"],
            "volume_24h": c["volume_24h"],
            "open_interest": c["open_interest"],
            "funding_rate": c.get("funding_rate"),
            "rsi": c.get("rsi"),
            "bb_width": c.get("bb_width"),
            "volume_ratio": c.get("volume_ratio"),
            "cumulative_return_7d": c.get("cumulative_return_7d", 0),
            "ema_deviation_pct": c.get("ema_deviation_pct", 0),
            "consecutive_up_days": c.get("consecutive_up_days", 0),
            "score": c[score_key],
        }

    result = {
        "pre_pump": [_fmt(c, "pre_pump_score") for c in pre_pump],
        "dump_risk": [_fmt(c, "dump_risk_score") for c in dump_risk],
        "total_scanned": len(candidates),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Cache
    _scanner_cache["result"] = result
    _scanner_cache["updated_at"] = datetime.now(timezone.utc)

    pp_top = pre_pump[0]["coin"] if pre_pump else "N/A"
    dr_top = dump_risk[0]["coin"] if dump_risk else "N/A"
    print(f"  ✓ Scan complete: {len(candidates)} coins | Pre-Pump #1: {pp_top} | Dump-Risk #1: {dr_top}")

    return result

