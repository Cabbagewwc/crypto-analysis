# -*- coding: utf-8 -*-
"""
===================================
数据源策略层 - 包初始化
===================================

本包实现策略模式管理多个数据源，实现：
1. 统一的数据获取接口
2. 自动故障切换
3. 防封禁流控策略

=== 加密货币数据源 ===
1. CCXTFetcher - 交易所现货数据 (Binance, OKX 等)
2. GeckoTerminalFetcher - 链上 DEX 数据 (100+ 条链)

=== A股数据源 (保留兼容) ===
1. EfinanceFetcher (Priority 0) - 最高优先级，来自 efinance 库
2. AkshareFetcher (Priority 1) - 来自 akshare 库
3. TushareFetcher (Priority 2) - 来自 tushare 库
4. BaostockFetcher (Priority 3) - 来自 baostock 库
5. YfinanceFetcher (Priority 4) - 来自 yfinance 库
"""

from .base import BaseFetcher, DataFetcherManager

# 加密货币数据源
from .ccxt_fetcher import (
    CCXTFetcher,
    CryptoRealtimeQuote,
    CryptoKlineData,
    create_binance_fetcher,
    create_okx_fetcher,
)
from .geckoterminal_fetcher import (
    GeckoTerminalFetcher,
    TokenInfo,
    PoolInfo,
    OnchainMetrics,
    create_geckoterminal_fetcher,
)

# A股数据源 (保留兼容)
from .efinance_fetcher import EfinanceFetcher
from .akshare_fetcher import AkshareFetcher
from .tushare_fetcher import TushareFetcher
from .baostock_fetcher import BaostockFetcher
from .yfinance_fetcher import YfinanceFetcher

__all__ = [
    # 基础类
    'BaseFetcher',
    'DataFetcherManager',
    
    # 加密货币数据源
    'CCXTFetcher',
    'CryptoRealtimeQuote',
    'CryptoKlineData',
    'create_binance_fetcher',
    'create_okx_fetcher',
    'GeckoTerminalFetcher',
    'TokenInfo',
    'PoolInfo',
    'OnchainMetrics',
    'create_geckoterminal_fetcher',
    
    # A股数据源
    'EfinanceFetcher',
    'AkshareFetcher',
    'TushareFetcher',
    'BaostockFetcher',
    'YfinanceFetcher',
]
