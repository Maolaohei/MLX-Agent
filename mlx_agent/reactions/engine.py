"""
表情回应引擎
"""

import re
import random
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta

from loguru import logger


class ReactionCategory(Enum):
    """表情类别"""
    ACKNOWLEDGE = "acknowledge"      # 确认/理解
    THINKING = "thinking"            # 思考/处理中
    SUCCESS = "success"              # 成功/完成
    ERROR = "error"                  # 错误/警告
    EMPATHY = "empathy"              # 情感共鸣
    HUMOR = "humor"                  # 幽默/玩笑
    SHINOBU = "shinobu"              # 吸血鬼风格
    PROFESSIONAL = "professional"    # 工作/专业
    LEARNING = "learning"            # 学习/知识
    EXCITED = "excited"              # 兴奋/激动
    CONFUSED = "confused"            # 困惑


@dataclass
class ReactionHistory:
    """表情使用历史"""
    emoji: str
    timestamp: datetime
    category: str
    message_snippet: str


class ReactionEngine:
    """
    智能表情回应引擎
    
    特性：
    - 10+ 表情类别，50+ 表情
    - 消息类型分类
    - 情绪检测
    - 历史去重
    - 平台适配
    """
    
    # 丰富的表情库 (比 OpenClaw 更丰富)
    EMOJI_CATEGORIES: Dict[ReactionCategory, List[str]] = {
        ReactionCategory.ACKNOWLEDGE: [
            "👍", "👌", "✅", "🆗", "💯", "✨", "🫡", "🎯", "📌", "🔖"
        ],
        ReactionCategory.THINKING: [
            "🤔", "💭", "🧐", "🔍", "📊", "🤖", "📝", "📋", "🔎", "📈"
        ],
        ReactionCategory.SUCCESS: [
            "🎉", "✨", "🌟", "💪", "🏆", "🎯", "✅", "🚀", "🌈", "⭐"
        ],
        ReactionCategory.ERROR: [
            "⚠️", "❗", "🚫", "💥", "😅", "🤦", "❌", "🛑", "🔴", "⚡"
        ],
        ReactionCategory.EMPATHY: [
            "❤️", "🫂", "💙", "🌈", "🌸", "☀️", "💝", "💖", "💗", "💓"
        ],
        ReactionCategory.HUMOR: [
            "😄", "🤣", "😏", "🤪", "👻", "🎭", "🤡", "🎪", "🎨", "🎬"
        ],
        ReactionCategory.SHINOBU: [
            "🦇", "🌙", "🍩", "⚡", "🖤", "🧛", "🦉", "🌑", "✝️", "🔮"
        ],
        ReactionCategory.PROFESSIONAL: [
            "📋", "📊", "💼", "🔧", "⚙️", "📈", "📉", "🏢", "📅", "⏰"
        ],
        ReactionCategory.LEARNING: [
            "📚", "💡", "🎓", "🔬", "🌟", "✨", "📖", "🔭", "🧬", "🧮"
        ],
        ReactionCategory.EXCITED: [
            "🎊", "🎉", "🤩", "😍", "🔥", "💫", "✨", "🌟", "💥", "🎆"
        ],
        ReactionCategory.CONFUSED: [
            "😕", "🤨", "🧐", "🤷", "❓", "❔", "🤯", "😵", "🌀", "💫"
        ]
    }
    
    # 消息类型匹配模式
    MESSAGE_PATTERNS: Dict[str, List[str]] = {
        "question": [r"^[?？]|^(什么|怎么|为什么|如何|哪里|谁|什么时候|多少)", r"^\\?"],
        "command": [r"^(执行|运行|开始|停止|查看|检查|启动|关闭|重启|安装|更新|删除|创建)"],
        "greeting": [r"^(你好|您好|嗨|hello|hi|👋|早上好|晚上好|早安|晚安)"],
        "thanks": [r"(谢谢|感谢|thx|thanks|🙏|多谢|感激)"],
        "joke": [r"(哈哈|好笑|😄|🤣|开玩笑|幽默|😂|😆|😹)"],
        "error": [r"(错误|失败|出错|error|fail|broken|crashed|exception|timeout)"],
        "success": [r"(完成|成功|搞定|done|success|✅|finished|ok|good|great)"],
        "help": [r"(帮助|help|assist|support|文档|document|guide|怎么|如何)"],
        "urgent": [r"(紧急|urgent|asap|立即|马上|快|hurry|critical|important)"],
        "complaint": [r"(不好|差|慢|卡|bug|问题|problem|issue|fix|repair)"]
    }
    
    def __init__(self, max_history: int = 20):
        self.max_history = max_history
        self.history: List[ReactionHistory] = []
        self._category_usage: Dict[ReactionCategory, int] = {cat: 0 for cat in ReactionCategory}
    
    def react(
        self,
        message: str,
        context: Optional[Dict] = None,
        platform: str = "telegram",
        prefer_shinobu: bool = False
    ) -> Optional[str]:
        """
        分析消息并返回合适的表情
        
        Args:
            message: 消息内容
            context: 上下文信息
            platform: 平台类型
            prefer_shinobu: 是否优先使用 Shinobu 风格表情
        
        Returns:
            表情字符或 None
        """
        if not message:
            return None
        
        context = context or {}
        
        # 1. 分析消息类型
        msg_type = self._classify_message(message)
        
        # 2. 检测情绪
        emotion = self._detect_emotion(message, context)
        
        # 3. 选择类别
        category = self._select_category(msg_type, emotion, prefer_shinobu)
        
        # 4. 选择具体表情（避免重复）
        emoji = self._select_emoji(category, avoid_recent=3)
        
        # 5. 记录历史
        if emoji:
            self._record_usage(emoji, category, message)
        
        return emoji
    
    def _classify_message(self, message: str) -> str:
        """分类消息类型"""
        message_lower = message.lower()
        
        for msg_type, patterns in self.MESSAGE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    return msg_type
        
        return "general"
    
    def _detect_emotion(self, message: str, context: Dict) -> str:
        """检测情绪"""
        # 基于标点符号
        if "!!!" in message or "！！！" in message:
            return "very_excited"
        elif message.endswith(("!", "！")):
            return "excited"
        elif message.endswith(("?", "？")):
            return "curious"
        elif "..." in message or "。。。" in message:
            return "thinking"
        
        # 基于上下文
        if context.get("is_error"):
            return "concerned"
        elif context.get("is_success"):
            return "happy"
        elif context.get("is_first_message"):
            return "welcoming"
        
        return "neutral"
    
    def _select_category(
        self,
        msg_type: str,
        emotion: str,
        prefer_shinobu: bool
    ) -> ReactionCategory:
        """选择表情类别"""
        
        # Shinobu 风格优先
        if prefer_shinobu and random.random() < 0.3:
            return ReactionCategory.SHINOBU
        
        # 消息类型映射
        type_mapping = {
            "question": ReactionCategory.THINKING,
            "command": ReactionCategory.PROFESSIONAL,
            "greeting": ReactionCategory.HUMOR,
            "thanks": ReactionCategory.EMPATHY,
            "joke": ReactionCategory.HUMOR,
            "error": ReactionCategory.ERROR,
            "success": ReactionCategory.SUCCESS,
            "help": ReactionCategory.LEARNING,
            "urgent": ReactionCategory.ERROR,
            "complaint": ReactionCategory.EMPATHY
        }
        
        # 情绪映射
        emotion_mapping = {
            "very_excited": ReactionCategory.EXCITED,
            "excited": ReactionCategory.EXCITED,
            "curious": ReactionCategory.THINKING,
            "thinking": ReactionCategory.THINKING,
            "concerned": ReactionCategory.ERROR,
            "happy": ReactionCategory.SUCCESS,
            "welcoming": ReactionCategory.HUMOR
        }
        
        # 优先使用情绪映射
        if emotion in emotion_mapping:
            return emotion_mapping[emotion]
        
        return type_mapping.get(msg_type, ReactionCategory.ACKNOWLEDGE)
    
    def _select_emoji(
        self,
        category: ReactionCategory,
        avoid_recent: int = 3
    ) -> Optional[str]:
        """从类别中选择表情"""
        candidates = self.EMOJI_CATEGORIES.get(category, ["👍"])
        
        # 获取最近使用的表情
        recent_emojis = {h.emoji for h in self.history[-avoid_recent:]}
        
        # 过滤掉最近用过的
        available = [e for e in candidates if e not in recent_emojis]
        
        # 如果都用过，就随机选
        if not available:
            available = candidates
        
        # 考虑类别使用频率，避免总是用同一类
        weights = []
        for emoji in available:
            # 使用越少权重越高
            usage_count = sum(1 for h in self.history if h.emoji == emoji)
            weight = 1.0 / (1 + usage_count * 0.5)
            weights.append(weight)
        
        # 加权随机选择
        return random.choices(available, weights=weights, k=1)[0] if available else None
    
    def _record_usage(self, emoji: str, category: ReactionCategory, message: str):
        """记录表情使用"""
        history = ReactionHistory(
            emoji=emoji,
            timestamp=datetime.now(),
            category=category.value,
            message_snippet=message[:30]
        )
        
        self.history.append(history)
        self._category_usage[category] += 1
        
        # 限制历史长度
        if len(self.history) > self.max_history:
            self.history.pop(0)
    
    def get_stats(self) -> Dict:
        """获取使用统计"""
        return {
            "total_reactions": len(self.history),
            "category_usage": {
                cat.value: count
                for cat, count in self._category_usage.items()
                if count > 0
            },
            "recent_history": [
                {
                    "emoji": h.emoji,
                    "category": h.category,
                    "time": h.timestamp.isoformat()
                }
                for h in self.history[-10:]
            ]
        }
