"""
原生工具系统 - Base

所有工具的基类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import asyncio


class ToolCategory(Enum):
    """工具分类"""
    SEARCH = "search"
    BROWSER = "browser"
    CODE = "code"
    FILE = "file"
    SYSTEM = "system"
    DATA = "data"
    UTILITY = "utility"


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    description: str
    type: str  # string, integer, number, boolean, array, object
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None


@dataclass
class ToolSchema:
    """工具 Schema (OpenAI Function Calling 格式)"""
    name: str
    description: str
    parameters: List[ToolParameter]
    category: ToolCategory


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


class BaseTool(ABC):
    """工具基类
    
    所有原生工具必须继承此类
    """
    
    def __init__(self):
        self._schema: Optional[ToolSchema] = None
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass
    
    @property
    @abstractmethod
    def category(self) -> ToolCategory:
        """工具分类"""
        pass
    
    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        """执行工具
        
        Args:
            **params: 工具参数
            
        Returns:
            ToolResult: 执行结果
        """
        pass
    
    def get_schema(self) -> Dict[str, Any]:
        """获取 OpenAI Function Calling 格式的 Schema"""
        properties = {}
        required = []
        
        for param in self.get_parameters():
            prop = {
                "type": param.type,
                "description": param.description
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            
            properties[param.name] = prop
            
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
    
    @abstractmethod
    def get_parameters(self) -> List[ToolParameter]:
        """获取工具参数定义"""
        pass
    
    def validate_params(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """验证参数
        
        Returns:
            (是否有效, 错误信息)
        """
        tool_params = {p.name: p for p in self.get_parameters()}
        
        # 检查必需参数
        for name, param in tool_params.items():
            if param.required and name not in params:
                return False, f"Missing required parameter: {name}"
        
        # 检查未知参数
        for name in params:
            if name not in tool_params:
                return False, f"Unknown parameter: {name}"
        
        return True, None


class ToolRegistry:
    """工具注册表
    
    统一管理所有可用工具
    """
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool):
        """注册工具"""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())
    
    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """获取所有工具的 Schema"""
        return [tool.get_schema() for tool in self._tools.values()]
    
    async def execute(self, name: str, **params) -> ToolResult:
        """执行工具"""
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                output=None,
                error=f"Tool not found: {name}"
            )
        
        # 验证参数
        valid, error = tool.validate_params(params)
        if not valid:
            return ToolResult(
                success=False,
                output=None,
                error=error
            )
        
        # 执行
        import time
        start = time.time()
        try:
            result = await tool.execute(**params)
            result.execution_time_ms = int((time.time() - start) * 1000)
            return result
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                execution_time_ms=int((time.time() - start) * 1000)
            )


# 全局工具注册表
tool_registry = ToolRegistry()


def register_tool(tool_class: type):
    """工具注册装饰器
    
    用法:
        @register_tool
        class MyTool(BaseTool):
            ...
    """
    instance = tool_class()
    tool_registry.register(instance)
    return tool_class
