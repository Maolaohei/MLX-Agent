"""
Telegram 平台表情回应实现
"""

from typing import Optional
from loguru import logger


class TelegramReactor:
    """
    Telegram 表情回应器
    
    支持 Telegram 的 Reaction 功能
    """
    
    def __init__(self, bot):
        self.bot = bot
    
    async def react(
        self,
        chat_id: int,
        message_id: int,
        emoji: str,
        is_big: bool = False
    ) -> bool:
        """
        发送表情回应
        
        Args:
            chat_id: 聊天 ID
            message_id: 消息 ID
            emoji: 表情字符
            is_big: 是否发送大表情（动画）
        
        Returns:
            是否成功
        """
        try:
            # 使用 python-telegram-bot 的 set_message_reaction
            await self.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[emoji],
                is_big=is_big
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to send reaction: {e}")
            return False
    
    async def remove_reaction(self, chat_id: int, message_id: int) -> bool:
        """移除表情回应"""
        try:
            await self.bot.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=[]  # 空列表表示移除
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to remove reaction: {e}")
            return False
