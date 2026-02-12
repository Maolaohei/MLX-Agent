"""
Telegram 平台适配器

使用 python-telegram-bot 库
"""

import asyncio
from typing import Optional

from loguru import logger
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from mlx_agent.config import PlatformConfig


class TelegramAdapter:
    """Telegram Bot 适配器"""
    
    def __init__(self, config: PlatformConfig, agent):
        self.config = config
        self.agent = agent
        self.application: Optional[Application] = None
        self._running = False
        
    async def initialize(self):
        """初始化 Telegram Bot"""
        if not self.config.enabled:
            logger.info("Telegram adapter disabled")
            return
            
        if not self.config.bot_token:
            logger.warning("Telegram bot token not configured")
            return
            
        # 创建 Application
        self.application = (
            Application.builder()
            .token(self.config.bot_token)
            .build()
        )
        
        # 注册处理器
        self.application.add_handler(CommandHandler("start", self._cmd_start))
        self.application.add_handler(CommandHandler("help", self._cmd_help))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        
        logger.info("Telegram adapter initialized")
    
    async def start(self):
        """启动 Bot"""
        if not self.application:
            logger.warning("Telegram application not initialized")
            return
            
        self._running = True
        logger.info("Starting Telegram bot...")
        
        # 启动 polling
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("Telegram bot started")
        
        # 保持运行
        while self._running:
            await asyncio.sleep(1)
    
    async def stop(self):
        """停止 Bot"""
        self._running = False
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Telegram bot stopped")
    
    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/start 命令"""
        await update.message.reply_text(
            "🚀 MLX-Agent 已启动！\n"
            "我是你的高性能 AI 助手。\n"
            "发送消息即可开始对话。"
        )
    
    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/help 命令"""
        await update.message.reply_text(
            "🤖 MLX-Agent 帮助\n"
            "\n"
            "可用命令:\n"
            "/start - 启动机器人\n"
            "/help - 显示帮助\n"
            "\n"
            "直接发送消息即可对话。"
        )
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理文本消息"""
        if not update.message or not update.message.text:
            return
            
        user_id = str(update.effective_user.id)
        chat_id = str(update.effective_chat.id)
        text = update.message.text
        
        logger.info(f"Telegram message from {user_id}: {text[:50]}...")
        
        try:
            # 显示输入中
            await context.bot.send_chat_action(
                chat_id=chat_id,
                action="typing"
            )
            
            # 交给 Agent 处理
            response = await self.agent.handle_message(
                platform="telegram",
                user_id=user_id,
                text=text
            )
            
            # 发送回复
            await update.message.reply_text(response)
            
        except Exception as e:
            logger.error(f"Error handling Telegram message: {e}")
            await update.message.reply_text(
                f"❌ 处理消息时出错: {str(e)[:200]}"
            )
    
    async def send_message(self, chat_id: str, text: str):
        """主动发送消息"""
        if self.application:
            await self.application.bot.send_message(chat_id=chat_id, text=text)
