---
title: 加密货币智能分析系统
emoji: 🪙
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
license: mit
---

# 🪙 加密货币智能分析系统

基于 AI 的加密货币智能分析工具，支持：
- BTC、ETH、SOL 等主流币种分析
- 技术指标（MA7/MA25/MA99 多头排列、乖离率）
- 链上数据分析
- AI 生成决策仪表盘

## 使用方式

1. 选择 AI 服务（Gemini 免费 或 OpenAI 兼容 API）
2. 输入你的 API Key
3. 输入要分析的交易对（如 BTC/USDT）
4. 点击"开始分析"
5. 等待 AI 生成分析报告

## 支持的 AI 服务

| 服务商 | API Base URL | 模型名称 |
|--------|-------------|----------|
| **Gemini** | 自动 | gemini-1.5-flash |
| **DeepSeek** | `https://api.deepseek.com/v1` | `deepseek-chat` |
| **通义千问** | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` |
| **Moonshot** | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |

## 配置说明（可选）

在 Settings → Variables and secrets 中添加：
- `CRYPTO_LIST`: 默认分析的交易对列表（如 BTC/USDT,ETH/USDT）

## 🤖 Telegram Bot 双向对话功能

本 Space 支持运行 Telegram Bot，让你可以随时与 AI 对话交流市场分析。

### 配置步骤

1. **创建 Telegram Bot**
   - 在 Telegram 中找到 @BotFather
   - 发送 `/newbot` 创建新 Bot
   - 获取 Bot Token

2. **配置 HuggingFace Secrets**
   - 进入 Space 的 Settings → Variables and secrets
   - 添加以下 Secrets（点击 "New secret"）：

   | Secret 名称 | 说明 | 示例 |
   |------------|------|------|
   | `TELEGRAM_BOT_TOKEN` | Bot Token | `123456:ABC-DEF...` |
   | `TELEGRAM_CHAT_ID` | 允许的用户 ID（可选） | `123456789` |
   | `OPENAI_API_KEY` | AI API Key | `sk-xxx` |
   | `OPENAI_BASE_URL` | API Base URL | `https://api.deepseek.com/v1` |
   | `OPENAI_MODEL` | 模型名称 | `deepseek-chat` |

3. **重启 Space**
   - 配置完成后，点击 "Restart" 重启 Space
   - Bot 会自动在后台启动

### 支持的命令

| 命令 | 功能 |
|------|------|
| `/start` | 开始对话 |
| `/help` | 查看帮助 |
| `/report` | 获取最新市场报告 |
| `/image` | 生成市场分析海报 |
| `/status` | 查看系统状态 |
| `/clear` | 清除对话历史 |

### 直接对话

除了命令，你也可以直接发送消息与 AI 对话：
- "BTC 现在能买吗？"
- "分析一下 ETH 的走势"
- "今天市场情绪如何？"

AI 会结合最新的市场报告数据给出智能回复。

---

Made with ❤️ | [GitHub](https://github.com/Cabbagewwc/crypto-analysis)
