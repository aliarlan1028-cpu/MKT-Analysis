"""Pump & Dump Scanner — scans ALL OKX USDT perpetual contracts.

Identifies:
  🟢 Pre-Pump: coins in accumulation phase (volume surge + low volatility + OI growth)
  🔴 Dump-Risk: coins at risk of crash (extreme funding + overbought + overextended)
"""

import asyncio
import json
import httpx
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
        # OKX kline: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        # Last candle may be incomplete (confirm=0), exclude it for volume calc
        confirmed = [k for k in klines if str(k[8]) == "1"] if len(klines[0]) > 8 else klines[:-1]
        if len(confirmed) < 2:
            confirmed = klines[:-1]  # fallback: exclude last candle

        closes = [float(k[4]) for k in klines]  # use all closes for RSI/EMA (current price matters)
        volumes_confirmed = [float(k[7]) for k in confirmed]  # only confirmed volumes

        coin_data["rsi"] = _calc_rsi(closes, 6)
        coin_data["bb_width"] = _calc_bb_width(closes)
        coin_data["volume_ratio"] = _calc_volume_ratio(volumes_confirmed)
        coin_data["consecutive_up_days"] = _calc_consecutive_up_days(closes)
        coin_data["cumulative_return_7d"] = _calc_cumulative_return(closes, 7)

        ema21 = _calc_ema(closes, min(5, len(closes)))
        if ema21 and ema21 > 0:
            coin_data["ema_deviation_pct"] = round(
                (closes[-1] - ema21) / ema21 * 100, 2
            )
        else:
            coin_data["ema_deviation_pct"] = 0

        # Volume trend: is confirmed volume increasing?
        if len(volumes_confirmed) >= 3:
            vol_recent = sum(volumes_confirmed[-2:]) / 2
            vol_older = sum(volumes_confirmed[:-2]) / max(len(volumes_confirmed) - 2, 1)
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

    # 6. OI at extreme (10% weight) — very high OI = crowded trade
    oi = c.get("open_interest", 0)
    vol = c.get("volume_24h", 1)
    if oi > 0 and vol > 0:
        oi_vol = oi / vol
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
    MIN_PRE_PUMP_SCORE = 45    # only show confident picks
    MIN_DUMP_RISK_SCORE = 15   # dump-risk already has a pump gate

    pre_pump_all = [
        c for c in enriched
        if c["pre_pump_score"] >= MIN_PRE_PUMP_SCORE
        and (c.get("volume_ratio") or 0) >= 0.3  # must have valid volume ratio
    ]
    dump_risk_all = [
        c for c in enriched
        if c["dump_risk_score"] >= MIN_DUMP_RISK_SCORE
    ]

    pre_pump = sorted(pre_pump_all, key=lambda x: x["pre_pump_score"], reverse=True)[:10]
    dump_risk = sorted(dump_risk_all, key=lambda x: x["dump_risk_score"], reverse=True)[:10]

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
            "ai_analysis": None,  # will be filled by Claude
        }

    pre_pump_fmt = [_fmt(c, "pre_pump_score") for c in pre_pump]
    dump_risk_fmt = [_fmt(c, "dump_risk_score") for c in dump_risk]

    # Claude AI analysis for top 3 of each category
    if settings.CLAUDE_API_KEY:
        ai_results = await _claude_batch_analysis(pre_pump_fmt[:3], dump_risk_fmt[:3])
        for i, analysis in enumerate(ai_results.get("pre_pump", [])):
            if i < len(pre_pump_fmt):
                pre_pump_fmt[i]["ai_analysis"] = analysis
        for i, analysis in enumerate(ai_results.get("dump_risk", [])):
            if i < len(dump_risk_fmt):
                dump_risk_fmt[i]["ai_analysis"] = analysis

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
# Claude AI Analysis
# ═══════════════════════════════════════════

async def _claude_batch_analysis(pre_pump_top: list[dict], dump_risk_top: list[dict]) -> dict:
    """Call Claude API to generate analysis for top candidates."""
    if not settings.CLAUDE_API_KEY:
        return {"pre_pump": [], "dump_risk": []}

    def _coin_summary(c: dict) -> str:
        fr_str = f"{c['funding_rate']*100:.4f}%" if c.get('funding_rate') is not None else "N/A"
        return (
            f"{c['coin']}: 价格${c['price']}, 24h涨跌{c['change_pct_24h']:+.2f}%, "
            f"7日涨幅{c.get('cumulative_return_7d',0):.1f}%, 资金费率{fr_str}, "
            f"RSI={c.get('rsi','N/A')}, 量比{c.get('volume_ratio','N/A')}x, "
            f"EMA偏离{c.get('ema_deviation_pct',0):.1f}%, 连涨{c.get('consecutive_up_days',0)}天, "
            f"评分{c['score']}"
        )

    pre_pump_text = "\n".join([_coin_summary(c) for c in pre_pump_top]) if pre_pump_top else "无"
    dump_risk_text = "\n".join([_coin_summary(c) for c in dump_risk_top]) if dump_risk_top else "无"

    prompt = f"""你是一位专业的加密货币永续合约分析师。请分析以下OKX永续合约扫描结果。

## 🚀 潜力拉升候选（蓄势待发，尚未大涨）:
{pre_pump_text}

## 💣 暴跌预警候选（已大涨，可能即将回调）:
{dump_risk_text}

请为每个币种提供简短精准的分析（每个30-50字），包含：
1. 关键信号解读（为什么被选中）
2. 操作建议（适合做多/做空/观望）
3. 风险提醒

严格按以下JSON格式返回，不要添加任何其他文字：
{{
  "pre_pump": ["币种1分析", "币种2分析", "币种3分析"],
  "dump_risk": ["币种1分析", "币种2分析", "币种3分析"]
}}"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.CLAUDE_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data["content"][0]["text"]
                # Extract JSON from response
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    parsed = json.loads(text[start:end])
                    print(f"  🤖 Claude AI analysis complete for {len(pre_pump_top)}+{len(dump_risk_top)} coins")
                    return parsed
            else:
                print(f"  ⚠ Claude API error: {resp.status_code} — {resp.text[:200]}")
    except Exception as e:
        print(f"  ⚠ Claude AI analysis failed: {e}")

    return {"pre_pump": [], "dump_risk": []}


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