# -*- coding: utf-8 -*-
"""
===================================
加密货币智能分析系统 - 主调度程序
===================================

职责：
1. 协调各模块完成加密货币分析流程
2. 实现低并发的线程池调度
3. 全局异常处理，确保单币失败不影响整体
4. 提供命令行入口

使用方式：
    python main.py              # 正常运行
    python main.py --debug      # 调试模式
    python main.py --dry-run    # 仅获取数据不分析

交易理念（已融入分析）：
- 严进策略：不追高，乖离率 > 10% 不买入
- 趋势交易：只做 MA7>MA25>MA99 多头排列
- 链上分析：关注巨鲸动向和持币分布
- 买点偏好：缩量回踩 MA7/MA25 支撑
"""
import os

# 代理配置 - 仅在本地环境使用，GitHub Actions 不需要
if os.getenv("GITHUB_ACTIONS") != "true":
    # 本地开发环境，如需代理请取消注释或修改端口
    # os.environ["http_proxy"] = "http://127.0.0.1:10809"
    # os.environ["https_proxy"] = "http://127.0.0.1:10809"
    pass

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timezone, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from feishu_doc import FeishuDocManager

from config import get_config, Config
from data_provider.ccxt_fetcher import CCXTFetcher, CryptoRealtimeQuote
from data_provider.geckoterminal_fetcher import GeckoTerminalFetcher, TokenInfo, OnchainMetrics
from analyzer import GeminiAnalyzer, AnalysisResult, CRYPTO_NAME_MAP
from notification import NotificationService, NotificationChannel
from search_service import SearchService, SearchResponse
from crypto_analyzer import CryptoTrendAnalyzer, CryptoAnalysisResult
from crypto_market_analyzer import CryptoMarketAnalyzer, CryptoMarketOverview

# 配置日志格式
LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def setup_logging(debug: bool = False, log_dir: str = "./logs") -> None:
    """
    配置日志系统（同时输出到控制台和文件）
    
    Args:
        debug: 是否启用调试模式
        log_dir: 日志文件目录
    """
    level = logging.DEBUG if debug else logging.INFO
    
    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # 日志文件路径（按日期分文件）
    today_str = datetime.now().strftime('%Y%m%d')
    log_file = log_path / f"crypto_analysis_{today_str}.log"
    debug_log_file = log_path / f"crypto_analysis_debug_{today_str}.log"
    
    # 创建根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 根 logger 设为 DEBUG，由 handler 控制输出级别
    
    # Handler 1: 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(console_handler)
    
    # Handler 2: 常规日志文件（INFO 级别，10MB 轮转）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(file_handler)
    
    # Handler 3: 调试日志文件（DEBUG 级别，包含所有详细信息）
    debug_handler = RotatingFileHandler(
        debug_log_file,
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=3,
        encoding='utf-8'
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(debug_handler)
    
    # 降低第三方库的日志级别
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('google').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    
    logging.info(f"日志系统初始化完成，日志目录: {log_path.absolute()}")
    logging.info(f"常规日志: {log_file}")
    logging.info(f"调试日志: {debug_log_file}")


logger = logging.getLogger(__name__)


class CryptoAnalysisPipeline:
    """
    加密货币分析主流程调度器
    
    职责：
    1. 管理整个分析流程
    2. 协调数据获取、搜索、分析、通知等模块
    3. 实现并发控制和异常处理
    """
    
    def __init__(
        self,
        config: Optional[Config] = None,
        max_workers: Optional[int] = None
    ):
        """
        初始化调度器
        
        Args:
            config: 配置对象（可选，默认使用全局配置）
            max_workers: 最大并发线程数（可选，默认从配置读取）
        """
        self.config = config or get_config()
        self.max_workers = max_workers or self.config.max_workers
        
        # 初始化各模块
        self.ccxt_fetcher = CCXTFetcher()  # 交易所数据获取
        self.gecko_fetcher = GeckoTerminalFetcher()  # 链上数据获取
        self.trend_analyzer = CryptoTrendAnalyzer()  # 加密货币趋势分析器
        self.analyzer = GeminiAnalyzer()
        self.notifier = NotificationService()
        
        # 初始化搜索服务
        self.search_service = SearchService(
            bocha_keys=self.config.bocha_api_keys,
            tavily_keys=self.config.tavily_api_keys,
            serpapi_keys=self.config.serpapi_keys,
        )
        
        logger.info(f"调度器初始化完成，最大并发数: {self.max_workers}")
        logger.info("已启用加密货币趋势分析器 (MA7>MA25>MA99 多头判断)")
        if self.search_service.is_available:
            logger.info("搜索服务已启用 (Tavily/SerpAPI)")
        else:
            logger.warning("搜索服务未启用（未配置 API Key）")
    
    def fetch_crypto_data(
        self,
        symbol: str,
        exchange: str = 'binance'
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        获取单个加密货币数据
        
        Args:
            symbol: 交易对符号（如 BTC/USDT）
            exchange: 交易所名称（默认 binance）
            
        Returns:
            Tuple[是否成功, 错误信息, 数据字典]
        """
        try:
            logger.info(f"[{symbol}] 开始从 {exchange} 获取数据...")
            
            # 获取实时行情
            realtime_quote = self.ccxt_fetcher.get_realtime_quote(symbol, exchange)
            if not realtime_quote:
                return False, "获取实时行情失败", None
            
            # 获取K线数据（用于技术分析）
            kline_data = self.ccxt_fetcher.get_kline(symbol, exchange, timeframe='1d', limit=100)
            if not kline_data or kline_data.empty:
                return False, "获取K线数据失败", None
            
            # 尝试获取链上数据（如果是链上Token）
            onchain_data = None
            try:
                # 解析交易对，提取Token地址（如果有）
                token_address = self.config.parse_crypto_identifier(symbol).get('address')
                if token_address:
                    chain = self.config.preferred_chains[0] if self.config.preferred_chains else 'solana'
                    token_info = self.gecko_fetcher.get_token_info(token_address, chain)
                    if token_info:
                        onchain_data = {
                            'holders': token_info.holder_count,
                            'top10_percentage': token_info.top10_holder_percentage,
                            'liquidity_usd': token_info.liquidity_usd,
                        }
            except Exception as e:
                logger.debug(f"[{symbol}] 获取链上数据失败（可能是CEX交易对）: {e}")
            
            # 组装数据
            data = {
                'symbol': symbol,
                'exchange': exchange,
                'realtime': realtime_quote,
                'kline': kline_data,
                'onchain': onchain_data,
            }
            
            logger.info(f"[{symbol}] 数据获取成功")
            return True, None, data
            
        except Exception as e:
            error_msg = f"获取数据失败: {str(e)}"
            logger.error(f"[{symbol}] {error_msg}")
            return False, error_msg, None
    
    def analyze_crypto(self, symbol: str, crypto_data: Dict) -> Optional[AnalysisResult]:
        """
        分析单个加密货币（含技术指标、链上数据、多维度情报）
        
        流程：
        1. 提取实时行情和K线数据
        2. 进行趋势分析（基于加密货币交易理念）
        3. 获取链上指标（如果有）
        4. 多维度情报搜索（Token Unlock、巨鲸动向、项目进展）
        5. 调用 AI 进行综合分析
        
        Args:
            symbol: 交易对符号（如 BTC/USDT）
            crypto_data: 加密货币数据字典
            
        Returns:
            AnalysisResult 或 None（如果分析失败）
        """
        try:
            # 获取币种名称
            crypto_name = CRYPTO_NAME_MAP.get(symbol, symbol.split('/')[0])
            
            # Step 1: 提取数据
            realtime_quote = crypto_data.get('realtime')
            kline_data = crypto_data.get('kline')
            onchain_data = crypto_data.get('onchain')
            
            if realtime_quote:
                logger.info(f"[{symbol}] {crypto_name} 实时行情: 价格=${realtime_quote.price:.2f}, "
                          f"24h涨跌={realtime_quote.change_24h:+.2f}%, 成交量=${realtime_quote.volume_24h:,.0f}")
            
            # Step 2: 趋势分析（基于加密货币交易理念）
            trend_result: Optional[CryptoAnalysisResult] = None
            try:
                if kline_data is not None and not kline_data.empty:
                    trend_result = self.trend_analyzer.analyze(kline_data, symbol)
                    if trend_result:
                        logger.info(f"[{symbol}] 趋势分析: 信号评分={trend_result.signal_score}/100, "
                                  f"趋势={trend_result.technical_indicators.trend_status}")
            except Exception as e:
                logger.warning(f"[{symbol}] 趋势分析失败: {e}")
            
            # Step 3: 多维度情报搜索（Token Unlock、巨鲸动向、项目进展）
            news_context = None
            if self.search_service.is_available:
                logger.info(f"[{symbol}] 开始多维度情报搜索...")
                
                try:
                    # 使用加密货币专用搜索
                    intel_results = self.search_service.search_crypto_news(
                        crypto_symbol=symbol,
                        crypto_name=crypto_name,
                        max_results=5
                    )
                    
                    if intel_results and intel_results.success:
                        news_context = f"最新消息（共{len(intel_results.results)}条）:\n"
                        for idx, result in enumerate(intel_results.results[:3], 1):
                            news_context += f"{idx}. {result.get('title', result.get('snippet', ''))}\n"
                        logger.info(f"[{symbol}] 情报搜索完成: 共 {len(intel_results.results)} 条结果")
                except Exception as e:
                    logger.warning(f"[{symbol}] 情报搜索失败: {e}")
            else:
                logger.info(f"[{symbol}] 搜索服务不可用，跳过情报搜索")
            
            # Step 4: 构建分析上下文
            context = {
                'symbol': symbol,
                'name': crypto_name,
                'exchange': crypto_data.get('exchange', 'binance'),
                'realtime': {
                    'price': realtime_quote.price if realtime_quote else 0,
                    'change_24h': realtime_quote.change_24h if realtime_quote else 0,
                    'volume_24h': realtime_quote.volume_24h if realtime_quote else 0,
                    'high_24h': realtime_quote.high_24h if realtime_quote else 0,
                    'low_24h': realtime_quote.low_24h if realtime_quote else 0,
                } if realtime_quote else {},
                'kline_data': kline_data.to_dict('records') if kline_data is not None else [],
            }
            
            # 添加趋势分析结果
            if trend_result:
                context['trend_analysis'] = {
                    'signal_score': trend_result.signal_score,
                    'trend_status': trend_result.technical_indicators.trend_status,
                    'ma7': trend_result.technical_indicators.ma7,
                    'ma25': trend_result.technical_indicators.ma25,
                    'ma99': trend_result.technical_indicators.ma99,
                    'bias_rate': trend_result.technical_indicators.bias_rate,
                    'momentum': trend_result.technical_indicators.momentum,
                }
            
            # 添加链上数据
            if onchain_data:
                context['onchain'] = onchain_data
            
            # Step 5: 调用 AI 分析
            result = self.analyzer.analyze(context, news_context=news_context)
            
            return result
            
        except Exception as e:
            logger.error(f"[{symbol}] 分析失败: {e}")
            logger.exception(f"[{symbol}] 详细错误信息:")
            return None
    
    def _describe_volume_status(self, volume_24h: float, avg_volume: float) -> str:
        """
        成交量状态描述
        
        Args:
            volume_24h: 24小时成交量
            avg_volume: 平均成交量
        """
        if avg_volume == 0:
            return "正常"
        
        ratio = volume_24h / avg_volume
        if ratio < 0.5:
            return "极度萎缩"
        elif ratio < 0.8:
            return "明显萎缩"
        elif ratio < 1.2:
            return "正常"
        elif ratio < 2.0:
            return "温和放量"
        elif ratio < 3.0:
            return "明显放量"
        else:
            return "巨量"
    
    def process_single_crypto(
        self,
        symbol: str,
        skip_analysis: bool = False,
        single_crypto_notify: bool = False
    ) -> Optional[AnalysisResult]:
        """
        处理单个加密货币的完整流程
        
        包括：
        1. 获取数据（交易所 + 链上）
        2. AI 分析
        3. 单币推送（可选）
        
        此方法会被线程池调用，需要处理好异常
        
        Args:
            symbol: 交易对符号（如 BTC/USDT）
            skip_analysis: 是否跳过 AI 分析
            single_crypto_notify: 是否启用单币推送模式（每分析完一个立即推送）
            
        Returns:
            AnalysisResult 或 None
        """
        logger.info(f"========== 开始处理 {symbol} ==========")
        
        try:
            # Step 1: 获取数据
            success, error, crypto_data = self.fetch_crypto_data(symbol)
            
            if not success:
                logger.warning(f"[{symbol}] 数据获取失败: {error}")
                return None
            
            # Step 2: AI 分析
            if skip_analysis:
                logger.info(f"[{symbol}] 跳过 AI 分析（dry-run 模式）")
                return None
            
            result = self.analyze_crypto(symbol, crypto_data)
            
            if result:
                logger.info(
                    f"[{symbol}] 分析完成: {result.operation_advice}, "
                    f"评分 {result.sentiment_score}"
                )
                
                # 单币推送模式：每分析完一个币种立即推送
                if single_crypto_notify and self.notifier.is_available():
                    try:
                        single_report = self.notifier.generate_single_crypto_report(result)
                        if self.notifier.send(single_report):
                            logger.info(f"[{symbol}] 单币推送成功")
                        else:
                            logger.warning(f"[{symbol}] 单币推送失败")
                    except Exception as e:
                        logger.error(f"[{symbol}] 单币推送异常: {e}")
            
            return result
            
        except Exception as e:
            # 捕获所有异常，确保单币失败不影响整体
            logger.exception(f"[{symbol}] 处理过程发生未知异常: {e}")
            return None
    
    def run(
        self,
        crypto_symbols: Optional[List[str]] = None,
        dry_run: bool = False,
        send_notification: bool = True
    ) -> List[AnalysisResult]:
        """
        运行完整的分析流程
        
        流程：
        1. 获取待分析的加密货币列表
        2. 使用线程池并发处理
        3. 收集分析结果
        4. 发送通知
        
        Args:
            crypto_symbols: 加密货币交易对列表（可选，默认使用配置中的列表）
            dry_run: 是否仅获取数据不分析
            send_notification: 是否发送推送通知
            
        Returns:
            分析结果列表
        """
        start_time = time.time()
        
        # 使用配置中的加密货币列表
        if crypto_symbols is None:
            crypto_symbols = self.config.crypto_list
        
        if not crypto_symbols:
            logger.error("未配置加密货币列表，请在 .env 文件中设置 CRYPTO_LIST")
            return []
        
        logger.info(f"===== 开始分析 {len(crypto_symbols)} 个加密货币 =====")
        logger.info(f"币种列表: {', '.join(crypto_symbols)}")
        logger.info(f"并发数: {self.max_workers}, 模式: {'仅获取数据' if dry_run else '完整分析'}")
        
        # 单币推送模式：从配置读取
        single_crypto_notify = getattr(self.config, 'single_crypto_notify', False)
        if single_crypto_notify:
            logger.info("已启用单币推送模式：每分析完一个币种立即推送")
        
        results: List[AnalysisResult] = []
        
        # 使用线程池并发处理
        # 注意：max_workers 设置较低（默认3）以避免触发API限流
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交任务
            future_to_symbol = {
                executor.submit(
                    self.process_single_crypto,
                    symbol,
                    skip_analysis=dry_run,
                    single_crypto_notify=single_crypto_notify and send_notification
                ): symbol
                for symbol in crypto_symbols
            }
            
            # 收集结果
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"[{symbol}] 任务执行失败: {e}")
        
        # 统计
        elapsed_time = time.time() - start_time
        success_count = len(results)
        fail_count = len(crypto_symbols) - success_count
        
        logger.info(f"===== 分析完成 =====")
        logger.info(f"成功: {success_count}, 失败: {fail_count}, 耗时: {elapsed_time:.2f} 秒")
        
        # 发送通知（单币推送模式下跳过汇总推送，避免重复）
        if results and send_notification and not dry_run:
            if single_crypto_notify:
                # 单币推送模式：只保存汇总报告，不再重复推送
                logger.info("单币推送模式：跳过汇总推送，仅保存报告到本地")
                self._send_notifications(results, skip_push=True)
            else:
                self._send_notifications(results)
        
        return results
    
    def _send_notifications(self, results: List[AnalysisResult], skip_push: bool = False) -> None:
        """
        发送分析结果通知
        
        生成决策仪表盘格式的报告
        
        Args:
            results: 分析结果列表
            skip_push: 是否跳过推送（仅保存到本地，用于单股推送模式）
        """
        try:
            logger.info("生成决策仪表盘日报...")
            
            # 生成决策仪表盘格式的详细日报
            report = self.notifier.generate_dashboard_report(results)
            
            # 保存到本地
            filepath = self.notifier.save_report_to_file(report)
            logger.info(f"决策仪表盘日报已保存: {filepath}")
            
            # 跳过推送（单股推送模式）
            if skip_push:
                return
            
            # 推送通知
            if self.notifier.is_available():
                channels = self.notifier.get_available_channels()

                # 企业微信：只发精简版（平台限制）
                wechat_success = False
                if NotificationChannel.WECHAT in channels:
                    dashboard_content = self.notifier.generate_wechat_dashboard(results)
                    logger.info(f"企业微信仪表盘长度: {len(dashboard_content)} 字符")
                    logger.debug(f"企业微信推送内容:\n{dashboard_content}")
                    wechat_success = self.notifier.send_to_wechat(dashboard_content)

                # 其他渠道：发完整报告（避免自定义 Webhook 被 wechat 截断逻辑污染）
                non_wechat_success = False
                for channel in channels:
                    if channel == NotificationChannel.WECHAT:
                        continue
                    if channel == NotificationChannel.FEISHU:
                        non_wechat_success = self.notifier.send_to_feishu(report) or non_wechat_success
                    elif channel == NotificationChannel.TELEGRAM:
                        non_wechat_success = self.notifier.send_to_telegram(report) or non_wechat_success
                    elif channel == NotificationChannel.EMAIL:
                        non_wechat_success = self.notifier.send_to_email(report) or non_wechat_success
                    elif channel == NotificationChannel.CUSTOM:
                        non_wechat_success = self.notifier.send_to_custom(report) or non_wechat_success
                    else:
                        logger.warning(f"未知通知渠道: {channel}")

                success = wechat_success or non_wechat_success
                if success:
                    logger.info("决策仪表盘推送成功")
                else:
                    logger.warning("决策仪表盘推送失败")
            else:
                logger.info("通知渠道未配置，跳过推送")
                
        except Exception as e:
            logger.error(f"发送通知失败: {e}")


def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='加密货币智能分析系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python main.py                    # 正常运行
  python main.py --debug            # 调试模式
  python main.py --dry-run          # 仅获取数据，不进行 AI 分析
  python main.py --cryptos BTC/USDT,ETH/USDT  # 指定分析特定币种
  python main.py --no-notify        # 不发送推送通知
  python main.py --single-notify    # 启用单币推送模式（每分析完一个立即推送）
  python main.py --schedule         # 启用定时任务模式
  python main.py --market-review    # 仅运行市场复盘
        '''
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用调试模式，输出详细日志'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅获取数据，不进行 AI 分析'
    )
    
    parser.add_argument(
        '--cryptos',
        type=str,
        help='指定要分析的加密货币交易对，逗号分隔（覆盖配置文件）'
    )
    
    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='不发送推送通知'
    )
    
    parser.add_argument(
        '--single-notify',
        action='store_true',
        help='启用单币推送模式：每分析完一个币种立即推送，而不是汇总推送'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='并发线程数（默认使用配置值）'
    )
    
    parser.add_argument(
        '--schedule',
        action='store_true',
        help='启用定时任务模式，每日定时执行'
    )
    
    parser.add_argument(
        '--market-review',
        action='store_true',
        help='仅运行加密货币市场复盘分析'
    )
    
    parser.add_argument(
        '--no-market-review',
        action='store_true',
        help='跳过市场复盘分析'
    )
    
    return parser.parse_args()


def run_market_review(notifier: NotificationService, analyzer=None, search_service=None) -> Optional[str]:
    """
    执行加密货币市场复盘分析
    
    Args:
        notifier: 通知服务
        analyzer: AI分析器（可选）
        search_service: 搜索服务（可选）
    
    Returns:
        复盘报告文本
    """
    logger.info("开始执行加密货币市场复盘分析...")
    
    try:
        market_analyzer = CryptoMarketAnalyzer(
            search_service=search_service,
            analyzer=analyzer
        )
        
        # 执行复盘
        review_report = market_analyzer.run_daily_review()
        
        if review_report:
            # 保存报告到文件
            date_str = datetime.now().strftime('%Y%m%d')
            report_filename = f"crypto_market_review_{date_str}.md"
            filepath = notifier.save_report_to_file(
                f"# 🎯 加密货币市场复盘\n\n{review_report}",
                report_filename
            )
            logger.info(f"市场复盘报告已保存: {filepath}")
            
            # 推送通知
            if notifier.is_available():
                # 添加标题
                report_content = f"🎯 加密货币市场复盘\n\n{review_report}"
                
                success = notifier.send(report_content)
                if success:
                    logger.info("市场复盘推送成功")
                else:
                    logger.warning("市场复盘推送失败")
            
            return review_report
        
    except Exception as e:
        logger.error(f"市场复盘分析失败: {e}")
    
    return None


def run_full_analysis(
    config: Config,
    args: argparse.Namespace,
    crypto_symbols: Optional[List[str]] = None
):
    """
    执行完整的分析流程（币种分析 + 市场复盘）
    
    这是定时任务调用的主函数
    """
    try:
        # 命令行参数 --single-notify 覆盖配置（#55）
        if getattr(args, 'single_notify', False):
            config.single_crypto_notify = True
        
        # 创建调度器
        pipeline = CryptoAnalysisPipeline(
            config=config,
            max_workers=args.workers
        )
        
        # 1. 运行币种分析
        results = pipeline.run(
            crypto_symbols=crypto_symbols,
            dry_run=args.dry_run,
            send_notification=not args.no_notify
        )
        
        # 2. 运行市场复盘（如果启用且不是仅币种模式）
        market_report = ""
        if config.market_review_enabled and not args.no_market_review:
            # 只调用一次，并获取结果
            review_result = run_market_review(
                notifier=pipeline.notifier,
                analyzer=pipeline.analyzer,
                search_service=pipeline.search_service
            )
            # 如果有结果，赋值给 market_report 用于后续飞书文档生成
            if review_result:
                market_report = review_result
        
        # 输出摘要
        if results:
            logger.info("\n===== 分析结果摘要 =====")
            for r in sorted(results, key=lambda x: x.sentiment_score, reverse=True):
                emoji = r.get_emoji()
                logger.info(
                    f"{emoji} {r.name}({r.code}): {r.operation_advice} | "
                    f"评分 {r.sentiment_score} | {r.trend_prediction}"
                )
        
        logger.info("\n任务执行完成")

        # === 新增：生成飞书云文档 ===
        try:
            feishu_doc = FeishuDocManager()
            if feishu_doc.is_configured() and (results or market_report):
                logger.info("正在创建飞书云文档...")

                # 1. 准备标题 "01-01 13:01 加密货币市场复盘"
                tz_cn = timezone(timedelta(hours=8))
                now = datetime.now(tz_cn)
                doc_title = f"{now.strftime('%Y-%m-%d %H:%M')} 加密货币市场复盘"

                # 2. 准备内容 (拼接币种分析和市场复盘)
                full_content = ""

                # 添加市场复盘内容（如果有）
                if market_report:
                    full_content += f"# 📈 加密货币市场复盘\n\n{market_report}\n\n---\n\n"

                # 添加币种决策仪表盘（使用 NotificationService 生成）
                if results:
                    dashboard_content = pipeline.notifier.generate_dashboard_report(results)
                    full_content += f"# 🚀 币种决策仪表盘\n\n{dashboard_content}"

                # 3. 创建文档
                doc_url = feishu_doc.create_daily_doc(doc_title, full_content)
                if doc_url:
                    logger.info(f"飞书云文档创建成功: {doc_url}")
                    # 可选：将文档链接也推送到群里
                    pipeline.notifier.send(f"[{now.strftime('%Y-%m-%d %H:%M')}] 复盘文档创建成功: {doc_url}")

        except Exception as e:
            logger.error(f"飞书文档生成失败: {e}")
        
    except Exception as e:
        logger.exception(f"分析流程执行失败: {e}")


def main() -> int:
    """
    主入口函数
    
    Returns:
        退出码（0 表示成功）
    """
    # 解析命令行参数
    args = parse_arguments()
    
    # 加载配置（在设置日志前加载，以获取日志目录）
    config = get_config()
    
    # 配置日志（输出到控制台和文件）
    setup_logging(debug=args.debug, log_dir=config.log_dir)
    
    logger.info("=" * 60)
    logger.info("加密货币智能分析系统 启动")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # 验证配置
    warnings = config.validate()
    for warning in warnings:
        logger.warning(warning)
    
    # 解析加密货币列表
    crypto_symbols = None
    if args.cryptos:
        crypto_symbols = [symbol.strip() for symbol in args.cryptos.split(',') if symbol.strip()]
        logger.info(f"使用命令行指定的交易对列表: {crypto_symbols}")
    
    try:
        # 模式1: 仅市场复盘
        if args.market_review:
            logger.info("模式: 仅市场复盘")
            notifier = NotificationService()
            
            # 初始化搜索服务和分析器（如果有配置）
            search_service = None
            analyzer = None
            
            if config.bocha_api_keys or config.tavily_api_keys or config.serpapi_keys:
                search_service = SearchService(
                    bocha_keys=config.bocha_api_keys,
                    tavily_keys=config.tavily_api_keys,
                    serpapi_keys=config.serpapi_keys
                )
            
            if config.gemini_api_key:
                analyzer = GeminiAnalyzer(api_key=config.gemini_api_key)
            
            run_market_review(notifier, analyzer, search_service)
            return 0
        
        # 模式2: 定时任务模式
        if args.schedule or config.schedule_enabled:
            logger.info("模式: 定时任务")
            logger.info(f"每日执行时间: {config.schedule_time}")
            
            from scheduler import run_with_schedule
            
            def scheduled_task():
                run_full_analysis(config, args, crypto_symbols)
            
            run_with_schedule(
                task=scheduled_task,
                schedule_time=config.schedule_time,
                run_immediately=True  # 启动时先执行一次
            )
            return 0
        
        # 模式3: 正常单次运行
        run_full_analysis(config, args, crypto_symbols)
        
        logger.info("\n程序执行完成")
        return 0
        
    except KeyboardInterrupt:
        logger.info("\n用户中断，程序退出")
        return 130
        
    except Exception as e:
        logger.exception(f"程序执行失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
