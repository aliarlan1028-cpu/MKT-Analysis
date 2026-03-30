"""SQLite database for storing analysis reports."""

import json
import os
import sqlite3
from datetime import datetime
from app.models.schemas import AnalysisReport, ReportListItem


DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "reports.db")


def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            session TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            price_at_analysis REAL NOT NULL,
            direction TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            report_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_symbol_ts
        ON reports(symbol, timestamp DESC)
    """)
    conn.commit()
    conn.close()


def save_report(report: AnalysisReport):
    """Save an analysis report to the database."""
    conn = _get_db()
    conn.execute(
        """INSERT OR REPLACE INTO reports
           (id, symbol, name, session, timestamp, price_at_analysis, direction, confidence, report_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            report.id,
            report.symbol,
            report.name,
            report.session,
            report.timestamp.isoformat(),
            report.price_at_analysis,
            report.signal.direction,
            report.signal.confidence,
            report.model_dump_json(),
        ),
    )
    conn.commit()
    conn.close()


def get_latest_reports(symbol: str | None = None, limit: int = 20) -> list[ReportListItem]:
    """Get list of recent reports."""
    conn = _get_db()
    if symbol:
        rows = conn.execute(
            "SELECT id, symbol, name, session, timestamp, direction, confidence, price_at_analysis "
            "FROM reports WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, symbol, name, session, timestamp, direction, confidence, price_at_analysis "
            "FROM reports ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [
        ReportListItem(
            id=r["id"], symbol=r["symbol"], name=r["name"], session=r["session"],
            timestamp=datetime.fromisoformat(r["timestamp"]),
            direction=r["direction"], confidence=r["confidence"],
            price_at_analysis=r["price_at_analysis"],
        )
        for r in rows
    ]


def get_report_by_id(report_id: str) -> AnalysisReport | None:
    """Get a full report by ID."""
    conn = _get_db()
    row = conn.execute(
        "SELECT report_json FROM reports WHERE id = ?", (report_id,)
    ).fetchone()
    conn.close()
    if row:
        return AnalysisReport.model_validate_json(row["report_json"])
    return None

