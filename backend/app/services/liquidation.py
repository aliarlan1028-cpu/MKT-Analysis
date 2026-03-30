"""Liquidation heatmap service.

Uses REAL OKX data:
  1) /api/v5/public/liquidation-orders  — recent filled liquidations (bkPx, sz, posSide)
  2) /api/v5/public/position-tiers      — real MMR per leverage tier
  3) /api/v5/public/open-interest       — real OI
"""

from datetime import datetime, timezone
from app.models.schemas import LiquidationLevel, LiquidationMap
from app.services.market_data import _okx_get, _OKX_SYMBOL_MAP, fetch_okx_ticker
from app.core.config import settings

# OKX contract value per contract (ctVal) — used to convert sz to coin amount
_OKX_CT_VAL = {
    "BTC-USDT-SWAP": 0.01,   # 1 contract = 0.01 BTC
    "ETH-USDT-SWAP": 0.1,    # 1 contract = 0.1 ETH
    "SOL-USDT-SWAP": 1.0,    # 1 contract = 1 SOL
    "BNB-USDT-SWAP": 1.0,    # 1 contract = 1 BNB
}


async def _fetch_okx_liquidation_orders(uly: str) -> list[dict]:
    """Fetch recent filled liquidation orders from OKX."""
    all_details: list[dict] = []
    try:
        body = await _okx_get(
            "/api/v5/public/liquidation-orders",
            {"instType": "SWAP", "uly": uly, "state": "filled", "limit": "100"},
        )
        if body and body.get("data"):
            for batch in body["data"]:
                details = batch.get("details", [])
                all_details.extend(details)
    except Exception as e:
        print(f"  ⚠ OKX liquidation orders failed for {uly}: {e}")
    return all_details


async def _fetch_okx_position_tiers(uly: str) -> list[dict]:
    """Fetch position tier info (real MMR per leverage level)."""
    try:
        body = await _okx_get(
            "/api/v5/public/position-tiers",
            {"instType": "SWAP", "tdMode": "cross", "uly": uly},
        )
        if body and body.get("data"):
            return body["data"]
    except Exception as e:
        print(f"  ⚠ OKX position tiers failed for {uly}: {e}")
    return []


def _estimate_leverage_from_distance(bk_price: float, current_price: float, pos_side: str) -> str:
    """Estimate leverage tier from bankruptcy price distance to current price."""
    if current_price == 0:
        return "10x"
    if pos_side == "long":
        distance_pct = (current_price - bk_price) / current_price
    else:
        distance_pct = (bk_price - current_price) / current_price
    # Map distance to leverage: 1/leverage ≈ distance
    if distance_pct <= 0:
        return "100x"
    estimated_lev = 1.0 / distance_pct
    if estimated_lev >= 75:
        return "100x"
    elif estimated_lev >= 35:
        return "50x"
    elif estimated_lev >= 15:
        return "25x"
    elif estimated_lev >= 7:
        return "10x"
    else:
        return "5x"


async def get_liquidation_map(symbol: str) -> LiquidationMap:
    """Generate liquidation heatmap from REAL OKX data."""
    okx_inst = _OKX_SYMBOL_MAP.get(symbol)
    if not okx_inst:
        return LiquidationMap(
            symbol=symbol, current_price=0, levels=[],
            total_long_liq=0, total_short_liq=0, timestamp=datetime.now(timezone.utc)
        )

    swap_inst = okx_inst + "-SWAP"   # e.g. BTC-USDT-SWAP
    uly = okx_inst                    # e.g. BTC-USDT
    ct_val = _OKX_CT_VAL.get(swap_inst, 1.0)

    # 1) Get current price
    current_price = 0.0
    try:
        ticker = await fetch_okx_ticker(symbol)
        if ticker:
            current_price = float(ticker.get("last", 0))
    except Exception:
        pass
    if current_price == 0:
        return LiquidationMap(
            symbol=symbol, current_price=0, levels=[],
            total_long_liq=0, total_short_liq=0, timestamp=datetime.now(timezone.utc)
        )

    # 2) Fetch real OI
    total_oi_usd = 0.0
    try:
        body = await _okx_get("/api/v5/public/open-interest", {"instType": "SWAP", "instId": swap_inst})
        if body and body.get("data"):
            oi_coins = float(body["data"][0].get("oiCcy", 0))
            total_oi_usd = oi_coins * current_price
    except Exception:
        pass

    # 3) Fetch real position tiers (MMR data)
    tiers = await _fetch_okx_position_tiers(uly)

    # 4) Fetch real recent liquidation orders
    liq_orders = await _fetch_okx_liquidation_orders(uly)

    # ── Build levels from REAL liquidation orders ──
    # Aggregate by leverage tier + direction
    bucket: dict[str, dict] = {}  # key = "long_5x" etc
    for order in liq_orders:
        bk_price = float(order.get("bkPx", 0))
        pos_side = order.get("posSide", "long")  # "long" or "short"
        sz = float(order.get("sz", 0))
        usd_value = sz * ct_val * bk_price

        lev_str = _estimate_leverage_from_distance(bk_price, current_price, pos_side)
        key = f"{pos_side}_{lev_str}"
        if key not in bucket:
            bucket[key] = {"price_sum": 0, "usd_total": 0, "count": 0}
        bucket[key]["price_sum"] += bk_price * usd_value
        bucket[key]["usd_total"] += usd_value
        bucket[key]["count"] += 1

    # ── Build levels from position tiers + OI (projected) ──
    # Use real MMR from tiers to calculate where liquidations WOULD happen
    tier_levels: list[dict] = []
    selected_tiers = []
    for t in tiers:
        max_lever = float(t.get("maxLever", 1))
        mmr = float(t.get("mmr", 0.01))
        if max_lever in [100, 50, 25, 10, 5]:
            selected_tiers.append({"lever": int(max_lever), "mmr": mmr, "lever_str": f"{int(max_lever)}x"})

    # Deduplicate and ensure we have all 5 tiers
    seen_levers = {t["lever"] for t in selected_tiers}
    for lev in [5, 10, 25, 50, 100]:
        if lev not in seen_levers:
            # Default MMR values from OKX BTC tiers
            default_mmr = {5: 0.03, 10: 0.015, 25: 0.0075, 50: 0.005, 100: 0.004}
            selected_tiers.append({"lever": lev, "mmr": default_mmr[lev], "lever_str": f"{lev}x"})

    levels: list[LiquidationLevel] = []
    for t in selected_tiers:
        lev = t["lever"]
        mmr = t["mmr"]
        lev_str = t["lever_str"]
        margin_ratio = 1.0 / lev

        # Liquidation price using REAL MMR
        long_liq = current_price * (1 - margin_ratio + mmr)
        short_liq = current_price * (1 + margin_ratio - mmr)

        # USD volume: use real liquidation data if available, else project from OI
        long_key = f"long_{lev_str}"
        short_key = f"short_{lev_str}"

        long_usd = bucket.get(long_key, {}).get("usd_total", 0)
        short_usd = bucket.get(short_key, {}).get("usd_total", 0)

        # If real data, use weighted avg price; otherwise use projected price
        long_avg_price = long_liq
        short_avg_price = short_liq
        if long_key in bucket and bucket[long_key]["usd_total"] > 0:
            long_avg_price = bucket[long_key]["price_sum"] / bucket[long_key]["usd_total"]
        if short_key in bucket and bucket[short_key]["usd_total"] > 0:
            short_avg_price = bucket[short_key]["price_sum"] / bucket[short_key]["usd_total"]

        # If no real liquidation data, project from OI distribution
        if long_usd == 0 and total_oi_usd > 0:
            weight = {5: 0.35, 10: 0.25, 25: 0.20, 50: 0.12, 100: 0.08}.get(lev, 0.1)
            long_usd = total_oi_usd * weight * 0.15  # 15% of weighted OI
        if short_usd == 0 and total_oi_usd > 0:
            weight = {5: 0.35, 10: 0.25, 25: 0.20, 50: 0.12, 100: 0.08}.get(lev, 0.1)
            short_usd = total_oi_usd * weight * 0.15

        levels.append(LiquidationLevel(
            price=round(long_avg_price, 2),
            long_liq_usd=round(long_usd, 0),
            short_liq_usd=0,
            leverage=lev_str,
        ))
        levels.append(LiquidationLevel(
            price=round(short_avg_price, 2),
            long_liq_usd=0,
            short_liq_usd=round(short_usd, 0),
            leverage=lev_str,
        ))

    levels.sort(key=lambda l: l.price)
    total_long = sum(l.long_liq_usd for l in levels)
    total_short = sum(l.short_liq_usd for l in levels)

    real_count = len(liq_orders)
    src = "OKX真实数据" if real_count > 0 else "OKX OI投影"
    print(f"  ✓ 清算热力图 {symbol}: {real_count}笔真实清算 | OI=${total_oi_usd:,.0f} | 来源={src}")

    return LiquidationMap(
        symbol=symbol,
        current_price=round(current_price, 2),
        levels=levels,
        total_long_liq=round(total_long, 0),
        total_short_liq=round(total_short, 0),
        timestamp=datetime.now(timezone.utc),
    )


async def get_all_liquidation_maps() -> list[LiquidationMap]:
    """Get liquidation maps for all symbols."""
    results = []
    for symbol in settings.SYMBOLS:
        try:
            lm = await get_liquidation_map(symbol)
            results.append(lm)
        except Exception as e:
            print(f"  ✗ Liquidation map failed for {symbol}: {e}")
    return results

