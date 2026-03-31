"""BTC Price Spike Monitor + Gemini AI Attribution.

Polls BTC price at regular intervals, detects rapid price movements,
and triggers Gemini analysis to identify the likely cause (news, whale activity,
liquidation cascade, macro data release, etc).
"""

import asyncio
import time
from datetime import datetime, timezone
from collections import deque
from google import genai
from google.genai import types
from app.core.config import settings
from app.services.market_data import fetch_klines

# ── Configuration ──
POLL_INTERVAL_SECONDS = 30       # Check price every 30 seconds
PRICE_HISTORY_WINDOW = 60        # Keep last 60 data points (~30 min)
SPIKE_THRESHOLD_PCT = 1.0        # 1% move in 5 minutes triggers alert
SPIKE_WINDOW_POINTS = 10         # 10 points × 30s = 5 minutes
COOLDOWN_SECONDS = 300           # Don't re-alert within 5 min of last alert
MAX_ALERTS = 20                  # Keep last 20 alerts in memory

# ── In-memory state ──
_price_history: deque[dict] = deque(maxlen=PRICE_HISTORY_WINDOW)
_spike_alerts: list[dict] = []
_last_alert_time: float = 0
_monitor_running = False


async def _fetch_btc_price() -> float | None:
    """Get current BTC price from OKX 1m klines."""
    try:
        klines = await fetch_klines("BTCUSDT", interval="1m", limit=1)
        if klines and len(klines) > 0:
            return float(klines[-1][4])  # close price
    except Exception as e:
        print(f"  ⚠ Price spike monitor: fetch failed: {e}")
    return None


def _detect_spike() -> dict | None:
    """Check if price moved significantly in the last SPIKE_WINDOW_POINTS."""
    if len(_price_history) < SPIKE_WINDOW_POINTS:
        return None

    recent = list(_price_history)
    current = recent[-1]
    window_start = recent[-SPIKE_WINDOW_POINTS]

    price_now = current["price"]
    price_then = window_start["price"]

    if price_then == 0:
        return None

    change_pct = ((price_now - price_then) / price_then) * 100

    if abs(change_pct) >= SPIKE_THRESHOLD_PCT:
        return {
            "price_before": round(price_then, 2),
            "price_after": round(price_now, 2),
            "change_pct": round(change_pct, 2),
            "direction": "pump" if change_pct > 0 else "dump",
            "window_seconds": SPIKE_WINDOW_POINTS * POLL_INTERVAL_SECONDS,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }
    return None


async def _analyze_spike_cause(spike: dict) -> str:
    """Use Gemini with Google Search to identify what caused the price spike."""
    direction_cn = "急速拉升" if spike["direction"] == "pump" else "急速下跌"
    prompt = f"""你是一位资深加密货币市场分析师。BTC 价格刚刚在 {spike['window_seconds']} 秒内发生了 {direction_cn}：

- 变动前价格: ${spike['price_before']:,.2f}
- 变动后价格: ${spike['price_after']:,.2f}  
- 涨跌幅: {spike['change_pct']:+.2f}%
- 时间: {spike['detected_at']}

请利用 Google 搜索最新新闻，分析最可能导致这次价格剧烈波动的原因。

要求：
1. 搜索最近 1 小时内的加密货币新闻、宏观经济新闻
2. 判断是以下哪种因素（可多选）：
   - 📰 突发新闻/政策（具体什么新闻）
   - 🐋 鲸鱼大额交易/抛售
   - 💥 大规模清算连锁反应
   - 📊 宏观经济数据发布（如 CPI、非农等）
   - 🏛️ 美联储/央行相关
   - 📈 技术面突破关键位
   - 🔄 其他因素

请用以下 JSON 格式回复（纯 JSON，无 markdown）：
{{
  "primary_cause": "最主要的原因（一句话）",
  "category": "news|whale|liquidation|macro|fed|technical|other",
  "details": "详细分析（2-3 句话，说明具体是什么事件/因素导致的）",
  "confidence": "high|medium|low",
  "sources": ["来源1", "来源2"]
}}"""

    try:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        google_search_tool = types.Tool(google_search=types.GoogleSearch())

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[google_search_tool],
                temperature=0.3,
                max_output_tokens=2048,
            ),
        )
        raw = response.text or ""
        # Strip markdown code fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
        if raw.rstrip().endswith("```"):
            raw = raw[: raw.rfind("```")]
        if raw.lstrip().startswith("json"):
            raw = raw.lstrip()[4:]

        import json
        raw = raw.strip()
        # Try to extract JSON object even if response is truncated
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Attempt to fix truncated JSON: close unclosed strings and arrays
            fixed = raw
            # Close unclosed string
            if fixed.count('"') % 2 != 0:
                fixed += '"'
            # Close unclosed array
            open_brackets = fixed.count('[') - fixed.count(']')
            fixed += ']' * open_brackets
            # Close unclosed object
            open_braces = fixed.count('{') - fixed.count('}')
            fixed += '}' * open_braces
            data = json.loads(fixed)

        return data
    except Exception as e:
        print(f"  ⚠ Gemini spike analysis failed: {e}")
        return {
            "primary_cause": "分析暂不可用",
            "category": "other",
            "details": f"Gemini 分析请求失败: {str(e)[:100]}",
            "confidence": "low",
            "sources": [],
        }


async def _monitor_loop():
    """Background loop: poll price, detect spikes, trigger analysis."""
    global _last_alert_time, _monitor_running
    _monitor_running = True
    print("  🔍 BTC Price Spike Monitor started")

    while _monitor_running:
        try:
            price = await _fetch_btc_price()
            if price is not None:
                _price_history.append({
                    "price": price,
                    "time": time.time(),
                })

                # Check for spike (respect cooldown)
                now = time.time()
                if now - _last_alert_time > COOLDOWN_SECONDS:
                    spike = _detect_spike()
                    if spike:
                        print(f"  ⚡ BTC SPIKE DETECTED: {spike['change_pct']:+.2f}% "
                              f"(${spike['price_before']:,.0f} → ${spike['price_after']:,.0f})")
                        _last_alert_time = now

                        # Analyze cause with Gemini
                        analysis = await _analyze_spike_cause(spike)
                        alert = {**spike, "analysis": analysis}
                        _spike_alerts.insert(0, alert)
                        if len(_spike_alerts) > MAX_ALERTS:
                            _spike_alerts.pop()
                        print(f"  📋 Cause: {analysis.get('primary_cause', 'N/A')}")
        except Exception as e:
            print(f"  ⚠ Price monitor error: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def start_monitor():
    """Start the background price monitor (call from app lifespan)."""
    asyncio.get_event_loop().create_task(_monitor_loop())


def stop_monitor():
    """Stop the background monitor."""
    global _monitor_running
    _monitor_running = False


def get_spike_alerts() -> list[dict]:
    """Return current spike alerts for API consumption."""
    return list(_spike_alerts)


def get_current_price() -> float | None:
    """Return latest tracked price."""
    if _price_history:
        return _price_history[-1]["price"]
    return None

