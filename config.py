"""
Configuration module for crypto-monitor.

Loads settings from the parent freqtrade/.env file using pydantic-settings.
Environment variables use prefixes: BINANCE_, ONCHAIN_, MONITOR_, FEISHU_, LOG_.
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

class OnChainSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ONCHAIN_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    moralis_api_key: str = ""
    helius_api_key: str = ""
    tonapi_base_url: str = "https://tonapi.io"
    defillama_base_url: str = "https://api.llama.fi"
    defillama_yields_url: str = "https://yields.llama.fi"
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    coingecko_api_key: str = ""
    coinlore_base_url: str = "https://api.coinlore.net/api"


# ── Monitor behaviour ────────────────────────────────────────────────────────

class MonitorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MONITOR_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    quote_asset: str = "USDT"
    market_cap_limit_usd: float = 1_000_000_000      # 1 billion
    max_analysis_symbols: int = 30
    top_n: int = 5
    push_interval_seconds: int = 60
    display_timezone: str = "Asia/Shanghai"
    min_quote_volume_5m_usd: float = 1_000_000        # 1 million
    min_quote_volume_1m_usd: float = 200_000           # 200 thousand
    http_concurrency: int = 20
    request_timeout_seconds: int = 30


# ── Feishu / Lark notifications ──────────────────────────────────────────────

class FeishuSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FEISHU_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: str = "app"                  # "app" or "webhook"
    app_id: str = ""
    app_secret: str = ""
    webhook_url: str = ""
    receive_id_type: str = "chat_id"
    chat_id: str = ""


# ── Logging ───────────────────────────────────────────────────────────────────

class LogSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_file: str = "logs/crypto_monitor.log"
    log_max_bytes: int = 10_485_760    # 10 MB
    log_to_stdout: bool = True


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
    trading_mode: str = "demo"         # "demo" or "live"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
