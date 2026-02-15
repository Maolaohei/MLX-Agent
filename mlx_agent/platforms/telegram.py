"""
Telegram 平台适配器 - v0.3.0

支持功能:
- 消息接收和发送
- 流式输出 (使用消息编辑)
- 打字状态显示
- 智能表情反应
- 消息回复
"""

import asyncio
from typing import Optional, Dict, List, AsyncGenerator
from dataclasses import dataclass
import random
import re

from loguru import logger


@dataclass
class TelegramConfig:
    """Telegram 配置"""
    enabled: bool = False
    bot_token: str = ""
    admin_user_id: Optional[str] = None
    webhook_url: Optional[str] = None


class ReactionEngine:
    """表情反应引擎"""
    
    EMOJI_LIBRARY = {
        'greeting': ["👋", "😊", "🤗", "✨", "🌟", "💫"],
        'question': ["🤔", "💭", "❓", "🔍", "🧐", "💡"],
        'code': ["💻", "⚡", "🚀", "🔧", "⌨️", "🛠️"],
        'thanks': ["🙏", "😌", "💝", "🌟", "💖", "🤝"],
        'happy': ["🎉", "😄", "🥳", "✨", "🌈", "💫"],
        'sad': ["😔", "💙", "🤗", "🌈", "💪", "🌻"],
        'angry': ["😤", "💪", "🔥", "⚡", "🌪️", "💢"],
        'confused': ["🤯", "🧐", "💫", "❓", "🌀", "🤔"],
        'waiting': ["⏳", "🕐", "🤔", "💭", "🌙", "☕"],
        'complete': ["✅", "🎊", "✨", "🙌", "🎯", "🏆"],
        'error': ["😅", "🤷", "💫", "🔧", "🛠️", "💭"],
        'thinking': ["🤔", "💭", "🧠", "✨", "🔮", "📚"],
        'surprise': ["😲", "🤩", "✨", "💫", "🌟", "🎊"],
        'love': ["❤️", "💖", "💕", "💗", "🥰", "😍"],
        'cool': ["😎", "🆒", "✨", "🔥", "⚡", "🚀"],
    }
    
    KEYWORD_PATTERNS = {
        'greeting': [r'^(hi|hello|hey|你好|您好|在吗|在？|哈喽)', r'(早上好|下午好|晚上好)'],
        'question': [r'[?？]', r'(怎么|如何|为什么|什么是|在哪里|多少钱|多少)'],
        'code': [r'(代码|编程|python|javascript|js|写个|实现|function|def |class )', r'(报错|错误|bug|fix|修复)'],
        'thanks': [r'(谢谢|感谢|thx|thanks|多谢|谢了)'],
        'happy': [r'(哈哈|嘻嘻|😄|🎉|棒|好耶|太好了|开心)'],
        'sad': [r'(难过|伤心|😢|😭|失败|不行|不能|错误)'],
        'waiting': [r'(等等|等一下|稍后|正在|请稍等|loading|处理中)'],
        'complete': [r'(完成|搞定|好了|done|ok|成功|✅)'],
        'error': [r'(错误|报错|exception|error|failed|失败|bug)'],
        'surprise': [r'(哇|wow|omg|真的吗|不会吧|😲|🤩)'],
        'love': [r'(爱你|喜欢|❤️|💖|😍|🥰|亲亲)'],
    }
    
    def __init__(self, mood: str = 'neutral'):
        self.mood = mood
        self.last_reactions: Dict[str, str] = {}
    
    def detect_mood(self, text: str) -> str:
        """根据消息内容检测情绪"""
        text_lower = text.lower()
        
        mood_scores = {}
        for mood, patterns in self.KEYWORD_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    mood_scores[mood] = mood_scores.get(mood, 0) + 1
        
        if mood_scores:
            return max(mood_scores.items(), key=lambda x: x[1])[0]
        
        if len(text) < 10:
            return 'greeting'
        elif '?' in text or '？' in text:
            return 'question'
        
        return 'thinking'
    
    def get_reaction(self, text: str, user_id: str = None) -> str:
        """获取合适的表情反应"""
        mood = self.detect_mood(text)
        emojis = self.EMOJI_LIBRARY.get(mood, self.EMOJI_LIBRARY['thinking'])
        
        emoji = random.choice(emojis)
        
        if user_id:
            last = self.last_reactions.get(user_id)
            if last == emoji:
                other_emojis = [e for e in emojis if e != last]
                if other_emojis:
                    emoji = random.choice(other_emojis)
            self.last_reactions[user_id] = emoji
        
        return emoji


class TelegramAdapter:
    """Telegram 平台适配器 - 支持流式输出"""
    
    def __init__(self, config: TelegramConfig, agent):
        """初始化适配器
        
        Args:
            config: Telegram 配置
            agent: MLXAgent 实例
        """
        self.config = config
        self.agent = agent
        self.bot = None
        self.application = None
        self.reaction_engine = ReactionEngine()
        self._running = False
        self._typing_tasks: Dict[str, asyncio.Task] = {}
        
        logger.info("Telegram adapter initialized")
    
    async def start_typing_loop(self, chat_id: str):
        """开始持续发送打字状态"""
        if chat_id in self._typing_tasks:
            return
        
        async def loop():
            try:
                while True:
                    await self._send_typing(chat_id)
                    await asyncio.sleep(4.0)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"Typing loop error: {e}")
        
        self._typing_tasks[chat_id] = asyncio.create_task(loop())
        logger.debug(f"Started typing loop for {chat_id}")
    
    async def stop_typing_loop(self, chat_id: str):
        """停止发送打字状态"""
        if chat_id in self._typing_tasks:
            self._typing_tasks[chat_id].cancel()
            try:
                await self._typing_tasks[chat_id]
            except asyncio.CancelledError:
                pass
            del self._typing_tasks[chat_id]
            logger.debug(f"Stopped typing loop for {chat_id}")
    
    async def initialize(self):
        """初始化 Telegram Bot"""
        try:
            from telegram import Bot
            from telegram.ext import Application, MessageHandler, filters, ContextTypes
            
            self._ContextTypes = ContextTypes
            self.bot = Bot(token=self.config.bot_token)
            
            self.application = Application.builder().token(self.config.bot_token).build()
            
            # 添加消息处理器
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
            )
            self.application.add_handler(
                MessageHandler(filters.COMMAND, self._handle_command)
            )
            
            logger.info("Telegram bot initialized")
            
        except ImportError:
            logger.error("python-telegram-bot not installed")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Telegram: {e}")
            raise
    
    async def start(self):
        """启动 Telegram Bot"""
        if not self.application:
            logger.error("Telegram not initialized")
            return
        
        self._running = True
        logger.info("Starting Telegram bot...")
        
        try:
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            
            logger.info("Telegram bot started")
            
            # 保持运行
            while self._running:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"[TELEGRAM] Error in main loop: {e}")
                    await asyncio.sleep(1)
            
            logger.info("[TELEGRAM] Main loop ended")
            
        except Exception as e:
            logger.error(f"Failed to start Telegram: {e}")
            raise
    
    async def stop(self):
        """停止 Telegram Bot - 优雅关闭"""
        self._running = False
        
        # 停止所有打字状态
        for chat_id in list(self._typing_tasks.keys()):
            await self.stop_typing_loop(chat_id)
        
        if self.application:
            try:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                logger.info("Telegram bot stopped")
            except Exception as e:
                logger.warning(f"Error stopping Telegram: {e}")
    
    async def _handle_message(self, update, context):
        """处理文本消息"""
        if not update or not update.message or not update.message.text:
            return
        
        user_id = str(update.message.from_user.id)
        chat_id = str(update.message.chat_id)
        message_id = str(update.message.message_id)
        text = update.message.text
        username = update.message.from_user.username or update.message.from_user.first_name
        
        logger.info(f"[MESSAGE] From {username}({user_id}): {text[:100]}")
        
        try:
            # 发送打字状态
            await self._send_typing(update.effective_chat.id)
            
            # 检查是否需要流式输出（长查询）
            use_streaming = len(text) > 100
            
            if use_streaming and hasattr(self.agent, 'handle_message_stream'):
                # 使用流式输出
                await self._handle_message_stream(
                    chat_id, message_id, text, user_id, username
                )
            else:
                # 普通处理
                response = await self.agent.handle_message(
                    platform="telegram",
                    user_id=user_id,
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    username=username
                )
                
                if response and response.strip():
                    await self.send_message(chat_id, response, reply_to_message_id=message_id)
                
        except Exception as e:
            logger.error(f"[MESSAGE ERROR] {type(e).__name__}: {e}")
            try:
                await self.send_message(chat_id, f"❌ 错误: {str(e)[:100]}", reply_to_message_id=message_id)
            except Exception as e2:
                logger.error(f"Failed to send error message: {e2}")
    
    async def _handle_message_stream(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        user_id: str,
        username: str
    ):
        """处理流式消息"""
        stream_message_id = None
        buffer = ""
        last_update = 0
        update_interval = 0.5  # 最小更新间隔（秒）
        
        try:
            # 先发送一个初始消息
            initial_msg = await self.bot.send_message(
                chat_id=chat_id,
                text="⏳ 正在思考...",
                reply_parameters=ReplyParameters(message_id=int(message_id)) if message_id else None
            )
            stream_message_id = str(initial_msg.message_id)
            
            # 开始流式接收
            async for chunk in self.agent.handle_message_stream(
                platform="telegram",
                user_id=user_id,
                text=text,
                chat_id=chat_id,
                message_id=message_id
            ):
                buffer += chunk
                
                # 检查是否需要更新消息
                current_time = asyncio.get_event_loop().time()
                if current_time - last_update >= update_interval:
                    # 截断到 Telegram 限制
                    display_text = buffer[:4090]
                    if len(buffer) > 4090:
                        display_text += "..."
                    
                    try:
                        await self.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=int(stream_message_id),
                            text=display_text
                        )
                        last_update = current_time
                    except Exception as e:
                        # 忽略编辑失败（可能是相同内容）
                        logger.debug(f"Edit message failed: {e}")
            
            # 最终更新
            if buffer:
                final_text = buffer[:4090]
                if len(buffer) > 4090:
                    # 发送剩余内容
                    await self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=int(stream_message_id),
                        text=final_text
                    )
                else:
                    await self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=int(stream_message_id),
                        text=buffer
                    )
            
        except Exception as e:
            logger.error(f"Stream handling error: {e}")
            # 如果流式失败，回退到普通处理
            if stream_message_id:
                try:
                    await self.bot.delete_message(chat_id=chat_id, message_id=int(stream_message_id))
                except:
                    pass
            
            response = await self.agent.handle_message(
                platform="telegram",
                user_id=user_id,
                text=text,
                chat_id=chat_id,
                message_id=message_id,
                username=username
            )
            if response:
                await self.send_message(chat_id, response, reply_to_message_id=message_id)
    
    async def _handle_command(self, update, context):
        """处理命令"""
        if not update.message or not update.message.text:
            return
        
        command = update.message.text.split()[0].lower()
        chat_id = str(update.message.chat_id)
        message_id = str(update.message.message_id)
        
        logger.info(f"Telegram command: {command}")
        
        if command == '/start':
            await self.send_message(
                chat_id,
                "👋 你好！我是 MLX-Agent v0.3.0\n\n"
                "新功能:\n"
                "• 🌊 流式输出支持\n"
                "• 🧠 ChromaDB 记忆系统\n"
                "• 💓 健康检查端点\n\n"
                "发送消息开始吧！",
                reply_to_message_id=message_id
            )
        elif command == '/help':
            await self.send_message(
                chat_id,
                "📖 帮助\n\n"
                "快速命令:\n"
                "• /start - 开始\n"
                "• /status - 查看状态\n"
                "• /tasks - 查看任务\n\n"
                "长消息会自动使用流式输出~",
                reply_to_message_id=message_id
            )
        else:
            await self._handle_message(update, context)
    
    async def _send_typing(self, chat_id):
        """发送打字状态"""
        try:
            await self.bot.send_chat_action(
                chat_id=chat_id,
                action='typing'
            )
        except Exception as e:
            logger.debug(f"Failed to send typing: {e}")
    
    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_to_message_id: str = None,
        parse_mode: str = 'Markdown'
    ) -> bool:
        """发送消息
        
        Args:
            chat_id: 聊天ID
            text: 消息内容
            reply_to_message_id: 回复的消息ID
            parse_mode: 解析模式 ('Markdown', 'HTML', None)
        
        Returns:
            是否成功发送
        """
        from telegram import ReplyParameters
        
        if not text or not text.strip():
            return False
        
        try:
            # 分割长消息
            max_length = 4096
            parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
            
            for i, part in enumerate(parts):
                kwargs = {
                    'chat_id': chat_id,
                    'text': part,
                }
                
                # 只在第一条消息添加 parse_mode 和 reply
                if i == 0:
                    if parse_mode:
                        kwargs['parse_mode'] = parse_mode
                    if reply_to_message_id:
                        kwargs['reply_parameters'] = ReplyParameters(message_id=int(reply_to_message_id))
                
                try:
                    await self.bot.send_message(**kwargs)
                except Exception as e:
                    # Markdown 解析失败，降级为纯文本
                    if 'parse_mode' in kwargs:
                        logger.warning(f"Markdown send failed, retrying with plain text: {e}")
                        kwargs.pop('parse_mode', None)
                        await self.bot.send_message(**kwargs)
                    else:
                        raise
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def send_message_stream(
        self,
        chat_id: str,
        text_stream: AsyncGenerator[str, None],
        reply_to_message_id: str = None,
        update_interval: float = 0.5
    ) -> bool:
        """发送流式消息（使用消息编辑模拟）
        
        Args:
            chat_id: 聊天ID
            text_stream: 文本流生成器
            reply_to_message_id: 回复的消息ID
            update_interval: 更新间隔（秒）
        
        Returns:
            是否成功发送
        """
        from telegram import ReplyParameters
        
        stream_message_id = None
        buffer = ""
        last_update = 0
        
        try:
            # 发送初始消息
            initial_msg = await self.bot.send_message(
                chat_id=chat_id,
                text="⏳ 正在生成...",
                reply_parameters=ReplyParameters(message_id=int(reply_to_message_id)) if reply_to_message_id else None
            )
            stream_message_id = initial_msg.message_id
            
            # 接收流式内容
            async for chunk in text_stream:
                buffer += chunk
                
                current_time = asyncio.get_event_loop().time()
                if current_time - last_update >= update_interval:
                    # 截断到 Telegram 限制
                    display_text = buffer[:4090]
                    if len(buffer) > 4090:
                        display_text += "..."
                    
                    try:
                        await self.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=stream_message_id,
                            text=display_text
                        )
                        last_update = current_time
                    except Exception as e:
                        logger.debug(f"Edit message failed: {e}")
            
            # 最终更新
            if buffer:
                final_text = buffer[:4090]
                if len(buffer) > 4090:
                    await self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=stream_message_id,
                        text=final_text
                    )
                else:
                    await self.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=stream_message_id,
                        text=buffer
                    )
            
            return True
            
        except Exception as e:
            logger.error(f"Stream send failed: {e}")
            return False
    
    async def update_message(self, chat_id: str, message_id: str, text: str) -> bool:
        """更新已发送的消息
        
        Args:
            chat_id: 聊天ID
            message_id: 消息ID
            text: 新内容
        
        Returns:
            是否成功更新
        """
        try:
            await self.bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(message_id),
                text=text[:4090],  # 截断到限制
                parse_mode='Markdown'
            )
            return True
        except Exception as e:
            logger.debug(f"Failed to update message: {e}")
            return False
