"""
原生 Python Skill 基类

用于实现高性能的原生 Skill
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass


@dataclass
class SkillContext:
    """Skill 执行上下文"""
    agent: Any  # MLXAgent 实例
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    platform: Optional[str] = None
    memory: Optional[List[Dict]] = None
    
    async def search_memory(self, query: str, top_k: int = 5):
        """搜索记忆"""
        if self.agent and self.agent.memory:
            return await self.agent.memory.search(query, top_k)
        return []
    
    async def add_memory(self, content: str, metadata: Dict = None):
        """添加记忆"""
        if self.agent and self.agent.memory:
            return await self.agent.memory.add(content, metadata)


@dataclass
class SkillResult:
    """Skill 执行结果"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: Dict = None


class NativeSkill(ABC):
    """原生 Python Skill 基类
    
    所有原生 Skill 都应继承此类
    
    Example:
        class WeatherSkill(NativeSkill):
            name = "weather"
            description = "查询天气"
            triggers = ["天气", "weather"]
            
            async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
                city = kwargs.get("city", "北京")
                weather = await self.fetch_weather(city)
                return SkillResult(success=True, output=weather)
    """
    
    # Skill 元数据
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    
    # 触发词列表
    triggers: List[str] = []
    
    # 所需权限
    permissions: List[str] = []
    
    def __init__(self, agent=None):
        self.agent = agent
    
    @abstractmethod
    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        """执行 Skill
        
        Args:
            context: 执行上下文
            **kwargs: 额外参数
            
        Returns:
            SkillResult
        """
        pass
    
    def match_intent(self, text: str) -> float:
        """匹配意图，返回置信度 (0-1)
        
        Args:
            text: 用户输入
            
        Returns:
            匹配置信度，0 表示不匹配
        """
        text_lower = text.lower()
        for trigger in self.triggers:
            if trigger.lower() in text_lower:
                return 1.0
        return 0.0
    
    async def before_execute(self, context: SkillContext):
        """执行前钩子"""
        pass
    
    async def after_execute(self, context: SkillContext, result: SkillResult):
        """执行后钩子"""
        pass


# 常用原生 Skill 示例
class EchoSkill(NativeSkill):
    """回声 Skill - 测试用"""
    
    name = "echo"
    description = "回显用户输入"
    triggers = ["echo", "回显"]
    
    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        text = kwargs.get("text", "Hello World")
        return SkillResult(success=True, output=f"Echo: {text}")


class MemorySkill(NativeSkill):
    """记忆管理 Skill"""
    
    name = "memory"
    description = "管理记忆"
    triggers = ["记住", "记忆", "remember"]
    
    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        action = kwargs.get("action", "add")
        
        if action == "add":
            content = kwargs.get("content", "")
            if not content:
                return SkillResult(success=False, error="Content is required")
            
            memory = await context.add_memory(content)
            return SkillResult(success=True, output=f"已记住: {content[:50]}...")
        
        elif action == "search":
            query = kwargs.get("query", "")
            results = await context.search_memory(query)
            return SkillResult(success=True, output=results)
        
        return SkillResult(success=False, error=f"Unknown action: {action}")
