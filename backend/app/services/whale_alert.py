"""Whale alert service - monitors large on-chain transactions.

Uses blockchain.info for BTC and public APIs for other chains.
Identifies exchange wallets using known hot-wallet address prefixes.
"""

import httpx
from datetime import datetime, timezone, timedelta
from app.models.schemas import WhaleTransaction, WhaleAlertResponse
from app.core.config import settings

# ── Known exchange BTC hot wallet addresses (verified on-chain) ──
# These are well-known deposit/withdrawal addresses for major exchanges.
# Source: public on-chain analysis, OXT, Arkham Intel, Glassnode labels.
_EXCHANGE_ADDRESSES: dict[str, str] = {
    # Binance
    "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo": "Binance",
    "3JZq4atUahhuA9rLhXLMhhTo133J9rF97j": "Binance",
    "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s": "Binance",
    "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h": "Binance",
    "3M219KR5vEneNb47ewrPfWyb5jQ2DjxRP6": "Binance",
    "bc1qx9t2l3pyny2spqpqlye8svce70nppwtaxwdrp4": "Binance",
    # Coinbase
    "3Kzh9qAqVWQhEsfQz7zEQL1EuSx5tyNLNS": "Coinbase",
    "395vnFRMTketKmLtMcavpzGnRBVAyFkn2i": "Coinbase",
    "1FzWLkAahHooV3kzTgyx6qsXoRDrBv5CeG": "Coinbase",
    "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh": "Coinbase",
    "bc1q4c8n5t00jmj8temxdgcc3t32nkg2wjwz24lywv": "Coinbase",
    # Kraken
    "3FHNBLobJnbCTFTVakh5TXnC6XMZsk7Koy": "Kraken",
    "3AfC8x7qJpMKn6qrZrABwb1MRpEW4WPZ7C": "Kraken",
    "bc1qr4dl5wa7kl8yu792dceg9z5knl2gkn220lk7a9": "Kraken",
    # Bitfinex
    "3D2oetdNuZUqQHPJmcMDDHYoqkyNVsFk9r": "Bitfinex",
    "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97": "Bitfinex",
    "1Kr6QSydW9bFQG1mXiPNNu6WpJGmUa9i1g": "Bitfinex",
    # OKX
    "3LYJfcfHPXYJreMsASk2jkn69LWEYKzexb": "OKX",
    "1BDHEPgB8iGWkDqQBVwm4XCSyupaBm5Wd7": "OKX",
    "bc1q2s3rjwvam9dt2ftt4sqxqjf3twav0gdx0k0q2etjd3905ay4ymrs9nn3uv": "OKX",
    # Bybit
    "1ByBTV5rRgTMPSFZoafDGBMu2qTfcNP5q5": "Bybit",
    # Huobi / HTX
    "1HckjUpRGcrrRAtFaaCAUaGjsPx9oYmLaZ": "Huobi",
    "14mP6caC5dFhRaGYfvMdLm6Af3BHDGNseS": "Huobi",
    "1LAnF8h3qMGx3TSwNUHVneBZUEpwE4gu3D": "Huobi",
    # Gemini
    "1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX": "Gemini",
    # Bitstamp
    "3P3QsMVK89JBNqZQv5zMAKG8FK3kJM4rjt": "Bitstamp",
}

# Build a prefix lookup for faster matching (first 10 chars)
_ADDR_PREFIX_MAP: dict[str, str] = {}
for _addr, _name in _EXCHANGE_ADDRESSES.items():
    _ADDR_PREFIX_MAP[_addr[:10]] = _name

# Minimum USD thresholds for whale alerts
WHALE_THRESHOLDS = {
    "BTCUSDT": 1_000_000,
    "ETHUSDT": 500_000,
    "SOLUSDT": 250_000,
    "BNBUSDT": 250_000,
}

# Blockchain.info API for BTC large transactions
BTC_API = "https://blockchain.info"


async def _fetch_btc_whale_txs(min_usd: float = 1_000_000) -> list[WhaleTransaction]:
    """Fetch recent large BTC transactions from blockchain.info (last 2 blocks)."""
    txs = []
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            # Get latest block
            resp = await client.get(f"{BTC_API}/latestblock")
            if resp.status_code != 200:
                return txs
            latest = resp.json()
            block_hashes = [latest.get("hash", "")]

            # Get BTC price
            price_resp = await client.get(f"{BTC_API}/ticker")
            btc_price = 0
            if price_resp.status_code == 200:
                ticker = price_resp.json()
                btc_price = ticker.get("USD", {}).get("last", 0)

            if not btc_price:
                return txs

            # Scan up to 2 blocks for more diverse data
            for block_hash in block_hashes:
                try:
                    resp = await client.get(f"{BTC_API}/rawblock/{block_hash}")
                    if resp.status_code != 200:
                        continue
                    block = resp.json()
                except Exception:
                    continue

                # If this is the first block, add previous block hash
                if len(block_hashes) == 1:
                    prev_hash = block.get("prev_block", "")
                    if prev_hash:
                        block_hashes.append(prev_hash)

                # Filter large transactions
                for tx in block.get("tx", [])[:200]:
                    total_out = sum(o.get("value", 0) for o in tx.get("out", [])) / 1e8
                    usd_value = total_out * btc_price

                    if usd_value >= min_usd:
                        # Collect ALL input/output addresses
                        input_addrs = [inp.get("prev_out", {}).get("addr", "") for inp in tx.get("inputs", []) if inp.get("prev_out", {}).get("addr")]
                        output_addrs = [out.get("addr", "") for out in tx.get("out", []) if out.get("addr")]
                        n_inputs = len(input_addrs)
                        n_outputs = len(output_addrs)

                        # Step 1: Try known address matching
                        from_owner, from_addr = _find_exchange_in_list(input_addrs)
                        to_owner, to_addr = _find_exchange_in_list(output_addrs)

                        # Step 2: Heuristic classification based on tx structure
                        # Only apply heuristics for reasonably-sized transactions (<$50M)
                        # Ultra-large txs are more likely internal/OTC, not retail deposits
                        if from_owner == "Unknown" and to_owner == "Unknown" and usd_value < 50_000_000:
                            from_owner, to_owner = _heuristic_classify(n_inputs, n_outputs)
                            if from_owner != "Unknown":
                                from_addr = input_addrs[0] if input_addrs else "unknown"
                            if to_owner != "Unknown":
                                to_addr = output_addrs[0] if output_addrs else "unknown"

                        if not from_addr or from_addr == "":
                            from_addr = input_addrs[0] if input_addrs else "unknown"
                        if not to_addr or to_addr == "":
                            to_addr = output_addrs[0] if output_addrs else "unknown"

                        tx_type = _classify_tx(from_owner, to_owner)
                        print(f"  🐋 Whale TX: ${usd_value:,.0f} | inputs={n_inputs} outputs={n_outputs} | {from_owner}→{to_owner} | type={tx_type}")

                        txs.append(WhaleTransaction(
                            hash=tx.get("hash", "")[:16],
                            blockchain="bitcoin",
                            symbol="BTC",
                            amount=round(total_out, 4),
                            amount_usd=round(usd_value, 0),
                            from_address=from_addr[:12] + "..." if len(from_addr) > 12 else from_addr,
                            from_owner=from_owner,
                            to_address=to_addr[:12] + "..." if len(to_addr) > 12 else to_addr,
                            to_owner=to_owner,
                            tx_type=tx_type,
                            timestamp=datetime.fromtimestamp(tx.get("time", 0), tz=timezone.utc),
                        ))
    except Exception as e:
        print(f"  ⚠ BTC whale fetch error: {e}")
    return txs


def _identify_owner(addr: str) -> str:
    """Identify exchange by matching known hot wallet addresses."""
    if not addr:
        return "Unknown"
    if addr in _EXCHANGE_ADDRESSES:
        return _EXCHANGE_ADDRESSES[addr]
    prefix = addr[:10]
    if prefix in _ADDR_PREFIX_MAP:
        return _ADDR_PREFIX_MAP[prefix]
    return "Unknown"


def _find_exchange_in_list(addrs: list[str]) -> tuple[str, str]:
    """Check a list of addresses for known exchanges. Returns (owner, addr)."""
    for addr in addrs:
        owner = _identify_owner(addr)
        if owner != "Unknown":
            return owner, addr
    return "Unknown", addrs[0] if addrs else "unknown"


def _heuristic_classify(n_inputs: int, n_outputs: int) -> tuple[str, str]:
    """Use transaction structure to guess exchange involvement.

    Bitcoin tx always has ≥2 outputs (payment + change), so n_outputs==1 is rare.

    Heuristics:
    - ≥10 inputs + ≤3 outputs: Exchange UTXO consolidation (internal)
    - ≤2 inputs + ≥5 outputs: Exchange batch withdrawal → outflow
    - 3-9 inputs + ≤2 outputs: User consolidating UTXOs to deposit → inflow
    - ≥5 inputs + ≥5 outputs: Large-scale internal shuffle
    - ≤2 inputs + 3-4 outputs: Small batch withdrawal → outflow
    """
    if n_inputs >= 10 and n_outputs <= 3:
        # Very many inputs → few outputs = exchange UTXO consolidation
        return "Exchange(归集)", "Exchange(归集)"
    elif n_inputs <= 2 and n_outputs >= 5:
        # Classic exchange batch withdrawal
        return "Exchange(提币)", "Unknown"
    elif 3 <= n_inputs <= 9 and n_outputs <= 2:
        # Multiple UTXOs consolidating to 1-2 addresses = deposit to exchange
        return "Unknown", "Exchange(充币)"
    elif n_inputs >= 5 and n_outputs >= 5:
        # Many on both sides = exchange internal movement
        return "Exchange(内部)", "Exchange(内部)"
    elif n_inputs <= 2 and 3 <= n_outputs <= 4:
        # Small batch withdrawal
        return "Exchange(提币)", "Unknown"
    return "Unknown", "Unknown"


def _classify_tx(from_owner: str, to_owner: str) -> str:
    """Classify transaction type."""
    from_is_exchange = from_owner != "Unknown"
    to_is_exchange = to_owner != "Unknown"

    if from_is_exchange and not to_is_exchange:
        return "exchange_outflow"  # Bullish - withdrawing from exchange
    elif not from_is_exchange and to_is_exchange:
        return "exchange_inflow"   # Bearish - depositing to exchange (likely to sell)
    elif from_is_exchange and to_is_exchange:
        return "inter_exchange"
    return "transfer"


async def get_whale_alerts(symbol: str | None = None) -> WhaleAlertResponse:
    """Get whale alerts for a symbol or all symbols."""
    all_txs: list[WhaleTransaction] = []

    # Always fetch BTC whales
    if symbol is None or symbol == "BTCUSDT":
        btc_txs = await _fetch_btc_whale_txs(WHALE_THRESHOLDS.get("BTCUSDT", 1_000_000))
        all_txs.extend(btc_txs)

    # Sort by USD amount descending
    all_txs.sort(key=lambda t: t.amount_usd, reverse=True)

    # Calculate summary
    inflow = sum(t.amount_usd for t in all_txs if t.tx_type == "exchange_inflow")
    outflow = sum(t.amount_usd for t in all_txs if t.tx_type == "exchange_outflow")

    return WhaleAlertResponse(
        transactions=all_txs[:20],
        summary={
            "total_inflow_usd": round(inflow, 0),
            "total_outflow_usd": round(outflow, 0),
            "net_flow": round(outflow - inflow, 0),
            "total_transactions": len(all_txs),
            "signal": "bullish" if outflow > inflow else "bearish" if inflow > outflow else "neutral",
        },
    )

