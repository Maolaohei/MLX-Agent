"""
原生工具系统

纯 Python 实现的工具集合，无需 Node/OpenClaw 依赖
"""

from .base import (
    BaseTool,
    ToolCategory,
    ToolParameter,
    ToolResult,
    ToolRegistry,
    tool_registry,
    register_tool
)

# 导入并注册所有工具
from . import search
from . import browser
from . import code
from . import file
from . import http
from . import system

__all__ = [
    "BaseTool",
    "ToolCategory", 
    "ToolParameter",
    "ToolResult",
    "ToolRegistry",
    "tool_registry",
    "register_tool",
    "get_available_tools",
    "execute_tool"
]


def get_available_tools() -> list:
    """获取所有可用工具列表"""
    return tool_registry.list_tools()


async def execute_tool(name: str, **params) -> ToolResult:
    """执行指定工具"""
    return await tool_registry.execute(name, **params)
