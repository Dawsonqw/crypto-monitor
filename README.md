# crypto-monitor

加密货币数据监控系统 — 采集 Binance 合约数据 + 链上数据，推送到飞书群。

作为 [freqtrade](https://github.com/Dawsonqw/freqtrade) 的子项目运行，共享 `.env` 配置。

## 功能

### Binance 合约数据
- 持仓量 (Open Interest) 及历史变化
- 多空比 (Long/Short Ratio) — 全市场 + 大户
- 资金费率 (Funding Rate) 及历史
- 主动买卖比 (Taker Buy/Sell Ratio)
- 爆仓数据 (Force Orders)
- 24h 行情、深度数据

### 链上数据
- **Moralis**: ERC-20 Top 持仓、Token 价格、统计
- **Helius**: Solana SPL Token 大额持仓
- **DefiLlama**: 协议 TVL、DEX 交易量、链级 TVL
- **CoinGecko**: 市值排名、币种详情

### 飞书推送
- 飞书 App 模式 (tenant_access_token)
- 交互式卡片消息 (富文本 + Markdown)
- 图片上传推送

## 项目结构

```
crypto-monitor/
├── main.py                 # 入口: CLI 参数解析, 启动循环
├── config.py               # pydantic-settings 配置 (读取 ../freqtrade/.env)
├── logger.py               # loguru 日志配置
├── scheduler.py            # 调度器: 数据采集 + 飞书推送编排
├── collectors/
│   ├── binance_futures.py  # Binance 合约数据采集 (14 个 API)
│   └── onchain.py          # 链上数据采集 (Moralis/Helius/DefiLlama/CoinGecko)
├── notifiers/
│   └── feishu.py           # 飞书消息推送 (文本/卡片/图片)
├── formatters/
│   └── report.py           # 报告格式化 + 飞书卡片构建
├── pyproject.toml
└── .gitignore
```

## 快速开始

### 1. 安装依赖

```bash
cd crypto-monitor
pip install -e .
# 或者
pip install httpx apscheduler pydantic-settings loguru
```

### 2. 配置

配置文件复用上级目录 `freqtrade/.env`，需要的关键变量：

```env
# Binance
BINANCE_FUTURES_BASE_URL=https://fapi.binance.com

# 链上数据 (可选)
MORALIS_API_KEY=your_key
HELIUS_API_KEY=your_key
COINGECKO_API_KEY=your_key

# 飞书推送
FEISHU_APP_ID=cli_a96cb38009f89cd2
FEISHU_APP_SECRET=your_secret
FEISHU_CHAT_ID=oc_xxxxxxxxxx      # 飞书群 chat_id
FEISHU_RECEIVE_ID_TYPE=chat_id

# 监控参数
PUSH_INTERVAL_SECONDS=60
MAX_ANALYSIS_SYMBOLS=30
TOP_N=5
```

### 3. 运行

```bash
# 默认: 合约数据循环推送 (60s 间隔)
python main.py

# 执行一次后退出
python main.py --once

# 指定任务
python main.py --tasks futures onchain liquidity

# 综合报告
python main.py --tasks full

# 自定义参数
python main.py --interval 120 --chat-id oc_xxx --symbols BTCUSDT ETHUSDT
```

### 4. systemd 服务 (可选)

```bash
cat > ~/.config/systemd/user/crypto-monitor.service << 'EOF'
[Unit]
Description=Crypto Monitor
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/workspace/freqtrade/crypto-monitor
ExecStart=/usr/bin/python3 main.py --tasks futures
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now crypto-monitor
```

## API 参考

| 模块 | 类 | 说明 |
|------|-----|------|
| `collectors.binance_futures` | `BinanceFuturesCollector` | 14 个 Binance 合约 API |
| `collectors.onchain` | `MoralisCollector` | EVM 链 Token 数据 |
| `collectors.onchain` | `HeliusCollector` | Solana Token 数据 |
| `collectors.onchain` | `DefiLlamaCollector` | DeFi TVL / DEX 数据 |
| `collectors.onchain` | `CoinGeckoCollector` | 市值 / 币种数据 |
| `notifiers.feishu` | `FeishuNotifier` | 飞书消息推送 |
| `formatters.report` | (functions) | 报告格式化 + 卡片构建 |
| `scheduler` | `MonitorScheduler` | 采集调度 + 推送编排 |

## License

MIT
