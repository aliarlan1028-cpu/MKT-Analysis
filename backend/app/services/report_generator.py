"""Report generation orchestrator - ties together data, indicators, and AI.

Enriched pipeline: multi-TF indicators, real key levels, news, BTC context.
"""

import asyncio
import traceback
import httpx
from datetime import datetime
from app.core.config import settings
from app.core.database import save_report
from app.models.schemas import AnalysisReport
from app.services.market_data import get_market_data_binance, fetch_cmc_batch, fetch_fear_greed
from app.services.technical import (
    calculate_multi_tf, calculate_key_levels, empty_indicators,
    format_multi_tf_for_prompt, format_key_levels_for_prompt,
)
from app.services.gemini_analyzer import analyze_symbol


# ── News fetcher (free, no API key) ──

async def fetch_crypto_news(symbol: str = "BTC", limit: int = 8) -> str:
    """Fetch latest crypto news headlines from CryptoCompare (free, no key)."""
    try:
        category_map = {
            "BTCUSDT": "BTC", "SOLUSDT": "SOL,Solana", "SUIUSDT": "SUI",
        }
        cats = category_map.get(symbol, "BTC")
        url = f"https://min-api.cryptocompare.com/data/v2/news/?lang=EN&categories={cats}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        articles = data.get("Data", [])[:limit]
        if not articles:
            return "暂无相关新闻"
        lines = []
        for i, a in enumerate(articles, 1):
            title = a.get("title", "")
            source = a.get("source", "")
            lines.append(f"{i}. [{source}] {title}")
        return "\n".join(lines)
    except Exception as e:
        print(f"  ⚠ News fetch failed: {e}")
        return "新闻获取失败"


# ── BTC context for altcoins ──

async def _get_btc_context() -> str:
    """Get BTC's current state as context for altcoin analysis."""
    try:
        btc_market = await get_market_data_binance("BTCUSDT")
        if not btc_market:
            return "BTC数据不可用"
        btc_tf = await calculate_multi_tf("BTCUSDT")
        btc_4h = btc_tf.get("4h")
        btc_1d = btc_tf.get("1d")
        trend_4h = "多头" if (btc_4h and btc_4h.ema_21 and btc_4h.ema_55 and btc_4h.ema_21 > btc_4h.ema_55) else "空头"
        trend_1d = "多头" if (btc_1d and btc_1d.ema_21 and btc_1d.ema_55 and btc_1d.ema_21 > btc_1d.ema_55) else "空头"
        return (
            f"=== BTC关联背景 ===\n"
            f"BTC价格: ${btc_market.price:,.2f} | 24h涨跌: {btc_market.price_change_pct_24h}%\n"
            f"BTC资金费率: {btc_market.funding_rate} | 多空比: {btc_market.long_short_ratio}\n"
            f"BTC 4h趋势: {trend_4h} (RSI={btc_4h.rsi if btc_4h else 'N/A'}) | 日线趋势: {trend_1d} (RSI={btc_1d.rsi if btc_1d else 'N/A'})\n"
            f"⚠ 山寨币高度关联BTC，BTC方向变化将直接影响本币走势"
        )
    except Exception as e:
        print(f"  ⚠ BTC context fetch failed: {e}")
        return "BTC关联数据获取失败"


async def generate_report_for_symbol(symbol: str, btc_context: str = "") -> AnalysisReport | None:
    """Generate a full analysis report for one symbol."""
    try:
        print(f"[{datetime.now():%H:%M:%S}] Generating report for {symbol}...")

        # 1. Fetch market data
        market = await get_market_data_binance(symbol)
        if not market:
            cmc_batch = await fetch_cmc_batch()
            market = cmc_batch.get(symbol)
        if not market:
            print(f"  ✗ No market data available for {symbol}")
            return None
        print(f"  ✓ Market data: ${market.price:,.2f}")

        # 2. Parallel fetch: multi-TF indicators + key levels + news
        try:
            multi_tf_task = calculate_multi_tf(symbol)
            key_levels_task = calculate_key_levels(symbol)
            news_task = fetch_crypto_news(symbol)
            multi_tf, key_levels, news_text = await asyncio.gather(
                multi_tf_task, key_levels_task, news_task
            )
            indicators = multi_tf.get("4h", empty_indicators(symbol))  # primary TF for schema
            multi_tf_text = format_multi_tf_for_prompt(multi_tf)
            key_levels_text = format_key_levels_for_prompt(key_levels)
            print(f"  ✓ Multi-TF indicators: 1h/4h/1D (RSI_4h={indicators.rsi})")
            print(f"  ✓ Key levels: {len(key_levels.get('swing_highs', []))} resistance, {len(key_levels.get('swing_lows', []))} support")
            print(f"  ✓ News: {news_text[:60]}...")
        except Exception as te:
            print(f"  ⚠ Enriched data partially failed ({te}), using basic mode")
            indicators = empty_indicators(symbol)
            multi_tf_text = ""
            key_levels_text = ""
            key_levels = {}
            news_text = ""

        # 3. Fetch fear & greed index
        fear_greed = await fetch_fear_greed()
        print(f"  ✓ Fear & Greed: {fear_greed.value} ({fear_greed.label})")

        # 4. Build enriched context
        enriched_context = {
            "multi_tf_text": multi_tf_text,
            "key_levels_text": key_levels_text,
            "key_levels": key_levels,
            "news_text": news_text,
            "btc_context": btc_context,
        }

        # 5. Run Gemini AI analysis (with retry)
        report = None
        last_err = None
        for attempt in range(3):
            try:
                report = await analyze_symbol(market, indicators, fear_greed, enriched_context)
                print(f"  ✓ Gemini Analysis: {report.signal.direction} (confidence: {report.signal.confidence})")
                break
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if "429" in err_str or "resource_exhausted" in err_str or "503" in err_str or "unavailable" in err_str:
                    delay = 5 * (2 ** attempt)
                    print(f"  ⚠ Gemini attempt {attempt+1}/3 failed (rate limit), retry in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    print(f"  ✗ Gemini failed: {e}")
                    traceback.print_exc()
                    return None
        if not report and last_err:
            print(f"  ✗ All Gemini retries failed: {last_err}")
            return None

        if not report:
            return None

        # 6. Save to database
        save_report(report)
        print(f"  ✓ Saved to database: {report.id}")
        return report

    except Exception as e:
        print(f"  ✗ Error generating report for {symbol}: {e}")
        traceback.print_exc()
        return None


async def generate_all_reports() -> list[AnalysisReport]:
    """Generate reports for all tracked symbols. Called by scheduler."""
    print(f"\n{'='*60}")
    print(f"  Starting scheduled analysis at {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"{'='*60}")

    # Pre-fetch BTC context once for altcoins
    btc_context = ""
    if any(s != "BTCUSDT" for s in settings.SYMBOLS):
        print("  📊 Fetching BTC context for altcoin analysis...")
        btc_context = await _get_btc_context()
        print(f"  ✓ BTC context ready")

    reports = []
    for symbol in settings.SYMBOLS:
        ctx = btc_context if symbol != "BTCUSDT" else ""
        report = await generate_report_for_symbol(symbol, btc_context=ctx)
        if report:
            reports.append(report)

    print(f"\n  Completed: {len(reports)}/{len(settings.SYMBOLS)} reports generated")
    print(f"{'='*60}\n")
    return reports

