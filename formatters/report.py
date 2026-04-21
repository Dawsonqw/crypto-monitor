"""
Report formatting utilities for crypto-monitor.

Produces human-readable markdown tables and Feishu interactive card JSON
from raw data collected by the various collectors.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_number(value: Any, decimals: int = 2) -> str:
    """Format a number with thousand separators, or return '-' if invalid."""
    if value is None:
        return "-"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(num) >= 1_000_000_000:
        return f"{num / 1_000_000_000:,.{decimals}f}B"
    if abs(num) >= 1_000_000:
        return f"{num / 1_000_000:,.{decimals}f}M"
    if abs(num) >= 1_000:
        return f"{num / 1_000:,.{decimals}f}K"
    return f"{num:,.{decimals}f}"


def _truncate_address(addr: str, head: int = 6, tail: int = 4) -> str:
    if not addr or len(addr) <= head + tail + 3:
        return addr or "-"
    return f"{addr[:head]}...{addr[-tail:]}"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ---------------------------------------------------------------------------
# Futures summary
# ---------------------------------------------------------------------------

def format_futures_summary(data: dict) -> str:
    """Format Binance futures data into a readable markdown report.

    Expected *data* keys (each maps symbol -> value):
      - open_interest: {symbol: {openInterest, ...}}
      - funding_rate:  {symbol: {lastFundingRate, ...}}
      - long_short_ratio: {symbol: {longShortRatio, longAccount, shortAccount, ...}}
    """
    logger.debug("Formatting futures summary")
    lines: list[str] = [
        f"**📊 Futures Market Summary**  ({_timestamp()})",
        "",
        "| Symbol | Open Interest | Funding Rate | L/S Ratio | Long% | Short% |",
        "|--------|--------------|-------------|-----------|-------|--------|",
    ]

    oi_data = data.get("open_interest", {})
    fr_data = data.get("funding_rate", {})
    ls_data = data.get("long_short_ratio", {})

    # Collect all symbols across sub-dicts
    symbols = sorted(
        set(list(oi_data.keys()) + list(fr_data.keys()) + list(ls_data.keys()))
    )

    for sym in symbols:
        oi_info = oi_data.get(sym, {})
        fr_info = fr_data.get(sym, {})
        ls_info = ls_data.get(sym, {})

        oi_val = oi_info.get("openInterest") if isinstance(oi_info, dict) else oi_info
        fr_val = fr_info.get("lastFundingRate") if isinstance(fr_info, dict) else fr_info
        ls_ratio = ls_info.get("longShortRatio") if isinstance(ls_info, dict) else ls_info
        long_pct = ls_info.get("longAccount", "-") if isinstance(ls_info, dict) else "-"
        short_pct = ls_info.get("shortAccount", "-") if isinstance(ls_info, dict) else "-"

        # Funding rate as percentage string
        try:
            fr_str = f"{float(fr_val) * 100:.4f}%" if fr_val is not None else "-"
        except (TypeError, ValueError):
            fr_str = str(fr_val)

        try:
            long_pct_str = f"{float(long_pct) * 100:.1f}%" if long_pct != "-" else "-"
        except (TypeError, ValueError):
            long_pct_str = str(long_pct)

        try:
            short_pct_str = f"{float(short_pct) * 100:.1f}%" if short_pct != "-" else "-"
        except (TypeError, ValueError):
            short_pct_str = str(short_pct)

        lines.append(
            f"| {sym} | {_fmt_number(oi_val)} | {fr_str} | "
            f"{_fmt_number(ls_ratio)} | {long_pct_str} | {short_pct_str} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# On-chain holders
# ---------------------------------------------------------------------------

def format_onchain_holders(holders: list[dict], symbol: str) -> str:
    """Format top token holders into a markdown table.

    Each holder dict may contain:
      - address / owner
      - amount / balance / uiAmountString
      - percentage / share
    """
    logger.debug("Formatting on-chain holders for {s} ({n} holders)", s=symbol, n=len(holders))
    lines: list[str] = [
        f"**🏦 Top Holders – {symbol}**",
        "",
        "| # | Address | Amount | Percentage |",
        "|---|---------|--------|------------|",
    ]

    for idx, h in enumerate(holders, start=1):
        addr = h.get("address") or h.get("owner") or h.get("owner_address", "-")
        amount = (
            h.get("amount")
            or h.get("balance")
            or h.get("uiAmountString")
            or h.get("balance_formatted")
            or "-"
        )
        pct = h.get("percentage") or h.get("share") or h.get("percentage_relative_to_total_supply")

        try:
            pct_str = f"{float(pct):.2f}%" if pct is not None else "-"
        except (TypeError, ValueError):
            pct_str = str(pct) if pct else "-"

        lines.append(
            f"| {idx} | `{_truncate_address(str(addr))}` | {_fmt_number(amount)} | {pct_str} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Liquidity / TVL report
# ---------------------------------------------------------------------------

def format_liquidity_report(tvl_data: dict, protocol: str) -> str:
    """Format DeFi liquidity / TVL data for a protocol."""
    logger.debug("Formatting liquidity report for {p}", p=protocol)
    lines: list[str] = [
        f"**💧 Liquidity Report – {protocol}**  ({_timestamp()})",
        "",
    ]

    # Current TVL
    current_tvl = tvl_data.get("currentChainTvls") or tvl_data.get("tvl")
    if isinstance(current_tvl, dict):
        lines.append("| Chain | TVL |")
        lines.append("|-------|-----|")
        for chain_name, val in sorted(current_tvl.items(), key=lambda x: -(x[1] if isinstance(x[1], (int, float)) else 0)):
            lines.append(f"| {chain_name} | ${_fmt_number(val)} |")
    elif isinstance(current_tvl, (int, float)):
        lines.append(f"**Total TVL:** ${_fmt_number(current_tvl)}")
    elif isinstance(current_tvl, list) and current_tvl:
        # Array of {date, totalLiquidityUSD}
        latest = current_tvl[-1] if current_tvl else {}
        lines.append(
            f"**Latest TVL:** ${_fmt_number(latest.get('totalLiquidityUSD'))}"
        )
    else:
        lines.append("No TVL data available.")

    # Category / description
    description = tvl_data.get("description", "")
    category = tvl_data.get("category", "")
    if category:
        lines.append(f"\n**Category:** {category}")
    if description:
        short = description[:200] + ("..." if len(description) > 200 else "")
        lines.append(f"**Description:** {short}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Full combined report
# ---------------------------------------------------------------------------

def format_full_report(
    futures_data: dict,
    onchain_data: dict | None = None,
) -> str:
    """Combine futures and (optional) on-chain data into one report."""
    logger.debug("Building full report")
    sections: list[str] = [
        f"# 📈 Crypto Monitor Report  ({_timestamp()})",
        "",
    ]

    # Futures section
    if futures_data:
        sections.append(format_futures_summary(futures_data))
        sections.append("")

    # On-chain section(s)
    if onchain_data:
        sections.append("---")
        sections.append("")

        holders = onchain_data.get("holders")
        symbol = onchain_data.get("symbol", "TOKEN")
        if holders:
            sections.append(format_onchain_holders(holders, symbol))
            sections.append("")

        tvl = onchain_data.get("tvl")
        protocol = onchain_data.get("protocol", "")
        if tvl and protocol:
            sections.append(format_liquidity_report(tvl, protocol))
            sections.append("")

        # Price info
        price_info = onchain_data.get("price")
        if price_info and isinstance(price_info, dict):
            usd = price_info.get("usdPrice") or price_info.get("usd")
            if usd is not None:
                sections.append(f"**💰 Price:** ${_fmt_number(usd, 4)}")
                sections.append("")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Feishu card builder
# ---------------------------------------------------------------------------

def build_feishu_card(title: str, sections: list[dict]) -> dict:
    """Build a Feishu interactive card JSON structure.

    Parameters
    ----------
    title : str
        Card header title text.
    sections : list[dict]
        Each section should have at least a ``content`` key with markdown text.
        Optional keys: ``title`` (section heading).

    Returns
    -------
    dict
        Feishu card payload ready to be sent via ``FeishuNotifier.send_card``.
    """
    logger.debug("Building Feishu card with {n} sections", n=len(sections))

    elements: list[dict] = []

    for i, section in enumerate(sections):
        md_content = section.get("content", "")
        section_title = section.get("title")

        # Optional section heading
        if section_title:
            md_content = f"**{section_title}**\n{md_content}"

        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": md_content},
            }
        )

        # Add divider between sections (not after the last one)
        if i < len(sections) - 1:
            elements.append({"tag": "hr"})

    card: dict[str, Any] = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"content": title, "tag": "plain_text"},
            "template": "blue",
        },
        "elements": elements,
    }

    return card
