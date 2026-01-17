"""
CCXT 数据获取模块 - 支持多交易所现货数据

支持的交易所：
- Binance（主要）
- OKX
- 其他 CCXT 支持的交易所

功能：
- 现货 K 线数据 (1m, 5m, 15m, 1h, 4h, 1d)
- 实时行情 (价格、成交量、24h涨跌幅)
- 订单簿深度
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import time

import pandas as pd
import numpy as np

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    ccxt = None

# 注意：CCXTFetcher 不继承 BaseFetcher，因为它是为加密货币设计的，
# 有完全不同的接口（get_kline, get_realtime_quote 等）

logger = logging.getLogger(__name__)


@dataclass
class CryptoRealtimeQuote:
    """加密货币实时行情数据"""
    symbol: str                     # 交易对 BTC/USDT
    exchange: str                   # 交易所名称
    price: float                    # 当前价格
    open_24h: float                 # 24h开盘价
    high_24h: float                 # 24h最高价
    low_24h: float                  # 24h最低价
    close: float                    # 收盘价（同price）
    change_24h: float               # 24h涨跌幅 (%)
    change_amount_24h: float        # 24h涨跌额
    volume_24h: float               # 24h成交量（基础货币）
    quote_volume_24h: float         # 24h成交额（计价货币）
    bid: float                      # 买一价
    ask: float                      # 卖一价
    spread: float                   # 买卖价差 (%)
    timestamp: datetime             # 数据时间戳
    
    # 额外信息
    base_currency: str = ""         # 基础货币 (BTC)
    quote_currency: str = ""        # 计价货币 (USDT)
    market_cap: Optional[float] = None  # 市值（如果可用）


@dataclass
class CryptoKlineData:
    """加密货币K线数据"""
    symbol: str
    exchange: str
    timeframe: str                  # 1m, 5m, 15m, 1h, 4h, 1d
    data: pd.DataFrame              # OHLCV DataFrame
    
    # 技术指标（计算后填充）
    ma7: Optional[pd.Series] = None
    ma25: Optional[pd.Series] = None
    ma99: Optional[pd.Series] = None
    bias_7: Optional[float] = None   # 7日乖离率
    trend_status: str = ""           # 趋势状态


class CCXTFetcher:
    """
    CCXT 统一交易所数据获取器
    
    支持功能：
    1. 多交易所切换 (Binance, OKX 等)
    2. K线数据获取
    3. 实时行情获取
    4. 订单簿深度
    
    使用示例：
        fetcher = CCXTFetcher(exchange='binance')
        
        # 获取K线
        kline = fetcher.get_kline('BTC/USDT', timeframe='1h', limit=100)
        
        # 获取实时行情
        quote = fetcher.get_realtime_quote('BTC/USDT')
    """
    
    # 数据源名称
    name: str = "CCXTFetcher"
    
    # 支持的交易所
    SUPPORTED_EXCHANGES = ['binance', 'okx', 'bybit', 'gate', 'kucoin', 'huobi']
    
    # 时间周期映射
    TIMEFRAME_MAP = {
        '1m': '1m',
        '5m': '5m',
        '15m': '15m',
        '30m': '30m',
        '1h': '1h',
        '4h': '4h',
        '1d': '1d',
        '1w': '1w',
    }
    
    def __init__(
        self,
        exchange: str = 'binance',
        api_key: str = '',
        api_secret: str = '',
        passphrase: str = '',  # OKX 需要
        sandbox: bool = False,
        timeout: int = 30000,
        rate_limit: bool = True,
    ):
        """
        初始化 CCXT Fetcher
        
        Args:
            exchange: 交易所名称 (binance, okx, bybit 等)
            api_key: API Key（可选，公开数据不需要）
            api_secret: API Secret
            passphrase: API Passphrase (OKX需要)
            sandbox: 是否使用沙盒/测试网
            timeout: 请求超时时间 (ms)
            rate_limit: 是否启用速率限制
        """
        if not CCXT_AVAILABLE:
            raise ImportError("ccxt 库未安装，请运行: pip install ccxt")
        
        self.exchange_id = exchange.lower()
        if self.exchange_id not in self.SUPPORTED_EXCHANGES:
            logger.warning(f"交易所 {exchange} 可能不受完全支持")
        
        # 创建交易所实例
        exchange_class = getattr(ccxt, self.exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"不支持的交易所: {exchange}")
        
        config = {
            'apiKey': api_key if api_key else None,
            'secret': api_secret if api_secret else None,
            'timeout': timeout,
            'enableRateLimit': rate_limit,
            'options': {
                'defaultType': 'spot',  # 默认现货
            }
        }
        
        # OKX 需要 passphrase
        if self.exchange_id == 'okx' and passphrase:
            config['password'] = passphrase
        
        # 沙盒模式
        if sandbox:
            config['sandbox'] = True
        
        self.exchange = exchange_class(config)
        
        # 缓存市场信息
        self._markets_loaded = False
        self._markets_cache: Dict[str, Any] = {}
        
        logger.info(f"CCXTFetcher 初始化完成: {self.exchange_id}")
    
    def _ensure_markets_loaded(self):
        """确保市场信息已加载"""
        if not self._markets_loaded:
            try:
                self.exchange.load_markets()
                self._markets_cache = self.exchange.markets
                self._markets_loaded = True
                logger.info(f"已加载 {len(self._markets_cache)} 个交易对")
            except Exception as e:
                logger.error(f"加载市场信息失败: {e}")
                raise
    
    def _normalize_symbol(self, symbol: str) -> str:
        """
        标准化交易对格式
        
        支持的格式：
        - BTC/USDT (标准格式)
        - BTCUSDT (无斜杠)
        - btc/usdt (小写)
        
        Returns:
            标准化的交易对 (BTC/USDT)
        """
        symbol = symbol.upper().strip()
        
        # 如果已经是标准格式
        if '/' in symbol:
            return symbol
        
        # 尝试添加斜杠
        # 常见的计价货币
        quote_currencies = ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'BNB']
        
        for quote in quote_currencies:
            if symbol.endswith(quote):
                base = symbol[:-len(quote)]
                if base:
                    return f"{base}/{quote}"
        
        # 默认添加 /USDT
        return f"{symbol}/USDT"
    
    def get_kline(
        self,
        symbol: str,
        timeframe: str = '1d',
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> Optional[CryptoKlineData]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对 (BTC/USDT)
            timeframe: 时间周期 (1m, 5m, 15m, 1h, 4h, 1d)
            limit: 获取数量
            since: 起始时间
            
        Returns:
            CryptoKlineData 或 None
        """
        try:
            self._ensure_markets_loaded()
            
            symbol = self._normalize_symbol(symbol)
            
            if symbol not in self._markets_cache:
                logger.warning(f"交易对 {symbol} 不存在于 {self.exchange_id}")
                return None
            
            # 转换时间周期
            tf = self.TIMEFRAME_MAP.get(timeframe, timeframe)
            
            # 转换起始时间
            since_ts = None
            if since:
                since_ts = int(since.timestamp() * 1000)
            
            # 获取OHLCV数据
            ohlcv = self.exchange.fetch_ohlcv(
                symbol,
                timeframe=tf,
                since=since_ts,
                limit=limit
            )
            
            if not ohlcv:
                logger.warning(f"未获取到 {symbol} 的K线数据")
                return None
            
            # 转换为DataFrame
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # 转换时间戳
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # 确保数据类型
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 创建结果对象
            kline_data = CryptoKlineData(
                symbol=symbol,
                exchange=self.exchange_id,
                timeframe=timeframe,
                data=df
            )
            
            # 计算技术指标
            self._calculate_indicators(kline_data)
            
            logger.info(f"获取 {symbol} K线数据成功: {len(df)} 条")
            return kline_data
            
        except Exception as e:
            logger.error(f"获取K线数据失败 {symbol}: {e}")
            return None
    
    def _calculate_indicators(self, kline_data: CryptoKlineData):
        """计算技术指标"""
        df = kline_data.data
        
        if len(df) < 7:
            return
        
        # 计算均线
        kline_data.ma7 = df['close'].rolling(window=7).mean()
        
        if len(df) >= 25:
            kline_data.ma25 = df['close'].rolling(window=25).mean()
        
        if len(df) >= 99:
            kline_data.ma99 = df['close'].rolling(window=99).mean()
        
        # 计算7日乖离率
        if kline_data.ma7 is not None and len(kline_data.ma7) > 0:
            current_price = df['close'].iloc[-1]
            ma7_value = kline_data.ma7.iloc[-1]
            if ma7_value and ma7_value > 0:
                kline_data.bias_7 = ((current_price - ma7_value) / ma7_value) * 100
        
        # 判断趋势状态
        kline_data.trend_status = self._determine_trend(kline_data)
    
    def _determine_trend(self, kline_data: CryptoKlineData) -> str:
        """判断趋势状态"""
        if kline_data.ma7 is None:
            return "数据不足"
        
        ma7 = kline_data.ma7.iloc[-1] if len(kline_data.ma7) > 0 else None
        ma25 = kline_data.ma25.iloc[-1] if kline_data.ma25 is not None and len(kline_data.ma25) > 0 else None
        ma99 = kline_data.ma99.iloc[-1] if kline_data.ma99 is not None and len(kline_data.ma99) > 0 else None
        
        if ma7 is None:
            return "数据不足"
        
        # 多头排列判断
        if ma25 is not None and ma99 is not None:
            if ma7 > ma25 > ma99:
                return "多头排列 📈"
            elif ma7 < ma25 < ma99:
                return "空头排列 📉"
            else:
                return "震荡整理 📊"
        elif ma25 is not None:
            if ma7 > ma25:
                return "短期看多 📈"
            else:
                return "短期看空 📉"
        else:
            return "数据不足"
    
    def get_realtime_quote(self, symbol: str) -> Optional[CryptoRealtimeQuote]:
        """
        获取实时行情
        
        Args:
            symbol: 交易对 (BTC/USDT)
            
        Returns:
            CryptoRealtimeQuote 或 None
        """
        try:
            self._ensure_markets_loaded()
            
            symbol = self._normalize_symbol(symbol)
            
            if symbol not in self._markets_cache:
                logger.warning(f"交易对 {symbol} 不存在于 {self.exchange_id}")
                return None
            
            # 获取行情
            ticker = self.exchange.fetch_ticker(symbol)
            
            if not ticker:
                return None
            
            # 解析货币对
            market = self._markets_cache.get(symbol, {})
            base = market.get('base', symbol.split('/')[0] if '/' in symbol else symbol)
            quote = market.get('quote', symbol.split('/')[1] if '/' in symbol else 'USDT')
            
            # 计算价差
            bid = ticker.get('bid', 0) or 0
            ask = ticker.get('ask', 0) or 0
            spread = 0
            if bid > 0 and ask > 0:
                spread = ((ask - bid) / bid) * 100
            
            # 计算24h涨跌幅
            change_24h = ticker.get('percentage', 0) or 0
            open_24h = ticker.get('open', 0) or 0
            close = ticker.get('last', 0) or ticker.get('close', 0) or 0
            change_amount = close - open_24h if open_24h else 0
            
            quote_data = CryptoRealtimeQuote(
                symbol=symbol,
                exchange=self.exchange_id,
                price=close,
                open_24h=open_24h,
                high_24h=ticker.get('high', 0) or 0,
                low_24h=ticker.get('low', 0) or 0,
                close=close,
                change_24h=change_24h,
                change_amount_24h=change_amount,
                volume_24h=ticker.get('baseVolume', 0) or 0,
                quote_volume_24h=ticker.get('quoteVolume', 0) or 0,
                bid=bid,
                ask=ask,
                spread=spread,
                timestamp=datetime.now(),
                base_currency=base,
                quote_currency=quote,
            )
            
            logger.debug(f"获取 {symbol} 实时行情成功: {close}")
            return quote_data
            
        except Exception as e:
            logger.error(f"获取实时行情失败 {symbol}: {e}")
            return None
    
    def get_multiple_quotes(self, symbols: List[str]) -> Dict[str, CryptoRealtimeQuote]:
        """
        批量获取多个交易对的行情
        
        Args:
            symbols: 交易对列表
            
        Returns:
            Dict[symbol, CryptoRealtimeQuote]
        """
        results = {}
        
        try:
            self._ensure_markets_loaded()
            
            # 标准化所有symbol
            normalized_symbols = [self._normalize_symbol(s) for s in symbols]
            
            # 检查是否支持批量获取
            if self.exchange.has.get('fetchTickers', False):
                try:
                    tickers = self.exchange.fetch_tickers(normalized_symbols)
                    for symbol, ticker in tickers.items():
                        quote = self._ticker_to_quote(symbol, ticker)
                        if quote:
                            results[symbol] = quote
                    return results
                except Exception as e:
                    logger.warning(f"批量获取行情失败，回退到单个获取: {e}")
            
            # 逐个获取
            for symbol in normalized_symbols:
                quote = self.get_realtime_quote(symbol)
                if quote:
                    results[symbol] = quote
                time.sleep(0.1)  # 速率限制
                
        except Exception as e:
            logger.error(f"批量获取行情失败: {e}")
        
        return results
    
    def _ticker_to_quote(self, symbol: str, ticker: Dict) -> Optional[CryptoRealtimeQuote]:
        """将 ticker 字典转换为 CryptoRealtimeQuote"""
        try:
            market = self._markets_cache.get(symbol, {})
            base = market.get('base', symbol.split('/')[0] if '/' in symbol else symbol)
            quote = market.get('quote', symbol.split('/')[1] if '/' in symbol else 'USDT')
            
            bid = ticker.get('bid', 0) or 0
            ask = ticker.get('ask', 0) or 0
            spread = 0
            if bid > 0 and ask > 0:
                spread = ((ask - bid) / bid) * 100
            
            open_24h = ticker.get('open', 0) or 0
            close = ticker.get('last', 0) or ticker.get('close', 0) or 0
            
            return CryptoRealtimeQuote(
                symbol=symbol,
                exchange=self.exchange_id,
                price=close,
                open_24h=open_24h,
                high_24h=ticker.get('high', 0) or 0,
                low_24h=ticker.get('low', 0) or 0,
                close=close,
                change_24h=ticker.get('percentage', 0) or 0,
                change_amount_24h=close - open_24h if open_24h else 0,
                volume_24h=ticker.get('baseVolume', 0) or 0,
                quote_volume_24h=ticker.get('quoteVolume', 0) or 0,
                bid=bid,
                ask=ask,
                spread=spread,
                timestamp=datetime.now(),
                base_currency=base,
                quote_currency=quote,
            )
        except Exception as e:
            logger.error(f"转换 ticker 失败 {symbol}: {e}")
            return None
    
    def get_orderbook(
        self,
        symbol: str,
        limit: int = 20
    ) -> Optional[Dict[str, Any]]:
        """
        获取订单簿深度
        
        Args:
            symbol: 交易对
            limit: 深度数量
            
        Returns:
            {
                'symbol': str,
                'bids': [[price, amount], ...],
                'asks': [[price, amount], ...],
                'timestamp': datetime,
                'bid_volume': float,  # 买盘总量
                'ask_volume': float,  # 卖盘总量
                'bid_ask_ratio': float,  # 买卖比
            }
        """
        try:
            self._ensure_markets_loaded()
            symbol = self._normalize_symbol(symbol)
            
            if symbol not in self._markets_cache:
                logger.warning(f"交易对 {symbol} 不存在")
                return None
            
            orderbook = self.exchange.fetch_order_book(symbol, limit)
            
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            bid_volume = sum(b[1] for b in bids) if bids else 0
            ask_volume = sum(a[1] for a in asks) if asks else 0
            bid_ask_ratio = bid_volume / ask_volume if ask_volume > 0 else 0
            
            return {
                'symbol': symbol,
                'bids': bids,
                'asks': asks,
                'timestamp': datetime.now(),
                'bid_volume': bid_volume,
                'ask_volume': ask_volume,
                'bid_ask_ratio': bid_ask_ratio,
            }
            
        except Exception as e:
            logger.error(f"获取订单簿失败 {symbol}: {e}")
            return None
    
    def get_historical_data(
        self,
        symbol: str,
        days: int = 30,
        timeframe: str = '1d'
    ) -> Optional[pd.DataFrame]:
        """
        获取历史数据（带标准列名，兼容原有分析器）
        
        Args:
            symbol: 交易对
            days: 天数
            timeframe: 时间周期
            
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        try:
            # 计算需要的K线数量
            timeframe_hours = {
                '1m': 1/60,
                '5m': 5/60,
                '15m': 0.25,
                '1h': 1,
                '4h': 4,
                '1d': 24,
            }
            
            hours_per_bar = timeframe_hours.get(timeframe, 24)
            limit = int((days * 24) / hours_per_bar) + 10  # 多取一些
            limit = min(limit, 1000)  # CCXT 限制
            
            kline = self.get_kline(symbol, timeframe=timeframe, limit=limit)
            
            if kline is None or kline.data.empty:
                return None
            
            df = kline.data.copy()
            df.reset_index(inplace=True)
            df.rename(columns={'timestamp': 'date'}, inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"获取历史数据失败 {symbol}: {e}")
            return None
    
    def search_symbols(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索交易对
        
        Args:
            keyword: 关键词 (如 "BTC", "SOL")
            limit: 返回数量
            
        Returns:
            [{'symbol': 'BTC/USDT', 'base': 'BTC', 'quote': 'USDT', ...}]
        """
        try:
            self._ensure_markets_loaded()
            
            keyword = keyword.upper()
            results = []
            
            for symbol, market in self._markets_cache.items():
                if keyword in symbol:
                    results.append({
                        'symbol': symbol,
                        'base': market.get('base', ''),
                        'quote': market.get('quote', ''),
                        'active': market.get('active', True),
                        'type': market.get('type', 'spot'),
                    })
                    
                    if len(results) >= limit:
                        break
            
            return results
            
        except Exception as e:
            logger.error(f"搜索交易对失败: {e}")
            return []
    
    def get_top_gainers(self, quote: str = 'USDT', limit: int = 10) -> List[CryptoRealtimeQuote]:
        """
        获取涨幅榜
        
        Args:
            quote: 计价货币
            limit: 返回数量
            
        Returns:
            按涨幅排序的行情列表
        """
        try:
            self._ensure_markets_loaded()
            
            # 获取所有 USDT 交易对
            usdt_symbols = [
                s for s in self._markets_cache.keys()
                if s.endswith(f'/{quote}') and self._markets_cache[s].get('active', True)
            ]
            
            # 限制数量避免请求过多
            usdt_symbols = usdt_symbols[:100]
            
            quotes = self.get_multiple_quotes(usdt_symbols)
            
            # 按涨幅排序
            sorted_quotes = sorted(
                quotes.values(),
                key=lambda x: x.change_24h,
                reverse=True
            )
            
            return sorted_quotes[:limit]
            
        except Exception as e:
            logger.error(f"获取涨幅榜失败: {e}")
            return []
    
    def get_top_losers(self, quote: str = 'USDT', limit: int = 10) -> List[CryptoRealtimeQuote]:
        """
        获取跌幅榜
        """
        try:
            self._ensure_markets_loaded()
            
            usdt_symbols = [
                s for s in self._markets_cache.keys()
                if s.endswith(f'/{quote}') and self._markets_cache[s].get('active', True)
            ]
            
            usdt_symbols = usdt_symbols[:100]
            quotes = self.get_multiple_quotes(usdt_symbols)
            
            sorted_quotes = sorted(
                quotes.values(),
                key=lambda x: x.change_24h,
                reverse=False
            )
            
            return sorted_quotes[:limit]
            
        except Exception as e:
            logger.error(f"获取跌幅榜失败: {e}")
            return []
    
    def get_top_volume(self, quote: str = 'USDT', limit: int = 10) -> List[CryptoRealtimeQuote]:
        """
        获取成交额榜
        """
        try:
            self._ensure_markets_loaded()
            
            usdt_symbols = [
                s for s in self._markets_cache.keys()
                if s.endswith(f'/{quote}') and self._markets_cache[s].get('active', True)
            ]
            
            usdt_symbols = usdt_symbols[:100]
            quotes = self.get_multiple_quotes(usdt_symbols)
            
            sorted_quotes = sorted(
                quotes.values(),
                key=lambda x: x.quote_volume_24h,
                reverse=True
            )
            
            return sorted_quotes[:limit]
            
        except Exception as e:
            logger.error(f"获取成交额榜失败: {e}")
            return []


# 便捷函数
def create_binance_fetcher(api_key: str = '', api_secret: str = '') -> CCXTFetcher:
    """创建 Binance 数据获取器"""
    return CCXTFetcher(exchange='binance', api_key=api_key, api_secret=api_secret)


def create_okx_fetcher(
    api_key: str = '',
    api_secret: str = '',
    passphrase: str = ''
) -> CCXTFetcher:
    """创建 OKX 数据获取器"""
    return CCXTFetcher(
        exchange='okx',
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase
    )
