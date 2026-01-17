# -*- coding: utf-8 -*-
"""
===================================
加密货币市场复盘分析模块
===================================

职责：
1. 获取加密市场整体数据（BTC主导率、总市值、恐慌指数等）
2. 获取热门代币排行榜
3. 搜索市场新闻形成复盘情报
4. 使用大模型生成每日市场复盘报告
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests
import pandas as pd

from config import get_config
from data_provider import CCXTFetcher, GeckoTerminalFetcher, CryptoRealtimeQuote, TokenInfo

logger = logging.getLogger(__name__)


@dataclass
class MarketMetric:
    """市场指标数据"""
    name: str                        # 指标名称
    value: float                     # 当前值
    change_24h: Optional[float] = None  # 24h变化
    unit: str = ""                   # 单位


@dataclass
class CryptoMarketOverview:
    """加密货币市场概览"""
    date: str                               # 日期
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 总体市场指标
    total_market_cap: float = 0.0           # 总市值 (USD)
    total_market_cap_change_24h: float = 0.0
    total_volume_24h: float = 0.0           # 24h总成交量
    
    # BTC 相关
    btc_price: float = 0.0
    btc_change_24h: float = 0.0
    btc_dominance: float = 0.0              # BTC 主导率 (%)
    
    # ETH 相关
    eth_price: float = 0.0
    eth_change_24h: float = 0.0
    eth_dominance: float = 0.0
    
    # 市场情绪
    fear_greed_index: int = 50              # 恐慌贪婪指数 (0-100)
    fear_greed_label: str = "中性"           # 恐慌/贪婪/极度贪婪等
    
    # 涨跌统计
    gainers_count: int = 0
    losers_count: int = 0
    
    # 排行榜
    top_gainers: List[Dict] = field(default_factory=list)     # 涨幅榜
    top_losers: List[Dict] = field(default_factory=list)      # 跌幅榜
    top_volume: List[Dict] = field(default_factory=list)      # 成交额榜
    trending_tokens: List[Dict] = field(default_factory=list)  # 热门代币
    
    # 板块/概念表现
    sector_performance: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'date': self.date,
            'total_market_cap': self.total_market_cap,
            'total_market_cap_change_24h': f"{self.total_market_cap_change_24h:+.2f}%",
            'total_volume_24h': self.total_volume_24h,
            'btc_price': self.btc_price,
            'btc_change_24h': f"{self.btc_change_24h:+.2f}%",
            'btc_dominance': f"{self.btc_dominance:.1f}%",
            'eth_price': self.eth_price,
            'eth_change_24h': f"{self.eth_change_24h:+.2f}%",
            'fear_greed_index': self.fear_greed_index,
            'fear_greed_label': self.fear_greed_label,
            'gainers_count': self.gainers_count,
            'losers_count': self.losers_count,
        }


class CryptoMarketAnalyzer:
    """
    加密货币市场复盘分析器
    
    功能：
    1. 获取市场整体指标（总市值、BTC主导率、恐慌指数等）
    2. 获取涨跌榜、成交额榜
    3. 获取链上热门代币
    4. 搜索市场新闻
    5. 生成市场复盘报告
    """
    
    # CoinGecko API (免费版)
    COINGECKO_API = "https://api.coingecko.com/api/v3"
    
    # 恐慌贪婪指数 API
    FEAR_GREED_API = "https://api.alternative.me/fng/"
    
    # 概念板块
    CRYPTO_SECTORS = {
        'meme': 'Meme币',
        'ai': 'AI概念',
        'defi': 'DeFi',
        'layer1': 'Layer1公链',
        'layer2': 'Layer2',
        'gamefi': 'GameFi',
        'rwa': 'RWA',
    }
    
    def __init__(
        self,
        ccxt_fetcher: Optional[CCXTFetcher] = None,
        gecko_fetcher: Optional[GeckoTerminalFetcher] = None,
        search_service=None,
        analyzer=None
    ):
        """
        初始化市场分析器
        
        Args:
            ccxt_fetcher: CCXT 数据获取器
            gecko_fetcher: GeckoTerminal 数据获取器
            search_service: 搜索服务实例
            analyzer: AI 分析器实例
        """
        self.config = get_config()
        self.search_service = search_service
        self.analyzer = analyzer
        
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
        
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'CryptoAnalyzer/1.0',
        })
        
        logger.info("CryptoMarketAnalyzer 初始化完成")
    
    def get_market_overview(self) -> CryptoMarketOverview:
        """
        获取市场概览数据
        
        Returns:
            CryptoMarketOverview: 市场概览数据对象
        """
        today = datetime.now().strftime('%Y-%m-%d')
        overview = CryptoMarketOverview(date=today)
        
        # 1. 获取全球市场数据
        self._get_global_market_data(overview)
        
        # 2. 获取 BTC/ETH 行情
        self._get_major_coins(overview)
        
        # 3. 获取恐慌贪婪指数
        self._get_fear_greed_index(overview)
        
        # 4. 获取涨跌榜
        self._get_rankings(overview)
        
        # 5. 获取热门代币
        self._get_trending_tokens(overview)
        
        return overview
    
    def _get_global_market_data(self, overview: CryptoMarketOverview):
        """获取全球市场数据"""
        try:
            logger.info("[市场] 获取全球市场数据...")
            
            url = f"{self.COINGECKO_API}/global"
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json().get('data', {})
                
                overview.total_market_cap = data.get('total_market_cap', {}).get('usd', 0)
                overview.total_volume_24h = data.get('total_volume', {}).get('usd', 0)
                
                market_cap_change = data.get('market_cap_change_percentage_24h_usd', 0)
                overview.total_market_cap_change_24h = market_cap_change or 0
                
                overview.btc_dominance = data.get('market_cap_percentage', {}).get('btc', 0)
                overview.eth_dominance = data.get('market_cap_percentage', {}).get('eth', 0)
                
                logger.info(f"[市场] 总市值: ${overview.total_market_cap/1e12:.2f}T, "
                          f"BTC主导率: {overview.btc_dominance:.1f}%")
            else:
                logger.warning(f"[市场] CoinGecko API 响应异常: {response.status_code}")
                
        except Exception as e:
            logger.error(f"[市场] 获取全球市场数据失败: {e}")
    
    def _get_major_coins(self, overview: CryptoMarketOverview):
        """获取 BTC/ETH 行情"""
        try:
            logger.info("[市场] 获取 BTC/ETH 行情...")
            
            # 使用 CCXT 获取
            btc_quote = self.ccxt.get_realtime_quote('BTC/USDT')
            if btc_quote:
                overview.btc_price = btc_quote.price
                overview.btc_change_24h = btc_quote.change_24h
                logger.info(f"[市场] BTC: ${overview.btc_price:.2f} ({overview.btc_change_24h:+.2f}%)")
            
            eth_quote = self.ccxt.get_realtime_quote('ETH/USDT')
            if eth_quote:
                overview.eth_price = eth_quote.price
                overview.eth_change_24h = eth_quote.change_24h
                logger.info(f"[市场] ETH: ${overview.eth_price:.2f} ({overview.eth_change_24h:+.2f}%)")
                
        except Exception as e:
            logger.error(f"[市场] 获取 BTC/ETH 行情失败: {e}")
    
    def _get_fear_greed_index(self, overview: CryptoMarketOverview):
        """获取恐慌贪婪指数"""
        try:
            logger.info("[市场] 获取恐慌贪婪指数...")
            
            response = self.session.get(self.FEAR_GREED_API, timeout=30)
            
            if response.status_code == 200:
                data = response.json().get('data', [])
                if data:
                    latest = data[0]
                    overview.fear_greed_index = int(latest.get('value', 50))
                    overview.fear_greed_label = self._get_fear_greed_label(overview.fear_greed_index)
                    logger.info(f"[市场] 恐慌贪婪指数: {overview.fear_greed_index} ({overview.fear_greed_label})")
                    
        except Exception as e:
            logger.error(f"[市场] 获取恐慌贪婪指数失败: {e}")
    
    def _get_fear_greed_label(self, value: int) -> str:
        """根据数值返回恐慌贪婪标签"""
        if value <= 20:
            return "极度恐慌"
        elif value <= 40:
            return "恐慌"
        elif value <= 60:
            return "中性"
        elif value <= 80:
            return "贪婪"
        else:
            return "极度贪婪"
    
    def _get_rankings(self, overview: CryptoMarketOverview):
        """获取涨跌榜"""
        try:
            logger.info("[市场] 获取涨跌榜...")
            
            # 使用 CCXT 获取
            gainers = self.ccxt.get_top_gainers(limit=10)
            losers = self.ccxt.get_top_losers(limit=10)
            volume = self.ccxt.get_top_volume(limit=10)
            
            overview.top_gainers = [
                {
                    'symbol': g.symbol,
                    'price': g.price,
                    'change_24h': g.change_24h,
                }
                for g in gainers
            ]
            
            overview.top_losers = [
                {
                    'symbol': l.symbol,
                    'price': l.price,
                    'change_24h': l.change_24h,
                }
                for l in losers
            ]
            
            overview.top_volume = [
                {
                    'symbol': v.symbol,
                    'price': v.price,
                    'volume_24h': v.quote_volume_24h,
                }
                for v in volume
            ]
            
            # 统计涨跌家数
            overview.gainers_count = len([g for g in gainers if g.change_24h > 0])
            overview.losers_count = len([l for l in losers if l.change_24h < 0])
            
            logger.info(f"[市场] 涨幅榜前3: {[g['symbol'] for g in overview.top_gainers[:3]]}")
            logger.info(f"[市场] 跌幅榜前3: {[l['symbol'] for l in overview.top_losers[:3]]}")
            
        except Exception as e:
            logger.error(f"[市场] 获取涨跌榜失败: {e}")
    
    def _get_trending_tokens(self, overview: CryptoMarketOverview):
        """获取热门代币（链上）"""
        try:
            logger.info("[市场] 获取链上热门代币...")
            
            # 获取各链热门
            for chain in self.config.preferred_chains[:3]:
                tokens = self.gecko.get_trending_tokens(chain, limit=5)
                
                for token in tokens:
                    overview.trending_tokens.append({
                        'chain': chain,
                        'symbol': token.symbol,
                        'name': token.name,
                        'price': token.price_usd,
                        'change_24h': token.price_change_24h,
                        'volume_24h': token.volume_24h,
                        'liquidity': token.liquidity_usd,
                    })
            
            logger.info(f"[市场] 获取到 {len(overview.trending_tokens)} 个链上热门代币")
            
        except Exception as e:
            logger.error(f"[市场] 获取链上热门代币失败: {e}")
    
    def search_market_news(self) -> List[Dict]:
        """
        搜索市场新闻
        
        Returns:
            新闻列表
        """
        if not self.search_service:
            logger.warning("[市场] 搜索服务未配置，跳过新闻搜索")
            return []
        
        all_news = []
        today = datetime.now()
        date_str = today.strftime('%Y-%m')
        
        # 多维度搜索
        search_queries = [
            f"crypto market analysis {date_str}",
            f"bitcoin BTC news today",
            f"cryptocurrency whale activity",
            f"DeFi crypto trending",
        ]
        
        try:
            logger.info("[市场] 开始搜索市场新闻...")
            
            for query in search_queries:
                # 使用 search_stock_news 方法
                response = self.search_service.search_stock_news(
                    stock_code="crypto",
                    stock_name="加密货币",
                    max_results=3,
                    focus_keywords=query.split()
                )
                if response and response.results:
                    all_news.extend(response.results)
                    logger.info(f"[市场] 搜索 '{query}' 获取 {len(response.results)} 条结果")
            
            logger.info(f"[市场] 共获取 {len(all_news)} 条市场新闻")
            
        except Exception as e:
            logger.error(f"[市场] 搜索市场新闻失败: {e}")
        
        return all_news
    
    def generate_market_review(self, overview: CryptoMarketOverview, news: List) -> str:
        """
        使用大模型生成市场复盘报告
        
        Args:
            overview: 市场概览数据
            news: 市场新闻列表
            
        Returns:
            市场复盘报告文本
        """
        if not self.analyzer or not self.analyzer.is_available():
            logger.warning("[市场] AI分析器未配置或不可用，使用模板生成报告")
            return self._generate_template_review(overview, news)
        
        # 构建 Prompt
        prompt = self._build_review_prompt(overview, news)
        
        try:
            logger.info("[市场] 调用大模型生成复盘报告...")
            
            generation_config = {
                'temperature': 0.7,
                'max_output_tokens': 2048,
            }
            
            # 根据 analyzer 使用的 API 类型调用
            if self.analyzer._use_openai:
                review = self.analyzer._call_openai_api(prompt, generation_config)
            else:
                response = self.analyzer._model.generate_content(
                    prompt,
                    generation_config=generation_config,
                )
                review = response.text.strip() if response and response.text else None
            
            if review:
                logger.info(f"[市场] 复盘报告生成成功，长度: {len(review)} 字符")
                return review
            else:
                logger.warning("[市场] 大模型返回为空")
                return self._generate_template_review(overview, news)
                
        except Exception as e:
            logger.error(f"[市场] 大模型生成复盘报告失败: {e}")
            return self._generate_template_review(overview, news)
    
    def _build_review_prompt(self, overview: CryptoMarketOverview, news: List) -> str:
        """构建复盘报告 Prompt"""
        # 涨幅榜
        gainers_text = "\n".join([
            f"- {g['symbol']}: ${g['price']:.4g} ({g['change_24h']:+.2f}%)"
            for g in overview.top_gainers[:5]
        ])
        
        # 跌幅榜
        losers_text = "\n".join([
            f"- {l['symbol']}: ${l['price']:.4g} ({l['change_24h']:+.2f}%)"
            for l in overview.top_losers[:5]
        ])
        
        # 热门链上代币
        trending_text = "\n".join([
            f"- [{t['chain'].upper()}] {t['symbol']}: ${t['price']:.4g} ({t['change_24h']:+.2f}%)"
            for t in overview.trending_tokens[:5]
        ])
        
        # 新闻信息
        news_text = ""
        for i, n in enumerate(news[:6], 1):
            if hasattr(n, 'title'):
                title = n.title[:50] if n.title else ''
                snippet = n.snippet[:100] if n.snippet else ''
            else:
                title = n.get('title', '')[:50]
                snippet = n.get('snippet', '')[:100]
            news_text += f"{i}. {title}\n   {snippet}\n"
        
        prompt = f"""你是一位专业的加密货币市场分析师，请根据以下数据生成一份简洁的市场复盘报告。

【重要】输出要求：
- 必须输出纯 Markdown 文本格式
- 禁止输出 JSON 格式
- 禁止输出代码块
- emoji 仅在标题处少量使用

---

# 今日市场数据

## 日期
{overview.date}

## 市场概况
- 总市值: ${overview.total_market_cap/1e12:.2f}T ({overview.total_market_cap_change_24h:+.2f}%)
- 24h成交量: ${overview.total_volume_24h/1e9:.2f}B
- BTC主导率: {overview.btc_dominance:.1f}%
- 恐慌贪婪指数: {overview.fear_greed_index} ({overview.fear_greed_label})

## 主流币行情
- BTC: ${overview.btc_price:.2f} ({overview.btc_change_24h:+.2f}%)
- ETH: ${overview.eth_price:.2f} ({overview.eth_change_24h:+.2f}%)

## 涨幅榜
{gainers_text}

## 跌幅榜
{losers_text}

## 链上热门代币
{trending_text}

## 市场新闻
{news_text if news_text else "暂无相关新闻"}

---

# 输出格式模板（请严格按此格式输出）

## 🚀 {overview.date} 加密货币市场复盘

### 一、市场总结
（2-3句话概括今日市场整体表现，包括总市值变化、BTC走势、市场情绪）

### 二、主流币点评
（分析 BTC、ETH 走势特点及原因）

### 三、热门板块
（分析今日涨幅较大的代币类型/概念）

### 四、链上动态
（分析链上热门代币，哪条链比较活跃）

### 五、市场情绪
（解读恐慌贪婪指数，结合新闻分析市场情绪）

### 六、后市展望
（给出短期市场预判）

### 七、风险提示
（需要关注的风险点）

---

请直接输出复盘报告内容，不要输出其他说明文字。
"""
        return prompt
    
    def _generate_template_review(self, overview: CryptoMarketOverview, news: List) -> str:
        """使用模板生成复盘报告"""
        
        # 判断市场走势
        if overview.btc_change_24h > 5:
            market_mood = "强势上涨"
        elif overview.btc_change_24h > 0:
            market_mood = "小幅上涨"
        elif overview.btc_change_24h > -5:
            market_mood = "小幅下跌"
        else:
            market_mood = "明显下跌"
        
        # 涨幅榜
        gainers_text = "\n".join([
            f"| {g['symbol']} | ${g['price']:.4g} | {g['change_24h']:+.2f}% |"
            for g in overview.top_gainers[:5]
        ])
        
        # 热门链上代币
        trending_text = "\n".join([
            f"- [{t['chain'].upper()}] {t['symbol']}: ${t['price']:.4g} ({t['change_24h']:+.2f}%)"
            for t in overview.trending_tokens[:5]
        ])
        
        report = f"""## 🚀 {overview.date} 加密货币市场复盘

### 一、市场总结
今日加密货币市场整体呈现**{market_mood}**态势。总市值 ${overview.total_market_cap/1e12:.2f}T，24h变化 {overview.total_market_cap_change_24h:+.2f}%。

### 二、主要指标
| 指标 | 数值 |
|------|------|
| BTC 价格 | ${overview.btc_price:.2f} ({overview.btc_change_24h:+.2f}%) |
| ETH 价格 | ${overview.eth_price:.2f} ({overview.eth_change_24h:+.2f}%) |
| BTC 主导率 | {overview.btc_dominance:.1f}% |
| 恐慌贪婪指数 | {overview.fear_greed_index} ({overview.fear_greed_label}) |
| 24h成交量 | ${overview.total_volume_24h/1e9:.2f}B |

### 三、涨幅榜
| 代币 | 价格 | 24h涨跌 |
|------|------|---------|
{gainers_text}

### 四、链上热门代币
{trending_text if trending_text else "暂无数据"}

### 五、风险提示
加密货币市场波动剧烈，投资需谨慎。以上数据仅供参考，不构成投资建议。

---
*复盘时间: {datetime.now().strftime('%H:%M')}*
"""
        return report
    
    def run_daily_review(self) -> str:
        """
        执行每日市场复盘流程
        
        Returns:
            复盘报告文本
        """
        logger.info("========== 开始加密货币市场复盘分析 ==========")
        
        # 1. 获取市场概览
        overview = self.get_market_overview()
        
        # 2. 搜索市场新闻
        news = self.search_market_news()
        
        # 3. 生成复盘报告
        report = self.generate_market_review(overview, news)
        
        logger.info("========== 加密货币市场复盘分析完成 ==========")
        
        return report


# 便捷函数
def create_crypto_market_analyzer() -> CryptoMarketAnalyzer:
    """创建加密货币市场分析器"""
    return CryptoMarketAnalyzer()


# 测试入口
if __name__ == "__main__":
    import sys
    sys.path.insert(0, '.')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    )
    
    analyzer = CryptoMarketAnalyzer()
    
    # 测试获取市场概览
    overview = analyzer.get_market_overview()
    print(f"\n=== 市场概览 ===")
    print(f"日期: {overview.date}")
    print(f"总市值: ${overview.total_market_cap/1e12:.2f}T")
    print(f"BTC: ${overview.btc_price:.2f} ({overview.btc_change_24h:+.2f}%)")
    print(f"ETH: ${overview.eth_price:.2f} ({overview.eth_change_24h:+.2f}%)")
    print(f"BTC主导率: {overview.btc_dominance:.1f}%")
    print(f"恐慌贪婪: {overview.fear_greed_index} ({overview.fear_greed_label})")
    
    # 测试生成模板报告
    report = analyzer._generate_template_review(overview, [])
    print(f"\n=== 复盘报告 ===")
    print(report)
