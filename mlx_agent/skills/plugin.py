import inspect
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel, Field

class PluginMetadata(BaseModel):
    """插件元数据"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "User"
    hidden: bool = False  # 是否对 LLM 隐藏（用于内部工具）

class BasePlugin(ABC):
    """
    所有 MLX-Agent 插件的基类。
    用户只需继承此类，实现 define_tools 和 execute 方法。
    """
    
    def __init__(self, context: Any = None):
        self.context = context
        self._metadata = self.on_load()

    @abstractmethod
    def on_load(self) -> PluginMetadata:
        """插件加载时调用，返回元数据"""
        pass

    @abstractmethod
    def define_tools(self) -> list[dict]:
        """
        定义 OpenAI 格式的 Tool Schema
        """
        pass

    @abstractmethod
    async def execute(self, name: str, arguments: dict, context: dict) -> Any:
        """
        执行工具调用
        Args:
            name: 工具名称 (function name)
            arguments: 参数字典
            context: 执行上下文 (user_id, chat_id 等)
        Returns:
            执行结果 (str, dict, or SkillResult)
        """
        pass

    async def on_unload(self):
        """插件卸载/重载时调用（用于清理资源）"""
        pass
