# -*- coding: utf-8 -*-
"""
===================================
加密货币智能分析系统 - 趋势分析模块
===================================

职责：
1. 技术指标分析（MA均线、乖离率、趋势判断）
2. 链上指标分析（巨鲸、持有人、流动性）
3. 生成结构化分析数据供 AI 决策

核心指标：
- MA7/MA25/MA99 均线系统
- 乖离率 BIAS（阈值 10% 适配加密货币波动性）
- 24h 涨跌幅、成交量变化
- 链上数据（Holder、巨鲸活动）
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

import pandas as pd
import numpy as np

from config import get_config
from data_provider import (
    CCXTFetcher,
    GeckoTerminalFetcher,
    CryptoRealtimeQuote,
    CryptoKlineData,
    TokenInfo,
)

logger = logging.getLogger(__name__)


class TrendStatus(Enum):
    """趋势状态枚举"""
    BULLISH_ALIGNED = "多头排列"      # MA7 > MA25 > MA99
    BEARISH_ALIGNED = "空头排列"      # MA7 < MA25 < MA99
    SHORT_BULLISH = "短期看多"        # MA7 > MA25
    SHORT_BEARISH = "短期看空"        # MA7 < MA25
    CONSOLIDATING = "震荡整理"        # 均线交织
    INSUFFICIENT_DATA = "数据不足"


class BiasLevel(Enum):
    """乖离率级别"""
    OVERSOLD = "超卖区"           # < -10%
    LOW_RISK = "低风险买入区"      # -10% ~ 0%
    NORMAL = "正常区间"            # 0% ~ 5%
    CAUTION = "谨慎区"             # 5% ~ 10%
    HIGH_RISK = "高风险追高区"     # > 10%


class SignalType(Enum):
    """信号类型"""
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    HOLD = "持有"
    SELL = "卖出"
    STRONG_SELL = "强烈卖出"
    WAIT = "观望"


@dataclass
class TechnicalIndicators:
    """技术指标数据"""
    # 均线
    ma7: Optional[float] = None
    ma25: Optional[float] = None
    ma99: Optional[float] = None
    
    # 乖离率
    bias_7: Optional[float] = None      # (价格 - MA7) / MA7 * 100
    bias_25: Optional[float] = None
    
    # 趋势
    trend_status: TrendStatus = TrendStatus.INSUFFICIENT_DATA
    bias_level: BiasLevel = BiasLevel.NORMAL
    
    # 动量指标
    rsi_14: Optional[float] = None
    volume_change_24h: Optional[float] = None  # 成交量变化率 %
    
    # 支撑阻力
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None


@dataclass
class OnchainIndicators:
    """链上指标数据"""
    # 持有人
    holder_count: Optional[int] = None
    holder_change_24h: Optional[int] = None
    top10_pct: Optional[float] = None  # Top10 持仓占比
    
    # 巨鲸活动
    whale_buys_24h: int = 0
    whale_sells_24h: int = 0
    whale_net_flow: float = 0.0
    
    # 流动性
    liquidity_usd: float = 0.0
    liquidity_change_24h: Optional[float] = None
    
    # 交易活跃度
    txns_24h: int = 0
    buys_24h: int = 0
    sells_24h: int = 0
    buy_sell_ratio: float = 1.0


@dataclass
class CryptoAnalysisResult:
    """加密货币分析结果"""
    # 基本信息
    symbol: str
    name: str
    source: str  # 'exchange' 或 'onchain'
    exchange: Optional[str] = None
    chain: Optional[str] = None
    address: Optional[str] = None
    
    # 价格信息
    current_price: float = 0.0
    price_change_1h: float = 0.0
    price_change_24h: float = 0.0
    price_change_7d: float = 0.0
    
    # 市值信息
    market_cap: Optional[float] = None
    fdv: Optional[float] = None
    volume_24h: float = 0.0
    
    # 技术指标
    technical: TechnicalIndicators = field(default_factory=TechnicalIndicators)
    
    # 链上指标
    onchain: OnchainIndicators = field(default_factory=OnchainIndicators)
    
    # 综合信号
    signal: SignalType = SignalType.WAIT
    signal_strength: int = 0  # 0-100
    signal_reasons: List[str] = field(default_factory=list)
    
    # 风险提示
    risk_warnings: List[str] = field(default_factory=list)
    
    # 时间戳
    analysis_time: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 AI 分析）"""
        return {
            'symbol': self.symbol,
            'name': self.name,
            'source': self.source,
            'exchange': self.exchange,
            'chain': self.chain,
            'current_price': self.current_price,
            'price_change_1h': f"{self.price_change_1h:.2f}%",
            'price_change_24h': f"{self.price_change_24h:.2f}%",
            'price_change_7d': f"{self.price_change_7d:.2f}%",
            'market_cap': self.market_cap,
            'fdv': self.fdv,
            'volume_24h': self.volume_24h,
            'technical': {
                'ma7': self.technical.ma7,
                'ma25': self.technical.ma25,
                'ma99': self.technical.ma99,
                'bias_7': f"{self.technical.bias_7:.2f}%" if self.technical.bias_7 else None,
                'trend': self.technical.trend_status.value,
                'bias_level': self.technical.bias_level.value,
            },
            'onchain': {
                'holder_count': self.onchain.holder_count,
                'holder_change_24h': self.onchain.holder_change_24h,
                'top10_pct': f"{self.onchain.top10_pct:.1f}%" if self.onchain.top10_pct else None,
                'whale_buys_24h': self.onchain.whale_buys_24h,
                'whale_sells_24h': self.onchain.whale_sells_24h,
                'liquidity_usd': self.onchain.liquidity_usd,
                'buy_sell_ratio': f"{self.onchain.buy_sell_ratio:.2f}",
            },
            'signal': self.signal.value,
            'signal_strength': self.signal_strength,
            'signal_reasons': self.signal_reasons,
            'risk_warnings': self.risk_warnings,
        }
    
    def to_summary(self) -> str:
        """生成文字摘要"""
        lines = [
            f"📊 {self.symbol} ({self.name})",
            f"💰 价格: ${self.current_price:.8g}",
            f"📈 24h: {self.price_change_24h:+.2f}%",
            f"📉 趋势: {self.technical.trend_status.value}",
            f"🎯 信号: {self.signal.value} ({self.signal_strength}/100)",
        ]
        
        if self.technical.bias_7 is not None:
            lines.append(f"📐 乖离率: {self.technical.bias_7:.2f}% ({self.technical.bias_level.value})")
        
        if self.onchain.holder_count:
            lines.append(f"👥 持有人: {self.onchain.holder_count:,}")
        
        if self.signal_reasons:
            lines.append(f"💡 原因: {', '.join(self.signal_reasons[:3])}")
        
        if self.risk_warnings:
            lines.append(f"⚠️ 风险: {', '.join(self.risk_warnings[:3])}")
        
        return '\n'.join(lines)


class CryptoTrendAnalyzer:
    """
    加密货币趋势分析器
    
    核心交易理念：
    1. 趋势跟踪：MA7 > MA25 > MA99 为多头排列
    2. 不追高：乖离率 > 10% 严禁追高
    3. 回调买入：价格回踩均线时介入
    4. 链上验证：结合巨鲸动向和持有人变化
    """
    
    # 乖离率阈值（加密货币版，比股票放宽）
    BIAS_THRESHOLD_LOW = 5.0      # 低风险区上限
    BIAS_THRESHOLD_CAUTION = 10.0  # 谨慎区上限
    BIAS_THRESHOLD_HIGH = 15.0     # 高风险区
    
    # 巨鲸阈值
    WHALE_THRESHOLD_USD = 100000.0
    
    def __init__(
        self,
        ccxt_fetcher: Optional[CCXTFetcher] = None,
        gecko_fetcher: Optional[GeckoTerminalFetcher] = None,
    ):
        """
        初始化分析器
        
        Args:
            ccxt_fetcher: CCXT 数据获取器（交易所数据）
            gecko_fetcher: GeckoTerminal 数据获取器（链上数据）
        """
        self.config = get_config()
        
        # 初始化数据获取器
        if ccxt_fetcher:
            self.ccxt = ccxt_fetcher
        else:
            self.ccxt = CCXTFetcher(
                exchange=self.config.default_exchange,
                api_key=self.config.binance_api_key or '',
                api_secret=self.config.binance_api_secret or '',
            )
        
        if gecko_fetcher:
            self.gecko = gecko_fetcher
        else:
            self.gecko = GeckoTerminalFetcher(
                api_key=self.config.geckoterminal_api_key or ''
            )
        
        # 更新阈值
        self.BIAS_THRESHOLD_CAUTION = self.config.bias_threshold
        
        logger.info("CryptoTrendAnalyzer 初始化完成")
    
    def analyze(self, identifier: str) -> Optional[CryptoAnalysisResult]:
        """
        分析加密货币
        
        Args:
            identifier: 代币标识符
                - "BTC/USDT" - 交易所代币
                - "binance:ETH/USDT" - 指定交易所
                - "sol:address" - 链上代币
        
        Returns:
            CryptoAnalysisResult 或 None
        """
        try:
            # 解析标识符
            parsed = self.config.parse_crypto_identifier(identifier)
            
            if parsed['type'] == 'exchange':
                return self._analyze_exchange_token(
                    symbol=parsed['symbol'],
                    exchange=parsed['exchange']
                )
            else:
                return self._analyze_onchain_token(
                    chain=parsed['chain'],
                    address=parsed['address']
                )
                
        except Exception as e:
            logger.error(f"分析 {identifier} 失败: {e}")
            return None
    
    def _analyze_exchange_token(
        self,
        symbol: str,
        exchange: str = 'binance'
    ) -> Optional[CryptoAnalysisResult]:
        """分析交易所代币"""
        try:
            # 获取实时行情
            quote = self.ccxt.get_realtime_quote(symbol)
            if not quote:
                logger.warning(f"无法获取 {symbol} 行情")
                return None
            
            # 获取K线数据
            kline = self.ccxt.get_kline(
                symbol,
                timeframe=self.config.default_timeframe,
                limit=100
            )
            
            # 创建结果对象
            result = CryptoAnalysisResult(
                symbol=symbol,
                name=quote.base_currency,
                source='exchange',
                exchange=exchange,
                current_price=quote.price,
                price_change_24h=quote.change_24h,
                volume_24h=quote.quote_volume_24h,
            )
            
            # 计算技术指标
            if kline and kline.data is not None and len(kline.data) > 0:
                self._calculate_technical_indicators(result, kline)
            
            # 生成交易信号
            self._generate_signal(result)
            
            logger.info(f"分析 {symbol} 完成: {result.signal.value}")
            return result
            
        except Exception as e:
            logger.error(f"分析交易所代币 {symbol} 失败: {e}")
            return None
    
    def _analyze_onchain_token(
        self,
        chain: str,
        address: str
    ) -> Optional[CryptoAnalysisResult]:
        """分析链上代币"""
        try:
            # 获取代币信息
            token_info = self.gecko.get_token_with_pools(chain, address)
            if not token_info or not token_info.get('token'):
                logger.warning(f"无法获取 {chain}:{address} 信息")
                return None
            
            token: TokenInfo = token_info['token']
            main_pool = token_info.get('main_pool')
            
            # 创建结果对象
            result = CryptoAnalysisResult(
                symbol=token.symbol,
                name=token.name,
                source='onchain',
                chain=chain,
                address=address,
                current_price=token.price_usd,
                price_change_1h=token.price_change_1h,
                price_change_24h=token.price_change_24h,
                volume_24h=token.volume_24h,
                market_cap=token.market_cap,
                fdv=token.fdv,
            )
            
            # 填充链上指标
            result.onchain.liquidity_usd = token.liquidity_usd
            result.onchain.txns_24h = token.txns_24h
            result.onchain.buys_24h = token.buys_24h
            result.onchain.sells_24h = token.sells_24h
            
            if token.sells_24h > 0:
                result.onchain.buy_sell_ratio = token.buys_24h / token.sells_24h
            
            # 获取K线数据
            if main_pool:
                df = self.gecko.get_pool_ohlcv(
                    chain,
                    main_pool.address,
                    timeframe='hour',
                    limit=100,
                    aggregate=4  # 4小时K线
                )
                
                if df is not None and len(df) > 7:
                    # 创建临时 kline 对象用于指标计算
                    kline = CryptoKlineData(
                        symbol=token.symbol,
                        exchange='geckoterminal',
                        timeframe='4h',
                        data=df
                    )
                    self._calculate_technical_indicators(result, kline)
            
            # 链上风险检测
            self._check_onchain_risks(result, token)
            
            # 生成交易信号
            self._generate_signal(result)
            
            logger.info(f"分析 {token.symbol} 完成: {result.signal.value}")
            return result
            
        except Exception as e:
            logger.error(f"分析链上代币 {chain}:{address} 失败: {e}")
            return None
    
    def _calculate_technical_indicators(
        self,
        result: CryptoAnalysisResult,
        kline: CryptoKlineData
    ):
        """计算技术指标"""
        df = kline.data
        
        if len(df) < 7:
            return
        
        current_price = df['close'].iloc[-1]
        
        # 计算均线
        ma7 = df['close'].rolling(window=7).mean()
        result.technical.ma7 = ma7.iloc[-1]
        
        if len(df) >= 25:
            ma25 = df['close'].rolling(window=25).mean()
            result.technical.ma25 = ma25.iloc[-1]
        
        if len(df) >= 99:
            ma99 = df['close'].rolling(window=99).mean()
            result.technical.ma99 = ma99.iloc[-1]
        
        # 计算乖离率
        if result.technical.ma7 and result.technical.ma7 > 0:
            result.technical.bias_7 = (
                (current_price - result.technical.ma7) / result.technical.ma7
            ) * 100
        
        if result.technical.ma25 and result.technical.ma25 > 0:
            result.technical.bias_25 = (
                (current_price - result.technical.ma25) / result.technical.ma25
            ) * 100
        
        # 判断趋势状态
        result.technical.trend_status = self._determine_trend(
            result.technical.ma7,
            result.technical.ma25,
            result.technical.ma99
        )
        
        # 判断乖离率级别
        result.technical.bias_level = self._determine_bias_level(
            result.technical.bias_7
        )
        
        # 计算成交量变化
        if len(df) >= 2:
            vol_today = df['volume'].iloc[-1]
            vol_yesterday = df['volume'].iloc[-2]
            if vol_yesterday > 0:
                result.technical.volume_change_24h = (
                    (vol_today - vol_yesterday) / vol_yesterday
                ) * 100
        
        # 计算支撑阻力位
        if len(df) >= 20:
            result.technical.support_level = df['low'].iloc[-20:].min()
            result.technical.resistance_level = df['high'].iloc[-20:].max()
    
    def _determine_trend(
        self,
        ma7: Optional[float],
        ma25: Optional[float],
        ma99: Optional[float]
    ) -> TrendStatus:
        """判断趋势状态"""
        if ma7 is None:
            return TrendStatus.INSUFFICIENT_DATA
        
        if ma25 is not None and ma99 is not None:
            if ma7 > ma25 > ma99:
                return TrendStatus.BULLISH_ALIGNED
            elif ma7 < ma25 < ma99:
                return TrendStatus.BEARISH_ALIGNED
            else:
                return TrendStatus.CONSOLIDATING
        elif ma25 is not None:
            if ma7 > ma25:
                return TrendStatus.SHORT_BULLISH
            else:
                return TrendStatus.SHORT_BEARISH
        else:
            return TrendStatus.INSUFFICIENT_DATA
    
    def _determine_bias_level(self, bias: Optional[float]) -> BiasLevel:
        """判断乖离率级别"""
        if bias is None:
            return BiasLevel.NORMAL
        
        if bias < -self.BIAS_THRESHOLD_CAUTION:
            return BiasLevel.OVERSOLD
        elif bias < 0:
            return BiasLevel.LOW_RISK
        elif bias < self.BIAS_THRESHOLD_LOW:
            return BiasLevel.NORMAL
        elif bias < self.BIAS_THRESHOLD_CAUTION:
            return BiasLevel.CAUTION
        else:
            return BiasLevel.HIGH_RISK
    
    def _check_onchain_risks(
        self,
        result: CryptoAnalysisResult,
        token: TokenInfo
    ):
        """检查链上风险"""
        warnings = []
        
        # 流动性检查
        if token.liquidity_usd < 10000:
            warnings.append("流动性极低 (<$10K)")
        elif token.liquidity_usd < 50000:
            warnings.append("流动性较低 (<$50K)")
        
        # FDV 检查
        if token.fdv and token.market_cap:
            fdv_ratio = token.fdv / token.market_cap if token.market_cap > 0 else 0
            if fdv_ratio > 10:
                warnings.append(f"FDV/市值比过高 ({fdv_ratio:.1f}x)")
        
        # 买卖比检查
        if token.sells_24h > 0:
            ratio = token.buys_24h / token.sells_24h
            if ratio < 0.5:
                warnings.append(f"卖盘压力大 (买卖比 {ratio:.2f})")
        
        # 新币检查
        if token.pool_created_at:
            age_hours = (datetime.now() - token.pool_created_at).total_seconds() / 3600
            if age_hours < 24:
                warnings.append("新币风险 (<24h)")
            elif age_hours < 72:
                warnings.append("新币 (<3天)")
        
        result.risk_warnings = warnings
    
    def _generate_signal(self, result: CryptoAnalysisResult):
        """生成交易信号"""
        score = 50  # 基础分
        reasons = []
        
        tech = result.technical
        onchain = result.onchain
        
        # === 趋势评分 ===
        if tech.trend_status == TrendStatus.BULLISH_ALIGNED:
            score += 20
            reasons.append("多头排列")
        elif tech.trend_status == TrendStatus.BEARISH_ALIGNED:
            score -= 20
            reasons.append("空头排列")
        elif tech.trend_status == TrendStatus.SHORT_BULLISH:
            score += 10
            reasons.append("短期看多")
        elif tech.trend_status == TrendStatus.SHORT_BEARISH:
            score -= 10
            reasons.append("短期看空")
        
        # === 乖离率评分 ===
        if tech.bias_level == BiasLevel.OVERSOLD:
            score += 15
            reasons.append("超卖区")
        elif tech.bias_level == BiasLevel.LOW_RISK:
            score += 10
            reasons.append("低风险区")
        elif tech.bias_level == BiasLevel.CAUTION:
            score -= 10
            reasons.append("乖离率偏高")
        elif tech.bias_level == BiasLevel.HIGH_RISK:
            score -= 20
            reasons.append("严禁追高")
        
        # === 价格动量评分 ===
        if result.price_change_24h > 20:
            score -= 10
            reasons.append("24h涨幅过大")
        elif result.price_change_24h > 10:
            score -= 5
        elif result.price_change_24h < -20:
            score += 5
            reasons.append("大幅回调")
        elif result.price_change_24h < -10:
            score += 3
        
        # === 成交量评分 ===
        if tech.volume_change_24h:
            if tech.volume_change_24h > 100:
                score += 5
                reasons.append("放量")
            elif tech.volume_change_24h < -50:
                score -= 5
                reasons.append("缩量")
        
        # === 链上指标评分 ===
        if onchain.buy_sell_ratio > 1.5:
            score += 10
            reasons.append("买盘强势")
        elif onchain.buy_sell_ratio < 0.5:
            score -= 10
            reasons.append("卖盘强势")
        
        if onchain.holder_change_24h:
            if onchain.holder_change_24h > 100:
                score += 5
                reasons.append("持有人增加")
            elif onchain.holder_change_24h < -100:
                score -= 5
                reasons.append("持有人减少")
        
        # === 风险扣分 ===
        score -= len(result.risk_warnings) * 5
        
        # 限制范围
        score = max(0, min(100, score))
        
        # 确定信号
        if score >= 80:
            signal = SignalType.STRONG_BUY
        elif score >= 65:
            signal = SignalType.BUY
        elif score >= 45:
            signal = SignalType.HOLD
        elif score >= 30:
            signal = SignalType.SELL
        else:
            signal = SignalType.STRONG_SELL
        
        # 如果风险警告过多，降级信号
        if len(result.risk_warnings) >= 3:
            if signal == SignalType.STRONG_BUY:
                signal = SignalType.BUY
            elif signal == SignalType.BUY:
                signal = SignalType.HOLD
            reasons.append("多重风险")
        
        result.signal = signal
        result.signal_strength = score
        result.signal_reasons = reasons
    
    def analyze_batch(
        self,
        identifiers: List[str]
    ) -> List[CryptoAnalysisResult]:
        """
        批量分析多个代币
        
        Args:
            identifiers: 代币标识符列表
            
        Returns:
            分析结果列表
        """
        results = []
        
        for identifier in identifiers:
            try:
                result = self.analyze(identifier)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"批量分析 {identifier} 失败: {e}")
                continue
        
        # 按信号强度排序
        results.sort(key=lambda x: x.signal_strength, reverse=True)
        
        return results
    
    def get_summary_stats(
        self,
        results: List[CryptoAnalysisResult]
    ) -> Dict[str, Any]:
        """获取分析汇总统计"""
        if not results:
            return {}
        
        # 信号分布
        signal_counts = {}
        for r in results:
            signal = r.signal.value
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
        
        # 趋势分布
        trend_counts = {}
        for r in results:
            trend = r.technical.trend_status.value
            trend_counts[trend] = trend_counts.get(trend, 0) + 1
        
        # 平均指标
        avg_bias = np.mean([
            r.technical.bias_7 for r in results 
            if r.technical.bias_7 is not None
        ]) if results else 0
        
        avg_change_24h = np.mean([r.price_change_24h for r in results])
        
        return {
            'total_count': len(results),
            'signal_distribution': signal_counts,
            'trend_distribution': trend_counts,
            'average_bias': f"{avg_bias:.2f}%",
            'average_change_24h': f"{avg_change_24h:.2f}%",
            'top_performers': [
                {'symbol': r.symbol, 'change': f"{r.price_change_24h:+.2f}%"}
                for r in sorted(results, key=lambda x: x.price_change_24h, reverse=True)[:5]
            ],
            'worst_performers': [
                {'symbol': r.symbol, 'change': f"{r.price_change_24h:+.2f}%"}
                for r in sorted(results, key=lambda x: x.price_change_24h)[:5]
            ],
        }


# 便捷函数
def create_crypto_analyzer() -> CryptoTrendAnalyzer:
    """创建加密货币分析器"""
    return CryptoTrendAnalyzer()


if __name__ == "__main__":
    # 测试分析器
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    analyzer = create_crypto_analyzer()
    
    # 测试交易所代币
    print("=== 测试交易所代币分析 ===")
    result = analyzer.analyze("BTC/USDT")
    if result:
        print(result.to_summary())
        print()
    
    # 测试批量分析
    print("=== 测试批量分析 ===")
    tokens = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    results = analyzer.analyze_batch(tokens)
    
    for r in results:
        print(f"{r.symbol}: {r.signal.value} ({r.signal_strength}/100)")
    
    # 汇总统计
    print("\n=== 汇总统计 ===")
    stats = analyzer.get_summary_stats(results)
    print(stats)
