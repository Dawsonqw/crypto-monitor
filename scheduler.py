"""
调度器 — 定时执行数据采集任务并推送到飞书。

支持的任务:
  - futures_summary: Binance 合约数据汇总 (OI, 多空比, 资费, 主动买卖比)
  - onchain_holders: 链上 Top 持仓数据
  - liquidity_report: DeFi 流动性报告
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from loguru import logger

from collectors.binance_futures import BinanceFuturesCollector
from collectors.onchain import (
    CoinGeckoCollector,
    DefiLlamaCollector,
    HeliusCollector,
    MoralisCollector,
)
from config import Settings
from formatters.report import (
    build_feishu_card,
    format_full_report,
    format_futures_summary,
    format_liquidity_report,
    format_onchain_holders,
)
from notifiers.feishu import FeishuNotifier


class MonitorScheduler:
    """数据采集调度器。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.tz = settings.monitor.display_timezone

        # Binance 合约采集器
        self.binance = BinanceFuturesCollector(
            base_url=settings.binance.futures_base_url,
            timeout=settings.monitor.request_timeout_seconds,
            proxy_url=settings.proxy_url or None,
        )

        # 链上采集器
        self.moralis = MoralisCollector(
            api_key=settings.onchain.moralis_api_key,
            proxy_url=settings.proxy_url or None,
        ) if settings.onchain.moralis_api_key else None

        self.defillama = DefiLlamaCollector(
            base_url=settings.onchain.defillama_base_url,
            yields_url=settings.onchain.defillama_yields_url,
            proxy_url=settings.proxy_url or None,
        )

        self.helius = HeliusCollector(
            api_key=settings.onchain.helius_api_key,
            proxy_url=settings.proxy_url or None,
        ) if settings.onchain.helius_api_key else None

        self.coingecko = CoinGeckoCollector(
            base_url=settings.onchain.coingecko_base_url,
            api_key=settings.onchain.coingecko_api_key or None,
            proxy_url=settings.proxy_url or None,
        )

        # 飞书推送
        self.feishu = FeishuNotifier(
            app_id=settings.feishu.app_id,
            app_secret=settings.feishu.app_secret,
            receive_id_type=settings.feishu.receive_id_type,
            chat_id=settings.feishu.chat_id or None,
            proxy_url=settings.proxy_url or None,
        )

        # 监控的交易对 (默认列表, 后续可通过 CoinGecko 市值动态更新)
        self._symbols: list[str] = []
        self._token_map: dict[str, dict] = {}  # symbol -> {address, chain, coingecko_id}

    # ─── 交易对管理 ──────────────────────────────────────────────

    def set_symbols(self, symbols: list[str]):
        """手动设置监控的交易对列表 (Binance 格式, 如 BTCUSDT)。"""
        self._symbols = symbols
        logger.info("监控交易对更新: {}", symbols)

    def set_token_map(self, token_map: dict[str, dict]):
        """设置 symbol -> 链上地址映射, 用于链上数据查询。

        格式: {"BTC": {"address": "0x...", "chain": "eth", "coingecko_id": "bitcoin"}}
        """
        self._token_map = token_map

    async def refresh_symbols_by_volume(self):
        """根据 Binance 合约 24h 成交量自动筛选交易对。"""
        quote = self.settings.monitor.quote_asset
        top_n = self.settings.monitor.max_analysis_symbols
        min_vol = self.settings.monitor.min_quote_volume_5m_usd

        tickers = await self.binance.get_ticker_24h()
        if not tickers:
            logger.warning("获取 ticker 失败, 保留当前交易对列表")
            return

        # 过滤 USDT 合约, 按成交额排序
        usdt_tickers = [
            t for t in tickers
            if t.get("symbol", "").endswith(quote)
            and float(t.get("quoteVolume", 0)) > min_vol
        ]
        usdt_tickers.sort(key=lambda t: float(t.get("quoteVolume", 0)), reverse=True)
        self._symbols = [t["symbol"] for t in usdt_tickers[:top_n]]
        logger.info("自动筛选 Top {} 交易对 (成交额 > {}): {}", top_n, min_vol, self._symbols)

    # ─── 数据采集任务 ────────────────────────────────────────────

    async def collect_futures_data(self) -> dict[str, Any] | None:
        """采集 Binance 合约数据汇总。"""
        if not self._symbols:
            await self.refresh_symbols_by_volume()
        if not self._symbols:
            logger.error("没有可监控的交易对")
            return None

        # 取 top_n 个推送
        top_n = self.settings.monitor.top_n
        symbols = self._symbols[:top_n]

        logger.info("开始采集合约数据: {}", symbols)
        data = await self.binance.get_multi_symbol_summary(symbols)
        if not data:
            logger.error("合约数据采集失败")
            return None

        logger.info("合约数据采集完成, {} 个交易对", len(data))
        return data

    async def collect_onchain_holders(
        self, token_address: str, chain: str = "eth", symbol: str = ""
    ) -> list[dict] | None:
        """采集链上 Top 持仓。"""
        if not self.moralis:
            logger.warning("Moralis API 未配置, 跳过链上持仓采集")
            return None

        logger.info("采集链上 Top 持仓: {} ({})", symbol or token_address[:10], chain)
        holders = await self.moralis.get_top_holders(
            token_address=token_address, chain=chain, limit=10
        )
        return holders

    async def collect_solana_holders(self, mint_address: str) -> list[dict] | None:
        """采集 Solana SPL Token Top 持仓。"""
        if not self.helius:
            logger.warning("Helius API 未配置, 跳过 Solana 持仓采集")
            return None

        logger.info("采集 Solana Top 持仓: {}", mint_address[:10])
        holders = await self.helius.get_token_holders(mint_address=mint_address, limit=10)
        return holders

    async def collect_defi_liquidity(self, protocols: list[str] | None = None) -> dict | None:
        """采集 DeFi 流动性数据。"""
        if not protocols:
            protocols = ["uniswap", "aave", "curve-dex"]

        result = {}
        for protocol in protocols:
            tvl = await self.defillama.get_protocol_tvl(protocol)
            if tvl:
                result[protocol] = tvl
        return result or None

    # ─── 推送任务 ────────────────────────────────────────────────

    async def push_futures_report(self, chat_id: str | None = None):
        """采集合约数据并推送到飞书。"""
        data = await self.collect_futures_data()
        if not data:
            return

        # 格式化报告
        md_text = format_futures_summary(data)
        now = datetime.now().strftime("%m-%d %H:%M")
        title = f"📊 合约数据监控 | {now}"

        # 构建飞书卡片
        sections = [{"title": "", "content": md_text}]
        card = build_feishu_card(title=title, sections=sections)

        try:
            await self.feishu.send_card(card, chat_id=chat_id)
            logger.info("合约报告推送成功")
        except Exception as e:
            logger.error("飞书推送失败: {}", e)

    async def push_onchain_report(
        self, tokens: list[dict] | None = None, chat_id: str | None = None
    ):
        """采集链上数据并推送到飞书。

        tokens: [{"address": "0x...", "chain": "eth", "symbol": "TOKEN"}, ...]
        """
        if not tokens:
            tokens = [
                {"address": addr_info["address"], "chain": addr_info.get("chain", "eth"),
                 "symbol": sym}
                for sym, addr_info in self._token_map.items()
            ]

        if not tokens:
            logger.warning("没有配置链上 token 地址, 跳过")
            return

        sections = []
        for token in tokens:
            holders = await self.collect_onchain_holders(
                token_address=token["address"],
                chain=token.get("chain", "eth"),
                symbol=token.get("symbol", ""),
            )
            if holders:
                md = format_onchain_holders(holders, symbol=token.get("symbol", ""))
                sections.append({"title": token.get("symbol", ""), "content": md})

        if not sections:
            logger.warning("没有采集到链上持仓数据")
            return

        now = datetime.now().strftime("%m-%d %H:%M")
        card = build_feishu_card(title=f"🔗 链上持仓监控 | {now}", sections=sections)
        try:
            await self.feishu.send_card(card, chat_id=chat_id)
            logger.info("链上报告推送成功")
        except Exception as e:
            logger.error("飞书推送失败: {}", e)

    async def push_liquidity_report(
        self, protocols: list[str] | None = None, chat_id: str | None = None
    ):
        """采集 DeFi 流动性数据并推送到飞书。"""
        data = await self.collect_defi_liquidity(protocols)
        if not data:
            return

        sections = []
        for protocol, tvl_data in data.items():
            md = format_liquidity_report(tvl_data, protocol)
            sections.append({"title": protocol, "content": md})

        now = datetime.now().strftime("%m-%d %H:%M")
        card = build_feishu_card(title=f"💧 DeFi 流动性 | {now}", sections=sections)
        try:
            await self.feishu.send_card(card, chat_id=chat_id)
            logger.info("流动性报告推送成功")
        except Exception as e:
            logger.error("飞书推送失败: {}", e)

    async def push_full_report(self, chat_id: str | None = None):
        """采集全部数据并推送综合报告。"""
        futures_data = await self.collect_futures_data()
        defi_data = await self.collect_defi_liquidity()

        md_text = format_full_report(
            futures_data=futures_data or {},
            onchain_data=defi_data,
        )

        now = datetime.now().strftime("%m-%d %H:%M")
        card = build_feishu_card(
            title=f"📋 综合监控报告 | {now}",
            sections=[{"title": "", "content": md_text}],
        )
        try:
            await self.feishu.send_card(card, chat_id=chat_id)
            logger.info("综合报告推送成功")
        except Exception as e:
            logger.error("飞书推送失败: {}", e)

    # ─── 定时循环 ────────────────────────────────────────────────

    async def run_loop(
        self,
        interval: int | None = None,
        tasks: list[str] | None = None,
        chat_id: str | None = None,
    ):
        """主循环 — 定时执行指定任务。

        Args:
            interval: 推送间隔秒数, 默认从配置读取
            tasks: 要执行的任务列表, 可选 futures / onchain / liquidity / full
            chat_id: 飞书群 chat_id, 覆盖配置默认值
        """
        interval = interval or self.settings.monitor.push_interval_seconds
        tasks = tasks or ["futures"]

        logger.info("调度器启动 | 间隔: {}s | 任务: {} | chat_id: {}",
                     interval, tasks, chat_id or "default")

        # 首次刷新交易对
        await self.refresh_symbols_by_volume()

        cycle = 0
        while True:
            cycle += 1
            logger.info("── 第 {} 轮采集 ──", cycle)

            try:
                if "full" in tasks:
                    await self.push_full_report(chat_id)
                else:
                    if "futures" in tasks:
                        await self.push_futures_report(chat_id)
                    if "onchain" in tasks:
                        await self.push_onchain_report(chat_id=chat_id)
                    if "liquidity" in tasks:
                        await self.push_liquidity_report(chat_id=chat_id)

                # 每 10 轮刷新交易对
                if cycle % 10 == 0:
                    await self.refresh_symbols_by_volume()

            except Exception as e:
                logger.exception("采集/推送异常: {}", e)

            await asyncio.sleep(interval)

    # ─── 资源清理 ────────────────────────────────────────────────

    async def close(self):
        """关闭所有连接。"""
        await self.binance.close()
        if self.moralis:
            await self.moralis.close()
        await self.defillama.close()
        if self.helius:
            await self.helius.close()
        await self.coingecko.close()
        await self.feishu.close()
        logger.info("所有连接已关闭")
