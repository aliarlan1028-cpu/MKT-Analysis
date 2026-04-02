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
from app.services.technical import format_indicators_for_prompt, format_multi_tf_for_prompt, format_key_levels_for_prompt
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


async def _fetch_funding_rate_history(inst_id: str, limit: int = 30) -> list[dict]:
    """Fetch funding rate history from OKX (up to 30 recent entries, every 8h)."""
    body = await _okx_get("/api/v5/public/funding-rate-history", {
        "instId": inst_id, "limit": str(min(limit, 100))
    })
    if not body or not body.get("data"):
        return []
    result = []
    for r in body["data"]:
        ts = int(r["fundingTime"]) / 1000
        dt = datetime.utcfromtimestamp(ts)
        result.append({
            "time": dt.strftime("%m-%d %H:%M"),
            "rate": round(float(r.get("realizedRate", r.get("fundingRate", 0))) * 100, 4),
        })
    return result[::-1]  # ASC order


def _detect_multi_leg_pumps(klines: list[dict]) -> list[dict]:
    """Detect multi-leg pump patterns: pump→consolidate→pump again."""
    if len(klines) < 10:
        return []
    legs = []
    i = 0
    while i < len(klines):
        # Look for a pump leg (cumulative >15% over 1-5 days)
        if klines[i]["change_pct"] >= 5:
            leg_start = i
            leg_gain = 0
            while i < len(klines) and klines[i]["change_pct"] > -2:
                leg_gain += klines[i]["change_pct"]
                i += 1
            if leg_gain >= 15:
                legs.append({
                    "start": klines[leg_start]["date"],
                    "end": klines[min(i - 1, len(klines) - 1)]["date"],
                    "gain_pct": round(leg_gain, 1),
                    "days": i - leg_start,
                })
        else:
            i += 1
    # Multi-leg = 2+ legs within 30-day window
    multi_legs = []
    for idx, leg in enumerate(legs):
        if idx > 0:
            multi_legs.append({"leg_1": legs[idx - 1], "leg_2": leg})
    return multi_legs[-3:]


def _analyze_volume_trend(klines: list[dict]) -> dict:
    """Analyze volume acceleration/deceleration patterns."""
    if len(klines) < 10:
        return {}
    vols = [k["vol_usd"] for k in klines if k["vol_usd"] > 0]
    if len(vols) < 10:
        return {}

    avg_vol_30d = sum(vols[-30:]) / len(vols[-30:]) if len(vols) >= 30 else sum(vols) / len(vols)
    avg_vol_7d = sum(vols[-7:]) / len(vols[-7:]) if len(vols) >= 7 else avg_vol_30d
    avg_vol_3d = sum(vols[-3:]) / len(vols[-3:]) if len(vols) >= 3 else avg_vol_7d

    # Volume on up days vs down days (last 14 days)
    recent = klines[-14:]
    up_vol = sum(k["vol_usd"] for k in recent if k["change_pct"] > 0) or 1
    down_vol = sum(k["vol_usd"] for k in recent if k["change_pct"] < 0) or 1

    return {
        "vol_ratio_7d_vs_30d": round(avg_vol_7d / avg_vol_30d, 2) if avg_vol_30d else 1,
        "vol_ratio_3d_vs_7d": round(avg_vol_3d / avg_vol_7d, 2) if avg_vol_7d else 1,
        "up_down_vol_ratio": round(up_vol / down_vol, 2),
        "trend": "放量" if avg_vol_3d > avg_vol_7d * 1.3 else ("缩量" if avg_vol_3d < avg_vol_7d * 0.7 else "平稳"),
    }


def _assess_consolidation_quality(klines: list[dict]) -> dict:
    """After a big move, assess if consolidation is healthy (accumulation) or unhealthy (distribution)."""
    if len(klines) < 7:
        return {}
    # Find the last big move (>10% over 3 days)
    for i in range(len(klines) - 4, max(len(klines) - 30, 0), -1):
        cum = sum(klines[j]["change_pct"] for j in range(i, min(i + 3, len(klines))))
        if abs(cum) >= 10:
            after = klines[min(i + 3, len(klines) - 1):]
            if len(after) < 2:
                continue
            # Consolidation metrics
            avg_vol_move = sum(klines[j]["vol_usd"] for j in range(i, min(i + 3, len(klines)))) / 3
            avg_vol_after = sum(k["vol_usd"] for k in after) / len(after) if after else avg_vol_move
            max_pullback = min(k["change_pct"] for k in after) if after else 0
            avg_change = sum(k["change_pct"] for k in after) / len(after) if after else 0
            move_type = "拉升" if cum > 0 else "暴跌"
            # Low-volume pullback after pump = healthy accumulation
            # High-volume pullback after pump = distribution (unhealthy)
            vol_ratio = round(avg_vol_after / avg_vol_move, 2) if avg_vol_move else 1
            quality = "健康蓄力" if (cum > 0 and vol_ratio < 0.6 and max_pullback > -5) else \
                      "出货迹象" if (cum > 0 and vol_ratio > 1.0) else \
                      "恐慌未止" if (cum < 0 and vol_ratio > 0.8) else \
                      "超跌反弹可能" if (cum < 0 and vol_ratio < 0.5) else "中性"
            return {
                "last_big_move": f"{move_type}{cum:+.1f}%",
                "consolidation_days": len(after),
                "vol_ratio_vs_move": vol_ratio,
                "max_pullback_pct": round(max_pullback, 2),
                "quality": quality,
            }
    return {}


def _analyze_funding_signals(funding_history: list[dict]) -> dict:
    """Analyze funding rate patterns for squeeze/liquidation signals."""
    if len(funding_history) < 3:
        return {}
    rates = [f["rate"] for f in funding_history]
    avg_rate = round(sum(rates) / len(rates), 4)
    latest_rate = rates[-1] if rates else 0
    # Consecutive negative = short squeeze building
    consecutive_neg = 0
    for r in reversed(rates):
        if r < 0:
            consecutive_neg += 1
        else:
            break
    consecutive_pos = 0
    for r in reversed(rates):
        if r > 0:
            consecutive_pos += 1
        else:
            break
    # Extreme funding
    extreme_neg = sum(1 for r in rates if r < -0.05)
    extreme_pos = sum(1 for r in rates if r > 0.1)

    signal = "中性"
    if consecutive_neg >= 4 and latest_rate < -0.01:
        signal = "空头拥挤→逼空风险"
    elif consecutive_pos >= 4 and latest_rate > 0.05:
        signal = "多头拥挤→清算风险"
    elif avg_rate < -0.02:
        signal = "整体偏空→反弹潜力"
    elif avg_rate > 0.08:
        signal = "整体偏多→回调压力"

    return {
        "avg_rate": avg_rate,
        "latest_rate": latest_rate,
        "consecutive_negative": consecutive_neg,
        "consecutive_positive": consecutive_pos,
        "extreme_negative_count": extreme_neg,
        "extreme_positive_count": extreme_pos,
        "signal": signal,
        "recent_5": [f"{f['time']}:{f['rate']:+.4f}%" for f in funding_history[-5:]],
    }


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

    # Post-pump continuation: after >10% pump, did it continue up in next 5 days?
    pump_continuation = []
    for i, k in enumerate(klines):
        if k["change_pct"] >= 10 and i + 5 < len(klines):
            next_5d_change = sum(klines[j]["change_pct"] for j in range(i + 1, i + 6))
            pump_continuation.append({
                "pump_date": k["date"],
                "pump_pct": k["change_pct"],
                "next_5d_pct": round(next_5d_change, 1),
                "continued": next_5d_change > 5,
            })

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
        "pump_continuation": pump_continuation[-3:],
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
    """Analyze a scanner candidate with DeepSeek + historical data + market maker behavior."""
    if not settings.DEEPSEEK_API_KEY:
        return None

    import asyncio
    direction = "潜力拉升" if category == "pre_pump" else "暴跌预警"
    coin_name = coin.get("coin", "UNKNOWN")
    inst_id = f"{coin_name}-USDT-SWAP"

    # Parallel fetch: 90-day klines + funding rate history
    klines_task = _fetch_daily_klines(inst_id, 90)
    funding_task = _fetch_funding_rate_history(inst_id, 30)
    daily_klines, funding_history = await asyncio.gather(klines_task, funding_task)

    hist = _compute_historical_stats(daily_klines) if daily_klines else {}
    vol_trend = _analyze_volume_trend(daily_klines) if daily_klines else {}
    multi_legs = _detect_multi_leg_pumps(daily_klines) if daily_klines else []
    consolidation = _assess_consolidation_quality(daily_klines) if daily_klines else {}
    funding_signals = _analyze_funding_signals(funding_history) if funding_history else {}

    system_prompt = (
        "你是一位顶级加密货币合约交易分析师，专注于庄家行为分析和做市商操盘模式识别。"
        "你会收到代币的实时指标、90天历史K线统计、资金费率走势、量能趋势、"
        "多段式拉盘检测、横盘蓄力质量评估等多维度真实数据。"
        "请基于这些数据深度分析庄家意图，判断当前走势是否可持续（继续涨或继续跌），"
        "特别关注：已经涨了很多的币是否还有继续涨的动力，已经跌了很多的币是否还会继续跌。"
        "必须严格按JSON格式返回，不要包含markdown代码块标记。"
    )

    # ── Build comprehensive context ──
    ctx = ""

    # 1. Historical K-line stats
    if hist:
        ctx += f"\n=== 历史K线（近{hist.get('total_days', 0)}天）===\n"
        ctx += f"90日高/低: ${hist.get('high_90d', 0):,.4f} / ${hist.get('low_90d', 0):,.4f}\n"
        ctx += f"当前在区间位置: {hist.get('position_in_range_pct', 0)}%\n"
        ctx += f"日均振幅: {hist.get('avg_daily_amplitude', 0)}% | 最大: {hist.get('max_daily_amplitude', 0)}%\n"
        ctx += f"7日趋势: {hist.get('trend_7d_pct', 0):+.1f}% | 30日: {hist.get('trend_30d_pct', 0):+.1f}%\n"

        pumps = hist.get("big_pumps", [])
        if pumps:
            pump_strs = ", ".join(p["date"] + "+" + str(p["pct"]) + "%" for p in pumps)
            ctx += f"大涨事件(>8%): {pump_strs}\n"
        dumps = hist.get("big_dumps", [])
        if dumps:
            dump_strs = ", ".join(d["date"] + str(d["pct"]) + "%" for d in dumps)
            ctx += f"大跌事件(>8%): {dump_strs}\n"

        pd_events = hist.get("pump_dump_events", [])
        if pd_events:
            pd_strs = "; ".join(e["pump_date"] + "+" + str(e["pump_pct"]) + "%→" + e["dump_date"] + str(e["dump_pct"]) + "%" for e in pd_events)
            ctx += f"拉盘→砸盘: {pd_strs}\n"

        # NEW: Post-pump continuation stats
        pc = hist.get("pump_continuation", [])
        if pc:
            ctx += f"\n--- 大涨后续走势（涨>10%后5天表现）---\n"
            for p in pc:
                label = "✅继续涨" if p["continued"] else "❌回落"
                ctx += f"  {p['pump_date']} 涨+{p['pump_pct']}% → 后5天{p['next_5d_pct']:+.1f}% {label}\n"
            cont_rate = sum(1 for p in pc if p["continued"]) / len(pc) * 100
            ctx += f"  历史大涨后继续上涨概率: {cont_rate:.0f}%\n"

        recent = hist.get("recent_10d_klines", [])
        if recent:
            ctx += f"近10天: {' | '.join(recent)}\n"

    # 2. Volume trend analysis
    if vol_trend:
        ctx += f"\n=== 量能趋势 ===\n"
        ctx += f"3日/7日量比: {vol_trend.get('vol_ratio_3d_vs_7d', 'N/A')}x | "
        ctx += f"7日/30日量比: {vol_trend.get('vol_ratio_7d_vs_30d', 'N/A')}x\n"
        ctx += f"涨日/跌日成交量比: {vol_trend.get('up_down_vol_ratio', 'N/A')}x\n"
        ctx += f"量能状态: {vol_trend.get('trend', 'N/A')}\n"

    # 3. Multi-leg pump detection
    if multi_legs:
        ctx += f"\n=== 多段式拉盘检测 ===\n"
        for ml in multi_legs:
            ctx += f"  第1段: {ml['leg_1']['start']}~{ml['leg_1']['end']} +{ml['leg_1']['gain_pct']}%({ml['leg_1']['days']}天)\n"
            ctx += f"  第2段: {ml['leg_2']['start']}~{ml['leg_2']['end']} +{ml['leg_2']['gain_pct']}%({ml['leg_2']['days']}天)\n"

    # 4. Consolidation quality
    if consolidation:
        ctx += f"\n=== 横盘蓄力评估 ===\n"
        ctx += f"最近大波动: {consolidation.get('last_big_move', 'N/A')}\n"
        ctx += f"横盘天数: {consolidation.get('consolidation_days', 0)} | "
        ctx += f"量比(vs大波动): {consolidation.get('vol_ratio_vs_move', 'N/A')}x\n"
        ctx += f"最大回撤: {consolidation.get('max_pullback_pct', 0)}%\n"
        ctx += f"蓄力质量: {consolidation.get('quality', 'N/A')}\n"

    # 5. Funding rate signals
    if funding_signals:
        ctx += f"\n=== 资金费率分析 ===\n"
        ctx += f"平均费率: {funding_signals.get('avg_rate', 0):+.4f}% | "
        ctx += f"最新: {funding_signals.get('latest_rate', 0):+.4f}%\n"
        ctx += f"连续负费率: {funding_signals.get('consecutive_negative', 0)}期 | "
        ctx += f"连续正费率: {funding_signals.get('consecutive_positive', 0)}期\n"
        ctx += f"信号: {funding_signals.get('signal', 'N/A')}\n"
        recent_fr = funding_signals.get("recent_5", [])
        if recent_fr:
            ctx += f"近5期: {', '.join(recent_fr)}\n"

    # ── Category-specific analysis questions ──
    if category == "pre_pump":
        analysis_questions = (
            "请重点分析以下庄家行为特征:\n"
            "1. 该币已经涨了不少，是否还有继续上涨的动力？具体依据是什么？\n"
            "   - 资金费率是否偏低/负值（空头拥挤→逼空）？\n"
            "   - 历史上大涨后是否有多段式继续拉升的习惯？\n"
            "   - 当前横盘是健康蓄力还是出货？\n"
            "   - 量能是否在递增（新资金入场）？\n"
            "2. 庄家操盘风格判断：这个币的庄家是快拉快砸型、缓慢拉升型、还是多段蓄力型？\n"
            "3. 最可能的后续走势及概率\n"
        )
    else:
        analysis_questions = (
            "请重点分析以下庄家行为特征:\n"
            "1. 该币已经跌了不少，是否还会继续下跌？具体依据是什么？\n"
            "   - 资金费率是否偏高（多头拥挤→清算瀑布）？\n"
            "   - 历史上大跌后是否有连续砸盘的习惯？\n"
            "   - 反弹量能是否充足（缩量反弹=死猫跳）？\n"
            "   - 是否出现恐慌性抛售特征？\n"
            "2. 庄家操盘风格判断：这个币的庄家是快速砸盘型、阶梯式出货型、还是洗盘吸筹型？\n"
            "3. 最可能的后续走势及概率\n"
        )

    user_prompt = (
        f"以下代币被扫描器标记为【{direction}】候选，请深度分析庄家行为:\n\n"
        f"=== {coin_name}-USDT 实时数据 ===\n"
        f"价格: ${coin.get('price', 0)} | 24h: {coin.get('change_pct_24h', 0)}%\n"
        f"24h成交量: ${coin.get('volume_24h', 0):,.0f}\n"
        f"持仓量: {coin.get('open_interest', 0)}\n"
        f"资金费率: {coin.get('funding_rate', 'N/A')}\n"
        f"RSI: {coin.get('rsi', 'N/A')} | BB宽度: {coin.get('bb_width', 'N/A')}\n"
        f"量比: {coin.get('volume_ratio', 'N/A')}\n"
        f"7日涨幅: {coin.get('cumulative_return_7d', 0)}% | EMA偏离: {coin.get('ema_deviation_pct', 0)}%\n"
        f"连涨天数: {coin.get('consecutive_up_days', 0)} | 评分: {coin.get('score', 0)}/100\n"
        f"{ctx}\n"
        f"{analysis_questions}\n"
        f"返回JSON格式:\n"
        f'{{"verdict":"看涨/看跌/观望",'
        f'"confidence":75,'
        f'"reasoning":"基于庄家行为和历史数据的深度分析(100-200字，必须引用具体数据)",'
        f'"market_style":"庄家操盘风格总结(40-80字)",'
        f'"historical_pattern":"当前走势与历史模式对比+后续走势概率(40-80字)",'
        f'"continuation_signal":"继续涨/跌的信号强度和依据(30-60字)",'
        f'"key_support":[价位1,价位2],'
        f'"key_resistance":[价位1,价位2],'
        f'"entry_price":具体入场价格(数字),'
        f'"stop_loss":止损价格(数字),'
        f'"take_profit_1":第一止盈目标(数字,2:1盈亏比),'
        f'"take_profit_2":第二止盈目标(数字,3:1盈亏比),'
        f'"suggestion":"具体交易建议(30-60字)",'
        f'"risk_warning":"主要风险(20-40字)"}}'
    )

    try:
        raw = await _deepseek_chat(system_prompt, user_prompt, temperature=0.5, max_tokens=2048)
        result = _parse_json(raw)
        result["source"] = "deepseek"
        data_depth = f"K线{hist.get('total_days', 0)}天+费率{len(funding_history)}期"
        print(f"  🤖 DeepSeek分析 {coin_name}: {result.get('verdict', 'N/A')} ({data_depth})")
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
    enriched_context: dict | None = None,
) -> AnalysisReport:
    """Generate analysis report using DeepSeek (Gemini fallback).

    Enhanced with: multi-TF indicators, real key levels, news, BTC context.
    """
    session = _get_session_name()
    label = SESSION_LABELS.get(session, session)
    ind_text = format_indicators_for_prompt(indicators)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Extract enriched context
    multi_tf_text = enriched_context.get("multi_tf_text", "") if enriched_context else ""
    key_levels_text = enriched_context.get("key_levels_text", "") if enriched_context else ""
    news_text = enriched_context.get("news_text", "") if enriched_context else ""
    btc_context = enriched_context.get("btc_context", "") if enriched_context else ""

    system_prompt = (
        "你是一位顶级加密货币合约交易分析师，精通多时间框架分析、量价关系和技术形态识别。"
        "你将收到丰富的多维度数据(多时间框架指标、真实关键价位、最新新闻)。"
        "请基于这些数据进行专业级分析，不要猜测没有数据支持的结论。"
        "必须严格按指定的JSON格式返回，不要包含markdown代码块标记。中文回复但JSON key保持英文。"
    )

    json_schema = (
        '{"signal":{"direction":"LONG/SHORT/NEUTRAL","confidence":72,'
        '"entry_zone":[84200,84500],"stop_loss":83400,'
        '"take_profit":[85800,87200],"leverage_suggestion":"3x-5x",'
        '"risk_reward_ratio":2.5},'
        '"technical":{"title":"技术面分析","content":"多时间框架综合判断","bullets":["日线趋势","4h结构","1h入场时机","量价背离检测"],"key_support":[83000,82500],"key_resistance":[86000,87500]},'
        '"fundamental":{"title":"基本面/新闻分析","content":"基于最新新闻的判断","bullets":["新闻要点1","新闻要点2"]},'
        '"sentiment":{"title":"情绪面分析","content":"资金费率+多空比+恐贪指数综合判断","bullets":["要点1","要点2"]},'
        '"macro":{"title":"宏观面分析","content":"基于新闻中的宏观线索推断","bullets":["要点1","要点2"]},'
        '"risk_warning":{"title":"风险提示","content":"风险总结","bullets":["风险1","风险2"]},'
        '"calendar_events":[{"date":"2026-04-03","time":"20:30","title":"美国非农就业数据",'
        '"impact":"HIGH","category":"economic","previous":"15.1万",'
        '"forecast":"16.0万","description":"影响说明",'
        '"impact_if_met":"达到或超预期: 对加密市场利好/利空分析",'
        '"impact_if_missed":"不及预期: 对加密市场利好/利空分析"}]}'
    )

    # Build rich data section
    data_section = (
        f"当前时间: {now_str} (北京时间)\n分析时段: {label}\n\n"
        f"=== {market.name} ({market.symbol}) 实时数据 ===\n"
        f"当前价格: ${market.price:,.2f}\n"
        f"24h涨跌: {market.price_change_pct_24h}%\n"
        f"24h最高/最低: ${market.high_24h:,.2f} / ${market.low_24h:,.2f}\n"
        f"24h成交量: ${market.volume_24h:,.0f}\n"
        f"资金费率: {market.funding_rate}\n"
        f"多空比(大户): {market.long_short_ratio}\n"
        f"未平仓量: {market.open_interest} ({market.open_interest_change_pct}% 变化)\n\n"
    )

    if multi_tf_text:
        data_section += f"=== 多时间框架技术分析 ===\n{multi_tf_text}\n\n"
    else:
        data_section += f"=== 技术指标 ===\n{ind_text}\n\n"

    if key_levels_text:
        data_section += f"{key_levels_text}\n\n"

    if btc_context:
        data_section += f"{btc_context}\n\n"

    data_section += (
        f"=== 市场情绪 ===\n"
        f"恐慌贪婪指数: {fear_greed.value} ({fear_greed.label})\n\n"
    )

    has_news = news_text and news_text not in ("暂无相关新闻", "新闻获取失败")
    if has_news:
        data_section += f"=== 最新新闻(请据此分析基本面和宏观面) ===\n{news_text}\n\n"

    news_instruction = (
        "4. **新闻驱动**: 结合提供的新闻判断基本面方向\n"
        if has_news else
        "4. **基本面分析**: 请根据你对该币种近期基本面的了解进行分析(项目进展、生态发展、链上活跃度等)\n"
    )
    fundamental_note = (
        "- fundamental部分请基于提供的新闻进行分析\n"
        if has_news else
        "- fundamental部分请基于你对该币种的知识进行基本面分析，不要说'无法搜索'或'新闻获取失败'\n"
    )

    user_prompt = (
        f"{data_section}"
        "=== 分析要求 ===\n"
        "请严格遵循专业交易分析框架:\n"
        "1. **多时间框架共振**: 日线定方向→4h找结构→1h抓入场\n"
        "2. **真实关键价位**: entry/SL/TP必须参考上方提供的摆动高低点和Fib回撤位，不要凭空编造\n"
        "3. **量价验证**: ADX判断趋势强度，OBV确认资金流向，VWAP作为机构成本参考\n"
        f"{news_instruction}"
        "5. **风险控制**: 如果多TF方向矛盾，降低confidence并说明\n\n"
        f"请严格按以下JSON格式返回:\n{json_schema}\n\n"
        "注意:\n"
        "- 所有价格用美元保留小数点后2位\n"
        "- confidence反映你对该方向判断的把握程度(0-100)\n"
        "- technical的key_support和key_resistance必须基于提供的摆动高低点\n"
        f"{fundamental_note}"
        "- calendar_events请列出未来7天内美国重大经济数据和事件(非农、CPI、FOMC、初请失业金等)\n"
        "- 每个calendar_event必须包含impact_if_met和impact_if_missed两个字段"
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

