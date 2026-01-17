"""
GeckoTerminal 数据获取模块 - 链上 DEX 代币数据

支持的链：
- Solana (sol)
- Ethereum (eth)
- BNB Chain (bsc)
- Base (base)
- Arbitrum (arbitrum)
- 等 100+ 条链

功能：
- DEX 代币 OHLCV 数据
- 代币信息 (Holder、流动性、FDV)
- 新代币发现
- 热门代币排行
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import time

import requests
import pandas as pd

from .base import BaseFetcher

logger = logging.getLogger(__name__)


@dataclass
class TokenInfo:
    """代币基本信息"""
    address: str                    # 合约地址
    symbol: str                     # 代币符号
    name: str                       # 代币名称
    chain: str                      # 链名称
    decimals: int = 18              # 精度
    
    # 价格信息
    price_usd: float = 0.0          # 当前价格 (USD)
    price_change_24h: float = 0.0   # 24h涨跌幅 (%)
    price_change_1h: float = 0.0    # 1h涨跌幅 (%)
    
    # 交易信息
    volume_24h: float = 0.0         # 24h成交量 (USD)
    txns_24h: int = 0               # 24h交易次数
    buys_24h: int = 0               # 24h买入次数
    sells_24h: int = 0              # 24h卖出次数
    
    # 市值信息
    market_cap: Optional[float] = None
    fdv: Optional[float] = None     # 完全稀释市值
    
    # 流动性信息
    liquidity_usd: float = 0.0      # 流动性 (USD)
    
    # 时间信息
    created_at: Optional[datetime] = None
    pool_created_at: Optional[datetime] = None


@dataclass
class PoolInfo:
    """交易池信息"""
    address: str                    # 池地址
    chain: str                      # 链名称
    dex: str                        # DEX 名称 (raydium, uniswap等)
    
    # 代币对
    base_token: TokenInfo
    quote_token: TokenInfo
    
    # 价格和交易
    price_usd: float = 0.0
    price_native: float = 0.0       # 以原生代币计价
    price_change_24h: float = 0.0
    
    volume_24h: float = 0.0
    txns_24h: int = 0
    
    # 流动性
    reserve_usd: float = 0.0
    liquidity_usd: float = 0.0


@dataclass
class OnchainMetrics:
    """链上指标"""
    token_address: str
    chain: str
    
    # 持有人信息
    holder_count: Optional[int] = None
    holder_change_24h: Optional[int] = None
    
    # Top 持有人分析
    top10_holders_pct: Optional[float] = None  # Top10持仓占比
    top50_holders_pct: Optional[float] = None
    
    # 巨鲸活动
    whale_buys_24h: int = 0
    whale_sells_24h: int = 0
    whale_net_flow_usd: float = 0.0
    
    # 安全检测
    is_honeypot: Optional[bool] = None
    is_mintable: Optional[bool] = None
    has_blacklist: Optional[bool] = None
    contract_verified: Optional[bool] = None
    
    # 风险评分 (0-100, 越低越安全)
    risk_score: Optional[int] = None


class GeckoTerminalFetcher(BaseFetcher):
    """
    GeckoTerminal API 数据获取器
    
    支持 100+ 条链的 DEX 数据
    
    使用示例：
        fetcher = GeckoTerminalFetcher()
        
        # 获取代币信息
        token = fetcher.get_token_info('sol', 'token_address')
        
        # 搜索代币
        results = fetcher.search_tokens('BONK')
        
        # 获取热门代币
        trending = fetcher.get_trending_tokens('sol')
    """
    
    BASE_URL = "https://api.geckoterminal.com/api/v2"
    
    # 支持的链ID映射
    CHAIN_MAP = {
        # 主要链
        'sol': 'solana',
        'solana': 'solana',
        'eth': 'eth',
        'ethereum': 'eth',
        'bsc': 'bsc',
        'bnb': 'bsc',
        'base': 'base',
        'arbitrum': 'arbitrum',
        'polygon': 'polygon-pos',
        'avalanche': 'avax',
        'optimism': 'optimism',
        
        # 其他链
        'fantom': 'ftm',
        'cronos': 'cro',
        'sui': 'sui-network',
        'aptos': 'aptos',
        'ton': 'ton',
    }
    
    # 热门 DEX
    POPULAR_DEXES = {
        'solana': ['raydium', 'orca', 'meteora', 'pump-fun'],
        'eth': ['uniswap_v3', 'uniswap_v2', 'sushiswap'],
        'bsc': ['pancakeswap_v3', 'pancakeswap_v2'],
        'base': ['aerodrome', 'uniswap_v3'],
        'arbitrum': ['camelot', 'uniswap_v3'],
    }
    
    def __init__(
        self,
        api_key: str = '',
        timeout: int = 30,
        rate_limit_delay: float = 0.5,  # 请求间隔(秒)
    ):
        """
        初始化 GeckoTerminal Fetcher
        
        Args:
            api_key: API Key (可选，免费版足够日常使用)
            timeout: 请求超时(秒)
            rate_limit_delay: 请求间隔(秒)，避免触发限速
        """
        super().__init__()
        
        self.api_key = api_key
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0
        
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'CryptoAnalyzer/1.0',
        })
        
        if api_key:
            self.session.headers['Authorization'] = f'Bearer {api_key}'
        
        logger.info("GeckoTerminalFetcher 初始化完成")
    
    def _normalize_chain(self, chain: str) -> str:
        """标准化链名称"""
        chain = chain.lower().strip()
        return self.CHAIN_MAP.get(chain, chain)
    
    def _rate_limit(self):
        """速率限制"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    def _request(
        self,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """发送请求"""
        self._rate_limit()
        
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code == 429:
                logger.warning("触发速率限制，等待后重试...")
                time.sleep(5)
                return self._request(endpoint, params)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"请求失败 {url}: {e}")
            return None
    
    def get_networks(self) -> List[Dict[str, Any]]:
        """获取支持的链列表"""
        try:
            data = self._request("/networks")
            if data and 'data' in data:
                return data['data']
            return []
        except Exception as e:
            logger.error(f"获取链列表失败: {e}")
            return []
    
    def get_token_info(
        self,
        chain: str,
        token_address: str
    ) -> Optional[TokenInfo]:
        """
        获取代币信息
        
        Args:
            chain: 链名称 (sol, eth, bsc 等)
            token_address: 代币合约地址
            
        Returns:
            TokenInfo 或 None
        """
        try:
            network = self._normalize_chain(chain)
            endpoint = f"/networks/{network}/tokens/{token_address}"
            
            data = self._request(endpoint)
            
            if not data or 'data' not in data:
                return None
            
            token_data = data['data']
            attrs = token_data.get('attributes', {})
            
            return TokenInfo(
                address=token_address,
                symbol=attrs.get('symbol', ''),
                name=attrs.get('name', ''),
                chain=chain,
                decimals=attrs.get('decimals', 18),
                price_usd=float(attrs.get('price_usd', 0) or 0),
                price_change_24h=float(attrs.get('price_change_percentage', {}).get('h24', 0) or 0),
                price_change_1h=float(attrs.get('price_change_percentage', {}).get('h1', 0) or 0),
                volume_24h=float(attrs.get('volume_usd', {}).get('h24', 0) or 0),
                market_cap=float(attrs.get('market_cap_usd', 0) or 0) if attrs.get('market_cap_usd') else None,
                fdv=float(attrs.get('fdv_usd', 0) or 0) if attrs.get('fdv_usd') else None,
            )
            
        except Exception as e:
            logger.error(f"获取代币信息失败 {chain}:{token_address}: {e}")
            return None
    
    def get_token_pools(
        self,
        chain: str,
        token_address: str,
        limit: int = 10
    ) -> List[PoolInfo]:
        """
        获取代币的交易池列表
        
        Args:
            chain: 链名称
            token_address: 代币地址
            limit: 返回数量
            
        Returns:
            PoolInfo 列表
        """
        try:
            network = self._normalize_chain(chain)
            endpoint = f"/networks/{network}/tokens/{token_address}/pools"
            
            data = self._request(endpoint, {'page': 1})
            
            if not data or 'data' not in data:
                return []
            
            pools = []
            for pool_data in data['data'][:limit]:
                pool = self._parse_pool(pool_data, chain)
                if pool:
                    pools.append(pool)
            
            return pools
            
        except Exception as e:
            logger.error(f"获取代币池失败: {e}")
            return []
    
    def _parse_pool(self, pool_data: Dict, chain: str) -> Optional[PoolInfo]:
        """解析交易池数据"""
        try:
            attrs = pool_data.get('attributes', {})
            relationships = pool_data.get('relationships', {})
            
            # 解析代币对
            base_token_data = relationships.get('base_token', {}).get('data', {})
            quote_token_data = relationships.get('quote_token', {}).get('data', {})
            
            base_token = TokenInfo(
                address=base_token_data.get('id', '').split('_')[-1] if base_token_data.get('id') else '',
                symbol=attrs.get('base_token_symbol', ''),
                name=attrs.get('base_token_name', ''),
                chain=chain,
            )
            
            quote_token = TokenInfo(
                address=quote_token_data.get('id', '').split('_')[-1] if quote_token_data.get('id') else '',
                symbol=attrs.get('quote_token_symbol', ''),
                name=attrs.get('quote_token_name', ''),
                chain=chain,
            )
            
            return PoolInfo(
                address=attrs.get('address', ''),
                chain=chain,
                dex=attrs.get('name', '').split()[0] if attrs.get('name') else '',
                base_token=base_token,
                quote_token=quote_token,
                price_usd=float(attrs.get('base_token_price_usd', 0) or 0),
                price_native=float(attrs.get('base_token_price_native_currency', 0) or 0),
                price_change_24h=float(attrs.get('price_change_percentage', {}).get('h24', 0) or 0),
                volume_24h=float(attrs.get('volume_usd', {}).get('h24', 0) or 0),
                txns_24h=int(attrs.get('transactions', {}).get('h24', {}).get('buys', 0) or 0) + 
                         int(attrs.get('transactions', {}).get('h24', {}).get('sells', 0) or 0),
                reserve_usd=float(attrs.get('reserve_in_usd', 0) or 0),
                liquidity_usd=float(attrs.get('reserve_in_usd', 0) or 0),
            )
            
        except Exception as e:
            logger.error(f"解析交易池失败: {e}")
            return None
    
    def get_pool_ohlcv(
        self,
        chain: str,
        pool_address: str,
        timeframe: str = 'day',
        limit: int = 100,
        aggregate: int = 1,
    ) -> Optional[pd.DataFrame]:
        """
        获取交易池 OHLCV 数据
        
        Args:
            chain: 链名称
            pool_address: 交易池地址
            timeframe: 时间周期 (minute, hour, day)
            limit: 数据条数
            aggregate: 聚合周期 (如 timeframe=minute, aggregate=5 表示5分钟)
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        try:
            network = self._normalize_chain(chain)
            endpoint = f"/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}"
            
            params = {
                'limit': limit,
                'aggregate': aggregate,
            }
            
            data = self._request(endpoint, params)
            
            if not data or 'data' not in data:
                return None
            
            ohlcv_data = data['data'].get('attributes', {}).get('ohlcv_list', [])
            
            if not ohlcv_data:
                return None
            
            # 转换为 DataFrame
            # 格式: [timestamp, open, high, low, close, volume]
            df = pd.DataFrame(
                ohlcv_data,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
            df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df
            
        except Exception as e:
            logger.error(f"获取 OHLCV 失败: {e}")
            return None
    
    def search_tokens(
        self,
        query: str,
        chain: Optional[str] = None
    ) -> List[TokenInfo]:
        """
        搜索代币
        
        Args:
            query: 搜索关键词 (代币名称或符号)
            chain: 限定链 (可选)
            
        Returns:
            TokenInfo 列表
        """
        try:
            endpoint = "/search/pools"
            params = {'query': query}
            
            if chain:
                params['network'] = self._normalize_chain(chain)
            
            data = self._request(endpoint, params)
            
            if not data or 'data' not in data:
                return []
            
            tokens = []
            seen_addresses = set()
            
            for pool_data in data['data']:
                attrs = pool_data.get('attributes', {})
                relationships = pool_data.get('relationships', {})
                
                # 获取 base token 信息
                base_token_id = relationships.get('base_token', {}).get('data', {}).get('id', '')
                
                if base_token_id and base_token_id not in seen_addresses:
                    seen_addresses.add(base_token_id)
                    
                    # 解析链和地址
                    parts = base_token_id.split('_')
                    if len(parts) >= 2:
                        token_chain = parts[0]
                        token_address = '_'.join(parts[1:])
                        
                        token = TokenInfo(
                            address=token_address,
                            symbol=attrs.get('base_token_symbol', ''),
                            name=attrs.get('base_token_name', ''),
                            chain=token_chain,
                            price_usd=float(attrs.get('base_token_price_usd', 0) or 0),
                            volume_24h=float(attrs.get('volume_usd', {}).get('h24', 0) or 0),
                            liquidity_usd=float(attrs.get('reserve_in_usd', 0) or 0),
                        )
                        tokens.append(token)
            
            return tokens
            
        except Exception as e:
            logger.error(f"搜索代币失败: {e}")
            return []
    
    def get_trending_tokens(
        self,
        chain: str,
        limit: int = 20
    ) -> List[TokenInfo]:
        """
        获取热门代币 (按成交量排序)
        
        Args:
            chain: 链名称
            limit: 返回数量
            
        Returns:
            TokenInfo 列表
        """
        try:
            network = self._normalize_chain(chain)
            endpoint = f"/networks/{network}/trending_pools"
            
            data = self._request(endpoint)
            
            if not data or 'data' not in data:
                return []
            
            tokens = []
            seen = set()
            
            for pool_data in data['data'][:limit*2]:  # 获取更多以去重
                attrs = pool_data.get('attributes', {})
                symbol = attrs.get('base_token_symbol', '')
                address = attrs.get('address', '')
                
                if symbol and symbol not in seen:
                    seen.add(symbol)
                    
                    price_change = attrs.get('price_change_percentage', {})
                    volume = attrs.get('volume_usd', {})
                    txns = attrs.get('transactions', {}).get('h24', {})
                    
                    token = TokenInfo(
                        address=address,
                        symbol=symbol,
                        name=attrs.get('base_token_name', ''),
                        chain=chain,
                        price_usd=float(attrs.get('base_token_price_usd', 0) or 0),
                        price_change_24h=float(price_change.get('h24', 0) or 0),
                        price_change_1h=float(price_change.get('h1', 0) or 0),
                        volume_24h=float(volume.get('h24', 0) or 0),
                        txns_24h=int(txns.get('buys', 0) or 0) + int(txns.get('sells', 0) or 0),
                        buys_24h=int(txns.get('buys', 0) or 0),
                        sells_24h=int(txns.get('sells', 0) or 0),
                        liquidity_usd=float(attrs.get('reserve_in_usd', 0) or 0),
                        fdv=float(attrs.get('fdv_usd', 0) or 0) if attrs.get('fdv_usd') else None,
                    )
                    tokens.append(token)
                    
                    if len(tokens) >= limit:
                        break
            
            return tokens
            
        except Exception as e:
            logger.error(f"获取热门代币失败: {e}")
            return []
    
    def get_new_tokens(
        self,
        chain: str,
        limit: int = 20
    ) -> List[TokenInfo]:
        """
        获取新上线代币
        
        Args:
            chain: 链名称
            limit: 返回数量
            
        Returns:
            TokenInfo 列表
        """
        try:
            network = self._normalize_chain(chain)
            endpoint = f"/networks/{network}/new_pools"
            
            data = self._request(endpoint)
            
            if not data or 'data' not in data:
                return []
            
            tokens = []
            seen = set()
            
            for pool_data in data['data'][:limit*2]:
                attrs = pool_data.get('attributes', {})
                symbol = attrs.get('base_token_symbol', '')
                
                if symbol and symbol not in seen:
                    seen.add(symbol)
                    
                    # 解析创建时间
                    created_at = None
                    pool_created = attrs.get('pool_created_at')
                    if pool_created:
                        try:
                            created_at = datetime.fromisoformat(pool_created.replace('Z', '+00:00'))
                        except:
                            pass
                    
                    token = TokenInfo(
                        address=attrs.get('address', ''),
                        symbol=symbol,
                        name=attrs.get('base_token_name', ''),
                        chain=chain,
                        price_usd=float(attrs.get('base_token_price_usd', 0) or 0),
                        price_change_24h=float(attrs.get('price_change_percentage', {}).get('h24', 0) or 0),
                        volume_24h=float(attrs.get('volume_usd', {}).get('h24', 0) or 0),
                        liquidity_usd=float(attrs.get('reserve_in_usd', 0) or 0),
                        pool_created_at=created_at,
                    )
                    tokens.append(token)
                    
                    if len(tokens) >= limit:
                        break
            
            return tokens
            
        except Exception as e:
            logger.error(f"获取新代币失败: {e}")
            return []
    
    def get_top_gainers(
        self,
        chain: str,
        timeframe: str = '24h',
        limit: int = 20
    ) -> List[TokenInfo]:
        """
        获取涨幅榜
        
        Args:
            chain: 链名称
            timeframe: 时间周期 (1h, 6h, 24h)
            limit: 返回数量
        """
        # GeckoTerminal 免费版暂不支持直接的涨幅榜
        # 使用 trending 作为替代，按涨幅排序
        tokens = self.get_trending_tokens(chain, limit=50)
        
        # 按涨幅排序
        if timeframe == '1h':
            tokens.sort(key=lambda x: x.price_change_1h, reverse=True)
        else:
            tokens.sort(key=lambda x: x.price_change_24h, reverse=True)
        
        return tokens[:limit]
    
    def get_top_losers(
        self,
        chain: str,
        timeframe: str = '24h',
        limit: int = 20
    ) -> List[TokenInfo]:
        """
        获取跌幅榜
        """
        tokens = self.get_trending_tokens(chain, limit=50)
        
        if timeframe == '1h':
            tokens.sort(key=lambda x: x.price_change_1h, reverse=False)
        else:
            tokens.sort(key=lambda x: x.price_change_24h, reverse=False)
        
        return tokens[:limit]
    
    def get_token_with_pools(
        self,
        chain: str,
        token_address: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取代币完整信息（包含交易池）
        
        Returns:
            {
                'token': TokenInfo,
                'pools': List[PoolInfo],
                'main_pool': PoolInfo,  # 流动性最大的池
            }
        """
        try:
            token = self.get_token_info(chain, token_address)
            if not token:
                return None
            
            pools = self.get_token_pools(chain, token_address, limit=5)
            
            # 找到主要交易池（流动性最大）
            main_pool = None
            if pools:
                main_pool = max(pools, key=lambda x: x.liquidity_usd)
            
            return {
                'token': token,
                'pools': pools,
                'main_pool': main_pool,
            }
            
        except Exception as e:
            logger.error(f"获取代币完整信息失败: {e}")
            return None
    
    def get_historical_data(
        self,
        chain: str,
        token_address: str,
        days: int = 30,
        timeframe: str = 'day'
    ) -> Optional[pd.DataFrame]:
        """
        获取代币历史数据
        
        先找到主要交易池，再获取 OHLCV
        
        Args:
            chain: 链名称
            token_address: 代币地址
            days: 天数
            timeframe: 时间周期 (minute, hour, day)
            
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        try:
            # 获取主要交易池
            pools = self.get_token_pools(chain, token_address, limit=1)
            
            if not pools:
                logger.warning(f"未找到 {token_address} 的交易池")
                return None
            
            main_pool = pools[0]
            
            # 获取 OHLCV
            df = self.get_pool_ohlcv(
                chain,
                main_pool.address,
                timeframe=timeframe,
                limit=days
            )
            
            if df is not None:
                df.reset_index(inplace=True)
                df.rename(columns={'timestamp': 'date'}, inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"获取历史数据失败: {e}")
            return None
    
    def parse_token_identifier(self, identifier: str) -> Dict[str, str]:
        """
        解析代币标识符
        
        支持的格式:
        - sol:address (链:地址)
        - solana:address
        - address (默认使用 solana)
        
        Returns:
            {'chain': 'sol', 'address': 'xxx'}
        """
        identifier = identifier.strip()
        
        if ':' in identifier:
            parts = identifier.split(':', 1)
            chain = parts[0].lower()
            address = parts[1]
        else:
            # 默认 Solana
            chain = 'sol'
            address = identifier
        
        chain = self._normalize_chain(chain)
        
        return {
            'chain': chain,
            'address': address,
        }
    
    def get_multi_chain_trending(
        self,
        chains: List[str] = None,
        limit_per_chain: int = 10
    ) -> Dict[str, List[TokenInfo]]:
        """
        获取多链热门代币
        
        Args:
            chains: 链列表，默认 ['sol', 'eth', 'bsc']
            limit_per_chain: 每条链返回数量
            
        Returns:
            {chain: [TokenInfo, ...]}
        """
        if chains is None:
            chains = ['sol', 'eth', 'bsc']
        
        results = {}
        
        for chain in chains:
            tokens = self.get_trending_tokens(chain, limit=limit_per_chain)
            results[chain] = tokens
        
        return results


# 便捷函数
def create_geckoterminal_fetcher(api_key: str = '') -> GeckoTerminalFetcher:
    """创建 GeckoTerminal 数据获取器"""
    return GeckoTerminalFetcher(api_key=api_key)
