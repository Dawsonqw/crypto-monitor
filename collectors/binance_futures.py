"""
Binance Futures data collector.

Fetches open interest, funding rates, long/short ratios, liquidations,
order book depth, and other futures market data from the Binance Futures API.
"""

import asyncio
import time
from typing import Optional, Union

import httpx
from loguru import logger


class BinanceFuturesCollector:
    """Collector for Binance USD-M Futures market data."""

    def __init__(
        self,
        base_url: str = "https://fapi.binance.com",
        timeout: int = 30,
        proxy_url: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ):
        """
        Initialize the Binance Futures collector.

        Args:
            base_url: Binance Futures API base URL.
            timeout: HTTP request timeout in seconds.
            proxy_url: Optional HTTP/SOCKS proxy URL.
            api_key: Optional Binance API key (needed for some endpoints).
            api_secret: Optional Binance API secret.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key
        self.api_secret = api_secret

        headers = {
            "Accept": "application/json",
            "User-Agent": "crypto-monitor/1.0",
        }
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key

        transport_kwargs = {}
        if proxy_url:
            transport_kwargs["proxy"] = proxy_url

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers=headers,
            **transport_kwargs,
        )
        self._semaphore = asyncio.Semaphore(10)
        logger.info(
            "BinanceFuturesCollector initialized | base_url={} timeout={}s proxy={}",
            self.base_url,
            self.timeout,
            proxy_url or "none",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        endpoint: str,
        params: Optional[dict] = None,
        max_retries: int = 3,
    ) -> Optional[Union[dict, list]]:
        """
        Send a GET request with retries and exponential backoff.

        Args:
            endpoint: API endpoint path (e.g. /fapi/v1/openInterest).
            params: Optional query parameters.
            max_retries: Number of retry attempts.

        Returns:
            Parsed JSON response, or None on failure.
        """
        for attempt in range(1, max_retries + 1):
            try:
                async with self._semaphore:
                    response = await self._client.get(endpoint, params=params)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        "Rate limited on {} | retrying after {}s (attempt {}/{})",
                        endpoint,
                        retry_after,
                        attempt,
                        max_retries,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                data = response.json()
                return data

            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "HTTP {} on {} | attempt {}/{} | {}",
                    exc.response.status_code,
                    endpoint,
                    attempt,
                    max_retries,
                    exc.response.text[:200],
                )
            except httpx.TimeoutException:
                logger.warning(
                    "Timeout on {} | attempt {}/{}",
                    endpoint,
                    attempt,
                    max_retries,
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "Request error on {} | attempt {}/{} | {}",
                    endpoint,
                    attempt,
                    max_retries,
                    str(exc),
                )
            except Exception as exc:
                logger.error(
                    "Unexpected error on {} | attempt {}/{} | {}",
                    endpoint,
                    attempt,
                    max_retries,
                    str(exc),
                )

            if attempt < max_retries:
                backoff = 2 ** (attempt - 1)
                logger.debug("Backing off {}s before retry", backoff)
                await asyncio.sleep(backoff)

        logger.error("All {} retries exhausted for {}", max_retries, endpoint)
        return None

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def get_open_interest(self, symbol: str) -> Optional[dict]:
        """
        Get current open interest for a symbol.

        GET /fapi/v1/openInterest?symbol={symbol}

        Returns:
            {'symbol', 'openInterest', 'time'} or None on failure.
        """
        logger.debug("Fetching open interest for {}", symbol)
        return await self._request(
            "/fapi/v1/openInterest",
            params={"symbol": symbol},
        )

    async def get_open_interest_hist(
        self, symbol: str, period: str = "5m", limit: int = 30
    ) -> Optional[list]:
        """
        Get open interest history.

        GET /futures/data/openInterestHist?symbol={symbol}&period={period}&limit={limit}

        Returns:
            List of {'symbol', 'sumOpenInterest', 'sumOpenInterestValue', 'timestamp'}
            or None on failure.
        """
        logger.debug("Fetching OI history for {} period={} limit={}", symbol, period, limit)
        return await self._request(
            "/futures/data/openInterestHist",
            params={"symbol": symbol, "period": period, "limit": limit},
        )

    async def get_long_short_ratio(
        self, symbol: str, period: str = "5m", limit: int = 30
    ) -> Optional[list]:
        """
        Get global long/short account ratio.

        GET /futures/data/globalLongShortAccountRatio?symbol={symbol}&period={period}&limit={limit}

        Returns:
            List of {'symbol', 'longShortRatio', 'longAccount', 'shortAccount', 'timestamp'}
            or None on failure.
        """
        logger.debug("Fetching long/short ratio for {} period={}", symbol, period)
        return await self._request(
            "/futures/data/globalLongShortAccountRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
        )

    async def get_top_long_short_ratio(
        self, symbol: str, period: str = "5m", limit: int = 30
    ) -> Optional[list]:
        """
        Get top trader long/short position ratio.

        GET /futures/data/topLongShortPositionRatio?symbol={symbol}&period={period}&limit={limit}

        Returns:
            List of {'symbol', 'longShortRatio', 'longAccount', 'shortAccount', 'timestamp'}
            or None on failure.
        """
        logger.debug("Fetching top long/short position ratio for {}", symbol)
        return await self._request(
            "/futures/data/topLongShortPositionRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
        )

    async def get_top_long_short_account_ratio(
        self, symbol: str, period: str = "5m", limit: int = 30
    ) -> Optional[list]:
        """
        Get top trader long/short account ratio.

        GET /futures/data/topLongShortAccountRatio?symbol={symbol}&period={period}&limit={limit}

        Returns:
            List of {'symbol', 'longShortRatio', 'longAccount', 'shortAccount', 'timestamp'}
            or None on failure.
        """
        logger.debug("Fetching top long/short account ratio for {}", symbol)
        return await self._request(
            "/futures/data/topLongShortAccountRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
        )

    async def get_funding_rate(self, symbol: str) -> Optional[dict]:
        """
        Get current funding rate / premium index for a symbol.

        GET /fapi/v1/premiumIndex?symbol={symbol}

        Returns:
            {'symbol', 'markPrice', 'indexPrice', 'lastFundingRate',
             'nextFundingTime', 'interestRate', ...} or None on failure.
        """
        logger.debug("Fetching funding rate for {}", symbol)
        return await self._request(
            "/fapi/v1/premiumIndex",
            params={"symbol": symbol},
        )

    async def get_funding_rate_history(
        self, symbol: str, limit: int = 100
    ) -> Optional[list]:
        """
        Get funding rate history.

        GET /fapi/v1/fundingRate?symbol={symbol}&limit={limit}

        Returns:
            List of {'symbol', 'fundingTime', 'fundingRate', 'markPrice'}
            or None on failure.
        """
        logger.debug("Fetching funding rate history for {} limit={}", symbol, limit)
        return await self._request(
            "/fapi/v1/fundingRate",
            params={"symbol": symbol, "limit": limit},
        )

    async def get_force_orders(
        self, symbol: Optional[str] = None, limit: int = 50
    ) -> Optional[list]:
        """
        Get forced liquidation orders.

        GET /fapi/v1/allForceOrders with optional symbol and limit.
        Note: May require API key depending on Binance access tier.

        Returns:
            List of liquidation order dicts or None on failure.
        """
        params: dict = {"limit": limit}
        if symbol is not None:
            params["symbol"] = symbol
        logger.debug("Fetching force orders symbol={} limit={}", symbol, limit)
        return await self._request("/fapi/v1/allForceOrders", params=params)

    async def get_taker_long_short_ratio(
        self, symbol: str, period: str = "5m", limit: int = 30
    ) -> Optional[list]:
        """
        Get taker buy/sell volume long/short ratio.

        GET /futures/data/takerlongshortRatio?symbol={symbol}&period={period}&limit={limit}

        Returns:
            List of {'buySellRatio', 'buyVol', 'sellVol', 'timestamp'}
            or None on failure.
        """
        logger.debug("Fetching taker long/short ratio for {} period={}", symbol, period)
        return await self._request(
            "/futures/data/takerlongshortRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
        )

    async def get_ticker_24h(
        self, symbol: Optional[str] = None
    ) -> Optional[Union[dict, list]]:
        """
        Get 24hr ticker price change statistics.

        GET /fapi/v1/ticker/24hr with optional symbol.

        Returns:
            Single dict if symbol provided, list of dicts otherwise,
            or None on failure.
        """
        params = {}
        if symbol is not None:
            params["symbol"] = symbol
        logger.debug("Fetching 24h ticker symbol={}", symbol)
        return await self._request("/fapi/v1/ticker/24hr", params=params or None)

    async def get_depth(self, symbol: str, limit: int = 20) -> Optional[dict]:
        """
        Get order book depth.

        GET /fapi/v1/depth?symbol={symbol}&limit={limit}

        Returns:
            {'lastUpdateId', 'bids': [[price, qty], ...], 'asks': [[price, qty], ...]}
            or None on failure.
        """
        logger.debug("Fetching depth for {} limit={}", symbol, limit)
        return await self._request(
            "/fapi/v1/depth",
            params={"symbol": symbol, "limit": limit},
        )

    async def get_multi_symbol_summary(
        self, symbols: list[str], concurrency: int = 5
    ) -> dict:
        """
        Concurrently fetch OI, funding rate, long/short ratio, and taker ratio
        for multiple symbols.

        Args:
            symbols: List of trading pair symbols (e.g. ['BTCUSDT', 'ETHUSDT']).
            concurrency: Max concurrent per-symbol fetches.

        Returns:
            {symbol: {open_interest, funding_rate, long_short_ratio,
                      taker_ratio, mark_price, index_price, ...}}
        """
        sem = asyncio.Semaphore(concurrency)
        results: dict = {}

        async def _fetch_symbol(symbol: str) -> tuple[str, dict]:
            async with sem:
                oi_task = self.get_open_interest(symbol)
                fr_task = self.get_funding_rate(symbol)
                ls_task = self.get_long_short_ratio(symbol, limit=1)
                taker_task = self.get_taker_long_short_ratio(symbol, limit=1)

                oi, fr, ls, taker = await asyncio.gather(
                    oi_task, fr_task, ls_task, taker_task,
                    return_exceptions=True,
                )

                summary: dict = {"symbol": symbol}

                # Open interest
                if isinstance(oi, dict) and oi:
                    summary["open_interest"] = float(oi.get("openInterest", 0))
                    summary["oi_time"] = oi.get("time")
                else:
                    summary["open_interest"] = None

                # Funding rate + mark/index price
                if isinstance(fr, dict) and fr:
                    summary["funding_rate"] = float(fr.get("lastFundingRate", 0))
                    summary["mark_price"] = float(fr.get("markPrice", 0))
                    summary["index_price"] = float(fr.get("indexPrice", 0))
                    summary["next_funding_time"] = fr.get("nextFundingTime")
                    summary["interest_rate"] = float(fr.get("interestRate", 0))
                else:
                    summary["funding_rate"] = None
                    summary["mark_price"] = None
                    summary["index_price"] = None
                    summary["next_funding_time"] = None
                    summary["interest_rate"] = None

                # Long/short ratio (latest entry)
                if isinstance(ls, list) and ls:
                    latest = ls[0]
                    summary["long_short_ratio"] = float(latest.get("longShortRatio", 0))
                    summary["long_account"] = float(latest.get("longAccount", 0))
                    summary["short_account"] = float(latest.get("shortAccount", 0))
                else:
                    summary["long_short_ratio"] = None
                    summary["long_account"] = None
                    summary["short_account"] = None

                # Taker buy/sell ratio (latest entry)
                if isinstance(taker, list) and taker:
                    latest = taker[0]
                    summary["taker_ratio"] = float(latest.get("buySellRatio", 0))
                    summary["taker_buy_vol"] = float(latest.get("buyVol", 0))
                    summary["taker_sell_vol"] = float(latest.get("sellVol", 0))
                else:
                    summary["taker_ratio"] = None
                    summary["taker_buy_vol"] = None
                    summary["taker_sell_vol"] = None

                return symbol, summary

        tasks = [_fetch_symbol(sym) for sym in symbols]
        fetched = await asyncio.gather(*tasks, return_exceptions=True)

        for item in fetched:
            if isinstance(item, tuple):
                sym, data = item
                results[sym] = data
            elif isinstance(item, Exception):
                logger.error("Error in multi-symbol fetch: {}", item)

        logger.info(
            "Multi-symbol summary fetched for {} symbols ({} ok)",
            len(symbols),
            len(results),
        )
        return results

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()
        logger.info("BinanceFuturesCollector client closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
