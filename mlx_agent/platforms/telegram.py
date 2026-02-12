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
        
        logger.info("Telegram adapter initialized")
    
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
        
        # 保持运行
        while self._running:
            await asyncio.sleep(1)
    
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
        if not update.message or not update.message.text:
            return
        
        user_id = str(update.message.from_user.id)
        chat_id = str(update.message.chat_id)
        message_id = str(update.message.message_id)
        text = update.message.text
        username = update.message.from_user.username or update.message.from_user.first_name
        
        logger.info(f"Telegram message from {username}({user_id}): {text[:50]}...")
        
        try:
            # 1. 发送表情反应（已读确认）- 立即发送，无需等待
            await self._send_reaction(update, text, user_id)
            
            # 2. 判断是否需要文字回复
            # 简短问候/感叹只回复表情，不回复文字
            if self._should_reply_with_text(text):
                # 发送打字状态
                await self._send_typing(update.effective_chat.id)
                
                # 处理消息
                response = await self.agent.handle_message(
                    platform="telegram",
                    user_id=user_id,
                    text=text,
                    chat_id=chat_id,
                    message_id=message_id,
                    username=username
                )
                
                # 发送回复
                if response:
                    await self.send_message(chat_id, response, reply_to_message_id=message_id)
            else:
                # 只回复表情，不处理复杂逻辑
                logger.debug(f"Short message '{text[:20]}...' - emoji only")
                
        except Exception as e:
            logger.error(f"Error handling Telegram message: {e}")
            # 错误时不回复，避免刷屏
            pass
    
    def _should_reply_with_text(self, text: str) -> bool:
        """判断是否需要文字回复
        
        简短消息（如"哈喽"、"你好"、"啊"）只回复表情
        复杂消息才回复文字
        
        Args:
            text: 用户消息
            
        Returns:
            是否需要文字回复
        """
        # 去除空白
        text = text.strip()
        
        # 长度检查 - 短消息只回复表情
        if len(text) <= 10:
            return False
        
        # 简单问候检查
        simple_greetings = [
            'hi', 'hello', 'hey', '你好', '您好', '哈喽', '在吗', '在？',
            '你好呀', '哈喽呀', 'hi~', 'hello~', 'hey~',
            '啊', '哦', '嗯', '哈', '嘿', '哎', '哇'
        ]
        if text.lower() in simple_greetings:
            return False
        
        # 纯表情不回复文字
        if self._is_only_emojis(text):
            return False
        
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
            
            # 方法1: 回复消息带表情
            # await update.message.reply_text(emoji)
            
            # 方法2: 添加消息反应 (需要 Bot API 6.4+)
            try:
                await self.bot.set_message_reaction(
                    chat_id=update.effective_chat.id,
                    message_id=update.message.message_id,
                    reaction=[{"type": "emoji", "emoji": emoji}]
                )
            except Exception:
                # 如果不支持反应，发送一个短暂的状态消息
                pass
                
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
            if len(text) > max_length:
                parts = [text[i:i+max_length] for i in range(0, len(text), max_length)]
            else:
                parts = [text]
            
            for i, part in enumerate(parts):
                kwargs = {
                    'chat_id': chat_id,
                    'text': part,
                    'parse_mode': 'Markdown'
                }
                
                # 只有第一部分回复原消息
                if i == 0 and reply_to_message_id:
                    kwargs['reply_parameters'] = ReplyParameters(message_id=int(reply_to_message_id))
                
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

