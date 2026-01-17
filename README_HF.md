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
