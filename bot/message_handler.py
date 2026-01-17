# -*- coding: utf-8 -*-
"""
统一消息处理器

处理来自不同平台的用户消息，生成 AI 响应
"""

import asyncio
import logging
import re
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass
from enum import Enum
import httpx

from bot.context_manager import ContextManager, get_context_manager
from bot.image_generator import ImageGenerator, get_image_generator, GeneratedImage

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型"""
    TEXT = "text"
    COMMAND = "command"
    IMAGE_REQUEST = "image_request"


@dataclass
class UserMessage:
    """用户消息"""
    user_id: str
    platform: str  # "telegram" 或 "wecom"
    content: str
    message_type: MessageType = MessageType.TEXT
    raw_data: Optional[Dict] = None


@dataclass
class BotResponse:
    """机器人响应"""
    text: Optional[str] = None
    image: Optional[GeneratedImage] = None
    error: Optional[str] = None
    metadata: Optional[Dict] = None
    
    @property
    def has_error(self) -> bool:
        return self.error is not None


class MessageHandler:
    """
    统一消息处理器
    
    功能：
    1. 解析用户消息
    2. 处理命令（/start, /help, /image, /clear 等）
    3. 调用 AI 生成响应
    4. 管理对话上下文
    """
    
    # 支持的命令
    COMMANDS = {
        "/start": "开始使用机器人",
        "/help": "显示帮助信息",
        "/image": "生成市场分析图表",
        "/clear": "清空对话历史",
        "/report": "获取最新市场报告",
        "/status": "查看系统状态",
    }
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        context_manager: Optional[ContextManager] = None,
        image_generator: Optional[ImageGenerator] = None
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.context_manager = context_manager or get_context_manager()
        self.image_generator = image_generator or get_image_generator()
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=60,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
        return self._client
    
    async def close(self):
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def parse_message(self, content: str) -> Tuple[MessageType, str]:
        """解析消息类型和内容"""
        content = content.strip()
        
        if content.startswith('/'):
            # 提取命令
            parts = content.split(maxsplit=1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            
            if command == '/image':
                return MessageType.IMAGE_REQUEST, args
            elif command in self.COMMANDS:
                return MessageType.COMMAND, content
        
        return MessageType.TEXT, content
    
    async def handle_message(self, message: UserMessage) -> BotResponse:
        """
        处理用户消息
        
        根据消息类型分发到不同的处理器
        """
        try:
            msg_type, content = self.parse_message(message.content)
            message.message_type = msg_type
            
            if msg_type == MessageType.COMMAND:
                return await self._handle_command(message, content)
            elif msg_type == MessageType.IMAGE_REQUEST:
                return await self._handle_image_request(message, content)
            else:
                return await self._handle_text_message(message)
                
        except Exception as e:
            logger.error(f"处理消息时出错: {e}", exc_info=True)
            return BotResponse(error=f"处理消息时出错: {str(e)}")
    
    async def _handle_command(
        self,
        message: UserMessage,
        command_str: str
    ) -> BotResponse:
        """处理命令"""
        parts = command_str.split(maxsplit=1)
        command = parts[0].lower()
        
        if command == "/start":
            return await self._cmd_start(message)
        elif command == "/help":
            return await self._cmd_help(message)
        elif command == "/clear":
            return await self._cmd_clear(message)
        elif command == "/report":
            return await self._cmd_report(message)
        elif command == "/status":
            return await self._cmd_status(message)
        else:
            return BotResponse(text=f"未知命令: {command}\n使用 /help 查看可用命令")
    
    async def _cmd_start(self, message: UserMessage) -> BotResponse:
        """处理 /start 命令"""
        welcome = """🚀 **欢迎使用加密货币智能分析助手！**

我可以帮你：
• 分析和解读市场报告
• 回答关于加密货币的问题
• 提供技术分析建议
• 生成市场分析图表

**可用命令：**
/help - 显示帮助
/report - 获取最新报告
/image - 生成分析图表
/clear - 清空对话历史

直接发送消息即可开始对话！"""
        
        return BotResponse(text=welcome)
    
    async def _cmd_help(self, message: UserMessage) -> BotResponse:
        """处理 /help 命令"""
        help_text = "**📚 可用命令：**\n\n"
        for cmd, desc in self.COMMANDS.items():
            help_text += f"`{cmd}` - {desc}\n"
        
        help_text += "\n**💬 对话功能：**\n"
        help_text += "• 直接发送问题即可与 AI 对话\n"
        help_text += "• AI 会结合最新的市场报告回答\n"
        help_text += "• 支持多轮对话，记住上下文\n"
        
        return BotResponse(text=help_text)
    
    async def _cmd_clear(self, message: UserMessage) -> BotResponse:
        """处理 /clear 命令"""
        await self.context_manager.clear_user_history(
            message.user_id,
            message.platform
        )
        return BotResponse(text="✅ 对话历史已清空")
    
    async def _cmd_report(self, message: UserMessage) -> BotResponse:
        """处理 /report 命令"""
        context = await self.context_manager.get_ai_context(
            message.user_id,
            message.platform,
            include_history=False
        )
        
        if context.get("has_report"):
            report_time = context.get("latest_report_time", "未知")
            report_content = context.get("report_context", "")
            
            # 截取报告摘要
            summary = report_content[:2000]
            if len(report_content) > 2000:
                summary += "\n\n...(报告内容较长，已截断)"
            
            return BotResponse(
                text=f"📊 **最新市场报告**\n\n生成时间: {report_time}\n\n{summary}"
            )
        else:
            return BotResponse(
                text="⚠️ 暂无市场报告\n\n系统会在每日定时分析后推送报告。"
            )
    
    async def _cmd_status(self, message: UserMessage) -> BotResponse:
        """处理 /status 命令"""
        stats = self.context_manager.get_active_sessions_count()
        
        status_text = "📈 **系统状态**\n\n"
        status_text += f"• AI 模型: `{self.model}`\n"
        status_text += f"• 活跃会话: {sum(stats.values())}\n"
        
        for platform, count in stats.items():
            status_text += f"  - {platform}: {count}\n"
        
        if self.image_generator:
            status_text += "• 图像生成: ✅ 可用\n"
        else:
            status_text += "• 图像生成: ❌ 未配置\n"
        
        return BotResponse(text=status_text)
    
    async def _handle_image_request(
        self,
        message: UserMessage,
        args: str
    ) -> BotResponse:
        """处理图像生成请求"""
        if not self.image_generator:
            return BotResponse(
                error="图像生成功能未配置，请联系管理员设置 API"
            )
        
        # 获取报告上下文
        context = await self.context_manager.get_ai_context(
            message.user_id,
            message.platform,
            include_history=False
        )
        
        if not context.get("has_report"):
            return BotResponse(
                error="暂无市场报告，无法生成图表。请等待下一次市场分析。"
            )
        
        # 确定样式
        style = "modern"
        if args:
            args_lower = args.lower()
            if "专业" in args or "professional" in args_lower:
                style = "professional"
            elif "简约" in args or "minimalist" in args_lower:
                style = "minimalist"
            elif "活力" in args or "vibrant" in args_lower:
                style = "vibrant"
        
        # 生成图像
        report_content = context.get("report_context", "")
        image, error = await self.image_generator.generate_market_poster(
            report_content,
            style=style
        )
        
        if error:
            # 生成失败，尝试生成描述
            description = await self.image_generator.generate_chart_description(
                report_content
            )
            return BotResponse(
                text=f"⚠️ 图像生成失败: {error}\n\n📝 **图表描述：**\n{description}"
            )
        
        return BotResponse(
            text="🖼️ 市场分析图表已生成",
            image=image
        )
    
    async def _handle_text_message(self, message: UserMessage) -> BotResponse:
        """处理普通文本消息"""
        # 获取上下文
        context = await self.context_manager.get_ai_context(
            message.user_id,
            message.platform,
            include_history=True
        )
        
        # 添加用户消息到历史
        await self.context_manager.add_user_message(
            message.user_id,
            message.platform,
            message.content
        )
        
        # 构建 AI 请求
        messages = self._build_ai_messages(context, message.content)
        
        # 调用 AI
        response_text = await self._call_ai(messages)
        
        if response_text:
            # 添加助手响应到历史
            await self.context_manager.add_assistant_message(
                message.user_id,
                message.platform,
                response_text
            )
            return BotResponse(text=response_text)
        else:
            return BotResponse(error="AI 响应失败，请稍后重试")
    
    def _build_ai_messages(
        self,
        context: Dict[str, Any],
        user_message: str
    ) -> List[Dict[str, str]]:
        """构建 AI 消息列表"""
        messages = [
            {
                "role": "system",
                "content": context.get("system_context", "你是一个加密货币市场分析助手。")
            }
        ]
        
        # 添加对话历史
        history = context.get("conversation_history", [])
        messages.extend(history)
        
        # 添加当前用户消息
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages
    
    async def _call_ai(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """调用 AI API"""
        try:
            client = await self._get_client()
            url = f"{self.base_url}/chat/completions"
            
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 2000,
                "temperature": 0.7
            }
            
            response = await client.post(url, json=payload)
            
            if response.status_code != 200:
                logger.error(f"AI API 错误: {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"调用 AI API 失败: {e}", exc_info=True)
            return None


# 全局实例
_message_handler: Optional[MessageHandler] = None


def get_message_handler() -> Optional[MessageHandler]:
    """获取全局消息处理器"""
    return _message_handler


def init_message_handler(
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o-mini",
    **kwargs
) -> MessageHandler:
    """初始化全局消息处理器"""
    global _message_handler
    _message_handler = MessageHandler(
        api_key=api_key,
        base_url=base_url,
        model=model,
        **kwargs
    )
    return _message_handler
