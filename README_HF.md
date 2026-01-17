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

1. 在左侧输入要分析的交易对（如 BTC/USDT）
2. 输入你的 Gemini API Key
3. 点击"开始分析"
4. 等待 AI 生成分析报告

## 配置说明

在 Settings → Variables and secrets 中添加：
- `GEMINI_API_KEY`: Google AI Studio 免费获取
- `CRYPTO_LIST`: 默认分析的交易对列表
