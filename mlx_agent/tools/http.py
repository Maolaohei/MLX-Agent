"""
HTTP 请求工具

发送 HTTP 请求
"""

from typing import List, Optional, Any, Dict
import json

from loguru import logger

from .base import BaseTool, ToolCategory, ToolParameter, ToolResult, register_tool


@register_tool
class HttpTool(BaseTool):
    """HTTP 请求工具"""
    
    name = "http_request"
    description = "发送 HTTP 请求 (GET/POST/PUT/DELETE 等)"
    category = ToolCategory.DATA
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="method",
                description="HTTP 方法: GET, POST, PUT, DELETE, PATCH",
                type="string",
                required=True,
                enum=["GET", "POST", "PUT", "DELETE", "PATCH"]
            ),
            ToolParameter(
                name="url",
                description="请求 URL",
                type="string",
                required=True
            ),
            ToolParameter(
                name="headers",
                description="请求头 (JSON 对象)",
                type="object",
                required=False
            ),
            ToolParameter(
                name="params",
                description="URL 参数 (JSON 对象)",
                type="object",
                required=False
            ),
            ToolParameter(
                name="body",
                description="请求体 (字符串或 JSON 对象)",
                type="string",
                required=False
            ),
            ToolParameter(
                name="timeout",
                description="超时时间(秒)",
                type="integer",
                required=False,
                default=30
            )
        ]
    
    async def execute(self, **params) -> ToolResult:
        method = params.get("method", "GET").upper()
        url = params.get("url", "")
        headers = params.get("headers", {})
        query_params = params.get("params", {})
        body = params.get("body")
        timeout = params.get("timeout", 30)
        
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                # 处理 body
                content = None
                if body:
                    if isinstance(body, dict):
                        content = json.dumps(body)
                        if "Content-Type" not in headers:
                            headers["Content-Type"] = "application/json"
                    else:
                        content = body
                
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=query_params,
                    content=content
                )
                
                # 解析响应
                try:
                    response_body = response.json()
                except:
                    response_body = response.text[:10000]
                
                return ToolResult(
                    success=200 <= response.status_code < 300,
                    output={
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                        "body": response_body
                    }
                )
        
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            return ToolResult(
                success=False,
                output=None,
                error=str(e)
            )


@register_tool
class JsonTool(BaseTool):
    """JSON 处理工具"""
    
    name = "json_operations"
    description = "JSON 解析、查询和转换"
    category = ToolCategory.DATA
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                description="操作: parse(解析), query(查询), stringify(转字符串)",
                type="string",
                required=True,
                enum=["parse", "query", "stringify"]
            ),
            ToolParameter(
                name="data",
                description="JSON 字符串或对象",
                type="string",
                required=True
            ),
            ToolParameter(
                name="query",
                description="JSONPath 查询 (query 时必需)",
                type="string",
                required=False
            ),
            ToolParameter(
                name="indent",
                description="格式化缩进 (stringify 时)",
                type="integer",
                required=False,
                default=2
            )
        ]
    
    async def execute(self, **params) -> ToolResult:
        action = params.get("action")
        data = params.get("data", "")
        
        try:
            if action == "parse":
                parsed = json.loads(data)
                return ToolResult(success=True, output=parsed)
            
            elif action == "stringify":
                obj = json.loads(data) if isinstance(data, str) else data
                indent = params.get("indent", 2)
                result = json.dumps(obj, indent=indent, ensure_ascii=False)
                return ToolResult(success=True, output={"json": result})
            
            elif action == "query":
                parsed = json.loads(data)
                query = params.get("query", "")
                
                # 简单的点号路径查询
                result = parsed
                for key in query.split("."):
                    if isinstance(result, dict):
                        result = result.get(key)
                    elif isinstance(result, list) and key.isdigit():
                        result = result[int(key)]
                    else:
                        return ToolResult(success=False, output=None, error=f"Invalid query path: {query}")
                
                return ToolResult(success=True, output=result)
            
            else:
                return ToolResult(success=False, output=None, error=f"Unknown action: {action}")
        
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))
