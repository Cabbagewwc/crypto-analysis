#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bot 独立运行入口

启动 Telegram 双向对话机器人
可以与定时分析任务并行运行
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import config
from bot.context_manager import init_context_manager
from bot.telegram_bot import TelegramBot, TelegramBotFactory

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_config() -> bool:
    """检查必要配置"""
    required = [
        ("TELEGRAM_BOT_TOKEN", config.TELEGRAM_BOT_TOKEN),
        ("OPENAI_API_KEY", config.OPENAI_API_KEY),
    ]
    
    missing = [name for name, value in required if not value]
    
    if missing:
        logger.error(f"缺少必要配置: {', '.join(missing)}")
        return False
    
    return True


async def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("加密货币分析助手 - Telegram Bot")
    logger.info("=" * 50)
    
    # 检查配置
    if not check_config():
        logger.error("配置检查失败，请设置必要的环境变量")
        sys.exit(1)
    
    # 初始化上下文管理器
    context_manager = init_context_manager(
        session_timeout_hours=24,
        max_sessions=1000
    )
    
    # 解析允许的 chat_id
    allowed_chat_ids = None
    if config.TELEGRAM_CHAT_ID:
        try:
            allowed_chat_ids = [
                int(x.strip()) 
                for x in str(config.TELEGRAM_CHAT_ID).split(",")
            ]
            logger.info(f"允许的 Chat IDs: {allowed_chat_ids}")
        except ValueError:
            logger.warning(f"无法解析 TELEGRAM_CHAT_ID: {config.TELEGRAM_CHAT_ID}")
    
    # 创建 Telegram Bot
    bot = TelegramBot(
        token=config.TELEGRAM_BOT_TOKEN,
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
        model=config.OPENAI_MODEL,
        image_model=getattr(config, 'IMAGE_MODEL', 'dall-e-3'),
        allowed_chat_ids=allowed_chat_ids,
        context_manager=context_manager
    )
    
    logger.info(f"AI 模型: {config.OPENAI_MODEL}")
    logger.info(f"API 地址: {config.OPENAI_BASE_URL}")
    
    try:
        # 启动机器人
        await bot.start_polling()
        logger.info("Bot 已启动，等待消息...")
        
        # 保持运行
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    except Exception as e:
        logger.error(f"运行出错: {e}", exc_info=True)
    finally:
        await bot.stop()
        logger.info("Bot 已停止")


def run():
    """同步运行入口"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
