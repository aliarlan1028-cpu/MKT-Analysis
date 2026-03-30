"""API routes for the crypto analysis platform."""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.core.config import settings
from app.core.database import get_latest_reports, get_report_by_id
from app.models.schemas import (
    AnalysisReport, DashboardResponse, ReportListItem, FearGreedIndex,
    PostMortem, WhaleAlertResponse, LiquidationMap, CorrelationMatrix,
)
from app.services.market_data import get_all_markets, get_market_data_binance, fetch_fear_greed, fetch_cmc_batch
from app.services.report_generator import generate_report_for_symbol, generate_all_reports
from app.services.postmortem import get_postmortems, get_win_rate, evaluate_all_expired
from app.services.whale_alert import get_whale_alerts
from app.services.liquidation import get_liquidation_map, get_all_liquidation_maps
from app.services.correlation import get_correlation_matrix
from app.services.price_spike import get_spike_alerts

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard():
    """Get real-time market data for all tracked symbols."""
    markets = await get_all_markets()
    fear_greed = await fetch_fear_greed()
    return DashboardResponse(
        markets=markets,
        fear_greed=fear_greed,
        last_updated=datetime.now(timezone.utc),
    )


@router.get("/reports", response_model=list[ReportListItem])
async def list_reports(symbol: str | None = None, limit: int = 20):
    """Get list of recent analysis reports."""
    return get_latest_reports(symbol=symbol, limit=limit)


@router.get("/reports/{report_id}", response_model=AnalysisReport)
async def get_report(report_id: str):
    """Get a full analysis report by ID."""
    report = get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/reports/latest/{symbol}", response_model=AnalysisReport | None)
async def get_latest_report(symbol: str):
    """Get the most recent report for a symbol."""
    items = get_latest_reports(symbol=symbol, limit=1)
    if not items:
        return None
    return get_report_by_id(items[0].id)


@router.post("/analyze/{symbol}", response_model=AnalysisReport)
async def trigger_analysis(symbol: str):
    """Manually trigger analysis for a symbol."""
    if symbol not in settings.SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol {symbol} not tracked")
    report = await generate_report_for_symbol(symbol)
    if not report:
        raise HTTPException(status_code=500, detail="Analysis failed")
    return report


@router.post("/analyze/all", response_model=list[AnalysisReport])
async def trigger_all():
    """Manually trigger analysis for all symbols."""
    return await generate_all_reports()


@router.get("/symbols")
async def get_symbols():
    """Get list of tracked symbols."""
    return [
        {"symbol": s, "name": settings.SYMBOL_NAMES.get(s, s)}
        for s in settings.SYMBOLS
    ]


# ── Post-Mortem (Signal Evaluation) ──

@router.get("/postmortems", response_model=list[PostMortem])
async def list_postmortems(symbol: str | None = None, limit: int = 20):
    """Get recent post-mortem evaluations."""
    return get_postmortems(symbol=symbol, limit=limit)


@router.get("/postmortems/stats")
async def postmortem_stats(symbol: str | None = None):
    """Get win rate statistics."""
    return get_win_rate(symbol=symbol)


@router.post("/postmortems/evaluate")
async def trigger_evaluation():
    """Manually trigger evaluation of all expired signals."""
    results = await evaluate_all_expired()
    return {"evaluated": len(results), "results": results}


# ── Price Spike Alerts ──

@router.get("/price-spikes")
async def price_spikes():
    """Get recent BTC price spike alerts with AI attribution."""
    return get_spike_alerts()


# ── Whale Alerts ──

@router.get("/whale-alerts", response_model=WhaleAlertResponse)
async def whale_alerts(symbol: str | None = None):
    """Get recent whale transactions."""
    return await get_whale_alerts(symbol=symbol)


# ── Liquidation Heatmap ──

@router.get("/liquidation/{symbol}", response_model=LiquidationMap)
async def liquidation_map(symbol: str):
    """Get liquidation heatmap for a symbol."""
    if symbol not in settings.SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol {symbol} not tracked")
    return await get_liquidation_map(symbol)


@router.get("/liquidation", response_model=list[LiquidationMap])
async def all_liquidation_maps():
    """Get liquidation heatmaps for all symbols."""
    return await get_all_liquidation_maps()


# ── Correlation Matrix ──

@router.get("/correlation", response_model=CorrelationMatrix)
async def correlation_matrix():
    """Get correlation matrix for all tracked assets + macro."""
    return await get_correlation_matrix()


# ── Professional Dashboard (all-in-one) ──

@router.get("/professional")
async def professional_dashboard():
    """Get all professional features in one call."""
    import asyncio
    whale, correlation, liquidation = await asyncio.gather(
        get_whale_alerts(),
        get_correlation_matrix(),
        get_all_liquidation_maps(),
        return_exceptions=True,
    )
    return {
        "price_spikes": get_spike_alerts(),
        "whale_alerts": whale if not isinstance(whale, Exception) else {"transactions": [], "summary": {}},
        "correlation": correlation if not isinstance(correlation, Exception) else None,
        "liquidation": liquidation if not isinstance(liquidation, Exception) else [],
        "postmortems": get_postmortems(limit=10),
        "win_rate": get_win_rate(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

