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

async def analyze_scanner_coin(coin: dict, category: str) -> dict | None:
    """Analyze a scanner candidate coin with DeepSeek.

    Args:
        coin: dict with price, change_pct_24h, volume_24h, rsi, funding_rate, etc.
        category: "pre_pump" or "dump_risk"
    Returns:
        dict with verdict, reasoning, key_levels, risk_warning
    """
    if not settings.DEEPSEEK_API_KEY:
        return None

    direction = "潜力拉升" if category == "pre_pump" else "暴跌预警"
    coin_name = coin.get("coin", "UNKNOWN")

    system_prompt = (
        "你是一位专业的加密货币合约交易分析师。你需要根据提供的实时数据，"
        "对候选代币进行深度分析，判断其短期走势并给出交易建议。"
        "必须严格按JSON格式返回，不要包含markdown代码块标记。"
    )

    user_prompt = (
        f"以下代币被扫描器标记为【{direction}】候选，请分析其短期(24-72h)走势:\n\n"
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
        f"扫描器评分: {coin.get('score', 0)}/100\n\n"
        f"请分析以下方面并返回JSON:\n"
        f"1. 该币的做市风格(是否经常被拉盘砸盘、波动特征)\n"
        f"2. 当前K线形态和趋势判断\n"
        f"3. 关键支撑位和阻力位\n"
        f"4. 具体交易建议(入场/观望/远离)\n\n"
        f'{{"verdict":"看涨/看跌/观望",'
        f'"confidence":75,'
        f'"reasoning":"详细分析理由(50-100字)",'
        f'"market_style":"做市风格描述(20-40字)",'
        f'"key_support":[价位1,价位2],'
        f'"key_resistance":[价位1,价位2],'
        f'"suggestion":"具体交易建议(30-60字)",'
        f'"risk_warning":"主要风险(20-40字)"}}'
    )

    try:
        raw = await _deepseek_chat(system_prompt, user_prompt, temperature=0.5, max_tokens=2048)
        result = _parse_json(raw)
        result["source"] = "deepseek"
        print(f"  🤖 DeepSeek分析 {coin_name}: {result.get('verdict', 'N/A')}")
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

