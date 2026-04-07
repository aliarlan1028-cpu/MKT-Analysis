"""Gemini AI analysis with Google Search Grounding."""

import json
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
from app.core.config import settings
from app.models.schemas import (
    MarketData, TechnicalIndicators, FearGreedIndex,
    AnalysisReport, AnalysisSection, TradingSignal, CalendarEvent,
)
from app.services.technical import format_indicators_for_prompt, format_multi_tf_for_prompt, format_key_levels_for_prompt

SESSION_LABELS = {
    "morning": "早盘分析 06:00",
    "evening": "晚盘分析 20:00",
}

_BEIJING_TZ = timezone(timedelta(hours=8))


def _get_session_name() -> str:
    """Determine session based on Beijing time (UTC+8)."""
    hour = datetime.now(_BEIJING_TZ).hour
    if hour < 13:
        return "morning"
    return "evening"


def _build_prompt(market: MarketData, indicators: TechnicalIndicators,
                  fear_greed: FearGreedIndex, session: str,
                  enriched: dict | None = None) -> str:
    label = SESSION_LABELS.get(session, session)
    ind_text = format_indicators_for_prompt(indicators)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Multi-TF and key levels from enriched context
    multi_tf_text = enriched.get("multi_tf_text", "") if enriched else ""
    key_levels_text = enriched.get("key_levels_text", "") if enriched else ""
    btc_context = enriched.get("btc_context", "") if enriched else ""

    data_section = (
        f"当前时间: {now_str} (北京时间)\n分析时段: {label}\n\n"
        f"=== 实时市场数据 ===\n"
        f"当前价格: ${market.price:,.2f}\n"
        f"24h涨跌: {market.price_change_pct_24h}%\n"
        f"24h最高/最低: ${market.high_24h:,.2f} / ${market.low_24h:,.2f}\n"
        f"24h成交量: ${market.volume_24h:,.0f}\n"
        f"资金费率: {market.funding_rate}\n"
        f"多空比(大户): {market.long_short_ratio}\n"
        f"未平仓量: {market.open_interest} ({market.open_interest_change_pct}% 变化)\n\n"
    )

    # Add multi-TF section
    if multi_tf_text:
        data_section += f"=== 多时间框架技术分析 ===\n{multi_tf_text}\n\n"
    else:
        data_section += f"=== 技术指标 ===\n{ind_text}\n\n"

    # Add key levels
    if key_levels_text:
        data_section += f"{key_levels_text}\n\n"

    # Add BTC context for altcoins
    if btc_context:
        data_section += f"{btc_context}\n\n"

    data_section += (
        f"=== 市场情绪 ===\n"
        f"恐慌贪婪指数: {fear_greed.value} ({fear_greed.label})"
    )

    json_schema = (
        '{"signal":{"direction":"LONG/SHORT/NEUTRAL","confidence":72,'
        '"entry_zone":[84200,84500],"stop_loss":83400,'
        '"take_profit":[85800,87200],"leverage_suggestion":"3x-5x",'
        '"risk_reward_ratio":2.5},'
        '"technical":{"title":"技术面分析","content":"多时间框架综合判断","bullets":["日线趋势判断","4h结构分析","1h入场时机","VWAP/StochRSI交叉信号"],"key_support":[83000,82500],"key_resistance":[86000,87500]},'
        '"fundamental":{"title":"基本面分析","content":"综合判断","bullets":["要点1","要点2"]},'
        '"sentiment":{"title":"情绪面分析","content":"综合判断","bullets":["要点1","要点2"]},'
        '"macro":{"title":"宏观面分析","content":"综合判断","bullets":["要点1","要点2"]},'
        '"risk_warning":{"title":"风险提示","content":"风险总结","bullets":["风险1","风险2"]},'
        '"calendar_events":[{"date":"2026-03-30","time":"20:30","title":"美国非农就业数据",'
        '"impact":"HIGH","category":"economic","previous":"15.1万",'
        '"forecast":"16.0万","description":"影响说明",'
        '"impact_if_met":"达到或超预期: 对加密市场利好/利空分析，预计BTC波动方向和幅度",'
        '"impact_if_missed":"不及预期: 对加密市场利好/利空分析，预计BTC波动方向和幅度"}]}'
    )

    return (
        "你是一位顶级加密货币合约交易分析师，精通多时间框架分析和量价关系。\n"
        "请根据以下**多维度实时数据**和你通过Google搜索获取的最新信息，"
        f"对 {market.name} ({market.symbol}) 进行专业级合约交易分析。\n\n"
        f"{data_section}\n\n"
        "=== 分析要求 ===\n"
        "请严格遵循以下专业交易分析框架:\n"
        "1. **多时间框架共振**: 日线定方向→4h找结构→1h抓入场，三个周期方向一致时信心最高\n"
        "2. **真实关键价位**: entry_zone/stop_loss/take_profit必须参考上方提供的摆动高低点和Fib回撤位\n"
        "3. **量价验证**: ADX判断趋势强度，OBV确认资金流向，VWAP作为机构成本参考\n"
        "4. **StochRSI交叉**: 比普通RSI更灵敏的超买超卖信号\n\n"
        f"请搜索并整合以下最新信息:\n"
        f"1. 最新的{market.name}相关新闻、政策、ETF资金流向\n"
        "2. 美联储最新政策动向、利率预期\n"
        "3. 美元指数DXY走势对加密市场影响\n"
        "4. 未来7天美国重大经济数据和事件\n\n"
        f"请严格按以下JSON格式返回(不要包含markdown代码块标记):\n{json_schema}\n\n"
        "注意:\n"
        "- calendar_events只包含未来7天内的美国经济数据和美联储相关事件\n"
        "- 每个calendar_event必须包含impact_if_met和impact_if_missed两个字段\n"
        "- previous和forecast字段：对于有数据的经济指标(如CPI、非农、PCE、GDP、初请失业金等)必须填入具体数值(如\"0.3%\"、\"15.1万\"、\"2.8%\")；只有会议纪要等非数据类事件才可以填null\n"
        "- 所有价格用美元保留小数点后2位\n"
        "- confidence反映你对该方向判断的把握程度(0-100)\n"
        "- 中文回复但JSON key保持英文\n"
        "- technical部分必须包含key_support和key_resistance字段，基于提供的摆动高低点给出2个关键价位\n"
        "- 如果多时间框架方向矛盾(如日线多头但1h空头)，confidence应降低并在risk_warning中说明"
    )



def _parse_response(text: str) -> dict:
    """Clean and parse Gemini JSON response (robust for 2.5 Flash thinking models)."""
    text = text.strip()
    # Remove markdown code block wrappers
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    if text.startswith("json"):
        text = text[4:]
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract JSON object between first { and last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    # Last resort: try fixing common issues (trailing commas, etc.)
    import re
    cleaned = text[first_brace:last_brace + 1] if first_brace != -1 else text
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)  # remove trailing commas
    return json.loads(cleaned)


async def analyze_symbol(
    market: MarketData,
    indicators: TechnicalIndicators,
    fear_greed: FearGreedIndex,
    enriched_context: dict | None = None,
) -> AnalysisReport:
    """Run Gemini analysis with Google Search Grounding for a symbol."""
    session = _get_session_name()
    prompt = _build_prompt(market, indicators, fear_greed, session, enriched_context)

    api_key = settings.get_next_gemini_key()
    client = genai.Client(api_key=api_key)

    google_search_tool = types.Tool(google_search=types.GoogleSearch())

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[google_search_tool],
            temperature=0.7,
            max_output_tokens=16384,
        ),
    )

    raw_text = response.text or ""
    print(f"  📝 Gemini raw response length: {len(raw_text)} chars")
    if not raw_text.strip():
        # Try extracting from candidates
        if response.candidates:
            parts = response.candidates[0].content.parts
            raw_text = "".join(p.text for p in parts if hasattr(p, "text") and p.text)
            print(f"  📝 Extracted from candidates: {len(raw_text)} chars")
    if not raw_text.strip():
        raise Exception(f"Gemini returned empty response. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'no candidates'}")

    data = _parse_response(raw_text)

    report_id = f"{market.symbol}_{session}_{datetime.now().strftime('%Y%m%d%H%M')}"

    return AnalysisReport(
        id=report_id,
        symbol=market.symbol,
        name=market.name,
        session=session,
        timestamp=datetime.now(timezone.utc),
        price_at_analysis=market.price,
        ai_provider="gemini",
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
