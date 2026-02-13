"""
原生 Python Skill 基类 - 支持 OpenAI Function Calling

所有原生 Skill 都应继承此类，并提供 JSON Schema
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


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
    metadata: Dict = field(default_factory=dict)


class NativeSkill(ABC):
    """原生 Python Skill 基类
    
    支持 OpenAI Function Calling 协议
    """
    
    # Skill 元数据
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    
    # OpenAI Function Parameters Schema
    # 必须在子类中定义
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    def __init__(self, agent=None):
        self.agent = agent
    
    @abstractmethod
    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        """执行 Skill
        
        Args:
            context: 执行上下文
            **kwargs: 参数 (来自 LLM tool_calls)
            
        Returns:
            SkillResult
        """
        pass
    
    def get_function_schema(self) -> Dict[str, Any]:
        """获取 OpenAI Function Schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
    
    async def before_execute(self, context: SkillContext):
        """执行前钩子"""
        pass
    
    async def after_execute(self, context: SkillContext, result: SkillResult):
        """执行后钩子"""
        pass


# --- 默认原生 Skill ---

class MemorySkill(NativeSkill):
    """记忆管理 Skill"""
    
    name = "memory_tool"
    description = "管理长期记忆（添加、搜索）。当用户让你'记住'某事时使用 add，当用户问及过去的事时使用 search。"
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "search"],
                "description": "操作类型：add (添加记忆) 或 search (搜索记忆)"
            },
            "content": {
                "type": "string",
                "description": "要添加的记忆内容（仅用于 action=add）"
            },
            "query": {
                "type": "string",
                "description": "搜索关键词（仅用于 action=search）"
            }
        },
        "required": ["action"]
    }
    
    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        action = kwargs.get("action")
        
        if not context.agent or not context.agent.memory:
            return SkillResult(success=False, error="Memory system not initialized or not available")
            
        try:
            if action == "add":
                content = kwargs.get("content")
                if not content:
                    return SkillResult(success=False, error="Content is required for add action")
                
                await context.agent.memory.add(content, {"source": "user_interaction"})
                return SkillResult(success=True, output=f"已记住: {content[:50]}...")
            
            elif action == "search":
                query = kwargs.get("query")
                if not query:
                    return SkillResult(success=False, error="Query is required for search action")
                
                results = await context.agent.memory.search(query, top_k=5)
                # 格式化结果
                formatted = "\n".join([f"- {r.get('content', '')}" for r in results])
                return SkillResult(success=True, output=formatted if formatted else "未找到相关记忆")
            
            return SkillResult(success=False, error=f"Unknown action: {action}")
            
        except Exception as e:
            import traceback
            logger.error(f"Memory skill error: {traceback.format_exc()}")
            return SkillResult(success=False, error=f"Internal error: {str(e)}")


class OpenClawRunnerSkill(NativeSkill):
    """运行 OpenClaw 兼容层 Skill"""
    
    name = "run_openclaw_skill"
    description = "运行 OpenClaw 生态中的技能（如 browser-cash, weather 等）。使用此工具执行特定的外部脚本或操作。"
    
    parameters = {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "OpenClaw 技能名称 (例如: 'weather', 'browser-cash')"
            },
            "action": {
                "type": "string",
                "description": "要执行的动作/脚本 (默认为 'run' 或 'index')"
            },
            "params": {
                "type": "object",
                "description": "传递给技能的参数 (key-value对)"
            }
        },
        "required": ["skill_name"]
    }
    
    async def execute(self, context: SkillContext, **kwargs) -> SkillResult:
        skill_name = kwargs.get("skill_name")
        action = kwargs.get("action", "run")
        params = kwargs.get("params", {})
        
        if not context.agent or not context.agent.openclaw_skills:
            return SkillResult(success=False, error="OpenClaw adapter not available")
        
        # 调用适配器
        result = await context.agent.openclaw_skills.execute(
            skill_name, action, params
        )
        
        return SkillResult(
            success=result.success,
            output=result.output,
            error=result.error
        )
