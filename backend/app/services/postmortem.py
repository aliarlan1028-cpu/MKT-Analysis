"""Post-Mortem signal evaluation service."""

import json
from datetime import datetime, timezone, timedelta
from app.core.config import settings
from app.core.database import get_latest_reports, get_report_by_id, _get_db
from app.models.schemas import PostMortem, AnalysisReport
from app.services.market_data import fetch_cmc_batch, fetch_klines

# Session validity windows (hours)
SESSION_VALIDITY = {
    "morning": 14,  # 06:00 → valid until 20:00
    "evening": 10,  # 20:00 → valid until 06:00 next day
}


def init_postmortem_table():
    """Create postmortem table if not exists."""
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS postmortems (
            report_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            direction TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            price_at_analysis REAL NOT NULL,
            price_at_expiry REAL NOT NULL,
            price_high REAL NOT NULL,
            price_low REAL NOT NULL,
            entry_zone TEXT NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit TEXT NOT NULL,
            hit_tp INTEGER DEFAULT 0,
            hit_sl INTEGER DEFAULT 0,
            pnl_pct REAL DEFAULT 0,
            result TEXT DEFAULT 'PENDING',
            analysis_time TEXT NOT NULL,
            expiry_time TEXT NOT NULL,
            evaluated_at TEXT NOT NULL,
            summary TEXT DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pm_symbol ON postmortems(symbol, evaluated_at DESC)")
    conn.commit()
    conn.close()


async def evaluate_report(report: AnalysisReport) -> PostMortem | None:
    """Evaluate a single report's signal accuracy."""
    validity_hours = SESSION_VALIDITY.get(report.session, 8)
    analysis_time = report.timestamp
    expiry_time = analysis_time + timedelta(hours=validity_hours)
    now = datetime.now(timezone.utc)

    if now < expiry_time:
        return None  # Not expired yet

    # Try to get price range during validity period from klines
    price_high = report.price_at_analysis
    price_low = report.price_at_analysis
    price_at_expiry = report.price_at_analysis

    try:
        klines = await fetch_klines(report.symbol, interval="1h", limit=validity_hours + 2)
        if klines:
            highs = [float(k[2]) for k in klines[-validity_hours:]]
            lows = [float(k[3]) for k in klines[-validity_hours:]]
            closes = [float(k[4]) for k in klines[-validity_hours:]]
            if highs:
                price_high = max(highs)
            if lows:
                price_low = min(lows)
            if closes:
                price_at_expiry = closes[-1]
    except Exception:
        # Fallback: use current CMC price
        try:
            cmc = await fetch_cmc_batch()
            if report.symbol in cmc:
                price_at_expiry = cmc[report.symbol].price
                price_high = price_at_expiry * 1.01
                price_low = price_at_expiry * 0.99
        except Exception:
            pass

    sig = report.signal
    hit_tp = 0
    hit_sl = False
    pnl_pct = 0.0

    if sig.direction == "LONG":
        if price_low <= sig.stop_loss:
            hit_sl = True
        for i, tp in enumerate(sig.take_profit):
            if price_high >= tp:
                hit_tp = i + 1
        if hit_sl and hit_tp == 0:
            pnl_pct = ((sig.stop_loss - sig.entry_zone[0]) / sig.entry_zone[0]) * 100
        elif hit_tp > 0:
            tp_price = sig.take_profit[hit_tp - 1]
            pnl_pct = ((tp_price - sig.entry_zone[0]) / sig.entry_zone[0]) * 100
        else:
            pnl_pct = ((price_at_expiry - sig.entry_zone[0]) / sig.entry_zone[0]) * 100
    elif sig.direction == "SHORT":
        if price_high >= sig.stop_loss:
            hit_sl = True
        for i, tp in enumerate(sig.take_profit):
            if price_low <= tp:
                hit_tp = i + 1
        if hit_sl and hit_tp == 0:
            pnl_pct = ((sig.entry_zone[0] - sig.stop_loss) / sig.entry_zone[0]) * 100
        elif hit_tp > 0:
            tp_price = sig.take_profit[hit_tp - 1]
            pnl_pct = ((sig.entry_zone[0] - tp_price) / sig.entry_zone[0]) * 100
        else:
            pnl_pct = ((sig.entry_zone[0] - price_at_expiry) / sig.entry_zone[0]) * 100

    if sig.direction == "NEUTRAL":
        result = "NEUTRAL"
    elif hit_tp > 0:
        result = "WIN"
    elif hit_sl:
        result = "LOSS"
    elif abs(pnl_pct) < 0.3:
        result = "BREAKEVEN"
    elif pnl_pct > 0:
        result = "WIN"
    else:
        result = "LOSS"

    summary = _build_summary(report, result, hit_tp, hit_sl, pnl_pct, price_high, price_low, price_at_expiry)

    pm = PostMortem(
        report_id=report.id or "",
        symbol=report.symbol,
        name=report.name,
        direction=sig.direction,
        confidence=sig.confidence,
        price_at_analysis=report.price_at_analysis,
        price_at_expiry=round(price_at_expiry, 2),
        price_high=round(price_high, 2),
        price_low=round(price_low, 2),
        entry_zone=sig.entry_zone,
        stop_loss=sig.stop_loss,
        take_profit=sig.take_profit,
        hit_tp=hit_tp,
        hit_sl=hit_sl,
        pnl_pct=round(pnl_pct, 2),
        result=result,
        analysis_time=analysis_time,
        expiry_time=expiry_time,
        evaluated_at=now,
        summary=summary,
    )
    _save_postmortem(pm)
    return pm


def _build_summary(report, result, hit_tp, hit_sl, pnl_pct, price_high, price_low, price_at_expiry):
    """Build human-readable summary."""
    dir_cn = {"LONG": "做多", "SHORT": "做空", "NEUTRAL": "观望"}.get(report.signal.direction, "")
    result_cn = {"WIN": "✅ 盈利", "LOSS": "❌ 亏损", "BREAKEVEN": "⚪ 持平", "NEUTRAL": "⚪ 观望"}.get(result, "")

    lines = [
        f"信号方向: {dir_cn} | 置信度: {report.signal.confidence}%",
        f"入场价: ${report.signal.entry_zone[0]:,.2f} | 分析时价: ${report.price_at_analysis:,.2f}",
        f"期间最高: ${price_high:,.2f} | 期间最低: ${price_low:,.2f} | 到期价: ${price_at_expiry:,.2f}",
    ]
    if hit_tp > 0:
        lines.append(f"✅ 触达止盈 TP{hit_tp} (${report.signal.take_profit[hit_tp-1]:,.2f})")
    if hit_sl:
        lines.append(f"❌ 触达止损 (${report.signal.stop_loss:,.2f})")
    lines.append(f"结果: {result_cn} | 预估收益: {pnl_pct:+.2f}%")
    return "\n".join(lines)


def _save_postmortem(pm: PostMortem):
    """Save postmortem to database."""
    conn = _get_db()
    conn.execute(
        """INSERT OR REPLACE INTO postmortems
           (report_id, symbol, name, direction, confidence, price_at_analysis,
            price_at_expiry, price_high, price_low, entry_zone, stop_loss,
            take_profit, hit_tp, hit_sl, pnl_pct, result, analysis_time,
            expiry_time, evaluated_at, summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            pm.report_id, pm.symbol, pm.name, pm.direction, pm.confidence,
            pm.price_at_analysis, pm.price_at_expiry, pm.price_high, pm.price_low,
            json.dumps(pm.entry_zone), pm.stop_loss, json.dumps(pm.take_profit),
            pm.hit_tp, int(pm.hit_sl), pm.pnl_pct, pm.result,
            pm.analysis_time.isoformat(), pm.expiry_time.isoformat(),
            pm.evaluated_at.isoformat(), pm.summary,
        ),
    )
    conn.commit()
    conn.close()


def get_postmortems(symbol: str | None = None, limit: int = 20) -> list[PostMortem]:
    """Get recent postmortems."""
    conn = _get_db()
    if symbol:
        rows = conn.execute(
            "SELECT * FROM postmortems WHERE symbol = ? ORDER BY evaluated_at DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM postmortems ORDER BY evaluated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [_row_to_postmortem(r) for r in rows]


def get_win_rate(symbol: str | None = None) -> dict:
    """Calculate win rate statistics."""
    conn = _get_db()
    if symbol:
        rows = conn.execute(
            "SELECT result, COUNT(*) as cnt FROM postmortems WHERE symbol = ? AND result != 'NEUTRAL' GROUP BY result",
            (symbol,),
        ).fetchall()
        total_pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl_pct), 0) FROM postmortems WHERE symbol = ? AND result != 'NEUTRAL'",
            (symbol,),
        ).fetchone()[0]
    else:
        rows = conn.execute(
            "SELECT result, COUNT(*) as cnt FROM postmortems WHERE result != 'NEUTRAL' GROUP BY result"
        ).fetchall()
        total_pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl_pct), 0) FROM postmortems WHERE result != 'NEUTRAL'"
        ).fetchone()[0]
    conn.close()

    stats = {"WIN": 0, "LOSS": 0, "BREAKEVEN": 0}
    for r in rows:
        stats[r["result"]] = r["cnt"]
    total = sum(stats.values())
    win_rate = (stats["WIN"] / total * 100) if total > 0 else 0

    return {
        "total_signals": total,
        "wins": stats["WIN"],
        "losses": stats["LOSS"],
        "breakeven": stats["BREAKEVEN"],
        "win_rate": round(win_rate, 1),
        "total_pnl_pct": round(total_pnl, 2),
    }


def _row_to_postmortem(r) -> PostMortem:
    return PostMortem(
        report_id=r["report_id"],
        symbol=r["symbol"],
        name=r["name"],
        direction=r["direction"],
        confidence=r["confidence"],
        price_at_analysis=r["price_at_analysis"],
        price_at_expiry=r["price_at_expiry"],
        price_high=r["price_high"],
        price_low=r["price_low"],
        entry_zone=json.loads(r["entry_zone"]),
        stop_loss=r["stop_loss"],
        take_profit=json.loads(r["take_profit"]),
        hit_tp=r["hit_tp"],
        hit_sl=bool(r["hit_sl"]),
        pnl_pct=r["pnl_pct"],
        result=r["result"],
        analysis_time=datetime.fromisoformat(r["analysis_time"]),
        expiry_time=datetime.fromisoformat(r["expiry_time"]),
        evaluated_at=datetime.fromisoformat(r["evaluated_at"]),
        summary=r["summary"],
    )


async def evaluate_all_expired():
    """Evaluate all expired signals that haven't been evaluated yet."""
    conn = _get_db()
    rows = conn.execute(
        """SELECT id FROM reports
           WHERE id NOT IN (SELECT report_id FROM postmortems)
           ORDER BY timestamp DESC LIMIT 50"""
    ).fetchall()
    conn.close()

    evaluated = []
    for row in rows:
        report = get_report_by_id(row["id"])
        if report:
            pm = await evaluate_report(report)
            if pm:
                evaluated.append(pm)
                print(f"  📊 Post-mortem: {pm.symbol} {pm.direction} → {pm.result} ({pm.pnl_pct:+.2f}%)")
    return evaluated

