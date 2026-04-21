#!/usr/bin/env python3
"""
crypto-monitor — 加密货币数据监控与飞书推送

用法:
  python main.py                        # 默认: 合约数据循环推送
  python main.py --tasks futures onchain liquidity
  python main.py --once                 # 执行一次后退出
  python main.py --chat-id oc_xxx       # 指定飞书群
  python main.py --interval 120         # 自定义间隔(秒)
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys

from loguru import logger

from config import get_settings
from logger import setup_logger
from scheduler import MonitorScheduler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="加密货币数据监控与飞书推送")
    parser.add_argument(
        "--tasks",
        nargs="+",
        choices=["futures", "onchain", "liquidity", "full"],
        default=["futures"],
        help="要执行的采集任务 (默认: futures)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="只执行一次, 不进入循环",
    )
    parser.add_argument(
        "--chat-id",
        type=str,
        default=None,
        help="飞书群 chat_id, 覆盖 .env 中的配置",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        help="推送间隔秒数, 覆盖 .env 中的 PUSH_INTERVAL_SECONDS",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="指定监控的交易对 (如 BTCUSDT ETHUSDT), 不指定则自动按成交量筛选",
    )
    return parser.parse_args()


async def run_once(scheduler: MonitorScheduler, tasks: list[str], chat_id: str | None):
    """执行一次采集推送。"""
    await scheduler.refresh_symbols_by_volume()

    if "full" in tasks:
        await scheduler.push_full_report(chat_id)
    else:
        if "futures" in tasks:
            await scheduler.push_futures_report(chat_id)
        if "onchain" in tasks:
            await scheduler.push_onchain_report(chat_id=chat_id)
        if "liquidity" in tasks:
            await scheduler.push_liquidity_report(chat_id=chat_id)


async def main():
    args = parse_args()
    settings = get_settings()
    setup_logger(settings.log)

    logger.info("crypto-monitor 启动")
    logger.info("任务: {} | 模式: {} | 间隔: {}s",
                args.tasks,
                "单次" if args.once else "循环",
                args.interval or settings.monitor.push_interval_seconds)

    scheduler = MonitorScheduler(settings)

    if args.symbols:
        scheduler.set_symbols(args.symbols)

    # 优雅退出
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("收到退出信号, 正在关闭...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        if args.once:
            await run_once(scheduler, args.tasks, args.chat_id)
        else:
            # 用 stop_event 替代无限循环, 支持优雅退出
            interval = args.interval or settings.monitor.push_interval_seconds
            await scheduler.refresh_symbols_by_volume()

            cycle = 0
            while not stop_event.is_set():
                cycle += 1
                logger.info("── 第 {} 轮采集 ──", cycle)

                try:
                    if "full" in args.tasks:
                        await scheduler.push_full_report(args.chat_id)
                    else:
                        if "futures" in args.tasks:
                            await scheduler.push_futures_report(args.chat_id)
                        if "onchain" in args.tasks:
                            await scheduler.push_onchain_report(chat_id=args.chat_id)
                        if "liquidity" in args.tasks:
                            await scheduler.push_liquidity_report(chat_id=args.chat_id)

                    if cycle % 10 == 0:
                        await scheduler.refresh_symbols_by_volume()

                except Exception as e:
                    logger.exception("采集/推送异常: {}", e)

                # 可中断的等待
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass  # 正常超时, 继续下一轮
    finally:
        await scheduler.close()
        logger.info("crypto-monitor 已停止")


if __name__ == "__main__":
    asyncio.run(main())
