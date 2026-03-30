"""Report generation orchestrator - ties together data, indicators, and AI."""

import traceback
from datetime import datetime
from app.core.config import settings
from app.core.database import save_report
from app.models.schemas import AnalysisReport
from app.services.market_data import get_market_data_binance, fetch_cmc_batch, fetch_fear_greed
from app.services.technical import calculate_indicators, empty_indicators
from app.services.gemini_analyzer import analyze_symbol


async def generate_report_for_symbol(symbol: str) -> AnalysisReport | None:
    """Generate a full analysis report for one symbol."""
    try:
        print(f"[{datetime.now():%H:%M:%S}] Generating report for {symbol}...")

        # 1. Fetch market data (Binance first, then CoinMarketCap batch fallback)
        market = await get_market_data_binance(symbol)
        if not market:
            cmc_batch = await fetch_cmc_batch()
            market = cmc_batch.get(symbol)
        if not market:
            print(f"  ✗ No market data available for {symbol}")
            return None
        print(f"  ✓ Market data: ${market.price:,.2f}")

        # 2. Calculate technical indicators locally (may fail if Binance klines blocked)
        try:
            indicators = await calculate_indicators(symbol, interval="4h")
            print(f"  ✓ Technical indicators: RSI={indicators.rsi}")
        except Exception as te:
            print(f"  ⚠ Technical indicators unavailable ({te}), using AI search instead")
            indicators = empty_indicators(symbol)

        # 3. Fetch fear & greed index
        fear_greed = await fetch_fear_greed()
        print(f"  ✓ Fear & Greed: {fear_greed.value} ({fear_greed.label})")

        # 4. Run Gemini AI analysis with Search Grounding
        report = await analyze_symbol(market, indicators, fear_greed)
        print(f"  ✓ AI Analysis: {report.signal.direction} (confidence: {report.signal.confidence})")

        # 5. Save to database
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

    reports = []
    for symbol in settings.SYMBOLS:
        report = await generate_report_for_symbol(symbol)
        if report:
            reports.append(report)

    print(f"\n  Completed: {len(reports)}/{len(settings.SYMBOLS)} reports generated")
    print(f"{'='*60}\n")
    return reports

