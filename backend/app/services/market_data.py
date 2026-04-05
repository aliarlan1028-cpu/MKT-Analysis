"""Market data collection with Binance mirror fallback + CoinMarketCap fallback."""

import httpx
from datetime import datetime, timezone
from app.models.schemas import MarketData, FearGreedIndex
from app.core.config import settings

# Binance API mirrors – try in order until one works
BINANCE_SPOT_URLS = [
    "https://api4.binance.com",
    "https://api1.binance.com",
    "https://api.binance.com",
]
BINANCE_FUTURES_URLS = [
    "https://fapi.binance.com",
]

# CoinMarketCap symbol mapping (strip USDT suffix)
CMC_SYMBOLS = {
    "BTCUSDT": "BTC",
    "SOLUSDT": "SOL",
    "SUIUSDT": "SUI",
}


async def _try_binance_get(path: str, params: dict, base_urls: list[str], timeout: float = 10) -> dict | list | None:
    """Try multiple Binance mirrors."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        for base in base_urls:
            try:
                resp = await client.get(f"{base}{path}", params=params)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                continue
    return None


async def fetch_binance_ticker(symbol: str) -> dict | None:
    """Fetch spot ticker from Binance mirrors."""
    return await _try_binance_get("/api/v3/ticker/24hr", {"symbol": symbol}, BINANCE_SPOT_URLS)


async def fetch_binance_futures_data(symbol: str) -> dict:
    """Fetch futures funding rate, long/short ratio, open interest."""
    result = {"funding_rate": None, "long_short_ratio": None, "open_interest": None, "oi_change_pct": None}
    try:
        funding = await _try_binance_get("/fapi/v1/fundingRate", {"symbol": symbol, "limit": 1}, BINANCE_FUTURES_URLS)
        if funding and isinstance(funding, list) and len(funding) > 0:
            result["funding_rate"] = float(funding[0]["fundingRate"])

        ls = await _try_binance_get("/futures/data/topLongShortAccountRatio", {"symbol": symbol, "period": "1h", "limit": 1}, BINANCE_FUTURES_URLS)
        if ls and isinstance(ls, list) and len(ls) > 0:
            result["long_short_ratio"] = float(ls[0]["longShortRatio"])

        oi = await _try_binance_get("/fapi/v1/openInterest", {"symbol": symbol}, BINANCE_FUTURES_URLS)
        if oi and isinstance(oi, dict):
            result["open_interest"] = float(oi.get("openInterest", 0))

        oi_hist = await _try_binance_get("/futures/data/openInterestHist", {"symbol": symbol, "period": "1h", "limit": 2}, BINANCE_FUTURES_URLS)
        if oi_hist and isinstance(oi_hist, list):
            result["oi_change_pct"] = _calc_oi_change(oi_hist)
    except Exception as e:
        print(f"  Futures data partial fail for {symbol}: {e}")
    return result


def _calc_oi_change(oi_hist: list) -> float | None:
    if len(oi_hist) >= 2:
        old = float(oi_hist[0]["sumOpenInterest"])
        new = float(oi_hist[1]["sumOpenInterest"])
        if old > 0:
            return round((new - old) / old * 100, 2)
    return None


# ── OKX v5 API ──
_OKX_ENDPOINTS = [
    "https://www.okx.com",
    "https://aws.okx.com",
]

# OKX bar mapping (Binance → OKX format)
_OKX_INTERVAL_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W", "1M": "1M",
}

# OKX symbol mapping (Binance format → OKX instId)
_OKX_SYMBOL_MAP = {
    "BTCUSDT": "BTC-USDT",
    "SOLUSDT": "SOL-USDT",
    "SUIUSDT": "SUI-USDT",
    "ETHUSDT": "ETH-USDT",
    "BNBUSDT": "BNB-USDT",
    "PAXGUSDT": "PAXG-USDT",
}


async def _okx_get(path: str, params: dict, timeout: float = 15) -> dict | None:
    """Try OKX v5 endpoints."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        for base in _OKX_ENDPOINTS:
            try:
                resp = await client.get(f"{base}{path}", params=params)
                if resp.status_code == 200:
                    body = resp.json()
                    if body.get("code") == "0" and body.get("data"):
                        return body
            except Exception:
                continue
    return None


async def fetch_okx_ticker(symbol: str) -> dict | None:
    """Fetch spot ticker from OKX (24h high/low/vol/price)."""
    okx_inst = _OKX_SYMBOL_MAP.get(symbol)
    if not okx_inst:
        return None
    body = await _okx_get("/api/v5/market/ticker", {"instId": okx_inst})
    if body and body.get("data"):
        return body["data"][0]
    return None


async def fetch_okx_swap_data(symbol: str) -> dict:
    """Fetch funding rate, open interest from OKX SWAP."""
    result = {"funding_rate": None, "open_interest": None, "oi_change_pct": None}
    okx_inst = _OKX_SYMBOL_MAP.get(symbol)
    if not okx_inst:
        return result
    swap_inst = okx_inst + "-SWAP"  # e.g. BTC-USDT-SWAP

    # Funding rate
    try:
        body = await _okx_get("/api/v5/public/funding-rate", {"instId": swap_inst})
        if body and body["data"]:
            result["funding_rate"] = float(body["data"][0].get("fundingRate", 0))
    except Exception as e:
        print(f"  ⚠ OKX funding rate failed for {symbol}: {e}")

    # Open interest
    try:
        body = await _okx_get("/api/v5/public/open-interest", {"instType": "SWAP", "instId": swap_inst})
        if body and body["data"]:
            oi_coin = float(body["data"][0].get("oiCcy", 0))
            result["open_interest"] = oi_coin  # in coins
    except Exception as e:
        print(f"  ⚠ OKX OI failed for {symbol}: {e}")

    return result


async def get_market_data_okx(symbol: str) -> MarketData | None:
    """Get full market data from OKX (ticker + swap data)."""
    ticker = await fetch_okx_ticker(symbol)
    if not ticker:
        return None
    swap = await fetch_okx_swap_data(symbol)

    price = float(ticker.get("last", 0))
    open_24h = float(ticker.get("open24h", 0))
    change = price - open_24h if open_24h else 0
    change_pct = (change / open_24h * 100) if open_24h else 0

    return MarketData(
        symbol=symbol,
        name=settings.SYMBOL_NAMES.get(symbol, symbol),
        price=price,
        price_change_24h=round(change, 2),
        price_change_pct_24h=round(change_pct, 2),
        high_24h=float(ticker.get("high24h", 0)),
        low_24h=float(ticker.get("low24h", 0)),
        volume_24h=float(ticker.get("volCcy24h", 0)),  # quote volume in USDT
        funding_rate=swap["funding_rate"],
        open_interest=swap["open_interest"],
        open_interest_change_pct=swap["oi_change_pct"],
        timestamp=datetime.now(timezone.utc),
    )


async def _fetch_okx_klines(symbol: str, interval: str, limit: int) -> list[list] | None:
    """Fetch klines from OKX v5 API. Converts to Binance-compatible format."""
    okx_bar = _OKX_INTERVAL_MAP.get(interval)
    okx_inst = _OKX_SYMBOL_MAP.get(symbol)
    if not okx_bar or not okx_inst:
        return None
    # OKX max limit per request is 300
    okx_limit = min(limit, 300)
    for base_url in _OKX_ENDPOINTS:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{base_url}/api/v5/market/candles",
                    params={"instId": okx_inst, "bar": okx_bar, "limit": str(okx_limit)},
                )
                if resp.status_code != 200:
                    continue
                body = resp.json()
                if body.get("code") != "0" or not body.get("data"):
                    continue
                # OKX returns [[ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm], ...]
                # Data is in DESC order (newest first), reverse to ASC
                rows = body["data"][::-1]
                result = []
                for r in rows:
                    ts = int(r[0])  # already ms
                    result.append([
                        ts,       # open_time
                        r[1],     # open
                        r[2],     # high
                        r[3],     # low
                        r[4],     # close
                        r[5],     # volume (base)
                        ts + 1,   # close_time (approx)
                        r[7],     # quote_volume (volCcyQuote)
                        0,        # trades
                        "0",      # taker_buy_base
                        "0",      # taker_buy_quote
                        "0",      # ignore
                    ])
                print(f"  ✓ OKX klines for {symbol} ({interval}): {len(result)} candles via {base_url}")
                return result
        except Exception as e:
            print(f"  ⚠ OKX {base_url} klines failed: {e}")
            continue
    return None


# ── Gate.io API ──
_GATEIO_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "8h": "8h",
    "1d": "1d", "1w": "7d", "1M": "30d",
}

_GATEIO_SYMBOL_MAP = {
    "BTCUSDT": "BTC_USDT",
    "ETHUSDT": "ETH_USDT",
    "SOLUSDT": "SOL_USDT",
    "BNBUSDT": "BNB_USDT",
    "PAXGUSDT": "PAXG_USDT",
}


async def _fetch_gateio_klines(symbol: str, interval: str, limit: int) -> list[list] | None:
    """Fetch klines from Gate.io as fallback. Converts to Binance-compatible format."""
    gate_interval = _GATEIO_INTERVAL_MAP.get(interval)
    gate_symbol = _GATEIO_SYMBOL_MAP.get(symbol)
    if not gate_interval or not gate_symbol:
        return None
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.gateio.ws/api/v4/spot/candlesticks",
                params={
                    "currency_pair": gate_symbol,
                    "interval": gate_interval,
                    "limit": limit,
                },
            )
            if resp.status_code != 200:
                print(f"  ⚠ Gate.io HTTP {resp.status_code} for {symbol}")
                return None
            rows = resp.json()
            if not rows or not isinstance(rows, list):
                return None
            # Gate.io returns [[unix_ts, quote_vol, close, high, low, open, base_vol, is_closed], ...]
            # Already in ASC order
            result = []
            for r in rows:
                ts = int(r[0]) * 1000  # Gate.io uses seconds, convert to ms
                result.append([
                    ts,          # open_time
                    r[5],        # open
                    r[3],        # high
                    r[4],        # low
                    r[2],        # close
                    r[6],        # volume (base)
                    ts + 1,      # close_time (approx)
                    r[1],        # quote_volume
                    0,           # trades
                    "0",         # taker_buy_base
                    "0",         # taker_buy_quote
                    "0",         # ignore
                ])
            print(f"  ✓ Gate.io klines for {symbol} ({interval}): {len(result)} candles")
            return result
    except Exception as e:
        print(f"  ⚠ Gate.io klines failed for {symbol}: {e}")
        return None


async def fetch_klines(symbol: str, interval: str = "4h", limit: int = 100) -> list[list]:
    """Fetch kline/candlestick data. Tries Binance → OKX → Gate.io."""
    # 1) Try Binance
    data = await _try_binance_get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit}, BINANCE_SPOT_URLS)
    if data:
        return data
    # 2) OKX fallback
    print(f"  ⚠ Binance klines failed for {symbol}, trying OKX...")
    okx_data = await _fetch_okx_klines(symbol, interval, limit)
    if okx_data:
        return okx_data
    # 3) Gate.io fallback
    print(f"  ⚠ OKX klines failed for {symbol}, trying Gate.io...")
    gate_data = await _fetch_gateio_klines(symbol, interval, limit)
    if gate_data:
        return gate_data
    raise Exception(f"All sources failed for klines {symbol} {interval}")


async def fetch_cmc_batch() -> dict[str, MarketData]:
    """Fetch all symbols from CoinMarketCap in ONE request (free tier: 10,000 calls/month)."""
    if not settings.CMC_API_KEY:
        print("  ⚠ CMC_API_KEY not set, skipping CoinMarketCap fallback")
        return {}
    # Build comma-separated CMC symbols
    cmc_list = [CMC_SYMBOLS[s] for s in settings.SYMBOLS if s in CMC_SYMBOLS]
    if not cmc_list:
        return {}
    # Reverse lookup: CMC symbol -> our symbol
    cmc_to_symbol = {v: k for k, v in CMC_SYMBOLS.items()}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                params={
                    "symbol": ",".join(cmc_list),
                    "convert": "USD",
                },
                headers={
                    "X-CMC_PRO_API_KEY": settings.CMC_API_KEY,
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                print(f"  CMC batch failed: HTTP {resp.status_code}")
                return {}
            body = resp.json()
            if body.get("status", {}).get("error_code", 0) != 0:
                print(f"  CMC API error: {body['status'].get('error_message', 'unknown')}")
                return {}
            coins = body.get("data", {})
            result: dict[str, MarketData] = {}
            for cmc_sym, coin_data in coins.items():
                our_symbol = cmc_to_symbol.get(cmc_sym)
                if not our_symbol:
                    continue
                quote = coin_data.get("quote", {}).get("USD", {})
                result[our_symbol] = MarketData(
                    symbol=our_symbol,
                    name=settings.SYMBOL_NAMES.get(our_symbol, our_symbol),
                    price=round(float(quote.get("price", 0)), 2),
                    price_change_24h=round(float(quote.get("volume_change_24h", 0)), 2),
                    price_change_pct_24h=round(float(quote.get("percent_change_24h", 0)), 2),
                    high_24h=0,  # CMC free tier doesn't provide 24h high/low
                    low_24h=0,
                    volume_24h=float(quote.get("volume_24h", 0)),
                    market_cap=float(quote.get("market_cap", 0)),
                    timestamp=datetime.now(timezone.utc),
                )
            return result
    except Exception as e:
        print(f"  CMC batch failed: {e}")
        return {}


async def fetch_fear_greed() -> FearGreedIndex:
    """Fetch Fear & Greed Index from Alternative.me."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("https://api.alternative.me/fng/?limit=1")
        resp.raise_for_status()
        data = resp.json()["data"][0]
    return FearGreedIndex(
        value=int(data["value"]),
        label=data["value_classification"],
        timestamp=datetime.fromtimestamp(int(data["timestamp"]), tz=timezone.utc),
    )


async def get_market_data_binance(symbol: str) -> MarketData | None:
    """Try to get market data from Binance mirrors."""
    ticker = await fetch_binance_ticker(symbol)
    if not ticker:
        return None
    futures = await fetch_binance_futures_data(symbol)
    price = float(ticker["lastPrice"])
    prev_close = float(ticker["prevClosePrice"])
    change = price - prev_close
    return MarketData(
        symbol=symbol,
        name=settings.SYMBOL_NAMES.get(symbol, symbol),
        price=price,
        price_change_24h=round(change, 2),
        price_change_pct_24h=round(float(ticker["priceChangePercent"]), 2),
        high_24h=float(ticker["highPrice"]),
        low_24h=float(ticker["lowPrice"]),
        volume_24h=float(ticker["quoteVolume"]),
        funding_rate=futures["funding_rate"],
        long_short_ratio=futures["long_short_ratio"],
        open_interest=futures["open_interest"],
        open_interest_change_pct=futures["oi_change_pct"],
        timestamp=datetime.now(timezone.utc),
    )


async def get_all_markets() -> list[MarketData]:
    """Fetch market data for all tracked symbols. Tries OKX → Binance → CMC."""
    results: list[MarketData] = []
    missing_symbols: list[str] = []

    # 1) Try OKX first (primary source)
    for symbol in settings.SYMBOLS:
        try:
            data = await get_market_data_okx(symbol)
            if data:
                print(f"  ✓ OKX market data for {symbol}: price=${data.price} high=${data.high_24h} low=${data.low_24h} funding={data.funding_rate}")
                results.append(data)
                continue
        except Exception as e:
            print(f"  ⚠ OKX market data failed for {symbol}: {e}")

        # 2) Fallback to Binance
        try:
            data = await get_market_data_binance(symbol)
            if data:
                results.append(data)
                continue
        except Exception:
            pass

        missing_symbols.append(symbol)

    # 3) Batch fallback to CoinMarketCap for all missing symbols
    if missing_symbols:
        print(f"  OKX+Binance unavailable for {missing_symbols}, falling back to CoinMarketCap...")
        cmc_batch = await fetch_cmc_batch()
        for symbol in missing_symbols:
            if symbol in cmc_batch:
                results.append(cmc_batch[symbol])
            else:
                print(f"  ⚠ No data for {symbol} from any source")

    return results



async def get_market_data_any_okx(coin: str) -> MarketData | None:
    """Get market data for ANY OKX perpetual symbol by base coin name (e.g. 'ETH', 'DOGE')."""
    spot_inst = f"{coin}-USDT"
    swap_inst = f"{coin}-USDT-SWAP"

    # Use SWAP ticker directly (perpetual contract only)
    body = await _okx_get("/api/v5/market/ticker", {"instId": swap_inst})
    if not body or not body.get("data"):
        return None
    ticker = body["data"][0]

    price_str = ticker.get("last", "0")
    price = float(price_str)
    open_24h = float(ticker.get("open24h", 0))
    change = price - open_24h if open_24h else 0
    change_pct = round((change / open_24h * 100), 2) if open_24h else 0

    # Fetch funding rate
    funding_rate = None
    try:
        fr_body = await _okx_get("/api/v5/public/funding-rate", {"instId": swap_inst})
        if fr_body and fr_body["data"]:
            funding_rate = float(fr_body["data"][0].get("fundingRate", 0))
    except Exception:
        pass

    # Fetch open interest
    open_interest = None
    try:
        oi_body = await _okx_get("/api/v5/public/open-interest", {"instType": "SWAP", "instId": swap_inst})
        if oi_body and oi_body["data"]:
            open_interest = float(oi_body["data"][0].get("oiCcy", 0))
    except Exception:
        pass

    return MarketData(
        symbol=f"{coin}USDT",
        name=coin,
        price=price,
        price_change_24h=change,
        price_change_pct_24h=change_pct,
        high_24h=float(ticker.get("high24h", 0)),
        low_24h=float(ticker.get("low24h", 0)),
        volume_24h=float(ticker.get("volCcy24h", 0)) * price,  # convert base volume to USD
        funding_rate=funding_rate,
        open_interest=open_interest,
        open_interest_change_pct=None,
        timestamp=datetime.now(timezone.utc),
    )