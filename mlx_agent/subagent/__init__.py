"""
子代理系统 - 真·隔离任务执行

提供类似 OpenClaw sessions_spawn 的功能：
- 完全隔离的 Agent 实例
- 独立的记忆、工具、LLM 配置
- 异步执行和回调机制
- 超时控制和错误隔离
"""

from .core import SubAgent, SubAgentConfig, SubAgentResult, SubAgentStatus
from .pool import SubAgentPool
from .manager import SubAgentManager

__all__ = [
    "SubAgent",
    "SubAgentConfig", 
    "SubAgentResult",
    "SubAgentStatus",
    "SubAgentPool",
    "SubAgentManager",
    "create_sub_agent"
]
