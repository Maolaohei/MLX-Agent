"""
智能表情回应系统

比 OpenClaw 更丰富、更智能的表情反应：
- 多维度情绪分析
- 丰富的表情库
- 平台适配
- 历史去重
- Shinobu 专属风格
"""

from .engine import ReactionEngine, ReactionCategory
from .telegram import TelegramReactor

__all__ = [
    "ReactionEngine",
    "ReactionCategory",
    "TelegramReactor"
]
