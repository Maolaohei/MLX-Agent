"""
原生技能基类

纯 Python 实现，无需外部依赖
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime


@dataclass
class SkillContext:
    """技能上下文"""
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    platform: Optional[str] = None
    message_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SkillResult:
    """技能执行结果"""
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


class NativeSkill(ABC):
    """原生技能基类
    
    所有原生 Python 技能应继承此类
    """
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._initialized = False
    
    @abstractmethod
    async def execute(self, action: str, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        """执行技能
        
        Args:
            action: 动作名称
            params: 参数
            context: 上下文
            
        Returns:
            SkillResult: 执行结果
        """
        pass
    
    @abstractmethod
    def get_tools(self) -> List[Dict]:
        """获取工具定义 (OpenAI Function Calling 格式)"""
        pass
    
    async def initialize(self):
        """初始化技能"""
        self._initialized = True
    
    async def cleanup(self):
        """清理资源"""
        self._initialized = False


class MemorySkill(NativeSkill):
    """记忆技能 - 直接与记忆系统交互"""
    
    def __init__(self, memory_manager=None):
        super().__init__(
            name="memory",
            description="记忆管理: 存储、检索、删除记忆"
        )
        self.memory_manager = memory_manager
    
    async def execute(self, action: str, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        """执行记忆操作"""
        if not self.memory_manager:
            return SkillResult(success=False, output=None, error="Memory manager not available")
        
        try:
            if action == "remember":
                content = params.get("content")
                level = params.get("level", "P1")
                tags = params.get("tags", [])
                
                # 使用记忆管理器存储
                await self.memory_manager.add(
                    content=content,
                    level=level,
                    tags=tags,
                    user_id=context.user_id,
                    chat_id=context.chat_id
                )
                return SkillResult(success=True, output={"stored": True})
            
            elif action == "recall":
                query = params.get("query")
                limit = params.get("limit", 5)
                
                memories = await self.memory_manager.search(
                    query=query,
                    limit=limit,
                    user_id=context.user_id
                )
                return SkillResult(success=True, output={"memories": memories})
            
            elif action == "forget":
                memory_id = params.get("memory_id")
                await self.memory_manager.delete(memory_id)
                return SkillResult(success=True, output={"deleted": memory_id})
            
            else:
                return SkillResult(success=False, output=None, error=f"Unknown action: {action}")
        
        except Exception as e:
            return SkillResult(success=False, output=None, error=str(e))
    
    def get_tools(self) -> List[Dict]:
        """记忆工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "memory_remember",
                    "description": "存储重要信息到长期记忆",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "要记忆的内容"},
                            "level": {"type": "string", "enum": ["P0", "P1", "P2"], "description": "优先级 (P0=永久, P1=普通, P2=临时)"},
                            "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"}
                        },
                        "required": ["content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "memory_recall",
                    "description": "从记忆中检索相关信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "查询关键词"},
                            "limit": {"type": "integer", "description": "返回数量"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
