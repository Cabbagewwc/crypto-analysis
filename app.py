# -*- coding: utf-8 -*-
"""
🪙 加密货币智能分析系统 - Gradio Web UI

用于 HuggingFace Spaces 部署的 Web 界面
"""

import os
import gradio as gr
from datetime import datetime

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


def analyze_crypto(symbol: str, gemini_api_key: str, exchange: str = "binance") -> str:
    """
    分析单个加密货币
    
    Args:
        symbol: 交易对（如 BTC/USDT）
        gemini_api_key: Gemini API Key
        exchange: 交易所名称
    
    Returns:
        分析报告文本
    """
    if not MODULES_LOADED:
        return f"❌ 模块加载失败: {IMPORT_ERROR}"
    
    if not symbol:
        return "❌ 请输入交易对符号（如 BTC/USDT）"
    
    if not gemini_api_key:
        return "❌ 请输入 Gemini API Key"
    
    try:
        # 设置 API Key
        os.environ['GEMINI_API_KEY'] = gemini_api_key
        
        # 初始化组件
        fetcher = CCXTFetcher()
        trend_analyzer = CryptoTrendAnalyzer()
        ai_analyzer = GeminiAnalyzer(api_key=gemini_api_key)
        
        # 获取数据
        report = f"# 🪙 {symbol} 分析报告\n\n"
        report += f"**分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        # 获取实时行情
        quote = fetcher.get_realtime_quote(symbol, exchange)
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
        kline = fetcher.get_kline(symbol, exchange, timeframe='1d', limit=100)
        if kline is not None and not kline.empty:
            # 趋势分析
            trend_result = trend_analyzer.analyze(kline, symbol)
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
                context['kline_data'] = kline.to_dict('records')[-30:]  # 最近30条
            
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
                api_key_input = gr.Textbox(
                    label="Gemini API Key",
                    placeholder="从 https://aistudio.google.com 获取",
                    type="password"
                )
                exchange_input = gr.Dropdown(
                    label="交易所",
                    choices=["binance", "okx", "coinbase", "bybit", "kucoin"],
                    value="binance"
                )
                analyze_btn = gr.Button("🔍 开始分析", variant="primary")
            
            with gr.Column(scale=2):
                analysis_output = gr.Markdown(label="分析结果")
        
        analyze_btn.click(
            fn=analyze_crypto,
            inputs=[symbol_input, api_key_input, exchange_input],
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
    
    1. **币种分析**: 输入交易对和 API Key，获取详细的技术分析和 AI 建议
    2. **市场概览**: 查看整体市场情况，包括恐惧贪婪指数、涨跌榜等
    
    ## 🔑 获取 API Key
    
    - **Gemini API**: 访问 [Google AI Studio](https://aistudio.google.com) 免费获取
    
    ## 📊 支持的交易所
    
    - Binance、OKX、Coinbase、Bybit、Kucoin 等 100+ 交易所
    
    ---
    
    Made with ❤️ | [GitHub](https://github.com/Cabbagewwc/crypto-analysis)
    """)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
