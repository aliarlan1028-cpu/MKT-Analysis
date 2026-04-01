"""DeepSeek AI analysis — fallback for Gemini + scanner coin analysis.

Uses OpenAI-compatible API at https://api.deepseek.com
"""

import json
import httpx
from datetime import datetime, timezone, timedelta
from app.core.config import settings
from app.models.schemas import (
    MarketData, TechnicalIndicators, FearGreedIndex,
    AnalysisReport, AnalysisSection, TradingSignal, CalendarEvent,
)
from app.services.technical import format_indicators_for_prompt
from app.services.market_data import _okx_get

_BEIJING_TZ = timezone(timedelta(hours=8))

SESSION_LABELS = {
    "morning": "早盘分析 06:00",
    "evening": "晚盘分析 20:00",
}


async def _deepseek_chat(system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 8192) -> str:
    """Call DeepSeek chat completions API."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _parse_json(text: str) -> dict:
    """Clean and parse JSON response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    if text.startswith("json"):
        text = text[4:]
    return json.loads(text.strip())


# ═══════════════════════════════════════════
# 1. Scanner coin analysis (for pump & dump candidates)
# ═══════════════════════════════════════════

async def _fetch_daily_klines(inst_id: str, limit: int = 90) -> list[dict]:
    """Fetch daily klines from OKX for historical analysis."""
    body = await _okx_get("/api/v5/market/candles", {
        "instId": inst_id, "bar": "1D", "limit": str(min(limit, 300))
    })
    if not body or not body.get("data"):
        return []
    # OKX: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm] DESC order
    rows = body["data"][::-1]  # reverse to ASC
    result = []
    for r in rows:
        ts = int(r[0]) / 1000
        dt = datetime.utcfromtimestamp(ts)
        o, h, l, c = float(r[1]), float(r[2]), float(r[3]), float(r[4])
        vol_usd = float(r[7]) if r[7] else 0
        result.append({
            "date": dt.strftime("%m-%d"),
            "open": o, "high": h, "low": l, "close": c,
            "vol_usd": vol_usd,
            "change_pct": round((c - o) / o * 100, 2) if o else 0,
            "amplitude_pct": round((h - l) / l * 100, 2) if l else 0,
        })
    return result


def _compute_historical_stats(klines: list[dict]) -> dict:
    """Compute historical volatility stats from daily klines."""
    if len(klines) < 5:
        return {}

    changes = [k["change_pct"] for k in klines]
    amplitudes = [k["amplitude_pct"] for k in klines]

    # Big moves (>8% daily change)
    big_pumps = [k for k in klines if k["change_pct"] >= 8]
    big_dumps = [k for k in klines if k["change_pct"] <= -8]

    # Pump-then-dump patterns: day with >10% pump followed by >5% dump within 3 days
    pump_dump_events = []
    for i, k in enumerate(klines):
        if k["change_pct"] >= 10:
            for j in range(i + 1, min(i + 4, len(klines))):
                if klines[j]["change_pct"] <= -5:
                    pump_dump_events.append({
                        "pump_date": k["date"],
                        "pump_pct": k["change_pct"],
                        "dump_date": klines[j]["date"],
                        "dump_pct": klines[j]["change_pct"],
                    })
                    break

    # Recent trend (last 7 days vs last 30 days)
    last_7 = klines[-7:] if len(klines) >= 7 else klines
    last_30 = klines[-30:] if len(klines) >= 30 else klines
    trend_7d = round(sum(k["change_pct"] for k in last_7), 2)
    trend_30d = round(sum(k["change_pct"] for k in last_30), 2)

    # Average daily volatility
    avg_amplitude = round(sum(amplitudes) / len(amplitudes), 2)
    max_amplitude = round(max(amplitudes), 2)

    # Price range (90d high/low)
    all_highs = [k["high"] for k in klines]
    all_lows = [k["low"] for k in klines]
    high_90d = max(all_highs)
    low_90d = min(all_lows)
    current = klines[-1]["close"]
    position_pct = round((current - low_90d) / (high_90d - low_90d) * 100, 2) if high_90d > low_90d else 50

    return {
        "total_days": len(klines),
        "avg_daily_amplitude": avg_amplitude,
        "max_daily_amplitude": max_amplitude,
        "big_pumps": [{"date": p["date"], "pct": p["change_pct"]} for p in big_pumps[-5:]],
        "big_dumps": [{"date": d["date"], "pct": d["change_pct"]} for d in big_dumps[-5:]],
        "pump_dump_events": pump_dump_events[-3:],
        "trend_7d_pct": trend_7d,
        "trend_30d_pct": trend_30d,
        "high_90d": high_90d,
        "low_90d": low_90d,
        "position_in_range_pct": position_pct,
        "recent_10d_klines": [
            f"{k['date']}: {k['change_pct']:+.1f}% (振幅{k['amplitude_pct']:.1f}%)"
            for k in klines[-10:]
        ],
    }


async def analyze_scanner_coin(coin: dict, category: str) -> dict | None:
    """Analyze a scanner candidate coin with DeepSeek + real historical data."""
    if not settings.DEEPSEEK_API_KEY:
        return None

    direction = "潜力拉升" if category == "pre_pump" else "暴跌预警"
    coin_name = coin.get("coin", "UNKNOWN")
    inst_id = f"{coin_name}-USDT-SWAP"

    # Fetch 90-day daily klines for historical analysis
    daily_klines = await _fetch_daily_klines(inst_id, 90)
    hist = _compute_historical_stats(daily_klines) if daily_klines else {}

    system_prompt = (
        "你是一位专业的加密货币合约交易分析师，擅长分析做市商行为和历史K线模式。"
        "你会收到代币的实时数据和真实的历史K线统计数据（包括历史大涨大跌事件、拉盘砸盘模式等），"
        "请基于这些真实数据进行深度分析。"
        "必须严格按JSON格式返回，不要包含markdown代码块标记。"
    )

    # Build historical context
    hist_text = ""
    if hist:
        hist_text += f"\n=== {coin_name} 历史K线分析（近{hist.get('total_days', 0)}天日线）===\n"
        hist_text += f"90日最高: ${hist.get('high_90d', 0):,.4f}\n"
        hist_text += f"90日最低: ${hist.get('low_90d', 0):,.4f}\n"
        hist_text += f"当前价位在90日区间中的位置: {hist.get('position_in_range_pct', 0)}%\n"
        hist_text += f"日均振幅: {hist.get('avg_daily_amplitude', 0)}%\n"
        hist_text += f"最大单日振幅: {hist.get('max_daily_amplitude', 0)}%\n"
        hist_text += f"近7日累计涨跌: {hist.get('trend_7d_pct', 0):+.1f}%\n"
        hist_text += f"近30日累计涨跌: {hist.get('trend_30d_pct', 0):+.1f}%\n"

        pumps = hist.get("big_pumps", [])
        if pumps:
            hist_text += f"\n--- 历史大涨事件（日涨>8%）---\n"
            for p in pumps:
                hist_text += f"  {p['date']}: +{p['pct']}%\n"

        dumps = hist.get("big_dumps", [])
        if dumps:
            hist_text += f"\n--- 历史大跌事件（日跌>8%）---\n"
            for d in dumps:
                hist_text += f"  {d['date']}: {d['pct']}%\n"

        pd_events = hist.get("pump_dump_events", [])
        if pd_events:
            hist_text += f"\n--- 拉盘后砸盘模式（涨>10%后3日内跌>5%）---\n"
            for e in pd_events:
                hist_text += f"  {e['pump_date']} 拉盘+{e['pump_pct']}% → {e['dump_date']} 砸盘{e['dump_pct']}%\n"

        recent = hist.get("recent_10d_klines", [])
        if recent:
            hist_text += f"\n--- 最近10天日线 ---\n"
            for line in recent:
                hist_text += f"  {line}\n"

    user_prompt = (
        f"以下代币被扫描器标记为【{direction}】候选，请结合实时数据和历史K线进行深度分析:\n\n"
        f"=== {coin_name}-USDT 实时数据 ===\n"
        f"当前价格: ${coin.get('price', 0)}\n"
        f"24h涨跌: {coin.get('change_pct_24h', 0)}%\n"
        f"24h成交量: ${coin.get('volume_24h', 0):,.0f}\n"
        f"持仓量: {coin.get('open_interest', 0)}\n"
        f"资金费率: {coin.get('funding_rate', 'N/A')}\n"
        f"RSI(14): {coin.get('rsi', 'N/A')}\n"
        f"BB宽度: {coin.get('bb_width', 'N/A')}\n"
        f"量比: {coin.get('volume_ratio', 'N/A')}\n"
        f"7日累计涨幅: {coin.get('cumulative_return_7d', 0)}%\n"
        f"EMA偏离: {coin.get('ema_deviation_pct', 0)}%\n"
        f"连涨天数: {coin.get('consecutive_up_days', 0)}\n"
        f"扫描器评分: {coin.get('score', 0)}/100\n"
        f"{hist_text}\n"
        f"请深度分析以下方面并返回JSON:\n"
        f"1. 做市风格: 基于历史K线数据，该币是否有明显的拉盘-砸盘模式？大涨后通常是什么走势？波动是否规律？\n"
        f"2. 当前位置判断: 当前价格在历史区间中的位置，是接近底部还是顶部？\n"
        f"3. 历史模式对比: 当前走势是否与历史上某次大涨/大跌前的形态相似？\n"
        f"4. 关键支撑位和阻力位（基于历史K线的真实高低点）\n"
        f"5. 具体交易建议\n\n"
        f'{{"verdict":"看涨/看跌/观望",'
        f'"confidence":75,'
        f'"reasoning":"基于历史数据的详细分析理由(80-150字)",'
        f'"market_style":"做市风格总结：拉盘砸盘规律、波动特征(40-80字)",'
        f'"historical_pattern":"当前走势与历史模式的对比分析(40-80字)",'
        f'"key_support":[价位1,价位2],'
        f'"key_resistance":[价位1,价位2],'
        f'"suggestion":"具体交易建议(30-60字)",'
        f'"risk_warning":"主要风险(20-40字)"}}'
    )

    try:
        raw = await _deepseek_chat(system_prompt, user_prompt, temperature=0.5, max_tokens=2048)
        result = _parse_json(raw)
        result["source"] = "deepseek"
        print(f"  🤖 DeepSeek分析 {coin_name}: {result.get('verdict', 'N/A')} (历史{hist.get('total_days', 0)}天)")
        return result
    except Exception as e:
        print(f"  ⚠ DeepSeek分析{coin_name}失败: {e}")
        return None


async def analyze_scanner_batch(candidates: list[dict], category: str) -> list[dict]:
    """Analyze a batch of scanner candidates (max 3 at a time)."""
    import asyncio
    tasks = [analyze_scanner_coin(c, category) for c in candidates[:3]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for r in results:
        if isinstance(r, Exception) or r is None:
            out.append(None)
        else:
            out.append(r)
    return out


# ═══════════════════════════════════════════
# 2. Report generation fallback (same format as Gemini)
# ═══════════════════════════════════════════

def _get_session_name() -> str:
    hour = datetime.now(_BEIJING_TZ).hour
    if hour < 13:
        return "morning"
    return "evening"


async def analyze_symbol_deepseek(
    market: MarketData,
    indicators: TechnicalIndicators,
    fear_greed: FearGreedIndex,
) -> AnalysisReport:
    """Generate analysis report using DeepSeek (Gemini fallback)."""
    session = _get_session_name()
    label = SESSION_LABELS.get(session, session)
    ind_text = format_indicators_for_prompt(indicators)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    system_prompt = (
        "你是一位顶级加密货币合约交易分析师。请根据提供的实时数据进行全面的合约交易分析。"
        "必须严格按指定的JSON格式返回，不要包含markdown代码块标记。中文回复但JSON key保持英文。"
    )

    json_schema = (
        '{"signal":{"direction":"LONG/SHORT/NEUTRAL","confidence":72,'
        '"entry_zone":[84200,84500],"stop_loss":83400,'
        '"take_profit":[85800,87200],"leverage_suggestion":"3x-5x",'
        '"risk_reward_ratio":2.5},'
        '"technical":{"title":"技术面分析","content":"综合判断","bullets":["要点1","要点2","要点3"],"key_support":[83000,82500],"key_resistance":[86000,87500]},'
        '"fundamental":{"title":"基本面分析","content":"综合判断","bullets":["要点1","要点2"]},'
        '"sentiment":{"title":"情绪面分析","content":"综合判断","bullets":["要点1","要点2"]},'
        '"macro":{"title":"宏观面分析","content":"综合判断","bullets":["要点1","要点2"]},'
        '"risk_warning":{"title":"风险提示","content":"风险总结","bullets":["风险1","风险2"]},'
        '"calendar_events":[]}'
    )

    user_prompt = (
        f"当前时间: {now_str} (北京时间)\n分析时段: {label}\n\n"
        f"=== {market.name} ({market.symbol}) 实时数据 ===\n"
        f"当前价格: ${market.price:,.2f}\n"
        f"24h涨跌: {market.price_change_pct_24h}%\n"
        f"24h最高/最低: ${market.high_24h:,.2f} / ${market.low_24h:,.2f}\n"
        f"24h成交量: ${market.volume_24h:,.0f}\n"
        f"资金费率: {market.funding_rate}\n"
        f"多空比(大户): {market.long_short_ratio}\n"
        f"未平仓量: {market.open_interest} ({market.open_interest_change_pct}% 变化)\n\n"
        f"=== 技术指标 ===\n{ind_text}\n\n"
        f"=== 市场情绪 ===\n"
        f"恐慌贪婪指数: {fear_greed.value} ({fear_greed.label})\n\n"
        f"请严格按以下JSON格式返回:\n{json_schema}\n\n"
        "注意:\n"
        "- 所有价格用美元保留小数点后2位\n"
        "- confidence反映你对该方向判断的把握程度(0-100)\n"
        "- technical部分必须包含key_support和key_resistance字段，各给出2个关键价位(数字数组)\n"
        "- calendar_events留空数组(DeepSeek无搜索能力)"
    )

    raw = await _deepseek_chat(system_prompt, user_prompt, temperature=0.7, max_tokens=8192)
    print(f"  📝 DeepSeek raw response length: {len(raw)} chars")

    data = _parse_json(raw)

    report_id = f"{market.symbol}_{session}_{datetime.now().strftime('%Y%m%d%H%M')}_ds"

    return AnalysisReport(
        id=report_id,
        symbol=market.symbol,
        name=market.name,
        session=session,
        timestamp=datetime.now(timezone.utc),
        price_at_analysis=market.price,
        ai_provider="deepseek",
        signal=TradingSignal(**data["signal"]),
        technical=AnalysisSection(**data["technical"]),
        fundamental=AnalysisSection(**data["fundamental"]),
        sentiment=AnalysisSection(**data["sentiment"]),
        macro=AnalysisSection(**data["macro"]),
        risk_warning=AnalysisSection(**data["risk_warning"]),
        calendar_events=[CalendarEvent(**e) for e in data.get("calendar_events", [])],
        raw_market_data=market,
        raw_indicators=indicators,
    )

