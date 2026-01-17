# 🪙 加密货币智能分析系统

[![GitHub stars](https://img.shields.io/github/stars/ZhuLinsen/daily_stock_analysis?style=social)](https://github.com/ZhuLinsen/daily_stock_analysis/stargazers)
[![CI](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Ready-2088FF?logo=github-actions&logoColor=white)](https://github.com/features/actions)

> 🤖 基于 AI 大模型的加密货币智能分析系统，每日自动分析并推送「决策仪表盘」到企业微信/飞书/Telegram/邮箱

![运行效果演示](./sources/all_2026-01-13_221547.gif)

## ✨ 功能特性

### 🎯 核心功能
- **AI 决策仪表盘** - 一句话核心结论 + 精确买卖点位 + 检查清单
- **多维度分析** - 技术面 + 链上数据 + 舆情情报 + 实时行情
- **市场复盘** - 每日市场概览、恐惧贪婪指数、BTC 主导率
- **多渠道推送** - 支持企业微信、飞书、Telegram、邮件（自动识别）
- **💬 双向对话** - Telegram/企业微信应用双向对话，随时询问市场分析
- **🖼️ 图像生成** - AI 生成市场分析海报，一键分享
- **零成本部署** - GitHub Actions 免费运行，无需服务器
- **💰 白嫖 Gemini API** - Google AI Studio 提供免费额度，个人使用完全够用
- **🔄 多模型支持** - 支持 OpenAI 兼容 API（DeepSeek、通义千问等）作为备选

### 📊 数据来源
- **CEX 行情**: CCXT 库（支持 Binance、OKX、Coinbase 等 100+ 交易所）
- **链上数据**: GeckoTerminal API（支持 Solana、Ethereum、BSC 等 100+ 链）
- **市场情绪**: 恐惧贪婪指数（Alternative.me）、CoinGecko 全局数据
- **新闻搜索**: Tavily、SerpAPI、Bocha
- **AI 分析**: 
  - 主力：Google Gemini（gemini-3-flash-preview）—— [免费获取](https://aistudio.google.com/)
  - 备选：应大家要求，也支持了OpenAI 兼容 API（DeepSeek、通义千问、Moonshot 等）

### 🛡️ 交易理念内置
- ❌ **严禁追高** - 乖离率 > 10% 自动标记「危险」（加密货币波动大，阈值提高）
- ✅ **趋势交易** - MA7 > MA25 > MA99 多头排列
- 📍 **精确点位** - 买入价、止损价、目标价
- 📋 **检查清单** - 每项条件用 ✅⚠️❌ 标记
- 🐋 **巨鲸追踪** - 关注大户动向和持币分布

## 🚀 快速开始

### 方式一：GitHub Actions（推荐，零成本）

**无需服务器，每天自动运行！**

#### 1. Fork 本仓库

点击右上角 `Fork` 按钮

#### 2. 配置 Secrets

进入你 Fork 的仓库 → `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

**AI 模型配置（二选一）**

| Secret 名称 | 说明 | 必填 |
|------------|------|:----:|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) 获取免费 Key | ✅* |
| `OPENAI_API_KEY` | OpenAI 兼容 API Key（支持 DeepSeek、通义千问等） | 可选 |
| `OPENAI_BASE_URL` | OpenAI 兼容 API 地址（如 `https://api.deepseek.com/v1`） | 可选 |
| `OPENAI_MODEL` | 模型名称（如 `deepseek-chat`） | 可选 |

> *注：`GEMINI_API_KEY` 和 `OPENAI_API_KEY` 至少配置一个

**通知渠道配置（可同时配置多个，全部推送）**

| Secret 名称 | 说明 | 必填 |
|------------|------|:----:|
| `WECHAT_WEBHOOK_URL` | 企业微信 Webhook URL | 可选 |
| `FEISHU_WEBHOOK_URL` | 飞书 Webhook URL | 可选 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（@BotFather 获取） | 可选 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 可选 |
| `EMAIL_SENDER` | 发件人邮箱（如 `xxx@qq.com`） | 可选 |
| `EMAIL_PASSWORD` | 邮箱授权码（非登录密码） | 可选 |
| `EMAIL_RECEIVERS` | 收件人邮箱（多个用逗号分隔，留空则发给自己） | 可选 |
| `CUSTOM_WEBHOOK_URLS` | 自定义 Webhook（支持钉钉等，多个用逗号分隔） | 可选 |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | 自定义 Webhook 的 Bearer Token（用于需要认证的 Webhook） | 可选 |
| `SINGLE_CRYPTO_NOTIFY` | 单币推送模式：设为 `true` 则每分析完一个币种立即推送 | 可选 |

> *注：至少配置一个渠道，配置多个则同时推送
>
> 📖 更多配置（Pushover 手机推送、飞书云文档等）请参考 [完整配置指南](docs/full-guide.md)

**加密货币配置**

| Secret 名称 | 说明 | 必填 |
|------------|------|:----:|
| `CRYPTO_LIST` | 监控的交易对，如 `BTC/USDT,ETH/USDT,SOL/USDT` | ✅ |
| `PREFERRED_EXCHANGES` | 首选交易所，如 `binance,okx` | 可选 |
| `PREFERRED_CHAINS` | 首选链（链上分析用），如 `solana,ethereum,bsc` | 可选 |
| `BINANCE_API_KEY` | Binance API Key（可选，提高请求限额） | 可选 |
| `BINANCE_API_SECRET` | Binance API Secret | 可选 |
| `OKX_API_KEY` | OKX API Key | 可选 |
| `OKX_API_SECRET` | OKX API Secret | 可选 |
| `OKX_PASSPHRASE` | OKX API Passphrase | 可选 |

**搜索配置**

| Secret 名称 | 说明 | 必填 |
|------------|------|:----:|
| `TAVILY_API_KEYS` | [Tavily](https://tavily.com/) 搜索 API（新闻搜索） | 推荐 |
| `BOCHA_API_KEYS` | [博查搜索](https://open.bocha.cn/) Web Search API（中文搜索优化，支持AI摘要，多个key用逗号分隔） | 可选 |
| `SERPAPI_API_KEYS` | [SerpAPI](https://serpapi.com/) 备用搜索 | 可选 |

#### 3. 启用 Actions

进入 `Actions` 标签 → 点击 `I understand my workflows, go ahead and enable them`

#### 4. 手动测试

`Actions` → `每日加密货币分析` → `Run workflow` → 选择模式 → `Run workflow`

#### 5. 完成！

加密货币市场24小时运行，默认每天 **08:00 和 20:00（北京时间）** 自动执行

### 方式二：本地运行 / Docker 部署

> 📖 本地运行、Docker 部署详细步骤请参考 [完整配置指南](docs/full-guide.md)

## 📱 推送效果

### 决策仪表盘
```
📊 2026-01-10 决策仪表盘
5个币种 | 🟢买入:2 🟡观望:2 🔴卖出:1

🟢 买入 | BTC/USDT
📌 回踩MA7支撑后企稳，乖离率3.2%处于安全区间
💰 狙击: 买入$42,500 | 止损$41,000 | 目标$48,000
✅多头排列 ✅乖离安全 ✅巨鲸增持

🟢 买入 | ETH/USDT
📌 突破MA25后缩量回踩确认，链上活跃度上升
💰 狙击: 买入$2,280 | 止损$2,150 | 目标$2,600
✅多头排列 ✅链上增持 ✅量能配合

🟡 观望 | SOL/USDT
📌 乖离率12.5%超过10%警戒线，严禁追高
⚠️ 等待回调至MA7附近再考虑

🔴 卖出 | PEPE/USDT
📌 MA死叉，巨鲸转入交易所，短期做空信号
💰 建议减仓，支撑位 $0.0000012

---
📈 市场情绪: 恐惧贪婪指数 65 (贪婪)
💰 BTC 主导率: 52.3%
生成时间: 20:00
```

### 市场复盘

```
🎯 2026-01-10 加密货币市场复盘

📊 主要币种
- BTC/USDT: $42,856 (🟢+2.35%)
- ETH/USDT: $2,312 (🟢+1.82%)
- SOL/USDT: $98.56 (🟢+5.21%)

📈 市场概况
恐惧贪婪指数: 65 (贪婪)
BTC 主导率: 52.3%
总市值: $1.68T (+1.5%)

🔥 24H 涨幅榜
1. PEPE/USDT +28.5%
2. WIF/USDT +15.2%
3. SOL/USDT +5.21%

📉 24H 跌幅榜
1. APT/USDT -4.2%
2. SUI/USDT -3.8%
```

## ⚙️ 配置说明

> 📖 完整环境变量、定时任务配置请参考 [完整配置指南](docs/full-guide.md)

## 📁 项目结构

```
daily_crypto_analysis/
├── main.py                    # 主程序入口
├── run_bot.py                 # 双向对话 Bot 入口
├── analyzer.py                # AI 分析器（Gemini）
├── crypto_analyzer.py         # 加密货币趋势分析器
├── crypto_market_analyzer.py  # 市场复盘分析
├── search_service.py          # 新闻搜索服务
├── notification.py            # 消息推送
├── scheduler.py               # 定时任务
├── storage.py                 # 数据存储
├── config.py                  # 配置管理
├── data_provider/             # 数据源适配器
│   ├── ccxt_fetcher.py        # CCXT 交易所数据
│   ├── geckoterminal_fetcher.py  # 链上 DEX 数据
│   ├── akshare_fetcher.py     # (保留，股票数据)
│   └── ...
├── bot/                       # 双向对话机器人
│   ├── telegram_bot.py        # Telegram Bot
│   ├── wecom_adapter.py       # 企业微信应用
│   ├── context_manager.py     # 上下文管理
│   ├── message_handler.py     # 消息处理
│   └── image_generator.py     # 图像生成
├── .github/workflows/         # GitHub Actions
├── Dockerfile                 # Docker 镜像
└── docker-compose.yml         # Docker 编排
```

## 🗺️ Roadmap

> 📢 以下功能将视后续情况逐步完成，如果你有好的想法或建议，欢迎 [提交 Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues) 讨论！

### 🔔 通知渠道扩展
- [x] 企业微信机器人
- [x] 飞书机器人
- [x] Telegram Bot
- [x] 邮件通知（SMTP）
- [x] 自定义 Webhook（支持钉钉、Discord、Slack、Bark 等）
- [x] iOS/Android 推送（Pushover）

### 🤖 AI 模型支持
- [x] Google Gemini（主力，免费额度）
- [x] OpenAI 兼容 API（支持 GPT-4/DeepSeek/通义千问/Claude/文心一言 等）
- [x] 本地模型（Ollama）

### 📊 数据源扩展
- [x] CCXT（100+ 交易所）
- [x] GeckoTerminal（100+ 链上 DEX）
- [x] 恐惧贪婪指数
- [x] CoinGecko 全局数据
- [ ] Dune Analytics 链上分析
- [ ] DefiLlama TVL 数据

### 🎯 功能增强
- [x] 决策仪表盘
- [x] 市场复盘
- [x] 定时推送
- [x] GitHub Actions
- [x] 技术指标分析
- [x] 链上数据分析
- [x] 双向对话（Telegram/企业微信应用）
- [x] AI 图像生成（市场分析海报）
- [ ] Web 管理界面
- [ ] 历史分析回测
- [ ] 合约分析支持

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

详见 [贡献指南](CONTRIBUTING.md)

## 📄 License
[MIT License](LICENSE) © 2026 ZhuLinsen

如果你在项目中使用或基于本项目进行二次开发，
非常欢迎在 README 或文档中注明来源并附上本仓库链接。
这将有助于项目的持续维护和社区发展。

## 📬 联系与合作
- GitHub Issues：[提交 Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)

## ⭐ Star History

<a href="https://star-history.com/#ZhuLinsen/daily_stock_analysis&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=ZhuLinsen/daily_stock_analysis&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=ZhuLinsen/daily_stock_analysis&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=ZhuLinsen/daily_stock_analysis&type=Date" />
 </picture>
</a>

## ⚠️ 免责声明

本项目仅供学习和研究使用，不构成任何投资建议。加密货币市场波动剧烈，风险极高，投资需谨慎。作者不对使用本项目产生的任何损失负责。

---

**如果觉得有用，请给个 ⭐ Star 支持一下！**
