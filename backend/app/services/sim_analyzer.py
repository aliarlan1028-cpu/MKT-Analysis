"""SimAnalyzer — 9-dimension comprehensive analysis engine.

Call 1: Token Economics + News & Catalyst (with Google Search)
Call 2: Technical Analysis (with kline data)
Call 3: On-Chain + Macro + Whale + Sentiment + Liquidity (with Google Search)
Call 4: Executive Summary + Trading Decision (synthesizing all)
"""

import json
import re
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types
from app.core.config import settings
from app.services.market_data import _okx_get

_BEIJING_TZ = timezone(timedelta(hours=8))


async def _gemini_call(prompt: str) -> str:
    """Call Gemini 2.5 Flash with Google Search grounding."""
    api_key = settings.get_next_gemini_key()
    client = genai.Client(api_key=api_key)
    google_search_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        tools=[google_search_tool],
        temperature=0.5,
        max_output_tokens=16384,
    )
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL, contents=prompt, config=config,
    )
    return response.text or ""


def _parse_json(text: str) -> dict:
    """Extract JSON from AI response (robust)."""
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
        pass
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        try:
            return json.loads(text[first:last + 1])
        except json.JSONDecodeError:
            cleaned = re.sub(r',\s*([}\]])', r'\1', text[first:last + 1])
            return json.loads(cleaned)
    raise ValueError(f"Cannot parse JSON from: {text[:200]}")


async def _fetch_coin_data(coin: str) -> dict:
    """Fetch comprehensive OKX data for analysis — multi-timeframe."""
    swap_id = f"{coin}-USDT-SWAP"
    data: dict = {"coin": coin}

    # Ticker
    body = await _okx_get("/api/v5/market/ticker", {"instId": swap_id})
    if body and body.get("data"):
        t = body["data"][0]
        data["ticker"] = {
            "price": float(t["last"]), "open24h": float(t.get("open24h", 0)),
            "high24h": float(t.get("high24h", 0)), "low24h": float(t.get("low24h", 0)),
            "vol24h": float(t.get("volCcy24h", 0)),
        }
        o = data["ticker"]["open24h"]
        data["ticker"]["change24h_pct"] = round((data["ticker"]["price"] - o) / o * 100, 2) if o else 0
    else:
        data["ticker"] = {}

    # Funding rate
    try:
        fr = await _okx_get("/api/v5/public/funding-rate", {"instId": swap_id})
        data["funding_rate"] = float(fr["data"][0]["fundingRate"]) if fr and fr.get("data") else None
    except Exception:
        data["funding_rate"] = None

    # Open interest
    try:
        oib = await _okx_get("/api/v5/public/open-interest", {"instType": "SWAP", "instId": swap_id})
        data["open_interest"] = float(oib["data"][0].get("oiCcy", 0)) if oib and oib.get("data") else None
    except Exception:
        data["open_interest"] = None

    # Multi-timeframe klines
    for tf, label in [("1H", "klines_1h"), ("4H", "klines_4h"), ("1D", "klines_1d")]:
        try:
            kb = await _okx_get("/api/v5/market/candles", {"instId": swap_id, "bar": tf, "limit": "100"})
            lines = []
            if kb and kb.get("data"):
                for k in kb["data"][:50]:
                    lines.append(f"{k[0]}|O:{k[1]}|H:{k[2]}|L:{k[3]}|C:{k[4]}|V:{k[5]}")
            data[label] = "\n".join(lines) if lines else "无数据"
        except Exception:
            data[label] = "无数据"

    return data


# ═══════════════════════════════════════════════════════
#  CALL 1: Token Economics + News/Catalyst (dimensions 1-2)
# ═══════════════════════════════════════════════════════

async def call1_economics_news(coin: str, md: dict) -> dict:
    price = md["ticker"].get("price", "N/A")
    prompt = (
        f"你是顶级加密货币研究分析师。请对 {coin} 进行以下两个维度的深度分析。\n"
        f"当前价格: ${price} | 24h涨跌: {md['ticker'].get('change24h_pct','N/A')}%\n\n"
        "=== 维度1: 代币经济学 ===\n"
        "搜索并提供：总发行量、流通量、当前市值、FDV、24h成交量、换手率、24h量比、"
        "赛道/叙事定位、代币经济学（解锁计划、通胀率、质押率等）。\n"
        "标注高风险点（大额解锁临近、流通率低、FDV/市值比过高等）。\n\n"
        "=== 维度2: 信息面/基本面 ===\n"
        "搜索最近7-30天关键新闻，按利好/利空分类：\n"
        "- 赛道整体利好/利空\n- 项目自身催化剂\n- 负面信息\n"
        "每条新闻评估影响强度(强/中/弱)。\n\n"
        "严格按JSON返回（不要markdown代码块）：\n"
        '{"token_economics":{"total_supply":"","circulating_supply":"","market_cap":"","fdv":"","volume_24h":"","turnover_rate":"","volume_ratio_24h":"","sector":"","token_model":"代币经济学描述","risk_flags":["风险点1"]},'
        '"news_catalyst":{"bullish_news":[{"event":"","impact":"强/中/弱","detail":""}],"bearish_news":[{"event":"","impact":"强/中/弱","detail":""}],"catalyst_strength":"整体催化剂强度评估","narrative_position":"当前叙事位置"}}'
    )
    return _parse_json(await _gemini_call(prompt))


# ═══════════════════════════════════════════════════════
#  CALL 2: Technical Analysis (dimension 3) — with kline data
# ═══════════════════════════════════════════════════════

async def call2_technical(coin: str, md: dict) -> dict:
    price = md["ticker"].get("price", "N/A")
    prompt = (
        f"你是顶级合约技术分析师。请对 {coin} (当前${price}) 进行全面技术分析。\n\n"
        f"=== 1H K线(最近50根) ===\n{md.get('klines_1h','无数据')}\n\n"
        f"=== 4H K线(最近50根) ===\n{md.get('klines_4h','无数据')}\n\n"
        f"=== 日线K线(最近50根) ===\n{md.get('klines_1d','无数据')}\n\n"
        f"资金费率: {md.get('funding_rate','N/A')} | 未平仓量: {md.get('open_interest','N/A')}\n\n"
        "请按以下子项逐一分析（基于真实K线数据计算）：\n"
        "1. 市场结构: HH/HL vs LH/LL序列，BOS/CHOCH判断\n"
        "2. K线形态: 反转形态(射击之星/锤头/吞没/晨星晚星)和持续形态\n"
        "3. 趋势与MA: EMA20/50/100/200关系，金叉/死叉，EMA对齐\n"
        "4. 动量指标: RSI(超买超卖+背离)，MACD(交叉+柱状线背离)，CCI\n"
        "5. 波动率: Bollinger Bands(Squeeze/突破)，ATR值，Keltner\n"
        "6. 量价关系: OBV趋势，量价背离，VWAP位置，Volume Profile关键节点\n"
        "7. 高级指标: Ichimoku云层，Supertrend，Fibonacci关键位，ADX趋势强度\n"
        "8. 多时间框架共振: 日线/4H/1H信号是否一致\n"
        "9. 触顶/触底判断: 综合RSI+量价背离+BB+结构破位+K线形态，给出明确判断\n"
        "10. Pump&Dump检测: 价格偏离20日EWMA程度，异常量能\n\n"
        "严格按JSON返回：\n"
        '{"market_structure":{"trend":"上升/下降/震荡","hh_hl_or_lh_ll":"描述","bos_choch":"结构破位情况"},'
        '"candlestick_patterns":["识别到的形态及位置"],'
        '"trend_ma":{"ema20":"价格vs EMA20关系","ema50":"","ema200":"","alignment":"EMA对齐情况","golden_death_cross":""},'
        '"momentum":{"rsi_14":"数值+状态","rsi_divergence":"是否背离","macd":"状态","macd_divergence":"","cci":"","adx":"趋势强度"},'
        '"volatility":{"bollinger":"位置+Squeeze状态","atr":"数值+含义","keltner":""},'
        '"volume_analysis":{"obv_trend":"","volume_price_divergence":"是否量价背离","vwap":"当前价vs VWAP","volume_profile_key_levels":"高成交量节点"},'
        '"advanced":{"ichimoku":"云层位置+信号","supertrend":"信号","fibonacci_levels":"关键回撤/扩展位","adx_value":""},'
        '"multi_timeframe":{"daily":"日线信号","four_hour":"4H信号","one_hour":"1H信号","confluence":"是否共振"},'
        '"top_bottom":{"verdict":"当前处于触顶/震荡/触底/拉升阶段","signals_present":["已出现的信号"],"signals_missing":["还缺的确认信号"],"pump_dump_stage":"Pump&Dump阶段评估"},'
        '"key_levels":{"support":[0.0],"resistance":[0.0]},'
        '"factors":[{"description":"具体技术因子","bias":"看多/看空/中性"}]}'
    )
    return _parse_json(await _gemini_call(prompt))


# ═══════════════════════════════════════════════════════
#  CALL 3: On-Chain + Macro + Whale + Sentiment + Liquidity (dimensions 4-8)
# ═══════════════════════════════════════════════════════

async def call3_onchain_macro_sentiment(coin: str, md: dict) -> dict:
    price = md["ticker"].get("price", "N/A")
    prompt = (
        f"你是顶级加密货币链上分析师和宏观策略师。请对 {coin} (${price}) 进行以下5个维度分析。\n\n"
        "=== 维度4: 链上数据 ===\n"
        "搜索：鲸鱼/大户交易所流入流出、MVRV Z-Score、NVT Ratio、SOPR、开发者/团队钱包活动。\n"
        "判断'聪明钱'行为（积累/分发/观望）。\n\n"
        "=== 维度5: 宏观市场 ===\n"
        "BTC Dominance趋势、Altcoin Season Index、Fear & Greed Index、整体市场阶段、"
        "全球宏观影响（利率/监管/地缘政治）。\n\n"
        "=== 维度6: 庄家/大户操纵 ===\n"
        "异常操作检测、筹码集中度(Top地址持有比例)、散户分布、"
        "拉盘所需资金估算、刷量(Wash Trading)评估（CEX量vs链上Tx、唯一钱包数异常）。\n\n"
        "=== 维度7: 情绪面 ===\n"
        "社交媒体热度(X/Telegram/Reddit)、看涨/看空比例、FOMO/恐慌程度。\n\n"
        "=== 维度8: 流动性与风险 ===\n"
        "订单簿深度/滑点风险、CEX vs DEX分布、永续合约资金费率影响、"
        "主要风险点（Rug Pull/监管/解锁/黑天鹅/流动性枯竭）。\n\n"
        "严格按JSON返回：\n"
        '{"onchain":{"whale_flow":"鲸鱼流向","mvrv":"","nvt":"","sopr":"","team_wallet":"","smart_money_verdict":"积累/分发/观望"},'
        '"macro":{"btc_dominance":"","altcoin_season":"","fear_greed":"","market_phase":"牛市/熊市/震荡","global_macro":""},'
        '"whale_manipulation":{"abnormal_activity":"","chip_concentration":"Top地址持有%","retail_distribution":"","pump_cost_estimate":"","wash_trading_risk":"低/中/高","wash_evidence":""},'
        '"sentiment":{"social_heat":"","bull_bear_ratio":"","fomo_level":"","overall":""},'
        '"liquidity_risk":{"orderbook_depth":"","slippage_risk":"","cex_dex_ratio":"","funding_rate_impact":"","major_risks":["风险1"],"risk_level":"低/中/高"}}'
    )
    return _parse_json(await _gemini_call(prompt))


# ═══════════════════════════════════════════════════════
#  CALL 4: Executive Summary + Trading Decision (dimension 9)
# ═══════════════════════════════════════════════════════

async def call4_summary_decision(coin: str, md: dict, c1: dict, c2: dict, c3: dict) -> dict:
    price = md["ticker"].get("price", 0)
    prompt = (
        f"你是顶级合约交易决策者。基于以下对 {coin} (${price}) 的9维分析结果，给出最终判断和交易决策。\n\n"
        f"=== 代币经济学+新闻 ===\n{json.dumps(c1, ensure_ascii=False)[:3000]}\n\n"
        f"=== 技术面分析 ===\n{json.dumps(c2, ensure_ascii=False)[:3000]}\n\n"
        f"=== 链上+宏观+情绪+流动性 ===\n{json.dumps(c3, ensure_ascii=False)[:3000]}\n\n"
        "请提供：\n"
        "1. 执行摘要：一句话核心结论 + 短期走势概率(涨/跌/震荡)\n"
        "2. 多维度共振判断：Pump&Dump阶段评估\n"
        "3. 触顶/触底信号确认：已出现哪些，还缺哪些\n"
        "4. 交易决策：方向、入场价、止盈1/2、止损、仓位建议\n"
        "   - 10x杠杆永续合约\n"
        "   - 做多入场价≤当前价(等回调)，做空≥当前价(等反弹)\n"
        "   - 止损不超过保证金30%\n"
        "   - 不建议交易则direction=NONE\n"
        "5. 关键观察指标警报\n\n"
        "严格按JSON返回：\n"
        '{"executive_summary":{"core_conclusion":"一句话结论","probability":{"up":30,"down":40,"sideways":30},"recommended_action":"观察/减仓/加仓/空仓"},'
        '"multi_dimension_confluence":{"pump_dump_stage":"早期Pump/高位Pump/Dump进行中/触底反弹/无明显信号","confluence_signals":["共振信号1"]},'
        '"top_bottom_confirmation":{"signals_present":["已出现信号"],"signals_missing":["缺少的确认"],"verdict":"判断"},'
        '"trade_decision":{"direction":"LONG/SHORT/NONE","confidence":72,"reasoning":"逻辑",'
        f'"entry_price":{price},"stop_loss":{price*0.97},"take_profit_1":{price*1.05},"take_profit_2":{price*1.10},'
        '"position_size_pct":100,"risk_assessment":"风险评估","key_invalidation":"失效条件"},'
        '"alert_indicators":["需要关注的指标1"],'
        '"factors":[{"description":"综合因子","bias":"看多/看空/中性"}]}'
    )
    return _parse_json(await _gemini_call(prompt))


# ═══════════════════════════════════════════════════════
#  MAIN ENTRY: run_full_analysis
# ═══════════════════════════════════════════════════════

async def run_full_analysis(coin: str) -> dict:
    """Run 9-dimension comprehensive analysis (4 Gemini calls)."""
    print(f"  🔬 SimAnalyzer: 9维分析 {coin}...")
    md = await _fetch_coin_data(coin)
    if not md.get("ticker", {}).get("price"):
        return {"error": f"无法获取 {coin} 的市场数据"}

    results = {"coin": coin, "timestamp": datetime.now(_BEIJING_TZ).isoformat(), "market_data": md}

    for label, func, args, key in [
        ("代币经济学+新闻", call1_economics_news, (coin, md), "call1"),
        ("技术面分析", call2_technical, (coin, md), "call2"),
        ("链上+宏观+情绪", call3_onchain_macro_sentiment, (coin, md), "call3"),
    ]:
        print(f"    📊 {label}...")
        try:
            results[key] = await func(*args)
        except Exception as e:
            print(f"    ❌ {label} failed: {e}")
            results[key] = {"error": str(e)}

    # Call 4 needs results from 1-3
    print(f"    📋 执行摘要+交易决策...")
    try:
        results["call4"] = await call4_summary_decision(
            coin, md,
            results.get("call1", {}), results.get("call2", {}), results.get("call3", {}),
        )
    except Exception as e:
        print(f"    ❌ 交易决策 failed: {e}")
        results["call4"] = {"error": str(e)}

    direction = results.get("call4", {}).get("trade_decision", {}).get("direction", "N/A")
    print(f"  ✅ SimAnalyzer: {coin} 完成 — {direction}")
    return results


# ═══════════════════════════════════════════
#  VOLATILITY EVENT ANALYSIS
# ═══════════════════════════════════════════

async def analyze_volatility_event(coin: str, price: float, change_pct: float, position: dict) -> str:
    prompt = (
        f"{coin} 短时间内{'上涨' if change_pct > 0 else '下跌'} {abs(change_pct):.1f}%，现价 ${price}。\n"
        f"持仓: {position['direction']} | 入场价: ${position['entry_price']}\n"
        "请搜索最新信息分析：1.触发原因 2.是否可持续 3.对持仓影响\n"
        "中文200字以内，不要JSON。"
    )
    try:
        return await _gemini_call(prompt)
    except Exception as e:
        return f"分析失败: {e}"


# ═══════════════════════════════════════════
#  POST-TRADE REVIEW (9-dimension based)
# ═══════════════════════════════════════════

async def review_trade_factors(position: dict, snapshots: list, events: list) -> dict:
    """Professional post-trade analysis using K-line data + news from entry to exit."""
    coin = position.get("coin", "UNKNOWN")

    # Build price path from snapshots
    price_path = ""
    kline_summary = ""
    if snapshots:
        prices = [s["price"] for s in snapshots]
        price_path = (
            f"入场: ${position['entry_price']} → 最低: ${min(prices):.6f} → 最高: ${max(prices):.6f} → "
            f"平仓: ${position['exit_price']} (最终: {position.get('pnl_pct',0):+.1f}%)\n"
            f"MAE(最大回撤): {position.get('mae',0):+.1f}% | MFE(最大浮盈): {position.get('mfe',0):+.1f}% | 持仓: {len(snapshots)}分钟"
        )
        # Sample every N snapshots to create kline-like data
        step = max(1, len(snapshots) // 30)
        sampled = snapshots[::step][:30]
        kline_lines = []
        for s in sampled:
            kline_lines.append(f"时间:{s.get('timestamp','?')[:16]} 价格:${s['price']:.6f}")
        kline_summary = "\n".join(kline_lines)

    # Fetch actual K-line data for the trade period from OKX
    trade_klines = ""
    try:
        swap_id = f"{coin}-USDT-SWAP"
        kb = await _okx_get("/api/v5/market/candles", {"instId": swap_id, "bar": "1H", "limit": "100"})
        if kb and kb.get("data"):
            lines = []
            for k in kb["data"][:48]:
                lines.append(f"{k[0]}|O:{k[1]}|H:{k[2]}|L:{k[3]}|C:{k[4]}|V:{k[5]}")
            trade_klines = "\n".join(lines)
    except Exception:
        pass

    events_text = "\n".join([f"[{e['timestamp'][:16]}] {e['event_type']}: ${e['price']} {(e.get('ai_analysis',''))[:100]}" for e in events]) if events else "无事件记录"
    factors_text = "\n".join([f"因子{i+1}: {f['description']} ({f['bias']})" for i, f in enumerate(position.get("factors", []))])

    is_profit = position.get('pnl', 0) > 0

    prompt = (
        f"你是一位顶级专业合约交易员，正在对 {coin} 的一笔已平仓交易做全面复盘分析。\n\n"
        f"=== 交易概况 ===\n"
        f"方向: {position['direction']} {position['leverage']}x | "
        f"结果: {'✅ 盈利' if is_profit else '❌ 亏损'} {position.get('pnl_pct',0):+.1f}% (${position.get('pnl',0):+.2f})\n"
        f"{price_path}\n\n"
        f"=== 持仓期间价格快照 ===\n{kline_summary or '无数据'}\n\n"
        f"=== 近期1H K线数据 ===\n{trade_klines or '无数据'}\n\n"
        f"=== 持仓期间事件 ===\n{events_text}\n\n"
        f"=== 入场时的分析因子 ===\n{factors_text or '无因子记录'}\n\n"
        "请你作为专业交易员，对这笔交易进行全面复盘。搜索这段时间的最新信息。\n\n"
        "你需要回答：\n"
        "1. 整体判断：我们的入场分析是否准确？准确率打分(1-10)\n"
        "2. 如果准确：哪些因素使行情按我们分析的方向走？具体列出\n"
        "3. 如果错误：哪些因素导致行情偏离了我们的分析？具体列出\n"
        "4. 技术面实际表现：持仓期间出现了什么K线形态？量价关系？支撑阻力是否有效？关键技术指标(RSI/MACD/BB等)怎么走的？\n"
        "5. 信息面影响：持仓期间有什么新闻/事件实际影响了行情？是利好还是利空？\n"
        "6. 最佳操作：如果你是专业交易员，面对同样的行情，你会怎么做？最优入场点、平仓点、仓位管理\n"
        "7. 可复用的教训和规则\n\n"
        "严格按以下JSON返回：\n"
        '{"accuracy_verdict":"准确/部分准确/错误",'
        '"accuracy_score":7,'
        '"accuracy_reason":"为什么判断准确或错误的一句话总结",'
        '"correct_factors":["使行情按分析走的因素1","因素2"],'
        '"wrong_factors":["导致分析偏差的因素1","因素2"],'
        '"technical_review":{"candlestick_patterns":"持仓期间实际出现的K线形态","volume_price":"量价关系表现","support_resistance":"支撑阻力是否有效","key_indicators":"RSI/MACD/BB等关键指标走势","market_structure":"市场结构变化"},'
        '"news_review":{"events":[{"news":"具体新闻","impact":"利好/利空","effect":"对价格的实际影响"}],"overall":"信息面整体影响"},'
        '"professional_opinion":{"optimal_entry":"最优入场点和时机","optimal_exit":"最优平仓点","position_management":"最优仓位管理策略","what_i_would_do":"如果我是专业交易员我会怎么做"},'
        '"key_lesson":"这笔交易最重要的一个教训",'
        '"reusable_rule":"可复用的交易规则",'
        '"what_if":"如果重来我会怎么做"}'
    )
    try:
        return _parse_json(await _gemini_call(prompt))
    except Exception as e:
        return {"error": str(e)}
