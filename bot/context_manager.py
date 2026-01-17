# -*- coding: utf-8 -*-
"""
上下文管理器

管理用户会话、报告上下文和对话历史
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """对话消息"""
    role: str  # "user" 或 "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content
        }


@dataclass 
class MarketReport:
    """市场报告数据"""
    content: str  # 完整报告内容
    summary: str  # 摘要
    timestamp: datetime
    market_data: Optional[Dict] = None  # 关联的市场数据
    report_type: str = "daily"  # daily, realtime, custom
    
    def to_context_string(self) -> str:
        """转换为上下文字符串供 AI 参考"""
        return f"""
【最新市场报告】
生成时间: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
报告类型: {self.report_type}

{self.content}
"""


@dataclass
class UserSession:
    """用户会话"""
    user_id: str
    platform: str  # "telegram" 或 "wecom"
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    context_reports: List[MarketReport] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str):
        """添加消息"""
        self.messages.append(Message(role=role, content=content))
        self.last_active = datetime.now()
        
        # 保留最近 20 条消息
        if len(self.messages) > 20:
            self.messages = self.messages[-20:]
    
    def get_conversation_history(self, max_messages: int = 10) -> List[dict]:
        """获取对话历史"""
        return [msg.to_dict() for msg in self.messages[-max_messages:]]
    
    def add_report(self, report: MarketReport):
        """添加报告到上下文"""
        self.context_reports.append(report)
        # 只保留最近 3 份报告
        if len(self.context_reports) > 3:
            self.context_reports = self.context_reports[-3:]
    
    def get_latest_report(self) -> Optional[MarketReport]:
        """获取最新报告"""
        return self.context_reports[-1] if self.context_reports else None
    
    def clear_history(self):
        """清空对话历史"""
        self.messages.clear()


class ContextManager:
    """
    上下文管理器
    
    负责管理：
    1. 用户会话（多平台支持）
    2. 市场报告上下文
    3. 对话历史
    4. 会话过期清理
    """
    
    def __init__(
        self,
        session_timeout_hours: int = 24,
        max_sessions: int = 1000
    ):
        self.sessions: Dict[str, UserSession] = {}
        self.session_timeout = timedelta(hours=session_timeout_hours)
        self.max_sessions = max_sessions
        self._latest_global_report: Optional[MarketReport] = None
        self._lock = asyncio.Lock()
        
    def _get_session_key(self, user_id: str, platform: str) -> str:
        """生成会话键"""
        return f"{platform}:{user_id}"
    
    async def get_or_create_session(
        self,
        user_id: str,
        platform: str
    ) -> UserSession:
        """获取或创建用户会话"""
        async with self._lock:
            key = self._get_session_key(user_id, platform)
            
            if key in self.sessions:
                session = self.sessions[key]
                session.last_active = datetime.now()
                return session
            
            # 创建新会话
            session = UserSession(user_id=user_id, platform=platform)
            
            # 如果有全局最新报告，添加到会话上下文
            if self._latest_global_report:
                session.add_report(self._latest_global_report)
            
            self.sessions[key] = session
            
            # 清理过期会话
            await self._cleanup_expired_sessions()
            
            return session
    
    async def _cleanup_expired_sessions(self):
        """清理过期会话"""
        now = datetime.now()
        expired_keys = [
            key for key, session in self.sessions.items()
            if now - session.last_active > self.session_timeout
        ]
        
        for key in expired_keys:
            del self.sessions[key]
            
        # 如果会话数超过限制，删除最早的会话
        if len(self.sessions) > self.max_sessions:
            sorted_sessions = sorted(
                self.sessions.items(),
                key=lambda x: x[1].last_active
            )
            for key, _ in sorted_sessions[:len(self.sessions) - self.max_sessions]:
                del self.sessions[key]
    
    async def update_global_report(
        self,
        content: str,
        summary: str = "",
        market_data: Optional[Dict] = None,
        report_type: str = "daily"
    ):
        """
        更新全局最新报告
        
        当系统生成新报告时调用，会自动推送到所有活跃会话
        """
        async with self._lock:
            report = MarketReport(
                content=content,
                summary=summary or content[:200],
                timestamp=datetime.now(),
                market_data=market_data,
                report_type=report_type
            )
            self._latest_global_report = report
            
            # 推送到所有活跃会话
            for session in self.sessions.values():
                session.add_report(report)
            
            logger.info(f"全局报告已更新，已推送到 {len(self.sessions)} 个活跃会话")
    
    async def get_ai_context(
        self,
        user_id: str,
        platform: str,
        include_history: bool = True,
        max_history: int = 10
    ) -> Dict[str, Any]:
        """
        获取 AI 对话上下文
        
        返回包含系统提示、报告上下文和对话历史的完整上下文
        """
        session = await self.get_or_create_session(user_id, platform)
        
        context = {
            "user_id": user_id,
            "platform": platform,
            "system_context": self._build_system_context(session),
            "conversation_history": [],
            "has_report": False,
            "latest_report_time": None
        }
        
        # 添加报告上下文
        latest_report = session.get_latest_report()
        if latest_report:
            context["has_report"] = True
            context["latest_report_time"] = latest_report.timestamp.isoformat()
            context["report_context"] = latest_report.to_context_string()
        
        # 添加对话历史
        if include_history:
            context["conversation_history"] = session.get_conversation_history(max_history)
        
        return context
    
    def _build_system_context(self, session: UserSession) -> str:
        """构建系统上下文"""
        parts = [
            "你是一个专业的加密货币市场分析助手。",
            "你可以：",
            "1. 分析和解读市场报告",
            "2. 回答关于加密货币市场的问题",
            "3. 提供技术分析建议",
            "4. 生成市场分析图表（使用 /image 命令）",
            "",
            "用户信息：",
            f"- 平台: {session.platform}",
            f"- 会话开始: {session.created_at.strftime('%Y-%m-%d %H:%M')}",
        ]
        
        if session.preferences:
            parts.append(f"- 用户偏好: {json.dumps(session.preferences, ensure_ascii=False)}")
        
        # 添加报告上下文
        latest_report = session.get_latest_report()
        if latest_report:
            parts.extend([
                "",
                "【当前市场报告上下文】",
                f"报告时间: {latest_report.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                latest_report.content[:3000]  # 限制长度
            ])
        
        return "\n".join(parts)
    
    async def add_user_message(
        self,
        user_id: str,
        platform: str,
        content: str
    ):
        """添加用户消息"""
        session = await self.get_or_create_session(user_id, platform)
        session.add_message("user", content)
    
    async def add_assistant_message(
        self,
        user_id: str,
        platform: str,
        content: str
    ):
        """添加助手消息"""
        session = await self.get_or_create_session(user_id, platform)
        session.add_message("assistant", content)
    
    async def clear_user_history(
        self,
        user_id: str,
        platform: str
    ):
        """清空用户对话历史"""
        session = await self.get_or_create_session(user_id, platform)
        session.clear_history()
    
    async def set_user_preference(
        self,
        user_id: str,
        platform: str,
        key: str,
        value: Any
    ):
        """设置用户偏好"""
        session = await self.get_or_create_session(user_id, platform)
        session.preferences[key] = value
    
    def get_active_sessions_count(self) -> Dict[str, int]:
        """获取活跃会话统计"""
        stats = defaultdict(int)
        for session in self.sessions.values():
            stats[session.platform] += 1
        return dict(stats)
    
    async def broadcast_message(
        self,
        message: str,
        platforms: Optional[List[str]] = None
    ) -> List[str]:
        """
        广播消息到所有活跃会话
        
        返回需要发送消息的用户列表（格式：platform:user_id）
        """
        async with self._lock:
            targets = []
            for key, session in self.sessions.items():
                if platforms is None or session.platform in platforms:
                    targets.append(key)
            return targets


# 全局单例
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """获取全局上下文管理器"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager


def init_context_manager(**kwargs) -> ContextManager:
    """初始化全局上下文管理器"""
    global _context_manager
    _context_manager = ContextManager(**kwargs)
    return _context_manager
