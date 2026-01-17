# -*- coding: utf-8 -*-
"""
🪙 加密货币智能分析系统 - Gradio Web UI

用于 HuggingFace Spaces 部署的 Web 界面
支持 Gemini 和 OpenAI 兼容 API（DeepSeek、通义千问等）
同时运行 Telegram Bot 提供双向对话功能
"""

import os
import asyncio
import threading
import logging
import gradio as gr
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 设置环境变量
os.environ.setdefault('PYTHONUNBUFFERED', '1')

# 导入分析模块
try:
    from config import get_config
    from data_provider.ccxt_fetcher import CCXTFetcher
    from crypto_analyzer import CryptoTrendAnalyzer
    from analyzer import GeminiAnalyzer
    MODULES_LOADED = True
except ImportError as e:
    MODULES_LOADED = False
    IMPORT_ERROR = str(e)


def analyze_crypto(
    symbol: str, 
    api_provider: str,
    api_key: str, 
    api_base_url: str,
    model_name: str,
    exchange: str = "okx"
) -> str:
    """
    分析单个加密货币
    
    Args:
        symbol: 交易对（如 BTC/USDT）
        api_provider: API 提供商（gemini / openai）
        api_key: API Key
        api_base_url: API Base URL（OpenAI 兼容 API 用）
        model_name: 模型名称
        exchange: 交易所名称
    
    Returns:
        分析报告文本
    """
    if not MODULES_LOADED:
        return f"❌ 模块加载失败: {IMPORT_ERROR}"
    
    if not symbol:
        return "❌ 请输入交易对符号（如 BTC/USDT）"
    
    if not api_key:
        return "❌ 请输入 API Key"
    
    try:
        # 根据选择的 API 提供商设置环境变量
        if api_provider == "openai":
            os.environ['OPENAI_API_KEY'] = api_key
            if api_base_url:
                os.environ['OPENAI_BASE_URL'] = api_base_url
            if model_name:
                os.environ['OPENAI_MODEL'] = model_name
            os.environ['GEMINI_API_KEY'] = ''  # 清空 Gemini，让系统使用 OpenAI
        else:
            os.environ['GEMINI_API_KEY'] = api_key
            os.environ['OPENAI_API_KEY'] = ''  # 清空 OpenAI
        
        # 初始化组件
        fetcher = CCXTFetcher(exchange=exchange)
        trend_analyzer = CryptoTrendAnalyzer()
        
        # 根据提供商初始化 AI 分析器
        if api_provider == "openai":
            from analyzer import GeminiAnalyzer
            ai_analyzer = GeminiAnalyzer()  # 会自动检测并使用 OpenAI
        else:
            ai_analyzer = GeminiAnalyzer(api_key=api_key)
        
        # 获取数据
        report = f"# 🪙 {symbol} 分析报告\n\n"
        report += f"**分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"**AI 模型**: {model_name if api_provider == 'openai' else 'Gemini'}\n\n"
        
        # 获取实时行情
        quote = fetcher.get_realtime_quote(symbol)
        if quote:
            report += "## 📊 实时行情\n\n"
            report += f"- **当前价格**: ${quote.price:,.2f}\n"
            report += f"- **24H 涨跌**: {quote.change_24h:+.2f}%\n"
            report += f"- **24H 最高**: ${quote.high_24h:,.2f}\n"
            report += f"- **24H 最低**: ${quote.low_24h:,.2f}\n"
            report += f"- **24H 成交量**: ${quote.volume_24h:,.0f}\n\n"
        else:
            report += "⚠️ 无法获取实时行情数据\n\n"
        
        # 获取K线数据并分析
        kline = fetcher.get_kline(symbol, timeframe='1d', limit=100)
        if kline is not None and not kline.data.empty:
            # 趋势分析
            trend_result = trend_analyzer.analyze(kline.data, symbol)
            if trend_result:
                report += "## 📈 技术分析\n\n"
                report += f"- **信号评分**: {trend_result.signal_score}/100\n"
                report += f"- **趋势状态**: {trend_result.technical_indicators.trend_status}\n"
                report += f"- **MA7**: ${trend_result.technical_indicators.ma7:,.2f}\n"
                report += f"- **MA25**: ${trend_result.technical_indicators.ma25:,.2f}\n"
                report += f"- **MA99**: ${trend_result.technical_indicators.ma99:,.2f}\n"
                report += f"- **乖离率**: {trend_result.technical_indicators.bias_rate:.2f}%\n\n"
                
                # 信号解读
                if trend_result.signal_score >= 70:
                    report += "🟢 **信号**: 强买入信号\n\n"
                elif trend_result.signal_score >= 50:
                    report += "🟡 **信号**: 观望或轻仓\n\n"
                else:
                    report += "🔴 **信号**: 回避或减仓\n\n"
        
        # AI 综合分析
        report += "## 🤖 AI 分析\n\n"
        try:
            context = {
                'symbol': symbol,
                'name': symbol.split('/')[0],
                'exchange': exchange,
            }
            if quote:
                context['realtime'] = {
                    'price': quote.price,
                    'change_24h': quote.change_24h,
                    'volume_24h': quote.volume_24h,
                }
            if kline is not None:
                context['kline_data'] = kline.data.to_dict('records')[-30:]  # 最近30条
            
            ai_result = ai_analyzer.analyze(context)
            if ai_result:
                report += f"**操作建议**: {ai_result.operation_advice}\n\n"
                report += f"**趋势预测**: {ai_result.trend_prediction}\n\n"
                report += f"**风险评估**: {ai_result.risk_assessment}\n\n"
                report += f"**综合评分**: {ai_result.sentiment_score}/100\n\n"
                report += f"---\n\n{ai_result.summary}\n"
        except Exception as e:
            report += f"⚠️ AI 分析失败: {str(e)}\n"
        
        return report
        
    except Exception as e:
        return f"❌ 分析失败: {str(e)}"


def market_overview() -> str:
    """获取市场概览"""
    if not MODULES_LOADED:
        return f"❌ 模块加载失败: {IMPORT_ERROR}"
    
    try:
        from crypto_market_analyzer import CryptoMarketAnalyzer
        
        analyzer = CryptoMarketAnalyzer()
        
        report = "# 🌍 加密货币市场概览\n\n"
        report += f"**更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        # 获取市场数据
        overview = analyzer.get_market_overview()
        if overview:
            report += "## 📊 市场指标\n\n"
            report += f"- **恐惧贪婪指数**: {overview.fear_greed_index} ({overview.fear_greed_label})\n"
            report += f"- **BTC 主导率**: {overview.btc_dominance:.1f}%\n"
            report += f"- **总市值**: ${overview.total_market_cap:,.0f}\n"
            report += f"- **24H 总成交量**: ${overview.total_volume_24h:,.0f}\n\n"
            
            if overview.top_gainers:
                report += "## 🚀 24H 涨幅榜\n\n"
                for i, coin in enumerate(overview.top_gainers[:5], 1):
                    report += f"{i}. {coin['symbol']}: +{coin['change']:.2f}%\n"
                report += "\n"
            
            if overview.top_losers:
                report += "## 📉 24H 跌幅榜\n\n"
                for i, coin in enumerate(overview.top_losers[:5], 1):
                    report += f"{i}. {coin['symbol']}: {coin['change']:.2f}%\n"
        
        return report
        
    except Exception as e:
        return f"❌ 获取市场概览失败: {str(e)}"


def update_api_fields(provider: str):
    """根据选择的 API 提供商更新界面"""
    if provider == "openai":
        return (
            gr.update(visible=True, placeholder="如: https://api.deepseek.com/v1"),
            gr.update(visible=True, value="deepseek-chat"),
            gr.update(placeholder="OpenAI 兼容 API Key")
        )
    else:
        return (
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(placeholder="从 https://aistudio.google.com 获取")
        )


# 创建 Gradio 界面
with gr.Blocks(title="🪙 加密货币智能分析", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🪙 加密货币智能分析系统
    
    基于 AI 的加密货币分析工具，提供技术分析、趋势判断和 AI 投资建议。
    
    > ⚠️ 本工具仅供学习研究，不构成投资建议。加密货币市场风险极高，请谨慎投资。
    """)
    
    with gr.Tab("📈 币种分析"):
        with gr.Row():
            with gr.Column(scale=1):
                symbol_input = gr.Textbox(
                    label="交易对",
                    placeholder="例如: BTC/USDT, ETH/USDT, SOL/USDT",
                    value="BTC/USDT"
                )
                
                api_provider = gr.Radio(
                    label="AI 模型提供商",
                    choices=[("Gemini（免费）", "gemini"), ("OpenAI 兼容 API", "openai")],
                    value="openai"
                )
                
                api_key_input = gr.Textbox(
                    label="API Key",
                    placeholder="OpenAI 兼容 API Key",
                    type="password"
                )
                
                api_base_url = gr.Textbox(
                    label="API Base URL",
                    placeholder="如: https://api.deepseek.com/v1",
                    visible=True
                )
                
                model_name = gr.Textbox(
                    label="模型名称",
                    value="deepseek-chat",
                    visible=True
                )
                
                exchange_input = gr.Dropdown(
                    label="交易所",
                    choices=["okx", "binance", "coinbase", "bybit", "kucoin"],
                    value="okx"
                )
                
                analyze_btn = gr.Button("🔍 开始分析", variant="primary")
            
            with gr.Column(scale=2):
                analysis_output = gr.Markdown(label="分析结果")
        
        # 根据 API 提供商更新界面
        api_provider.change(
            fn=update_api_fields,
            inputs=[api_provider],
            outputs=[api_base_url, model_name, api_key_input]
        )
        
        analyze_btn.click(
            fn=analyze_crypto,
            inputs=[symbol_input, api_provider, api_key_input, api_base_url, model_name, exchange_input],
            outputs=analysis_output
        )
    
    with gr.Tab("🌍 市场概览"):
        market_btn = gr.Button("🔄 刷新市场数据", variant="primary")
        market_output = gr.Markdown(label="市场概览")
        
        market_btn.click(
            fn=market_overview,
            inputs=[],
            outputs=market_output
        )
    
    gr.Markdown("""
    ---
    
    ## 📖 使用说明
    
    1. **选择 AI 模型**:
       - **Gemini**: Google 免费 API，从 [AI Studio](https://aistudio.google.com) 获取
       - **OpenAI 兼容 API**: 支持 DeepSeek、通义千问、Moonshot 等第三方服务
    
    2. **OpenAI 兼容 API 配置示例**:
    
       | 服务商 | Base URL | 模型名称 |
       |--------|----------|----------|
       | DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
       | 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-turbo` |
       | Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
       | 硅基流动 | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-72B-Instruct` |
    
    ## 📊 支持的交易所
    
    Binance、OKX、Coinbase、Bybit、Kucoin 等 100+ 交易所
    
    ---
    
    Made with ❤️ | [GitHub](https://github.com/Cabbagewwc/crypto-analysis)
    """)


def start_telegram_bot():
    """在后台线程中启动 Telegram Bot（异步方式）"""
    telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not telegram_token:
        logger.info("未配置 TELEGRAM_BOT_TOKEN，跳过 Telegram Bot 启动")
        return
    
    # 检查 OpenAI API 配置
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        logger.warning("未配置 OPENAI_API_KEY，Telegram Bot 无法启动")
        return
    
    import time
    max_retries = 5
    retry_delay = 10  # 秒
    
    for attempt in range(max_retries):
        try:
            from bot.telegram_bot import TelegramBot
            from bot.context_manager import init_context_manager
            
            # 初始化上下文管理器
            init_context_manager()
            
            # 创建新的事件循环（在后台线程中需要创建新的循环）
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 初始化 Telegram Bot
            allowed_chats = None
            chat_id = os.environ.get('TELEGRAM_CHAT_ID')
            if chat_id:
                try:
                    allowed_chats = [int(x.strip()) for x in chat_id.split(',')]
                except ValueError:
                    logger.warning(f"无法解析 TELEGRAM_CHAT_ID: {chat_id}")
            
            # 获取 API 配置
            base_url = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
            model = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')
            image_model = os.environ.get('IMAGE_MODEL', 'dall-e-3')
            
            bot = TelegramBot(
                token=telegram_token,
                api_key=api_key,
                base_url=base_url,
                model=model,
                image_model=image_model,
                allowed_chat_ids=allowed_chats
            )
            
            logger.info(f"🤖 Telegram Bot 启动中... (尝试 {attempt + 1}/{max_retries})")
            
            # 使用异步方式启动（适用于后台线程）
            async def run_bot():
                await bot.start_polling()
                # 保持运行
                try:
                    while True:
                        await asyncio.sleep(1)
                except asyncio.CancelledError:
                    pass
                finally:
                    await bot.stop()
            
            loop.run_until_complete(run_bot())
            break  # 成功启动，退出重试循环
            
        except Exception as e:
            error_msg = str(e)
            if "No address associated with hostname" in error_msg or "ConnectError" in error_msg:
                logger.warning(f"Telegram Bot 网络连接失败 (尝试 {attempt + 1}/{max_retries}): {error_msg}")
                if attempt < max_retries - 1:
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                    continue
            logger.error(f"Telegram Bot 启动失败: {e}", exc_info=True)
            break


if __name__ == "__main__":
    # 在后台线程中启动 Telegram Bot
    telegram_thread = threading.Thread(target=start_telegram_bot, daemon=True)
    telegram_thread.start()
    
    logger.info("🚀 启动 Gradio Web UI...")
    
    # 启动 Gradio
    demo.launch(server_name="0.0.0.0", server_port=7860)
