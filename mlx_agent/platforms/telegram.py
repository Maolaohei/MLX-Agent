"""
Telegram 平台适配器

支持功能:
- 消息接收和发送
- 打字状态显示
- 智能表情反应
- 消息回复
"""

import asyncio
from typing import Optional, Dict, List
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
    """表情反应引擎
    
    根据消息内容和上下文动态选择表情
    """
    
    # 表情库
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
    
    # 关键词映射
    KEYWORD_PATTERNS = {
        'greeting': [r'^(hi|hello|hey|你好|您好|在吗|在？|哈喽)', r'(早上好|下午好|晚上好)'],
        'question': [r'[?？]', r'(怎么|如何|为什么|什么是|在哪里|多少钱|多少)'],
        'code': [r'(代码|编程|python|javascript|js|写个|实现|function|def |class )', r'(报错|错误|bug|fix|修复)'],
        'thanks': [r'(谢谢|感谢|thx|thanks|多谢|谢了)'],
        'happy': [r'(哈哈|嘻嘻|😄|🎉|棒|好耶|太好了|开心)'],
        'sad': [r'(难过|伤心|😢|😭|失败|不行|不能|错误)'],
        'angry': [r'(生气|愤怒|😤|妈的|混蛋|垃圾|烦)'],
        'waiting': [r'(等等|等一下|稍后|正在|请稍等|loading|处理中)'],
        'complete': [r'(完成|搞定|好了|done|ok|成功|✅)'],
        'error': [r'(错误|报错|exception|error|failed|失败|bug)'],
        'surprise': [r'(哇|wow|omg|真的吗|不会吧|😲|🤩)'],
        'love': [r'(爱你|喜欢|❤️|💖|😍|🥰|亲亲)'],
    }
    
    def __init__(self, mood: str = 'neutral'):
        self.mood = mood
        self.last_reactions: Dict[str, str] = {}  # 避免重复发送相同表情
    
    def detect_mood(self, text: str) -> str:
        """根据消息内容检测情绪
        
        Args:
            text: 用户消息
            
        Returns:
            情绪类型
        """
        text_lower = text.lower()
        
        # 检查关键词匹配
        mood_scores = {}
        for mood, patterns in self.KEYWORD_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    mood_scores[mood] = mood_scores.get(mood, 0) + 1
        
        # 返回得分最高的情绪，如果没有匹配则返回 'thinking'
        if mood_scores:
            return max(mood_scores.items(), key=lambda x: x[1])[0]
        
        # 根据消息长度判断
        if len(text) < 10:
            return 'greeting'
        elif '?' in text or '？' in text:
            return 'question'
        
        return 'thinking'
    
    def get_reaction(self, text: str, user_id: str = None) -> str:
        """获取合适的表情反应
        
        Args:
            text: 用户消息
            user_id: 用户ID（用于避免重复）
            
        Returns:
            表情符号
        """
        mood = self.detect_mood(text)
        emojis = self.EMOJI_LIBRARY.get(mood, self.EMOJI_LIBRARY['thinking'])
        
        # 随机选择一个表情
        emoji = random.choice(emojis)
        
        # 避免对同一用户重复发送相同表情
        if user_id:
            last = self.last_reactions.get(user_id)
            if last == emoji:
                # 选择不同的表情
                other_emojis = [e for e in emojis if e != last]
                if other_emojis:
                    emoji = random.choice(other_emojis)
            self.last_reactions[user_id] = emoji
        
        return emoji
    
    def get_typing_duration(self, text: str) -> float:
        """根据消息长度计算打字状态持续时间
        
        Args:
            text: 用户消息
            
        Returns:
            持续时间（秒）
        """
        # 基础时间 + 根据长度增加的时间
        base_time = 1.5
        char_time = len(text) * 0.02  # 每个字符20ms
        return min(base_time + char_time, 5.0)  # 最多5秒


class TelegramAdapter:
    """Telegram 平台适配器"""
    
    def __init__(self, config: TelegramConfig, agent):
        """初始化适配器
        
        Args:
            config: Telegram 配置
            agent: MLXAgent 实例
        """
        self.config = config
        self.agent = agent
        self.bot = None
        self.reaction_engine = ReactionEngine()
        self._running = False
        self._typing_tasks: Dict[str, asyncio.Task] = {}  # chat_id -> task
        
        logger.info("Telegram adapter initialized")
        
    async def start_typing_loop(self, chat_id: str):
        """开始持续发送打字状态"""
        if chat_id in self._typing_tasks:
            return
            
        async def loop():
            try:
                while True:
                    await self._send_typing(chat_id)
                    await asyncio.sleep(4.0)  # Telegram typing lasts ~5s
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
            del self._typing_tasks[chat_id]
            logger.debug(f"Stopped typing loop for {chat_id}")
    
    async def initialize(self):
        """初始化 Telegram Bot"""
        try:
            from telegram import Bot
            from telegram.ext import Application, MessageHandler, filters, ContextTypes
            
            # 保存 ContextTypes 用于类型提示
            self._ContextTypes = ContextTypes
            
            self.bot = Bot(token=self.config.bot_token)
            
            # 创建应用
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
            logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
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
        
        # 启动轮询
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)
        
        logger.info("Telegram bot started")
        
        # 保持运行 - 添加错误处理防止意外退出
        logger.debug("[TELEGRAM] Entering main loop...")
        loop_count = 0
        while self._running:
            try:
                await asyncio.sleep(1)
                loop_count += 1
                if loop_count % 60 == 0:  # 每分钟记录一次
                    logger.debug(f"[TELEGRAM] Main loop alive, iteration {loop_count}")
            except Exception as e:
                logger.error(f"[TELEGRAM] Error in main loop: {e}")
                await asyncio.sleep(1)
        
        logger.info("[TELEGRAM] Main loop ended")
    
    async def stop(self):
        """停止 Telegram Bot"""
        self._running = False
        
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        
        logger.info("Telegram bot stopped")
    
    async def _handle_message(self, update, context):
        """处理文本消息"""
        logger.info(f"[TELEGRAM] _handle_message called! update_id={update.update_id if update else 'None'}")
        
        if not update:
            logger.error("[TELEGRAM] Update is None!")
            return
            
        if not update.message:
            logger.error("[TELEGRAM] update.message is None!")
            return
            
        if not update.message.text:
            logger.info("[TELEGRAM] Message has no text, ignoring")
            return
        
        user_id = str(update.message.from_user.id)
        chat_id = str(update.message.chat_id)
        message_id = str(update.message.message_id)
        text = update.message.text
        username = update.message.from_user.username or update.message.from_user.first_name
        
        logger.info(f"[MESSAGE] From {username}({user_id}): {text[:100]}")
        logger.debug(f"[MESSAGE] chat_id={chat_id}, message_id={message_id}")
        
        try:
            # 可选：发送表情反应（已读确认），但不阻塞文字回复
            # await self._send_reaction(update, text, user_id)
            
            logger.debug("[MESSAGE] Sending typing indicator...")
            # 发送打字状态
            await self._send_typing(update.effective_chat.id)
            
            logger.debug("[MESSAGE] Calling agent.handle_message...")
            # 处理消息
            response = await self.agent.handle_message(
                platform="telegram",
                user_id=user_id,
                text=text,
                chat_id=chat_id,
                message_id=message_id,
                username=username
            )
            
            logger.debug(f"[MESSAGE] Got response: {response[:100] if response else 'None'}...")
            
            # 发送回复 (忽略空消息)
            if response and response.strip():
                logger.debug("[MESSAGE] Sending response...")
                result = await self.send_message(chat_id, response, reply_to_message_id=message_id)
                logger.debug(f"[MESSAGE] Send result: {result}")
            else:
                logger.debug("[MESSAGE] Empty response, ignoring")
                
        except Exception as e:
            logger.error(f"[MESSAGE ERROR] {type(e).__name__}: {e}")
            logger.exception("[MESSAGE ERROR] Full traceback:")
            try:
                await self.send_message(chat_id, f"❌ 错误: {str(e)[:100]}", reply_to_message_id=message_id)
            except Exception as e2:
                logger.error(f"[MESSAGE ERROR] Failed to send error message: {e2}")
    
    def _should_reply_with_text(self, text: str) -> bool:
        """判断是否需要文字回复
        
        现在所有消息都会回复文字（正常 AI 助手模式）
        表情反应仅作为辅助，不替代文字回复
        """
        # 纯表情消息可以不回复文字
        if self._is_only_emojis(text.strip()):
            return False
        
        # 其他所有消息都回复文字
        return True
    
    def _is_only_emojis(self, text: str) -> bool:
        """检查是否只有表情符号"""
        # 简单检查：去除常见标点后是否还有字母/汉字
        cleaned = text.replace(' ', '').replace('！', '').replace('？', '').replace('。', '')
        cleaned = cleaned.replace('~', '').replace('…', '').replace(',', '').replace('，', '')
        # 如果清理后长度小于原长度的一半，可能是纯表情
        return len(cleaned) < 3
    
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
                "👋 你好！我是 MLX-Agent\n\n"
                "我可以帮你:\n"
                "• 💬 聊天对话\n"
                "• 🧠 记忆和学习\n"
                "• ⚡ 执行各种任务\n\n"
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
                "我会根据你的消息自动选择表情反应哦~",
                reply_to_message_id=message_id
            )
        else:
            # 其他命令当作普通消息处理
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
    
    async def _send_reaction(self, update, text: str, user_id: str):
        """发送表情反应
        
        模拟已读和心情
        """
        try:
            # 获取合适的表情
            emoji = self.reaction_engine.get_reaction(text, user_id)
            
            # 方法1: 添加消息反应 (需要 Bot API 6.4+)
            reaction_sent = False
            try:
                await self.bot.set_message_reaction(
                    chat_id=update.effective_chat.id,
                    message_id=update.message.message_id,
                    reaction=[{"type": "emoji", "emoji": emoji}]
                )
                reaction_sent = True
                logger.debug(f"Reaction sent: {emoji}")
            except Exception as e:
                logger.debug(f"set_message_reaction failed: {e}")
            
            # 方法2: 如果反应失败，发送表情消息
            if not reaction_sent:
                try:
                    await update.message.reply_text(emoji)
                    logger.debug(f"Emoji reply sent: {emoji}")
                except Exception as e2:
                    logger.debug(f"Emoji reply failed: {e2}")
                
        except Exception as e:
            logger.debug(f"Failed to send reaction: {e}")
    
    async def send_message(self, chat_id: str, text: str, reply_to_message_id: str = None) -> bool:
        """发送消息
        
        Args:
            chat_id: 聊天ID
            text: 消息内容
            reply_to_message_id: 回复的消息ID
            
        Returns:
            是否成功发送
        """
        try:
            from telegram import ReplyParameters
            
            # 分割长消息
            max_length = 4096
            parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
            
            for i, part in enumerate(parts):
                kwargs = {
                    'chat_id': chat_id,
                    'text': part,
                    'parse_mode': 'Markdown'
                }
                
                if i == 0 and reply_to_message_id:
                    kwargs['reply_parameters'] = ReplyParameters(message_id=int(reply_to_message_id))
                
                try:
                    await self.bot.send_message(**kwargs)
                except Exception as e:
                    # Markdown 解析失败，降级为纯文本
                    logger.warning(f"Markdown send failed, retrying with plain text: {e}")
                    kwargs.pop('parse_mode', None)
                    await self.bot.send_message(**kwargs)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def update_message(self, chat_id: str, message_id: str, text: str) -> bool:
        """更新已发送的消息（用于进度更新）
        
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
                text=text,
                parse_mode='Markdown'
            )
            return True
        except Exception as e:
            logger.debug(f"Failed to update message: {e}")
            return False

