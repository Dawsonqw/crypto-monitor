"""
On-chain data collectors for crypto-monitor.

Provides async collectors for:
- Moralis (ERC-20 holders, prices, stats)
- DefiLlama (TVL, pools, DEX volumes)
- Helius (Solana token holders & supply)
- CoinGecko (market data, coin info)
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from loguru import logger


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.0  # seconds, doubles each retry


class _BaseCollector:
    """Shared logic: httpx client, _request with retries."""

    def __init__(
        self,
        *,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        proxy_url: str | None = None,
    ) -> None:
        transport_kwargs: dict[str, Any] = {}
        client_kwargs: dict[str, Any] = {
            "timeout": _DEFAULT_TIMEOUT,
            "headers": headers or {},
        }
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
        if base_url:
            client_kwargs["base_url"] = base_url

        self._client = httpx.AsyncClient(**client_kwargs)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """HTTP request with exponential-backoff retries."""
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = await self._client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=extra_headers,
                )
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_exc = exc
                wait = _RETRY_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "Request {method} {url} attempt {attempt}/{max} failed: {exc} – retrying in {wait}s",
                    method=method,
                    url=url,
                    attempt=attempt,
                    max=_MAX_RETRIES,
                    exc=exc,
                    wait=wait,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(wait)
        # All retries exhausted
        logger.error("Request {method} {url} failed after {max} retries", method=method, url=url, max=_MAX_RETRIES)
        raise last_exc  # type: ignore[misc]

    async def close(self) -> None:
        await self._client.aclose()
        logger.debug("{cls} HTTP client closed", cls=type(self).__name__)


# ---------------------------------------------------------------------------
# Moralis – ERC-20 on-chain data
# ---------------------------------------------------------------------------

class MoralisCollector(_BaseCollector):
    """Moralis Web3 API collector for ERC-20 token data."""

    BASE_URL = "https://deep-index.moralis.io/api/v2.2"

    def __init__(self, api_key: str, proxy_url: str | None = None) -> None:
        self.api_key = api_key
        super().__init__(
            base_url=self.BASE_URL,
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            proxy_url=proxy_url,
        )
        logger.info("MoralisCollector initialised")

    async def get_top_holders(
        self, token_address: str, chain: str = "eth", limit: int = 10
    ) -> list[dict]:
        """Return top holders for an ERC-20 token."""
        logger.debug(
            "Fetching top holders for {token} on {chain}",
            token=token_address,
            chain=chain,
        )
        data = await self._request(
            "GET",
            f"/erc20/{token_address}/top-holders",
            params={"chain": chain, "limit": limit},
        )
        # Moralis may wrap in a list or dict with 'result' key
        if isinstance(data, dict):
            return data.get("result", [data])
        return data

    async def get_token_price(
        self, token_address: str, chain: str = "eth"
    ) -> dict:
        """Return current price info for an ERC-20 token."""
        logger.debug(
            "Fetching token price for {token} on {chain}",
            token=token_address,
            chain=chain,
        )
        return await self._request(
            "GET",
            f"/erc20/{token_address}/price",
            params={"chain": chain},
        )

    async def get_token_stats(
        self, token_address: str, chain: str = "eth"
    ) -> dict:
        """Return token statistics (transfers, holders count, etc.)."""
        logger.debug(
            "Fetching token stats for {token} on {chain}",
            token=token_address,
            chain=chain,
        )
        return await self._request(
            "GET",
            f"/erc20/{token_address}/stats",
            params={"chain": chain},
        )


# ---------------------------------------------------------------------------
# DefiLlama – TVL, pools, DEX volumes
# ---------------------------------------------------------------------------

class DefiLlamaCollector(_BaseCollector):
    """DefiLlama open API collector (no key required)."""

    def __init__(
        self,
        base_url: str = "https://api.llama.fi",
        yields_url: str = "https://yields.llama.fi",
        proxy_url: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.yields_url = yields_url.rstrip("/")
        # Don't set base_url on the client – we use full URLs since there are
        # two different hosts.
        super().__init__(
            headers={"Accept": "application/json"},
            proxy_url=proxy_url,
        )
        logger.info("DefiLlamaCollector initialised (base={base}, yields={yields})", base=self.base_url, yields=self.yields_url)

    async def get_protocol_tvl(self, protocol: str) -> dict:
        """Full protocol data including current TVL."""
        logger.debug("Fetching protocol TVL for {p}", p=protocol)
        return await self._request("GET", f"{self.base_url}/protocol/{protocol}")

    async def get_tvl_history(self, protocol: str) -> list:
        """Extract the TVL timeseries from protocol data."""
        logger.debug("Fetching TVL history for {p}", p=protocol)
        data = await self._request("GET", f"{self.base_url}/protocol/{protocol}")
        tvl_array = data.get("tvl", []) if isinstance(data, dict) else []
        logger.debug("Got {n} TVL data points for {p}", n=len(tvl_array), p=protocol)
        return tvl_array

    async def get_pools(self, pool_id: str | None = None) -> dict | list:
        """Fetch yield pools. Optionally filter by pool_id."""
        logger.debug("Fetching pools (pool_id={pid})", pid=pool_id)
        data = await self._request("GET", f"{self.yields_url}/pools")
        if pool_id is not None:
            pools = data.get("data", []) if isinstance(data, dict) else data
            filtered = [p for p in pools if p.get("pool") == pool_id]
            return filtered[0] if len(filtered) == 1 else filtered
        return data

    async def get_chain_tvl(self, chain: str | None = None) -> dict:
        """Chain-level TVL. If chain given, return historical TVL for that chain."""
        if chain:
            logger.debug("Fetching historical chain TVL for {c}", c=chain)
            return await self._request(
                "GET", f"{self.base_url}/v2/historicalChainTvl/{chain}"
            )
        logger.debug("Fetching all chains TVL")
        return await self._request("GET", f"{self.base_url}/v2/chains")

    async def get_dex_volumes(self, chain: str | None = None) -> dict:
        """DEX volume overview, optionally per chain."""
        if chain:
            logger.debug("Fetching DEX volumes for chain {c}", c=chain)
            return await self._request(
                "GET", f"{self.base_url}/overview/dexs/{chain}"
            )
        logger.debug("Fetching global DEX volumes")
        return await self._request("GET", f"{self.base_url}/overview/dexs")


# ---------------------------------------------------------------------------
# Helius – Solana on-chain data (JSON-RPC)
# ---------------------------------------------------------------------------

class HeliusCollector(_BaseCollector):
    """Helius / Solana RPC collector for SPL token data."""

    def __init__(self, api_key: str, proxy_url: str | None = None) -> None:
        self.api_key = api_key
        self.rpc_url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
        super().__init__(
            headers={"Content-Type": "application/json"},
            proxy_url=proxy_url,
        )
        logger.info("HeliusCollector initialised")

    async def _rpc_call(self, method: str, params: list) -> Any:
        """Perform a Solana JSON-RPC call via Helius."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        data = await self._request("POST", self.rpc_url, json_body=payload)
        if "error" in data:
            logger.error("RPC error for {m}: {e}", m=method, e=data["error"])
            raise RuntimeError(f"Helius RPC error: {data['error']}")
        return data.get("result")

    async def get_token_holders(
        self, mint_address: str, limit: int = 10
    ) -> list[dict]:
        """Get largest token accounts for a given SPL mint."""
        logger.debug("Fetching token holders for mint {m}", m=mint_address)
        result = await self._rpc_call("getTokenLargestAccounts", [mint_address])
        accounts = result.get("value", []) if isinstance(result, dict) else []
        # Trim to requested limit
        return accounts[:limit]

    async def get_token_supply(self, mint_address: str) -> dict:
        """Get total supply info for an SPL token."""
        logger.debug("Fetching token supply for mint {m}", m=mint_address)
        result = await self._rpc_call("getTokenSupply", [mint_address])
        return result if isinstance(result, dict) else {"value": result}


# ---------------------------------------------------------------------------
# CoinGecko – market data
# ---------------------------------------------------------------------------

class CoinGeckoCollector(_BaseCollector):
    """CoinGecko API collector for market data."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.api_key = api_key
        headers: dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["x-cg-demo-api-key"] = api_key
        self.cg_base_url = base_url.rstrip("/")
        super().__init__(
            headers=headers,
            proxy_url=proxy_url,
        )
        logger.info("CoinGeckoCollector initialised (base={b})", b=self.cg_base_url)

    async def get_market_data(
        self, ids: list[str], vs_currency: str = "usd"
    ) -> list[dict]:
        """Fetch market data for a list of coin IDs."""
        ids_str = ",".join(ids)
        logger.debug("Fetching market data for {ids}", ids=ids_str)
        return await self._request(
            "GET",
            f"{self.cg_base_url}/coins/markets",
            params={
                "vs_currency": vs_currency,
                "ids": ids_str,
                "order": "market_cap_desc",
            },
        )

    async def get_coin_info(self, coin_id: str) -> dict:
        """Fetch detailed info for a single coin."""
        logger.debug("Fetching coin info for {id}", id=coin_id)
        return await self._request(
            "GET", f"{self.cg_base_url}/coins/{coin_id}"
        )
