# -*- coding: utf-8 -*-
"""
Telegram Bot 双向对话模块

使用 python-telegram-bot 库实现双向对话功能
"""

import asyncio
import logging
import io
from typing import Optional, Dict, Any, Callable
from functools import partial

from telegram import Update, Bot
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler as TGMessageHandler,
    ContextTypes,
    filters
)
from telegram.constants import ParseMode, ChatAction

from bot.context_manager import ContextManager, get_context_manager
from bot.message_handler import (
    MessageHandler,
    UserMessage,
    BotResponse,
    init_message_handler
)
from bot.image_generator import init_image_generator

logger = logging.getLogger(__name__)


class TelegramBot:
    """
    Telegram 双向对话机器人
    
    功能：
    1. 接收用户消息
    2. 处理命令
    3. 与 AI 进行对话
    4. 发送图片
    5. 推送市场报告
    """
    
    def __init__(
        self,
        token: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        image_model: str = "dall-e-3",
        allowed_chat_ids: Optional[list] = None,
        context_manager: Optional[ContextManager] = None
    ):
        self.token = token
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.image_model = image_model
        self.allowed_chat_ids = set(allowed_chat_ids) if allowed_chat_ids else None
        
        # 初始化组件
        self.context_manager = context_manager or get_context_manager()
        
        # 初始化图像生成器
        self.image_generator = init_image_generator(
            api_key=api_key,
            base_url=base_url,
            model=image_model
        )
        
        # 初始化消息处理器
        self.message_handler = init_message_handler(
            api_key=api_key,
            base_url=base_url,
            model=model,
            context_manager=self.context_manager,
            image_generator=self.image_generator
        )
        
        # Telegram 应用
        self.application: Optional[Application] = None
        self._running = False
    
    def _check_access(self, chat_id: int) -> bool:
        """检查访问权限"""
        if self.allowed_chat_ids is None:
            return True
        return chat_id in self.allowed_chat_ids
    
    async def _send_typing_action(self, update: Update):
        """发送正在输入状态"""
        await update.effective_chat.send_action(action=ChatAction.TYPING)
    
    async def _handle_start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """处理 /start 命令"""
        if not self._check_access(update.effective_chat.id):
            await update.message.reply_text("⚠️ 您没有权限使用此机器人")
            return
        
        user_msg = UserMessage(
            user_id=str(update.effective_user.id),
            platform="telegram",
            content="/start"
        )
        
        response = await self.message_handler.handle_message(user_msg)
        await self._send_response(update, response)
    
    async def _handle_help(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """处理 /help 命令"""
        if not self._check_access(update.effective_chat.id):
            return
        
        user_msg = UserMessage(
            user_id=str(update.effective_user.id),
            platform="telegram",
            content="/help"
        )
        
        response = await self.message_handler.handle_message(user_msg)
        await self._send_response(update, response)
    
    async def _handle_clear(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """处理 /clear 命令"""
        if not self._check_access(update.effective_chat.id):
            return
        
        user_msg = UserMessage(
            user_id=str(update.effective_user.id),
            platform="telegram",
            content="/clear"
        )
        
        response = await self.message_handler.handle_message(user_msg)
        await self._send_response(update, response)
    
    async def _handle_report(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """处理 /report 命令"""
        if not self._check_access(update.effective_chat.id):
            return
        
        user_msg = UserMessage(
            user_id=str(update.effective_user.id),
            platform="telegram",
            content="/report"
        )
        
        response = await self.message_handler.handle_message(user_msg)
        await self._send_response(update, response)
    
    async def _handle_status(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """处理 /status 命令"""
        if not self._check_access(update.effective_chat.id):
            return
        
        user_msg = UserMessage(
            user_id=str(update.effective_user.id),
            platform="telegram",
            content="/status"
        )
        
        response = await self.message_handler.handle_message(user_msg)
        await self._send_response(update, response)
    
    async def _handle_image(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """处理 /image 命令"""
        if not self._check_access(update.effective_chat.id):
            return
        
        await self._send_typing_action(update)
        
        # 获取参数
        args = " ".join(context.args) if context.args else ""
        
        user_msg = UserMessage(
            user_id=str(update.effective_user.id),
            platform="telegram",
            content=f"/image {args}"
        )
        
        # 通知用户正在生成
        await update.message.reply_text("🎨 正在生成市场分析图表，请稍候...")
        
        response = await self.message_handler.handle_message(user_msg)
        await self._send_response(update, response)
    
    async def _handle_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """处理普通文本消息"""
        if not self._check_access(update.effective_chat.id):
            return
        
        if not update.message or not update.message.text:
            return
        
        await self._send_typing_action(update)
        
        user_msg = UserMessage(
            user_id=str(update.effective_user.id),
            platform="telegram",
            content=update.message.text
        )
        
        response = await self.message_handler.handle_message(user_msg)
        await self._send_response(update, response)
    
    async def _send_response(self, update: Update, response: BotResponse):
        """发送响应"""
        try:
            # 发送图片
            if response.image:
                image_bytes = io.BytesIO(response.image.data)
                image_bytes.name = f"chart.{response.image.format}"
                await update.message.reply_photo(
                    photo=image_bytes,
                    caption=response.text[:1024] if response.text else None
                )
                return
            
            # 发送文本
            text = response.text or response.error or "未知响应"
            
            # 分割长消息
            max_length = 4000
            if len(text) > max_length:
                parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
                for part in parts:
                    await update.message.reply_text(
                        part,
                        parse_mode=ParseMode.MARKDOWN
                    )
            else:
                await update.message.reply_text(
                    text,
                    parse_mode=ParseMode.MARKDOWN
                )
                
        except Exception as e:
            logger.error(f"发送响应失败: {e}", exc_info=True)
            # 尝试不使用 Markdown 格式
            try:
                plain_text = response.text or response.error or "响应发送失败"
                await update.message.reply_text(plain_text)
            except Exception as e2:
                logger.error(f"发送纯文本响应也失败: {e2}")
    
    async def push_message(
        self,
        chat_id: int,
        text: str,
        image_data: Optional[bytes] = None
    ):
        """
        主动推送消息到指定聊天
        
        用于推送市场报告等
        """
        if not self.application:
            logger.error("Telegram Bot 未初始化")
            return
        
        bot = self.application.bot
        
        try:
            if image_data:
                image_bytes = io.BytesIO(image_data)
                image_bytes.name = "report.png"
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=image_bytes,
                    caption=text[:1024] if text else None
                )
            else:
                # 分割长消息
                max_length = 4000
                if len(text) > max_length:
                    parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
                    for part in parts:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=part,
                            parse_mode=ParseMode.MARKDOWN
                        )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    
            logger.info(f"消息已推送到 chat_id={chat_id}")
            
        except Exception as e:
            logger.error(f"推送消息失败: {e}", exc_info=True)
    
    async def update_report(
        self,
        content: str,
        summary: str = "",
        market_data: Optional[Dict] = None
    ):
        """
        更新市场报告
        
        当新报告生成时调用，更新上下文管理器
        """
        await self.context_manager.update_global_report(
            content=content,
            summary=summary,
            market_data=market_data,
            report_type="daily"
        )
        logger.info("市场报告已更新到上下文管理器")
    
    def build_application(self) -> Application:
        """构建 Telegram 应用"""
        self.application = (
            ApplicationBuilder()
            .token(self.token)
            .build()
        )
        
        # 注册命令处理器
        self.application.add_handler(
            CommandHandler("start", self._handle_start)
        )
        self.application.add_handler(
            CommandHandler("help", self._handle_help)
        )
        self.application.add_handler(
            CommandHandler("clear", self._handle_clear)
        )
        self.application.add_handler(
            CommandHandler("report", self._handle_report)
        )
        self.application.add_handler(
            CommandHandler("status", self._handle_status)
        )
        self.application.add_handler(
            CommandHandler("image", self._handle_image)
        )
        
        # 注册文本消息处理器
        self.application.add_handler(
            TGMessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handle_text_message
            )
        )
        
        return self.application
    
    async def start_polling(self):
        """启动轮询模式"""
        if not self.application:
            self.build_application()
        
        logger.info("Telegram Bot 开始轮询...")
        self._running = True
        
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(
            drop_pending_updates=True
        )
        
        logger.info("Telegram Bot 已启动")
    
    async def stop(self):
        """停止机器人"""
        if self.application and self._running:
            logger.info("正在停止 Telegram Bot...")
            self._running = False
            
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            
            logger.info("Telegram Bot 已停止")
    
    def run(self):
        """
        阻塞式运行机器人（用于独立运行）
        
        使用方式：
        ```python
        bot = TelegramBot(...)
        bot.run()
        ```
        """
        if not self.application:
            self.build_application()
        
        logger.info("Telegram Bot 阻塞式运行...")
        self.application.run_polling(drop_pending_updates=True)


class TelegramBotFactory:
    """Telegram Bot 工厂"""
    
    @staticmethod
    def create_from_config(config: Dict[str, Any]) -> Optional[TelegramBot]:
        """从配置创建 Telegram Bot"""
        token = config.get("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.warning("未配置 TELEGRAM_BOT_TOKEN")
            return None
        
        api_key = config.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("未配置 OPENAI_API_KEY")
            return None
        
        # 解析允许的 chat_id 列表
        chat_id_str = config.get("TELEGRAM_CHAT_ID", "")
        allowed_chat_ids = None
        if chat_id_str:
            try:
                allowed_chat_ids = [int(x.strip()) for x in chat_id_str.split(",")]
            except ValueError:
                logger.warning(f"无法解析 TELEGRAM_CHAT_ID: {chat_id_str}")
        
        return TelegramBot(
            token=token,
            api_key=api_key,
            base_url=config.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=config.get("OPENAI_MODEL", "gpt-4o-mini"),
            image_model=config.get("IMAGE_MODEL", "dall-e-3"),
            allowed_chat_ids=allowed_chat_ids
        )


# 全局实例
_telegram_bot: Optional[TelegramBot] = None


def get_telegram_bot() -> Optional[TelegramBot]:
    """获取全局 Telegram Bot"""
    return _telegram_bot


def init_telegram_bot(**kwargs) -> TelegramBot:
    """初始化全局 Telegram Bot"""
    global _telegram_bot
    _telegram_bot = TelegramBot(**kwargs)
    return _telegram_bot


async def run_telegram_bot_async(
    token: str,
    api_key: str,
    **kwargs
):
    """
    异步运行 Telegram Bot
    
    可与其他异步任务一起运行
    """
    bot = TelegramBot(
        token=token,
        api_key=api_key,
        **kwargs
    )
    
    try:
        await bot.start_polling()
        
        # 保持运行
        while bot._running:
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        pass
    finally:
        await bot.stop()


if __name__ == "__main__":
    import os
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # 从环境变量读取配置
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not token or not api_key:
        print("请设置 TELEGRAM_BOT_TOKEN 和 OPENAI_API_KEY 环境变量")
        exit(1)
    
    # 创建并运行机器人
    bot = TelegramBot(
        token=token,
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    )
    
    bot.run()
