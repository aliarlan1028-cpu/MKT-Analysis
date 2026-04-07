"""SimAnalyzer — Gemini 4-step deep analysis for sim trading.

Step 1: Fundamental scan — what is this coin?
Step 2: Strategy selection — what's the best analytical approach?
Step 3: Deep analysis — execute with dynamic factors
Step 4: Trade decision — entry, SL, TP, direction
"""

import json
import traceback
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
from app.core.config import settings
from app.services.market_data import _okx_get

_BEIJING_TZ = timezone(timedelta(hours=8))


async def _gemini_call(prompt: str, system: str = None) -> str:
    """Call Gemini 2.5 Flash with Google Search grounding."""
    api_key = settings.get_next_gemini_key()
    client = genai.Client(api_key=api_key)
    google_search_tool = types.Tool(google_search=types.GoogleSearch())

    contents = prompt
    config = types.GenerateContentConfig(
        tools=[google_search_tool],
        temperature=0.7,
        max_output_tokens=16384,
    )
    if system:
        config.system_instruction = system

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=contents,
        config=config,
    )
    return response.text or ""


def _parse_json(text: str) -> dict:
    """Extract JSON from AI response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    if text.startswith("json"):
        text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last > first:
            try:
                return json.loads(text[first:last + 1])
            except json.JSONDecodeError:
                pass
        import re
        cleaned = text[first:last + 1] if first != -1 else text
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
        return json.loads(cleaned)


async def _fetch_coin_data(coin: str) -> dict:
    """Fetch comprehensive OKX data for analysis."""
    swap_id = f"{coin}-USDT-SWAP"

    # Ticker
    ticker = {}
    body = await _okx_get("/api/v5/market/ticker", {"instId": swap_id})
    if body and body.get("data"):
        t = body["data"][0]
        ticker = {
            "price": float(t["last"]),
            "open24h": float(t.get("open24h", 0)),
            "high24h": float(t.get("high24h", 0)),
            "low24h": float(t.get("low24h", 0)),
            "vol24h": float(t.get("volCcy24h", 0)),
        }
        ticker["change24h_pct"] = round((ticker["price"] - ticker["open24h"]) / ticker["open24h"] * 100, 2) if ticker["open24h"] else 0

    # Funding rate
    funding = None
    try:
        fr = await _okx_get("/api/v5/public/funding-rate", {"instId": swap_id})
        if fr and fr["data"]:
            funding = float(fr["data"][0]["fundingRate"])
    except Exception:
        pass

    # Klines (4H, last 100)
    klines_4h = []
    try:
        kb = await _okx_get("/api/v5/market/candles", {"instId": swap_id, "bar": "4H", "limit": "100"})
        if kb and kb["data"]:
            for k in kb["data"][:50]:  # last 50 candles
                klines_4h.append({"t": k[0], "o": k[1], "h": k[2], "l": k[3], "c": k[4], "v": k[5]})
    except Exception:
        pass

    # Open interest
    oi = None
    try:
        oib = await _okx_get("/api/v5/public/open-interest", {"instType": "SWAP", "instId": swap_id})
        if oib and oib["data"]:
            oi = float(oib["data"][0].get("oiCcy", 0))
    except Exception:
        pass

    return {
        "coin": coin,
        "ticker": ticker,
        "funding_rate": funding,
        "klines_4h_count": len(klines_4h),
        "klines_4h_summary": _summarize_klines(klines_4h) if klines_4h else "无数据",
        "open_interest": oi,
    }


def _summarize_klines(klines: list) -> str:
    """Create a text summary of kline data for the prompt."""
    if not klines:
        return "无K线数据"
    lines = []
    for k in klines[:30]:
        lines.append(f"O:{k['o']} H:{k['h']} L:{k['l']} C:{k['c']} V:{k['v']}")


# ═══════════════════════════════════════════
#  STEP 1: FUNDAMENTAL SCAN
# ═══════════════════════════════════════════

async def step1_fundamental_scan(coin: str, market_data: dict) -> dict:
    """What is this coin? Project, recent events, narrative."""
    prompt = (
        f"你是一位资深加密货币研究员。请对 {coin} 进行基本面扫描。\n\n"
        f"当前价格: ${market_data['ticker'].get('price', 'N/A')}\n"
        f"24h涨跌: {market_data['ticker'].get('change24h_pct', 'N/A')}%\n"
        f"资金费率: {market_data.get('funding_rate', 'N/A')}\n\n"
        "请搜索最新信息并回答：\n"
        "1. 这个项目是什么？属于什么赛道？\n"
        "2. 项目当前阶段（早期/成长/成熟/衰退/炒作期）？\n"
        "3. 近期重大事件（融资、合作、上架、解锁、技术升级等）？\n"
        "4. 社区热度来源：是 FOMO 炒作、庄家拉盘、还是真实增长？\n"
        "5. 当前价格是否有基本面支撑？\n\n"
        "严格按以下JSON格式返回（不要markdown代码块）：\n"
        '{"project_summary":"项目简介","sector":"赛道","stage":"当前阶段",'
        '"recent_events":["事件1","事件2"],'
        '"hype_source":"热度来源分析",'
        '"fundamental_support":"基本面是否支撑当前价格的判断",'
        '"conclusion":"总结性判断"}'
    )
    raw = await _gemini_call(prompt)
    return _parse_json(raw)


# ═══════════════════════════════════════════
#  STEP 2: STRATEGY SELECTION
# ═══════════════════════════════════════════

async def step2_strategy_selection(coin: str, step1_result: dict, market_data: dict) -> dict:
    """Based on Step 1, determine the best analytical approach."""
    prompt = (
        f"你是一位资深加密货币交易策略师。基于以下对 {coin} 的基本面扫描结果，\n"
        f"请确定最适合分析这个币种的方法论。\n\n"
        f"=== 基本面扫描结果 ===\n{json.dumps(step1_result, ensure_ascii=False, indent=2)}\n\n"
        f"当前价格: ${market_data['ticker'].get('price', 'N/A')}\n"
        f"资金费率: {market_data.get('funding_rate', 'N/A')}\n"
        f"未平仓量: {market_data.get('open_interest', 'N/A')}\n\n"
        "不要使用千篇一律的 RSI+MACD 分析。根据这个币的特性选择最优方法：\n"
        "- 如果是 meme 币：重点看链上数据、社区情绪、巨鲸动向\n"
        "- 如果是 L1/L2：重点看 TVL 趋势、开发活跃度、生态增长\n"
        "- 如果是 DeFi：重点看协议收入、锁仓量变化、代币经济模型\n"
        "- 如果是新币/炒作期：重点看庄家行为、筹码分布、拉盘模式\n"
        "- 其他情况：根据实际情况自行判断最优方法\n\n"
        "严格按以下JSON格式返回：\n"
        '{"coin_type":"币种类型判断",'
        '"recommended_methods":["方法1描述","方法2描述","方法3描述"],'
        '"key_metrics_to_watch":["关键指标1","关键指标2"],'
        '"analysis_framework":"整体分析框架描述",'
        '"risk_focus":"该币种需要特别关注的风险点"}'
    )
    raw = await _gemini_call(prompt)
    return _parse_json(raw)


# ═══════════════════════════════════════════
#  STEP 3: DEEP ANALYSIS WITH DYNAMIC FACTORS
# ═══════════════════════════════════════════

async def step3_deep_analysis(coin: str, step1: dict, step2: dict, market_data: dict) -> dict:
    """Execute deep analysis using the selected strategy, generate dynamic factors."""
    klines_text = market_data.get("klines_4h_summary", "无数据")
    prompt = (
        f"你是一位顶级加密货币合约交易分析师。请对 {coin} 进行深度行情分析。\n\n"
        f"=== 基本面 ===\n{json.dumps(step1, ensure_ascii=False, indent=2)}\n\n"
        f"=== 分析策略 ===\n{json.dumps(step2, ensure_ascii=False, indent=2)}\n\n"
        f"=== 市场数据 ===\n"
        f"当前价格: ${market_data['ticker'].get('price', 'N/A')}\n"
        f"24h涨跌: {market_data['ticker'].get('change24h_pct', 'N/A')}%\n"
        f"24h最高: ${market_data['ticker'].get('high24h', 'N/A')}\n"
        f"24h最低: ${market_data['ticker'].get('low24h', 'N/A')}\n"
        f"资金费率: {market_data.get('funding_rate', 'N/A')}\n"
        f"未平仓量: {market_data.get('open_interest', 'N/A')}\n\n"
        f"=== 4H K线数据 (最近30根) ===\n{klines_text}\n\n"
        "请按照上面选定的分析策略进行深度分析，并生成动态因子列表。\n"
        "每个因子是你在分析中发现的一个具体事实或判断，不是固定分类。\n"
        "因子内容应该是具体的、可回溯验证的。\n\n"
        "同时必须分析以下维度：\n"
        "1. 是否触顶/触底？\n"
        "2. 是否有庄家出货/吸筹迹象？\n"
        "3. 是否存在真实催化剂？还是纯 FOMO/社区炒作？\n"
        "4. 急速回调/拉升风险？\n"
        "5. 基本面是否支撑当前价格？\n\n"
        "严格按以下JSON格式返回：\n"
        '{"overall_bias":"看多/看空/中性",'
        '"confidence":72,'
        '"factors":['
        '{"description":"具体因子描述，例如：4H级别价格走高但OBV持续走平，资金并未真正流入","bias":"看多/看空/中性"},'
        '{"description":"另一个因子","bias":"看多/看空/中性"}'
        '],'
        '"top_bottom_analysis":"触顶/触底分析",'
        '"market_maker_analysis":"庄家行为分析",'
        '"catalyst_analysis":"催化剂真实性分析",'
        '"pullback_risk":"急速回调/拉升风险评估",'
        '"price_support":"基本面是否支撑价格",'
        '"bullish_factors":["利好因素1","利好因素2"],'
        '"bearish_factors":["利空因素1","利空因素2"],'
        '"key_levels":{"support":[价格1,价格2],"resistance":[价格1,价格2]}}'
    )
    raw = await _gemini_call(prompt)
    return _parse_json(raw)


# ═══════════════════════════════════════════
#  STEP 4: TRADE DECISION
# ═══════════════════════════════════════════

async def step4_trade_decision(coin: str, step3: dict, market_data: dict) -> dict:
    """Final trade decision with entry, SL, TP."""
    price = market_data['ticker'].get('price', 0)
    prompt = (
        f"你是一位顶级合约交易员。基于以下对 {coin} 的深度分析，做出交易决策。\n\n"
        f"=== 深度分析结果 ===\n{json.dumps(step3, ensure_ascii=False, indent=2)}\n\n"
        f"当前价格: ${price}\n"
        f"交易条件: 10x杠杆，永续合约\n\n"
        "请给出精确的交易决策：\n"
        "- 如果不建议交易（风险过高/信号不明确），direction 填 NONE\n"
        "- 入场价要合理：做多时入场价应 ≤ 当前价格（等回调），做空时 ≥ 当前价格（等反弹）\n"
        "- 止损要明确且合理（10x杠杆下不超过保证金的30%）\n"
        "- 止盈分两档\n\n"
        "严格按以下JSON格式返回：\n"
        '{"direction":"LONG/SHORT/NONE",'
        '"confidence":72,'
        '"reasoning":"交易逻辑简述",'
        f'"entry_price":{price},'
        f'"stop_loss":{price * 0.97},'
        f'"take_profit_1":{price * 1.05},'
        f'"take_profit_2":{price * 1.10},'
        '"risk_assessment":"风险评估",'
        '"key_invalidation":"什么情况下这个判断会失效"}'
    )
    raw = await _gemini_call(prompt)
    return _parse_json(raw)


# ═══════════════════════════════════════════
#  FULL 4-STEP ANALYSIS
# ═══════════════════════════════════════════

async def run_full_analysis(coin: str) -> dict:
    """Run complete 4-step analysis for a coin."""
    print(f"  🔬 SimAnalyzer: Starting 4-step analysis for {coin}...")

    # Fetch data
    market_data = await _fetch_coin_data(coin)
    if not market_data.get("ticker", {}).get("price"):
        return {"error": f"无法获取 {coin} 的市场数据"}

    results = {"coin": coin, "timestamp": datetime.now(_BEIJING_TZ).isoformat(), "market_data": market_data}

    # Step 1
    print(f"    Step 1: 基本面扫描...")
    try:
        results["step1"] = await step1_fundamental_scan(coin, market_data)
    except Exception as e:
        print(f"    ❌ Step 1 failed: {e}")
        results["step1"] = {"error": str(e)}
        return results

    # Step 2
    print(f"    Step 2: 分析策略选择...")
    try:
        results["step2"] = await step2_strategy_selection(coin, results["step1"], market_data)
    except Exception as e:
        print(f"    ❌ Step 2 failed: {e}")
        results["step2"] = {"error": str(e)}
        return results

    # Step 3
    print(f"    Step 3: 深度行情分析...")
    try:
        results["step3"] = await step3_deep_analysis(coin, results["step1"], results["step2"], market_data)
    except Exception as e:
        print(f"    ❌ Step 3 failed: {e}")
        results["step3"] = {"error": str(e)}
        return results

    # Step 4
    print(f"    Step 4: 交易决策...")
    try:
        results["step4"] = await step4_trade_decision(coin, results["step3"], market_data)
    except Exception as e:
        print(f"    ❌ Step 4 failed: {e}")
        results["step4"] = {"error": str(e)}
        return results

    print(f"  ✅ SimAnalyzer: {coin} analysis complete — {results['step4'].get('direction', 'N/A')}")
    return results


# ═══════════════════════════════════════════
#  VOLATILITY EVENT ANALYSIS
# ═══════════════════════════════════════════

async def analyze_volatility_event(coin: str, price: float, change_pct: float, position: dict) -> str:
    """Analyze why a significant price move happened."""
    prompt = (
        f"{coin} 在短时间内价格{'上涨' if change_pct > 0 else '下跌'}了 {abs(change_pct):.1f}%，"
        f"当前价格 ${price}。\n\n"
        f"持仓方向: {position['direction']} | 入场价: ${position['entry_price']}\n\n"
        "请搜索最新信息，分析这次波动的原因：\n"
        "1. 是什么触发了这次波动？（新闻/清算/BTC联动/技术面突破...）\n"
        "2. 这次波动是否可持续？\n"
        "3. 对当前持仓有什么影响？需要调整策略吗？\n\n"
        "请用中文简洁回答（200字以内），不要JSON格式。"
    )
    try:
        return await _gemini_call(prompt)
    except Exception as e:
        return f"分析失败: {e}"


# ═══════════════════════════════════════════
#  POST-TRADE FACTOR REVIEW
# ═══════════════════════════════════════════

async def review_trade_factors(position: dict, snapshots: list, events: list) -> dict:
    """Post-trade analysis: review each factor with hindsight."""
    factors = position.get("factors", [])
    if not factors:
        return {"error": "没有因子数据"}

    # Build price path summary
    price_path = ""
    if snapshots:
        prices = [s["price"] for s in snapshots]
        price_path = (
            f"入场价: ${position['entry_price']} → "
            f"MAE: ${position.get('mae_price', 'N/A')} ({position.get('mae', 0):+.1f}%) → "
            f"MFE: ${position.get('mfe_price', 'N/A')} ({position.get('mfe', 0):+.1f}%) → "
            f"平仓价: ${position['exit_price']} (最终: {position.get('pnl_pct', 0):+.1f}%)\n"
            f"价格范围: ${min(prices):.6f} ~ ${max(prices):.6f} | 持仓时长: {len(snapshots)}分钟"
        )

    # Build events summary
    events_text = ""
    for ev in events:
        events_text += f"[{ev['timestamp']}] {ev['event_type']}: ${ev['price']} {ev.get('ai_analysis', '')[:100]}\n"

    factors_text = "\n".join([f"因子{i+1}: {f['description']} (判断: {f['bias']})" for i, f in enumerate(factors)])

    prompt = (
        f"你是一位交易复盘专家。请对以下 {position['coin']} 的交易进行深度因子归因分析。\n\n"
        f"=== 交易概况 ===\n"
        f"方向: {position['direction']} | 杠杆: {position['leverage']}x\n"
        f"最终结果: {'盈利' if position.get('pnl', 0) > 0 else '亏损'} {position.get('pnl_pct', 0):+.1f}% (${position.get('pnl', 0):+.2f})\n\n"
        f"=== 价格路径 ===\n{price_path}\n\n"
        f"=== 波动事件 ===\n{events_text or '无重大波动事件'}\n\n"
        f"=== 入场时的分析因子 ===\n{factors_text}\n\n"
        "请逐一回溯每个因子，判断它是否有效，并追溯根源。\n"
        "不是简单的对错，而是分析为什么对/为什么错的具体原因。\n\n"
        "严格按以下JSON格式返回：\n"
        '{"factor_reviews":['
        '{"factor_index":1,"original":"因子原文","verdict":"✅有效/❌误判/⚠️部分有效",'
        '"explanation":"具体解释为什么有效或误判，追溯到根源"}],'
        '"core_correct_factor":"本次交易核心正确因素及原因",'
        '"core_wrong_factor":"本次交易核心错误因素及原因",'
        '"root_lesson":"根源教训（具体到方法论层面）",'
        '"what_if":"如果重来，应该怎么做",'
        '"reusable_rule":"从这笔交易提取的可复用规则"}'
    )
    try:
        raw = await _gemini_call(prompt)
        return _parse_json(raw)
    except Exception as e:
        return {"error": str(e)}
