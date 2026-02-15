"""
原生工具系统 - Base

所有工具的基类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import asyncio
import re
import json


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
    
    # ========== Token Sanitizer (工具结果清理) ==========
    
    def sanitize_output(self, output: Any, max_length: int = 5000) -> Any:
        """
        清理工具输出，节省 Token
        
        功能:
        - 截断 Base64 数据
        - 截断 Hex 数据  
        - 截断大列表/JSON
        - 截断长文本
        
        Args:
            output: 原始输出
            max_length: 最大长度限制
            
        Returns:
            清理后的输出
        """
        if not isinstance(output, str):
            return output
        
        original_length = len(output)
        if original_length <= max_length:
            return output
        
        # 1. 清理 Base64 (data URI 格式)
        output = self._sanitize_base64(output)
        
        # 2. 清理 Hex 数据
        output = self._sanitize_hex(output)
        
        # 3. 清理大 JSON 数组
        output = self._sanitize_json_arrays(output)
        
        # 4. 截断长行
        output = self._sanitize_long_lines(output)
        
        # 5. 最终长度截断
        if len(output) > max_length:
            output = output[:max_length] + f"\n\n... [truncated {original_length - max_length} chars]"
        
        return output
    
    def _sanitize_base64(self, text: str) -> str:
        """清理 Base64 数据"""
        # data:image/png;base64,xxxxx... 格式
        pattern = r'data:[a-zA-Z]+/[a-zA-Z]+;base64,[A-Za-z0-9+/=]{100,}'
        
        def replace_base64(match):
            full = match.group(0)
            size = len(full) * 3 // 4  # 估算原始大小
            return f'[base64:data:{self._format_size(size)}]'
        
        return re.sub(pattern, replace_base64, text)
    
    def _sanitize_hex(self, text: str) -> str:
        """清理 Hex 数据"""
        # 连续 50+ 个 hex 字节
        pattern = r'([0-9a-fA-F]{2}[\s:]){50,}[0-9a-fA-F]{2}'
        
        def replace_hex(match):
            hex_str = match.group(0)
            byte_count = len(re.findall(r'[0-9a-fA-F]{2}', hex_str))
            return f'[hex:{byte_count} bytes]'
        
        return re.sub(pattern, replace_hex, text)
    
    def _sanitize_json_arrays(self, text: str) -> str:
        """清理大 JSON 数组"""
        try:
            data = json.loads(text)
            if isinstance(data, list) and len(data) > 20:
                # 截断大数组
                truncated = data[:10] + [f'... {len(data) - 20} more items ...'] + data[-10:]
                return json.dumps(truncated, indent=2, ensure_ascii=False)
            elif isinstance(data, dict):
                # 处理嵌套数组
                data = self._truncate_nested_arrays(data)
                return json.dumps(data, indent=2, ensure_ascii=False)
        except:
            pass
        return text
    
    def _truncate_nested_arrays(self, data: Any, max_items: int = 20) -> Any:
        """递归截断嵌套数组"""
        if isinstance(data, list):
            if len(data) > max_items:
                return data[:10] + [f'... {len(data) - 20} more ...'] + data[-10:]
            return [self._truncate_nested_arrays(item, max_items) for item in data]
        elif isinstance(data, dict):
            return {k: self._truncate_nested_arrays(v, max_items) for k, v in data.items()}
        return data
    
    def _sanitize_long_lines(self, text: str, max_line_length: int = 500) -> str:
        """截断长行"""
        lines = text.split('\n')
        result = []
        for line in lines:
            if len(line) > max_line_length:
                line = line[:max_line_length] + ' ... [truncated]'
            result.append(line)
        return '\n'.join(result)
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f}KB"
        else:
            return f"{size_bytes/(1024*1024):.1f}MB"


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
    
    async def execute(self, name: str, sanitize: bool = True, **params) -> ToolResult:
        """执行工具
        
        Args:
            name: 工具名称
            sanitize: 是否清理输出以节省 token (默认 True)
            **params: 工具参数
        """
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
            
            # 自动清理输出 (节省 token)
            if sanitize and result.success and result.output:
                original_len = len(str(result.output))
                result.output = tool.sanitize_output(result.output)
                sanitized_len = len(str(result.output))
                
                # 记录节省的 token (估算: 1 token ≈ 4 chars)
                saved_tokens = (original_len - sanitized_len) // 4
                if saved_tokens > 100:
                    logger.debug(f"Tool {name}: sanitized output, saved ~{saved_tokens} tokens")
            
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
