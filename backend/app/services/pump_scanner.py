"""Pump & Dump Scanner — scans ALL OKX USDT perpetual contracts.

Identifies:
  🟢 Pre-Pump: coins in accumulation phase (volume surge + low volatility + OI growth)
  🔴 Dump-Risk: coins at risk of crash (extreme funding + overbought + overextended)
"""

import asyncio
import json

import math
import sqlite3
import os
from datetime import datetime, timezone, timedelta
from app.services.market_data import _okx_get, _OKX_ENDPOINTS
from app.core.config import settings

# ── Cache ──
_scanner_cache: dict = {"result": None, "updated_at": None}
CACHE_TTL_SECONDS = 90  # 1.5 minutes (scanner runs every 2 min)

# ── Database for postmortem ──
_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "reports.db")


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


async def _fetch_klines(inst_id: str) -> list[list] | None:
    """Fetch 4H klines (42 candles ≈ 7 days) for richer technical data."""
    body = await _okx_get("/api/v5/market/candles", {
        "instId": inst_id, "bar": "4H", "limit": "42"
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


def _calc_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    """Calculate Average True Range."""
    if len(closes) < 2 or len(highs) < 2:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    p = min(period, len(trs))
    if p == 0:
        return None
    return sum(trs[-p:]) / p


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
    """Fetch 4H klines and funding rate, compute advanced indicators."""
    inst_id = coin_data["inst_id"]

    # Fetch klines and funding in parallel
    klines_task = _fetch_klines(inst_id)
    funding_task = _fetch_funding_rate(inst_id)
    klines, funding = await asyncio.gather(klines_task, funding_task)

    coin_data["funding_rate"] = funding

    if klines and len(klines) >= 6:
        # OKX kline: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        confirmed = [k for k in klines if str(k[8]) == "1"] if len(klines[0]) > 8 else klines[:-1]
        if len(confirmed) < 4:
            confirmed = klines[:-1]

        closes = [float(k[4]) for k in klines]
        volumes_confirmed = [float(k[7]) for k in confirmed]  # USDT volume

        # RSI with proper 14-period on 4H data (enough data points now)
        coin_data["rsi"] = _calc_rsi(closes, 14)
        coin_data["bb_width"] = _calc_bb_width(closes, 20)
        coin_data["volume_ratio"] = _calc_volume_ratio(volumes_confirmed)

        # Convert 4H bars to daily closes for consecutive_up_days / cumulative_return
        # Group 4H bars into days (6 bars per day)
        daily_closes = []
        for i in range(0, len(closes) - 5, 6):
            daily_closes.append(closes[min(i + 5, len(closes) - 1)])
        if len(daily_closes) < 2:
            daily_closes = closes[::6]  # fallback
        coin_data["consecutive_up_days"] = _calc_consecutive_up_days(daily_closes)
        coin_data["cumulative_return_7d"] = _calc_cumulative_return(closes, len(closes))

        # EMA deviation — use 21-period EMA on 4H (meaningful with 42 bars)
        ema21 = _calc_ema(closes, 21)
        if ema21 and ema21 > 0:
            coin_data["ema_deviation_pct"] = round(
                (closes[-1] - ema21) / ema21 * 100, 2
            )
        else:
            coin_data["ema_deviation_pct"] = 0

        # Volume trend: recent 6 bars (24h) vs prior average
        if len(volumes_confirmed) >= 12:
            vol_recent = sum(volumes_confirmed[-6:]) / 6
            vol_older = sum(volumes_confirmed[:-6]) / max(len(volumes_confirmed) - 6, 1)
            coin_data["volume_trend"] = round(
                (vol_recent / vol_older) if vol_older > 0 else 1, 2
            )
        else:
            coin_data["volume_trend"] = 1.0

        # OI in USD (fix unit mismatch: oi is in coins, convert to USD)
        oi_coins = coin_data.get("open_interest", 0)
        price = coin_data.get("price", 0)
        coin_data["oi_usd"] = oi_coins * price if oi_coins and price else 0

        # ATR for entry/SL/TP calculation
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        atr = _calc_atr(highs, lows, closes, 14)
        coin_data["atr"] = atr

        # Recent swing low/high (last 12 bars = 2 days of 4H)
        recent_lows = lows[-12:] if len(lows) >= 12 else lows
        recent_highs = highs[-12:] if len(highs) >= 12 else highs
        coin_data["recent_swing_low"] = min(recent_lows) if recent_lows else price
        coin_data["recent_swing_high"] = max(recent_highs) if recent_highs else price

        # EMA21 value for reference
        coin_data["ema21"] = ema21
    else:
        coin_data.update({
            "rsi": None, "bb_width": None, "volume_ratio": None,
            "consecutive_up_days": 0, "cumulative_return_7d": 0,
            "ema_deviation_pct": 0, "volume_trend": 1.0, "oi_usd": 0,
            "atr": None, "recent_swing_low": None, "recent_swing_high": None,
            "ema21": None,
        })

    return coin_data


def _score_pre_pump(c: dict) -> float:
    """Score 0-100 for pre-pump (accumulation) potential.

    High score = volume surge + OI/volume ratio (USD) + BB squeeze + funding signal.
    """
    score = 0.0

    # 1. Volume surge (25% weight) — volume increasing vs historical
    vol_ratio = c.get("volume_ratio") or 1.0
    if vol_ratio > 3.0:
        score += 25
    elif vol_ratio > 2.0:
        score += 18
    elif vol_ratio > 1.5:
        score += 12
    elif vol_ratio > 1.2:
        score += 6

    # 2. OI/Volume ratio in USD (20% weight) — positions building relative to trading
    oi_usd = c.get("oi_usd", 0)
    vol = c.get("volume_24h", 1)
    if oi_usd > 0 and vol > 0:
        oi_vol_ratio = oi_usd / vol
        if oi_vol_ratio > 0.8:
            score += 20   # very high OI relative to volume = heavy positioning
        elif oi_vol_ratio > 0.4:
            score += 14
        elif oi_vol_ratio > 0.2:
            score += 8
        elif oi_vol_ratio > 0.1:
            score += 4

    # 3. BB squeeze / low volatility (20% weight) — 20-period on 4H data
    bb = c.get("bb_width")
    if bb is not None:
        if bb < 1.5:
            score += 20  # very tight squeeze
        elif bb < 3.0:
            score += 14
        elif bb < 5.0:
            score += 8

    # 4. Funding rate signal (20% weight)
    fr = c.get("funding_rate")
    if fr is not None:
        # Negative funding = shorts paying → short squeeze potential (strong pre-pump)
        if fr < -0.0005:
            score += 20  # heavily negative = high squeeze potential
        elif fr < -0.0002:
            score += 15
        elif fr < 0:
            score += 10
        # Mildly positive = early longs accumulating
        elif 0 < fr < 0.0003:
            score += 8
        # High positive = already crowded, less pre-pump potential
        elif fr >= 0.0005:
            score += 0

    # 5. Volume trend acceleration (15% weight)
    vol_trend = c.get("volume_trend", 1.0)
    if vol_trend > 2.0:
        score += 15
    elif vol_trend > 1.5:
        score += 10
    elif vol_trend > 1.2:
        score += 6

    # Penalty: if already pumped hard, reduce score
    cum_ret = c.get("cumulative_return_7d", 0)
    if cum_ret > 20:
        score *= 0.4  # already pumped, not pre-pump
    elif cum_ret > 10:
        score *= 0.65

    return min(round(score, 1), 100)


def _score_dump_risk(c: dict) -> float:
    """Score 0-100 for dump risk (post-pump exhaustion).

    High score = extreme funding + overbought RSI + overextended price.
    PREREQUISITE: coin must have pumped significantly to qualify.
    """
    # Gate: must have pumped at least 8% in 7 days OR 5% in 24h to be dump-risk
    cum_ret = c.get("cumulative_return_7d", 0)
    change_24h = c.get("change_pct_24h", 0)
    if cum_ret < 8 and change_24h < 5:
        return 0.0  # hasn't pumped enough, not a dump candidate

    score = 0.0

    # 1. Pump magnitude — this is now the primary signal (30% weight)
    up_days = c.get("consecutive_up_days", 0)
    if cum_ret > 50:
        score += 30
    elif cum_ret > 30 and up_days >= 3:
        score += 25
    elif cum_ret > 20 and up_days >= 2:
        score += 18
    elif cum_ret > 10:
        score += 12
    elif cum_ret > 8:
        score += 8

    # 2. Extreme funding rate (20% weight)
    fr = c.get("funding_rate")
    if fr is not None:
        if fr > 0.001:
            score += 20  # extremely high
        elif fr > 0.0005:
            score += 15
        elif fr > 0.0003:
            score += 10
        elif fr > 0.0001:
            score += 5

    # 3. RSI overbought (15% weight)
    rsi = c.get("rsi")
    if rsi is not None:
        if rsi > 85:
            score += 15
        elif rsi > 75:
            score += 10
        elif rsi > 70:
            score += 5

    # 4. Overextension from EMA (15% weight)
    dev = c.get("ema_deviation_pct", 0)
    if dev > 20:
        score += 15
    elif dev > 12:
        score += 10
    elif dev > 8:
        score += 6

    # 5. Price-volume divergence (10% weight) — price up but volume dropping
    vol_ratio = c.get("volume_ratio") or 1.0
    if change_24h > 5 and vol_ratio < 0.8:
        score += 10  # price pumping, volume dying
    elif change_24h > 3 and vol_ratio < 0.9:
        score += 6

    # 6. OI at extreme (10% weight) — very high OI/Volume ratio (both in USD)
    oi_usd = c.get("oi_usd", 0)
    vol = c.get("volume_24h", 1)
    if oi_usd > 0 and vol > 0:
        oi_vol = oi_usd / vol
        if oi_vol > 1.0:
            score += 10  # extremely crowded
        elif oi_vol > 0.6:
            score += 6

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

    # Step 6: Filter by minimum score + quality, then sort
    MIN_PRE_PUMP_SCORE = 40    # only show confident picks
    MIN_DUMP_RISK_SCORE = 25   # dump-risk already has a pump gate, raise to reduce noise

    pre_pump_all = [
        c for c in enriched
        if c["pre_pump_score"] >= MIN_PRE_PUMP_SCORE
        and (c.get("volume_ratio") or 0) >= 0.3  # must have valid volume ratio
    ]
    dump_risk_all = [
        c for c in enriched
        if c["dump_risk_score"] >= MIN_DUMP_RISK_SCORE
    ]

    pre_pump = sorted(pre_pump_all, key=lambda x: x["pre_pump_score"], reverse=True)[:3]
    dump_risk = sorted(dump_risk_all, key=lambda x: x["dump_risk_score"], reverse=True)[:3]

    # Format output
    def _calc_trade_levels(c: dict, is_pump: bool) -> dict:
        """Calculate entry, stop-loss, and take-profit based on ATR and swing levels."""
        price = c["price"]
        atr = c.get("atr")
        swing_low = c.get("recent_swing_low", price)
        swing_high = c.get("recent_swing_high", price)
        ema21 = c.get("ema21")

        if is_pump:
            # Pre-pump: long setup
            # Entry: current price or slightly below (near EMA21 if available)
            entry = round(ema21, 8) if ema21 and ema21 < price else round(price, 8)
            # SL: 1.5x ATR below entry, or recent swing low (whichever is tighter)
            if atr:
                atr_sl = round(entry - 1.5 * atr, 8)
                sl = max(atr_sl, round(swing_low * 0.99, 8))  # don't go below swing low - 1%
            else:
                sl = round(swing_low * 0.99, 8)
            # TP: 2:1 and 3:1 RR
            risk = entry - sl if entry > sl else price * 0.02
            tp1 = round(entry + 2.0 * risk, 8)
            tp2 = round(entry + 3.0 * risk, 8)
        else:
            # Dump-risk: short setup
            # Entry: current price or slightly above (near recent high)
            entry = round(price, 8)
            # SL: 1.5x ATR above entry, or recent swing high + 1%
            if atr:
                atr_sl = round(entry + 1.5 * atr, 8)
                sl = min(atr_sl, round(swing_high * 1.01, 8))
            else:
                sl = round(swing_high * 1.01, 8)
            # TP: 2:1 and 3:1 RR
            risk = sl - entry if sl > entry else price * 0.02
            tp1 = round(entry - 2.0 * risk, 8)
            tp2 = round(entry - 3.0 * risk, 8)

        return {
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
        }

    def _fmt(c: dict, score_key: str, is_pump: bool) -> dict:
        levels = _calc_trade_levels(c, is_pump)
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
            "ai_analysis": None,
            **levels,
        }

    pre_pump_fmt = [_fmt(c, "pre_pump_score", is_pump=True) for c in pre_pump]
    dump_risk_fmt = [_fmt(c, "dump_risk_score", is_pump=False) for c in dump_risk]

    # Step 7: DeepSeek AI analysis for top candidates
    if pre_pump_fmt or dump_risk_fmt:
        try:
            from app.services.deepseek_analyzer import analyze_scanner_batch
            print("  🤖 DeepSeek: analyzing scanner candidates...")

            pp_coro = analyze_scanner_batch(pre_pump_fmt, "pre_pump") if pre_pump_fmt else asyncio.sleep(0)
            dr_coro = analyze_scanner_batch(dump_risk_fmt, "dump_risk") if dump_risk_fmt else asyncio.sleep(0)
            pp_ai, dr_ai = await asyncio.gather(pp_coro, dr_coro)

            if isinstance(pp_ai, list):
                for i, ai in enumerate(pp_ai):
                    if ai and i < len(pre_pump_fmt):
                        pre_pump_fmt[i]["ai_analysis"] = ai

            if isinstance(dr_ai, list):
                for i, ai in enumerate(dr_ai):
                    if ai and i < len(dump_risk_fmt):
                        dump_risk_fmt[i]["ai_analysis"] = ai

            print("  ✓ DeepSeek analysis complete")
        except Exception as ds_err:
            print(f"  ⚠ DeepSeek scanner analysis failed: {ds_err}")

    now = datetime.now(timezone.utc)
    result = {
        "pre_pump": pre_pump_fmt,
        "dump_risk": dump_risk_fmt,
        "total_scanned": len(candidates),
        "timestamp": now.isoformat(),
    }

    # Save snapshot for postmortem
    _save_scan_snapshot(pre_pump_fmt, dump_risk_fmt, now)

    # Cache
    _scanner_cache["result"] = result
    _scanner_cache["updated_at"] = now

    pp_top = pre_pump[0]["coin"] if pre_pump else "N/A"
    dr_top = dump_risk[0]["coin"] if dump_risk else "N/A"
    print(f"  ✓ Scan complete: {len(candidates)} coins | Pre-Pump #1: {pp_top} | Dump-Risk #1: {dr_top}")

    return result







# ═══════════════════════════════════════════
# Pump & Dump Postmortem System
# ═══════════════════════════════════════════

def _get_scanner_db():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_scanner_tables():
    """Create scanner postmortem tables."""
    conn = _get_scanner_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scanner_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coin TEXT NOT NULL,
            category TEXT NOT NULL,
            price_at_scan REAL NOT NULL,
            score REAL NOT NULL,
            change_pct_24h REAL,
            funding_rate REAL,
            rsi REAL,
            cumulative_return_7d REAL,
            scanned_at TEXT NOT NULL,
            price_after_24h REAL,
            price_after_48h REAL,
            change_after_24h REAL,
            change_after_48h REAL,
            result TEXT DEFAULT 'PENDING',
            evaluated_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ss_coin ON scanner_snapshots(coin, scanned_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ss_pending ON scanner_snapshots(result, scanned_at)")
    conn.commit()
    conn.close()


def _save_scan_snapshot(pre_pump: list[dict], dump_risk: list[dict], timestamp: datetime):
    """Save top 5 from each category for later evaluation."""
    try:
        conn = _get_scanner_db()
        # Check if table exists
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scanner_snapshots'").fetchall()
        if not tables:
            conn.close()
            init_scanner_tables()
            conn = _get_scanner_db()

        # Only save top 5, deduplicate (don't save same coin within 1 hour)
        one_hour_ago = (timestamp - timedelta(hours=1)).isoformat()

        for c in pre_pump[:5]:
            existing = conn.execute(
                "SELECT id FROM scanner_snapshots WHERE coin=? AND category='pre_pump' AND scanned_at>?",
                (c["coin"], one_hour_ago)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO scanner_snapshots
                       (coin, category, price_at_scan, score, change_pct_24h, funding_rate, rsi, cumulative_return_7d, scanned_at)
                       VALUES (?, 'pre_pump', ?, ?, ?, ?, ?, ?, ?)""",
                    (c["coin"], c["price"], c["score"], c.get("change_pct_24h"),
                     c.get("funding_rate"), c.get("rsi"), c.get("cumulative_return_7d", 0),
                     timestamp.isoformat())
                )

        for c in dump_risk[:5]:
            existing = conn.execute(
                "SELECT id FROM scanner_snapshots WHERE coin=? AND category='dump_risk' AND scanned_at>?",
                (c["coin"], one_hour_ago)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO scanner_snapshots
                       (coin, category, price_at_scan, score, change_pct_24h, funding_rate, rsi, cumulative_return_7d, scanned_at)
                       VALUES (?, 'dump_risk', ?, ?, ?, ?, ?, ?, ?)""",
                    (c["coin"], c["price"], c["score"], c.get("change_pct_24h"),
                     c.get("funding_rate"), c.get("rsi"), c.get("cumulative_return_7d", 0),
                     timestamp.isoformat())
                )

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  ⚠ Failed to save scan snapshot: {e}")


async def evaluate_scanner_postmortems():
    """Evaluate pending scanner snapshots that are at least 24h old."""
    try:
        conn = _get_scanner_db()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scanner_snapshots'").fetchall()
        if not tables:
            conn.close()
            return []

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        pending = conn.execute(
            "SELECT * FROM scanner_snapshots WHERE result='PENDING' AND scanned_at < ? LIMIT 20",
            (cutoff,)
        ).fetchall()
        conn.close()

        if not pending:
            return []

        evaluated = []
        for row in pending:
            coin = row["coin"]
            category = row["category"]
            price_at_scan = row["price_at_scan"]
            inst_id = f"{coin}-USDT-SWAP"

            # Fetch current price
            try:
                body = await _okx_get("/api/v5/market/ticker", {"instId": inst_id})
                if body and body.get("data") and len(body["data"]) > 0:
                    current_price = float(body["data"][0].get("last", 0))
                else:
                    continue
            except Exception:
                continue

            if current_price == 0 or price_at_scan == 0:
                continue

            change_pct = round((current_price - price_at_scan) / price_at_scan * 100, 2)

            # Determine result
            if category == "pre_pump":
                # Pre-pump prediction: coin should go UP
                if change_pct >= 10:
                    result = "STRONG_WIN"
                elif change_pct >= 5:
                    result = "WIN"
                elif change_pct >= 2:
                    result = "PARTIAL_WIN"
                elif change_pct > -3:
                    result = "NEUTRAL"
                else:
                    result = "LOSS"
            else:
                # Dump-risk prediction: coin should go DOWN (or at least stop rising)
                if change_pct <= -10:
                    result = "STRONG_WIN"
                elif change_pct <= -5:
                    result = "WIN"
                elif change_pct <= -2:
                    result = "PARTIAL_WIN"
                elif change_pct < 3:
                    result = "NEUTRAL"
                else:
                    result = "LOSS"

            now = datetime.now(timezone.utc)
            conn2 = _get_scanner_db()
            conn2.execute(
                """UPDATE scanner_snapshots
                   SET price_after_24h=?, change_after_24h=?, result=?, evaluated_at=?
                   WHERE id=?""",
                (current_price, change_pct, result, now.isoformat(), row["id"])
            )
            conn2.commit()
            conn2.close()

            evaluated.append({
                "coin": coin,
                "category": category,
                "price_at_scan": price_at_scan,
                "price_after": current_price,
                "change_pct": change_pct,
                "score": row["score"],
                "result": result,
                "scanned_at": row["scanned_at"],
            })
            print(f"  📊 Scanner PM: {coin} ({category}) → {result} ({change_pct:+.2f}%)")

        return evaluated
    except Exception as e:
        print(f"  ⚠ Scanner postmortem evaluation failed: {e}")
        return []


def get_scanner_postmortems(limit: int = 30) -> dict:
    """Get scanner postmortem stats and recent results."""
    try:
        conn = _get_scanner_db()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scanner_snapshots'").fetchall()
        if not tables:
            conn.close()
            return {"records": [], "stats": _empty_stats()}

        # Recent evaluated records
        rows = conn.execute(
            "SELECT * FROM scanner_snapshots WHERE result != 'PENDING' ORDER BY evaluated_at DESC LIMIT ?",
            (limit,)
        ).fetchall()

        # Stats by category
        stats = {}
        for cat in ["pre_pump", "dump_risk"]:
            cat_rows = conn.execute(
                """SELECT result, COUNT(*) as cnt FROM scanner_snapshots
                   WHERE category=? AND result != 'PENDING'
                   GROUP BY result""",
                (cat,)
            ).fetchall()

            total = sum(r["cnt"] for r in cat_rows)
            wins = sum(r["cnt"] for r in cat_rows if r["result"] in ("WIN", "STRONG_WIN"))
            partial = sum(r["cnt"] for r in cat_rows if r["result"] == "PARTIAL_WIN")
            losses = sum(r["cnt"] for r in cat_rows if r["result"] == "LOSS")

            avg_change_row = conn.execute(
                "SELECT AVG(change_after_24h) as avg_chg FROM scanner_snapshots WHERE category=? AND result != 'PENDING'",
                (cat,)
            ).fetchone()
            avg_change = round(avg_change_row["avg_chg"], 2) if avg_change_row and avg_change_row["avg_chg"] is not None else 0

            stats[cat] = {
                "total": total,
                "wins": wins,
                "partial_wins": partial,
                "losses": losses,
                "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
                "avg_change_24h": avg_change,
            }

        conn.close()

        records = []
        for r in rows:
            records.append({
                "coin": r["coin"],
                "category": r["category"],
                "price_at_scan": r["price_at_scan"],
                "price_after_24h": r["price_after_24h"],
                "change_after_24h": r["change_after_24h"],
                "score": r["score"],
                "result": r["result"],
                "scanned_at": r["scanned_at"],
                "evaluated_at": r["evaluated_at"],
            })

        return {"records": records, "stats": stats}
    except Exception as e:
        print(f"  ⚠ Failed to get scanner postmortems: {e}")
        return {"records": [], "stats": _empty_stats()}


def _empty_stats() -> dict:
    return {
        "pre_pump": {"total": 0, "wins": 0, "partial_wins": 0, "losses": 0, "win_rate": 0, "avg_change_24h": 0},
        "dump_risk": {"total": 0, "wins": 0, "partial_wins": 0, "losses": 0, "win_rate": 0, "avg_change_24h": 0},
    }