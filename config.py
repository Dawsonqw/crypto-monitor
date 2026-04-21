"""
Configuration module for crypto-monitor.

Loads settings from the parent freqtrade/.env file using pydantic-settings.
Variable names match the existing .env layout — no extra prefixes needed.
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve .env path: honour DOTENV_PATH env var, otherwise walk up to freqtrade/
_DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_ENV_FILE = Path(os.getenv("DOTENV_PATH", str(_DEFAULT_ENV_FILE)))


# ── Binance ───────────────────────────────────────────────────────────────────

class BinanceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BINANCE_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    futures_base_url: str = "https://fapi.binance.com"
    demo_base_url: str = "https://testnet.binancefuture.com"
    demo_api_key: str = ""
    demo_api_secret: str = ""
    live_base_url: str = "https://fapi.binance.com"
    live_api_key: str = ""
    live_api_secret: str = ""


# ── On-chain / third-party data ──────────────────────────────────────────────
# .env uses bare names: MORALIS_API_KEY, HELIUS_API_KEY, DEFILLAMA_BASE_URL, etc.

class OnChainSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    moralis_api_key: str = Field(default="", alias="MORALIS_API_KEY")
    helius_api_key: str = Field(default="", alias="HELIUS_API_KEY")
    tonapi_base_url: str = Field(default="https://tonapi.io", alias="TONAPI_BASE_URL")
    defillama_base_url: str = Field(default="https://api.llama.fi", alias="DEFILLAMA_BASE_URL")
    defillama_yields_url: str = Field(default="https://yields.llama.fi", alias="DEFILLAMA_YIELDS_URL")
    coingecko_base_url: str = Field(default="https://api.coingecko.com/api/v3", alias="COINGECKO_BASE_URL")
    coingecko_api_key: str = Field(default="", alias="COINGECKO_API_KEY")
    coinlore_base_url: str = Field(default="https://api.coinlore.net/api", alias="COINLORE_BASE_URL")


# ── Monitor behaviour ────────────────────────────────────────────────────────
# .env uses bare names: QUOTE_ASSET, MAX_ANALYSIS_SYMBOLS, TOP_N, etc.

class MonitorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    quote_asset: str = Field(default="USDT", alias="QUOTE_ASSET")
    market_cap_limit_usd: float = Field(default=1_000_000_000, alias="MARKET_CAP_LIMIT_USD")
    max_analysis_symbols: int = Field(default=30, alias="MAX_ANALYSIS_SYMBOLS")
    top_n: int = Field(default=5, alias="TOP_N")
    push_interval_seconds: int = Field(default=60, alias="PUSH_INTERVAL_SECONDS")
    display_timezone: str = Field(default="Asia/Shanghai", alias="DISPLAY_TIMEZONE")
    min_quote_volume_5m_usd: float = Field(default=1_000_000, alias="MIN_QUOTE_VOLUME_5M_USD")
    min_quote_volume_1m_usd: float = Field(default=200_000, alias="MIN_QUOTE_VOLUME_1M_USD")
    http_concurrency: int = Field(default=20, alias="HTTP_CONCURRENCY")
    request_timeout_seconds: int = Field(default=30, alias="REQUEST_TIMEOUT_SECONDS")


# ── Feishu / Lark notifications ──────────────────────────────────────────────
# .env: FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_RECEIVE_ID, FEISHU_RECEIVE_ID_TYPE

class FeishuSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FEISHU_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: str = "app"
    app_id: str = ""
    app_secret: str = ""
    webhook_url: str = ""
    receive_id: str = ""                    # maps to FEISHU_RECEIVE_ID
    receive_id_type: str = "chat_id"        # maps to FEISHU_RECEIVE_ID_TYPE

    @property
    def chat_id(self) -> str:
        """Alias: chat_id = receive_id when receive_id_type is chat_id."""
        return self.receive_id


# ── Logging ───────────────────────────────────────────────────────────────────

class LogSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    file: str = Field(default="logs/crypto_monitor.log", alias="LOG_FILE")
    max_bytes: int = Field(default=10_485_760, alias="LOG_MAX_BYTES")
    to_stdout: bool = Field(default=True, alias="LOG_TO_STDOUT")


# ── Root settings (composes all sub-models) ───────────────────────────────────

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    binance: BinanceSettings = Field(default_factory=BinanceSettings)
    onchain: OnChainSettings = Field(default_factory=OnChainSettings)
    monitor: MonitorSettings = Field(default_factory=MonitorSettings)
    feishu: FeishuSettings = Field(default_factory=FeishuSettings)
    log: LogSettings = Field(default_factory=LogSettings)

    proxy_url: str = ""
    trading_mode: str = "demo"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
