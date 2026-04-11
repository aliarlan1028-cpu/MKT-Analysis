"""Simulated Trading System — AI-driven paper trading with deep analysis & postmortem.

Database: SQLite (data/sim_trading.db)
Tables: sim_account, sim_positions, sim_price_snapshots, sim_events, sim_trade_reports
"""

import json
import os
import sqlite3
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional
from app.core.config import settings
from app.services.market_data import _okx_get

_BEIJING_TZ = timezone(timedelta(hours=8))
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sim_trading.db")

LEVERAGE = 10
INITIAL_BALANCE = 1000.0
REFUND_THRESHOLD = 200.0
REFUND_AMOUNT = 1000.0
MAX_POSITIONS = 2
LIQUIDATION_PCT = 0.90  # 90% loss = liquidation
VOLATILITY_THRESHOLD = 3.0  # 3% move triggers AI analysis


# ═══════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════

def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_sim_db():
    """Create all sim trading tables."""
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sim_account (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            balance REAL NOT NULL DEFAULT 1000.0,
            total_pnl REAL NOT NULL DEFAULT 0.0,
            total_trades INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sim_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coin TEXT NOT NULL,
            direction TEXT NOT NULL,  -- LONG / SHORT
            status TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING / OPEN / CLOSED / LIQUIDATED
            leverage INTEGER NOT NULL DEFAULT 10,
            margin REAL NOT NULL,
            entry_price REAL,
            target_entry_price REAL NOT NULL,
            stop_loss REAL NOT NULL,
            take_profit_1 REAL NOT NULL,
            take_profit_2 REAL,
            exit_price REAL,
            pnl REAL,
            pnl_pct REAL,
            mae REAL DEFAULT 0,  -- max adverse excursion %
            mfe REAL DEFAULT 0,  -- max favorable excursion %
            mae_price REAL,
            mfe_price REAL,
            reversal_price REAL,  -- price where it reversed from MAE
            analysis_id TEXT,  -- links to the AI analysis
            factors_json TEXT,  -- AI factors at entry (JSON array)
            factor_review_json TEXT,  -- post-trade factor attribution (JSON)
            opened_at TEXT,
            closed_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sim_price_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL,
            price REAL NOT NULL,
            pnl_pct REAL NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (position_id) REFERENCES sim_positions(id)
        );

        CREATE TABLE IF NOT EXISTS sim_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,  -- ENTRY / EXIT / VOLATILITY / SL_HIT / TP_HIT / LIQUIDATION / AI_ANALYSIS
            price REAL NOT NULL,
            change_pct REAL,
            ai_analysis TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (position_id) REFERENCES sim_positions(id)
        );

        CREATE TABLE IF NOT EXISTS sim_trade_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL UNIQUE,
            summary TEXT NOT NULL,
            correct_factors TEXT,
            wrong_factors TEXT,
            root_cause TEXT,
            lesson TEXT,
            what_if TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (position_id) REFERENCES sim_positions(id)
        );

        CREATE TABLE IF NOT EXISTS sim_strategy_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_count INTEGER NOT NULL,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    # Ensure account exists
    existing = conn.execute("SELECT id FROM sim_account WHERE id=1").fetchone()
    if not existing:
        now = datetime.now(_BEIJING_TZ).isoformat()
        conn.execute(
            "INSERT INTO sim_account (id, balance, total_pnl, total_trades, wins, losses, created_at, updated_at) VALUES (1,?,0,0,0,0,?,?)",
            (INITIAL_BALANCE, now, now)
        )
    conn.commit()
    conn.close()
    print("  ✓ Sim trading database initialized")


# ═══════════════════════════════════════════
#  ACCOUNT
# ═══════════════════════════════════════════

def get_account() -> dict:
    conn = _get_db()
    row = conn.execute("SELECT * FROM sim_account WHERE id=1").fetchone()
    conn.close()
    if not row:
        init_sim_db()
        return get_account()
    # Count active positions' margin
    conn2 = _get_db()
    active = conn2.execute(
        "SELECT COALESCE(SUM(margin),0) as used FROM sim_positions WHERE status IN ('PENDING','OPEN')"
    ).fetchone()
    conn2.close()
    return {
        "balance": row["balance"],
        "used_margin": active["used"],
        "available_balance": row["balance"] - active["used"],
        "total_pnl": row["total_pnl"],
        "total_trades": row["total_trades"],
        "wins": row["wins"],
        "losses": row["losses"],
        "win_rate": round(row["wins"] / row["total_trades"] * 100, 1) if row["total_trades"] > 0 else 0,
        "can_refund": row["balance"] < REFUND_THRESHOLD,
    }


def refund_account() -> dict:
    """Reset balance to INITIAL_BALANCE if below threshold."""
    conn = _get_db()
    row = conn.execute("SELECT balance FROM sim_account WHERE id=1").fetchone()
    if row["balance"] >= REFUND_THRESHOLD:
        conn.close()
        return {"success": False, "message": f"余额 {row['balance']:.2f} USDT 高于 {REFUND_THRESHOLD} USDT，无需补充"}
    now = datetime.now(_BEIJING_TZ).isoformat()
    conn.execute("UPDATE sim_account SET balance=?, updated_at=? WHERE id=1", (REFUND_AMOUNT, now))
    conn.commit()
    conn.close()
    return {"success": True, "message": f"已补充资金至 {REFUND_AMOUNT} USDT", "balance": REFUND_AMOUNT}


# ═══════════════════════════════════════════
#  POSITIONS
# ═══════════════════════════════════════════

def get_positions(status: str = None) -> list[dict]:
    conn = _get_db()
    if status:
        rows = conn.execute("SELECT * FROM sim_positions WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM sim_positions ORDER BY created_at DESC").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["factors"] = json.loads(d["factors_json"]) if d["factors_json"] else []
        d["factor_review"] = json.loads(d["factor_review_json"]) if d["factor_review_json"] else None
        result.append(d)
    return result


def get_position(position_id: int) -> dict | None:
    conn = _get_db()
    row = conn.execute("SELECT * FROM sim_positions WHERE id=?", (position_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["factors"] = json.loads(d["factors_json"]) if d["factors_json"] else []
    d["factor_review"] = json.loads(d["factor_review_json"]) if d["factor_review_json"] else None
    return d


def get_position_events(position_id: int) -> list[dict]:
    conn = _get_db()
    rows = conn.execute("SELECT * FROM sim_events WHERE position_id=? ORDER BY timestamp ASC", (position_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_position_snapshots(position_id: int) -> list[dict]:
    conn = _get_db()
    rows = conn.execute("SELECT price, pnl_pct, timestamp FROM sim_price_snapshots WHERE position_id=? ORDER BY timestamp ASC", (position_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def open_position(coin: str, direction: str, target_entry: float, stop_loss: float,
                  tp1: float, tp2: float | None, factors: list[dict], analysis_id: str = None) -> dict:
    """Create a new pending position."""
    # Validate
    active = get_positions("OPEN") + get_positions("PENDING")
    if len(active) >= MAX_POSITIONS:
        return {"success": False, "message": f"最多同时持有 {MAX_POSITIONS} 个仓位"}

    account = get_account()
    if account["available_balance"] <= 0:
        return {"success": False, "message": "可用余额不足"}

    margin = account["available_balance"]  # Use all available balance
    now = datetime.now(_BEIJING_TZ).isoformat()

    conn = _get_db()
    cursor = conn.execute("""
        INSERT INTO sim_positions
        (coin, direction, status, leverage, margin, target_entry_price, stop_loss, take_profit_1, take_profit_2,
         analysis_id, factors_json, created_at)
        VALUES (?, ?, 'PENDING', ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (coin, direction, LEVERAGE, margin, target_entry, stop_loss, tp1, tp2,
          analysis_id, json.dumps(factors, ensure_ascii=False), now))
    pid = cursor.lastrowid
    conn.commit()
    conn.close()

    return {"success": True, "position_id": pid, "message": f"限价单已挂出，等待 {coin} 到达 ${target_entry}"}


def close_position_manual(position_id: int) -> dict:
    """Manually close an open position at current market price."""
    pos = get_position(position_id)
    if not pos or pos["status"] not in ("OPEN", "PENDING"):
        return {"success": False, "message": "仓位不存在或已关闭"}

    if pos["status"] == "PENDING":
        # Cancel pending order
        conn = _get_db()
        now = datetime.now(_BEIJING_TZ).isoformat()
        conn.execute("UPDATE sim_positions SET status='CLOSED', closed_at=?, pnl=0, pnl_pct=0 WHERE id=?", (now, position_id))
        conn.execute("UPDATE sim_account SET balance=balance+? WHERE id=1", (pos["margin"],))
        conn.commit()
        conn.close()
        return {"success": True, "message": "限价单已取消，保证金已退回"}

    # For open positions, need current price
    return {"success": False, "message": "请使用 close_at_price 平仓"}


def _close_position_at(position_id: int, exit_price: float, reason: str = "MANUAL"):
    """Internal: close position at given price, update account."""
    pos = get_position(position_id)
    if not pos or pos["status"] != "OPEN":
        return
    entry = pos["entry_price"]
    direction = pos["direction"]
    margin = pos["margin"]

    if direction == "LONG":
        pnl_pct = (exit_price - entry) / entry * 100 * LEVERAGE
    else:
        pnl_pct = (entry - exit_price) / entry * 100 * LEVERAGE

    pnl = margin * (pnl_pct / 100)
    now = datetime.now(_BEIJING_TZ).isoformat()

    conn = _get_db()
    conn.execute("""
        UPDATE sim_positions SET status=?, exit_price=?, pnl=?, pnl_pct=?, closed_at=? WHERE id=?
    """, ("LIQUIDATED" if reason == "LIQUIDATION" else "CLOSED", exit_price, round(pnl, 2), round(pnl_pct, 2), now, position_id))

    # Update account
    returned = margin + pnl
    if returned < 0:
        returned = 0
    is_win = 1 if pnl > 0 else 0
    is_loss = 1 if pnl <= 0 else 0
    conn.execute("""
        UPDATE sim_account SET balance=balance+?, total_pnl=total_pnl+?,
        total_trades=total_trades+1, wins=wins+?, losses=losses+?, updated_at=? WHERE id=1
    """, (round(returned, 2), round(pnl, 2), is_win, is_loss, now))

    # Record exit event
    conn.execute("INSERT INTO sim_events (position_id, event_type, price, change_pct, timestamp) VALUES (?,?,?,?,?)",
                 (position_id, reason, exit_price, round(pnl_pct, 2), now))
    conn.commit()
    conn.close()
    print(f"  💰 Position #{position_id} {pos['coin']} closed: {reason} | PnL: {pnl_pct:+.2f}% (${pnl:+.2f})")


async def get_current_price(coin: str) -> float | None:
    """Get current SWAP price for a coin."""
    body = await _okx_get("/api/v5/market/ticker", {"instId": f"{coin}-USDT-SWAP"})
    if body and body.get("data"):
        return float(body["data"][0]["last"])
    return None


async def monitor_positions():
    """Called every 60s: check pending fills, update P&L, detect SL/TP/liquidation, track MAE/MFE."""
    open_positions = get_positions("OPEN") + get_positions("PENDING")
    if not open_positions:
        return

    for pos in open_positions:
        price = await get_current_price(pos["coin"])
        if not price:
            continue

        now = datetime.now(_BEIJING_TZ).isoformat()
        conn = _get_db()

        # --- PENDING: check if entry price hit ---
        if pos["status"] == "PENDING":
            target = pos["target_entry_price"]
            filled = False
            if pos["direction"] == "LONG" and price <= target:
                filled = True
            elif pos["direction"] == "SHORT" and price >= target:
                filled = True

            if filled:
                conn.execute("UPDATE sim_positions SET status='OPEN', entry_price=?, opened_at=? WHERE id=?",
                             (target, now, pos["id"]))
                conn.execute("INSERT INTO sim_events (position_id, event_type, price, timestamp) VALUES (?,?,?,?)",
                             (pos["id"], "ENTRY", target, now))
                conn.commit()
                print(f"  ✅ Position #{pos['id']} {pos['coin']} filled at ${target}")
            conn.close()
            continue

        # --- OPEN: track price ---
        entry = pos["entry_price"]
        direction = pos["direction"]

        if direction == "LONG":
            pnl_pct = (price - entry) / entry * 100 * LEVERAGE
        else:
            pnl_pct = (entry - price) / entry * 100 * LEVERAGE

        # Save price snapshot
        conn.execute("INSERT INTO sim_price_snapshots (position_id, price, pnl_pct, timestamp) VALUES (?,?,?,?)",
                     (pos["id"], price, round(pnl_pct, 2), now))

        # Update MAE/MFE
        updates = []
        if pnl_pct < (pos["mae"] or 0):
            updates.append(f"mae={round(pnl_pct,2)}")
            updates.append(f"mae_price={price}")
        if pnl_pct > (pos["mfe"] or 0):
            updates.append(f"mfe={round(pnl_pct,2)}")
            updates.append(f"mfe_price={price}")
        # Track reversal from MAE
        if pos["mae"] and pos["mae"] < -3 and pnl_pct > (pos["mae"] + 3) and not pos.get("reversal_price"):
            updates.append(f"reversal_price={price}")
        if updates:
            conn.execute(f"UPDATE sim_positions SET {','.join(updates)} WHERE id=?", (pos["id"],))

        conn.commit()
        conn.close()

        # Check SL/TP/Liquidation
        if pnl_pct <= -(LIQUIDATION_PCT * 100):
            _close_position_at(pos["id"], price, "LIQUIDATION")
        elif direction == "LONG" and price <= pos["stop_loss"]:
            _close_position_at(pos["id"], pos["stop_loss"], "SL_HIT")
        elif direction == "SHORT" and price >= pos["stop_loss"]:
            _close_position_at(pos["id"], pos["stop_loss"], "SL_HIT")
        elif direction == "LONG" and price >= pos["take_profit_1"]:
            _close_position_at(pos["id"], pos["take_profit_1"], "TP_HIT")
        elif direction == "SHORT" and price <= pos["take_profit_1"]:
            _close_position_at(pos["id"], pos["take_profit_1"], "TP_HIT")

        # --- Volatility detection: >3% move since last snapshot ---
        try:
            conn2 = _get_db()
            prev_snapshots = conn2.execute(
                "SELECT price FROM sim_price_snapshots WHERE position_id=? ORDER BY id DESC LIMIT 10",
                (pos["id"],)
            ).fetchall()
            conn2.close()
            if len(prev_snapshots) >= 5:
                price_5min_ago = prev_snapshots[4]["price"]
                short_change = abs((price - price_5min_ago) / price_5min_ago * 100)
                if short_change >= VOLATILITY_THRESHOLD:
                    # Check we haven't done a volatility analysis in last 10 minutes
                    conn3 = _get_db()
                    recent_vol = conn3.execute(
                        "SELECT id FROM sim_events WHERE position_id=? AND event_type='VOLATILITY' AND timestamp > datetime('now','-10 minutes')",
                        (pos["id"],)
                    ).fetchone()
                    conn3.close()
                    if not recent_vol:
                        print(f"  ⚡ Volatility detected: {pos['coin']} moved {short_change:.1f}% in 5min")
                        try:
                            from app.services.sim_analyzer import analyze_volatility_event
                            ai_text = await analyze_volatility_event(pos["coin"], price, short_change if price > price_5min_ago else -short_change, pos)
                            conn4 = _get_db()
                            conn4.execute(
                                "INSERT INTO sim_events (position_id, event_type, price, change_pct, ai_analysis, timestamp) VALUES (?,?,?,?,?,?)",
                                (pos["id"], "VOLATILITY", price, round(short_change, 2), ai_text, now)
                            )
                            conn4.commit()
                            conn4.close()
                        except Exception as e:
                            print(f"    ⚠ Volatility analysis failed: {e}")
        except Exception:
            pass

        # --- Periodic re-analysis: every 4 hours ---
        try:
            if pos.get("opened_at"):
                opened = datetime.fromisoformat(pos["opened_at"])
                hours_open = (datetime.now(_BEIJING_TZ) - opened).total_seconds() / 3600
                if hours_open >= 4:
                    conn5 = _get_db()
                    last_reanalysis = conn5.execute(
                        "SELECT timestamp FROM sim_events WHERE position_id=? AND event_type='AI_ANALYSIS' ORDER BY id DESC LIMIT 1",
                        (pos["id"],)
                    ).fetchone()
                    conn5.close()
                    should_reanalyze = True
                    if last_reanalysis:
                        last_t = datetime.fromisoformat(last_reanalysis["timestamp"])
                        if (datetime.now(_BEIJING_TZ) - last_t).total_seconds() < 4 * 3600:
                            should_reanalyze = False
                    if should_reanalyze:
                        print(f"  🔄 Periodic re-analysis for {pos['coin']} (open {hours_open:.1f}h)")
                        try:
                            from app.services.sim_analyzer import run_full_analysis
                            reanalysis = await run_full_analysis(pos["coin"])
                            summary = ""
                            if reanalysis.get("step4"):
                                s4 = reanalysis["step4"]
                                summary = f"重新分析: {s4.get('direction','N/A')} (置信度{s4.get('confidence','N/A')}%) — {s4.get('reasoning','')}"
                            conn6 = _get_db()
                            conn6.execute(
                                "INSERT INTO sim_events (position_id, event_type, price, ai_analysis, timestamp) VALUES (?,?,?,?,?)",
                                (pos["id"], "AI_ANALYSIS", price, summary[:500], now)
                            )
                            conn6.commit()
                            conn6.close()
                        except Exception as e:
                            print(f"    ⚠ Re-analysis failed: {e}")
        except Exception:
            pass


async def close_position_at_market(position_id: int) -> dict:
    """Close an open position at current market price."""
    pos = get_position(position_id)
    if not pos:
        return {"success": False, "message": "仓位不存在"}
    if pos["status"] == "PENDING":
        return close_position_manual(position_id)
    if pos["status"] != "OPEN":
        return {"success": False, "message": "仓位已关闭"}

    price = await get_current_price(pos["coin"])
    if not price:
        return {"success": False, "message": "无法获取当前价格"}

    _close_position_at(position_id, price, "MANUAL")
    return {"success": True, "message": f"已平仓 {pos['coin']} @ ${price}"}


def get_factor_analytics():
    """Analyze win rates by initial factors."""
    conn = _get_db()

    # Get all closed positions with factors
    rows = conn.execute("""
        SELECT direction, factors_json, pnl_pct
        FROM sim_positions
        WHERE status IN ('CLOSED', 'LIQUIDATED') AND factors_json IS NOT NULL
    """).fetchall()

    conn.close()

    factor_stats = {} # factor_name -> {factor_value -> {total_trades, wins, losses, total_pnl_pct}}

    for r in rows:
        direction = r["direction"]
        factors_str = r["factors_json"]
        pnl_pct = r["pnl_pct"]

        if not factors_str:
            continue

        try:
            factors = json.loads(factors_str)
        except json.JSONDecodeError:
            continue

        for factor_dict in factors:
            factor_name = factor_dict.get("name")
            factor_value = factor_dict.get("value")

            if not factor_name or not factor_value:
                continue

            # Use a combined key for factor_name and direction
            factor_key = f"{factor_name}__{direction}"

            if factor_key not in factor_stats:
                factor_stats[factor_key] = {}

            if factor_value not in factor_stats[factor_key]:
                factor_stats[factor_key][factor_value] = {
                    "total_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "total_pnl_pct": 0.0
                }

            stats = factor_stats[factor_key][factor_value]
            stats["total_trades"] += 1
            if pnl_pct > 0:
                stats["wins"] += 1
            else:
                stats["losses"] += 1
            stats["total_pnl_pct"] += pnl_pct

    # Calculate win rates and average PnL
    result = []
    for factor_key, values in factor_stats.items():
        factor_name, direction = factor_key.split("__")
        for factor_value, stats in values.items():
            total_trades = stats["total_trades"]
            wins = stats["wins"]
            losses = stats["losses"]
            total_pnl_pct = stats["total_pnl_pct"]

            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            avg_pnl_pct = (total_pnl_pct / total_trades) if total_trades > 0 else 0

            result.append({
                "factor_name": factor_name,
                "factor_value": factor_value,
                "direction": direction,
                "total_trades": total_trades,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 2),
                "avg_pnl_pct": round(avg_pnl_pct, 2)
            })

    # Sort for better readability (optional)
    result.sort(key=lambda x: (x["factor_name"], x["factor_value"], x["direction"]))

    return result

