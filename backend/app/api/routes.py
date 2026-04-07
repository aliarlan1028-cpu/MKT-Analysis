"""API routes for the crypto analysis platform."""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.core.config import settings
from app.core.database import get_latest_reports, get_report_by_id
from app.models.schemas import (
    AnalysisReport, DashboardResponse, ReportListItem, FearGreedIndex,
    PostMortem, WhaleAlertResponse, LiquidationMap, CorrelationMatrix,
)
from app.services.market_data import get_all_markets, get_market_data_binance, fetch_fear_greed, fetch_cmc_batch, get_market_data_any_okx
from app.services.report_generator import generate_report_for_symbol, generate_all_reports
from app.services.postmortem import get_postmortems, get_win_rate, evaluate_all_expired
from app.services.whale_alert import get_whale_alerts
from app.services.liquidation import get_liquidation_map, get_all_liquidation_maps
from app.services.correlation import get_correlation_matrix
from app.services.price_spike import get_spike_alerts
from app.services.pump_scanner import scan_all_coins, get_scanner_postmortems, analyze_custom_coin
from app.services.btc_derivatives import get_btc_derivatives, get_derivatives, get_okx_perpetual_symbols
from app.services.sim_trading import (
    init_sim_db, get_account, refund_account, get_positions, get_position,
    get_position_events, get_position_snapshots, open_position, close_position_at_market,
    close_position_manual, get_current_price,
)
from app.services.sim_analyzer import run_full_analysis, review_trade_factors

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


@router.post("/analyze/all", response_model=list[AnalysisReport])
async def trigger_all():
    """Manually trigger analysis for all symbols."""
    return await generate_all_reports()


@router.post("/analyze/{symbol}", response_model=AnalysisReport)
async def trigger_analysis(symbol: str):
    """Manually trigger analysis for a symbol."""
    if symbol not in settings.SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol {symbol} not tracked")
    report = await generate_report_for_symbol(symbol)
    if not report:
        raise HTTPException(status_code=500, detail="Analysis failed")
    return report


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


# ── Pump & Dump Scanner ──

@router.get("/pump-scanner")
async def pump_scanner():
    """Scan all OKX USDT perpetuals for pre-pump and dump-risk coins."""
    return await scan_all_coins()


@router.get("/pump-scanner/postmortems")
async def scanner_postmortems(limit: int = 30):
    """Get scanner postmortem stats and recent evaluation results."""
    return get_scanner_postmortems(limit=limit)


@router.get("/scanner/analyze/{symbol}")
async def scanner_analyze_coin(symbol: str):
    """Analyze any OKX perpetual symbol using scanner DeepSeek logic."""
    try:
        result = await analyze_custom_coin(symbol)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


# ── Market Data (Any OKX Symbol) ──

@router.get("/market/okx/{coin}")
async def market_data_okx(coin: str):
    """Get market data for any OKX perpetual symbol by base coin name."""
    coin = coin.upper()
    data = await get_market_data_any_okx(coin)
    if not data:
        raise HTTPException(status_code=404, detail=f"No data found for {coin}")
    return data


# ── Derivatives Dashboard (Universal) ──

@router.get("/btc-derivatives")
async def btc_derivatives():
    """Get BTC derivatives dashboard (backward compatible)."""
    return await get_btc_derivatives()


@router.get("/derivatives/symbols")
async def derivatives_symbols():
    """Get all available OKX USDT perpetual symbols for the selector."""
    return await get_okx_perpetual_symbols()


@router.get("/derivatives/{symbol}")
async def derivatives_by_symbol(symbol: str):
    """Get derivatives dashboard for any OKX perpetual symbol."""
    return await get_derivatives(symbol)


# ── Professional Dashboard (all-in-one) ──

@router.get("/professional")
async def professional_dashboard():
    """Get all professional features in one call."""
    import asyncio
    whale, correlation, liquidation, scanner = await asyncio.gather(
        get_whale_alerts(),
        get_correlation_matrix(),
        get_all_liquidation_maps(),
        scan_all_coins(),
        return_exceptions=True,
    )
    return {
        "price_spikes": get_spike_alerts(),
        "whale_alerts": whale if not isinstance(whale, Exception) else {"transactions": [], "summary": {}},
        "correlation": correlation if not isinstance(correlation, Exception) else None,
        "liquidation": liquidation if not isinstance(liquidation, Exception) else [],
        "pump_scanner": scanner if not isinstance(scanner, Exception) else {"pre_pump": [], "dump_risk": [], "total_scanned": 0},
        "postmortems": get_postmortems(limit=10),
        "win_rate": get_win_rate(),
        "scanner_postmortems": get_scanner_postmortems(limit=20),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }



# ══════════════════════════════════════════════
#  SIM TRADING API
# ══════════════════════════════════════════════

@router.get("/sim/account")
async def sim_account():
    return get_account()


@router.post("/sim/refund")
async def sim_refund():
    return refund_account()


@router.get("/sim/positions")
async def sim_positions(status: str = None):
    return get_positions(status)


@router.get("/sim/positions/{position_id}")
async def sim_position_detail(position_id: int):
    pos = get_position(position_id)
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    pos["events"] = get_position_events(position_id)
    pos["snapshots"] = get_position_snapshots(position_id)
    return pos


@router.post("/sim/analyze/{coin}")
async def sim_analyze(coin: str):
    """Run 4-step deep analysis for a coin."""
    coin = coin.upper()
    result = await run_full_analysis(coin)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/sim/open")
async def sim_open_position(data: dict):
    """Open a new position based on analysis."""
    required = ["coin", "direction", "entry_price", "stop_loss", "take_profit_1", "factors"]
    for key in required:
        if key not in data:
            raise HTTPException(status_code=400, detail=f"Missing field: {key}")
    result = open_position(
        coin=data["coin"].upper(),
        direction=data["direction"].upper(),
        target_entry=float(data["entry_price"]),
        stop_loss=float(data["stop_loss"]),
        tp1=float(data["take_profit_1"]),
        tp2=float(data.get("take_profit_2")) if data.get("take_profit_2") else None,
        factors=data["factors"],
        analysis_id=data.get("analysis_id"),
    )
    return result


@router.post("/sim/close/{position_id}")
async def sim_close_position(position_id: int):
    """Close an open position at market price."""
    return await close_position_at_market(position_id)


@router.post("/sim/review/{position_id}")
async def sim_review_position(position_id: int):
    """Generate post-trade factor review."""
    pos = get_position(position_id)
    if not pos or pos["status"] not in ("CLOSED", "LIQUIDATED"):
        raise HTTPException(status_code=400, detail="仓位未关闭，无法复盘")
    snapshots = get_position_snapshots(position_id)
    events = get_position_events(position_id)
    review = await review_trade_factors(pos, snapshots, events)
    # Save review to DB
    if "error" not in review:
        import json
        from app.services.sim_trading import _get_db
        from datetime import datetime, timedelta, timezone as tz
        _BJ = tz(timedelta(hours=8))
        now = datetime.now(_BJ).isoformat()
        conn = _get_db()
        conn.execute("""
            INSERT OR REPLACE INTO sim_trade_reports (position_id, summary, correct_factors, wrong_factors, root_cause, lesson, what_if, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (position_id,
              json.dumps(review.get("factor_reviews", []), ensure_ascii=False),
              review.get("core_correct_factor", ""),
              review.get("core_wrong_factor", ""),
              review.get("root_lesson", ""),
              review.get("reusable_rule", ""),
              review.get("what_if", ""),
              now))
        # Also save to position
        conn.execute("UPDATE sim_positions SET factor_review_json=? WHERE id=?",
                     (json.dumps(review, ensure_ascii=False), position_id))
        conn.commit()
        conn.close()
    return review


@router.get("/sim/klines/{coin}")
async def sim_klines(coin: str, bar: str = "5m", limit: int = 200):
    """Get klines for chart display."""
    coin = coin.upper()
    from app.services.market_data import _okx_get
    body = await _okx_get("/api/v5/market/candles", {"instId": f"{coin}-USDT-SWAP", "bar": bar, "limit": str(limit)})
    if not body or not body.get("data"):
        raise HTTPException(status_code=404, detail=f"No kline data for {coin}")
    # OKX returns [ts, o, h, l, c, vol, volCcy, ...]
    klines = []
    for k in reversed(body["data"]):  # reverse to chronological order
        klines.append({
            "time": int(k[0]) // 1000,  # ms to seconds for lightweight-charts
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        })
    return klines