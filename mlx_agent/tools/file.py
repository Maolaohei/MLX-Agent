"""
文件操作工具

文件读写、目录操作等
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional, Any
import aiofiles

from loguru import logger

from .base import BaseTool, ToolCategory, ToolParameter, ToolResult, register_tool


@register_tool
class FileTool(BaseTool):
    """文件操作工具"""
    
    name = "file_operations"
    description = "文件和目录操作：读取、写入、列出、复制、移动、删除"
    category = ToolCategory.FILE
    
    # 允许操作的目录白名单 (安全配置)
    ALLOWED_PATHS = [
        "/tmp",
        "/root/.openclaw/workspace",
        str(Path.home() / "workspace"),
    ]
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                description="操作类型: read(读取), write(写入), list(列出), copy(复制), move(移动), delete(删除), exists(检查存在)",
                type="string",
                required=True,
                enum=["read", "write", "list", "copy", "move", "delete", "exists"]
            ),
            ToolParameter(
                name="path",
                description="文件或目录路径",
                type="string",
                required=True
            ),
            ToolParameter(
                name="content",
                description="写入内容 (write 时必需)",
                type="string",
                required=False
            ),
            ToolParameter(
                name="destination",
                description="目标路径 (copy/move 时必需)",
                type="string",
                required=False
            ),
            ToolParameter(
                name="recursive",
                description="是否递归操作目录",
                type="boolean",
                required=False,
                default=False
            )
        ]
    
    def _validate_path(self, path: str) -> tuple[bool, Optional[str]]:
        """验证路径是否在允许范围内"""
        abs_path = os.path.abspath(path)
        
        # 检查是否在白名单内
        for allowed in self.ALLOWED_PATHS:
            if abs_path.startswith(os.path.abspath(allowed)):
                return True, None
        
        # 允许 /tmp 下的任何路径
        if abs_path.startswith("/tmp"):
            return True, None
        
        return False, f"Path not allowed: {path}. Allowed paths: {self.ALLOWED_PATHS}"
    
    async def execute(self, **params) -> ToolResult:
        action = params.get("action")
        path = params.get("path", "")
        
        # 验证路径
        valid, error = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, output=None, error=error)
        
        try:
            if action == "read":
                return await self._read(path)
            elif action == "write":
                return await self._write(path, params.get("content", ""))
            elif action == "list":
                return await self._list(path, params.get("recursive", False))
            elif action == "copy":
                return await self._copy(path, params.get("destination", ""))
            elif action == "move":
                return await self._move(path, params.get("destination", ""))
            elif action == "delete":
                return await self._delete(path, params.get("recursive", False))
            elif action == "exists":
                return await self._exists(path)
            else:
                return ToolResult(success=False, output=None, error=f"Unknown action: {action}")
        
        except Exception as e:
            logger.error(f"File operation failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))
    
    async def _read(self, path: str) -> ToolResult:
        """读取文件"""
        if not os.path.isfile(path):
            return ToolResult(success=False, output=None, error=f"Not a file: {path}")
        
        async with aiofiles.open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = await f.read()
        
        # 限制返回长度
        if len(content) > 50000:
            content = content[:50000] + "\n... (truncated)"
        
        return ToolResult(
            success=True,
            output={
                "path": path,
                "content": content,
                "size": len(content)
            }
        )
    
    async def _write(self, path: str, content: str) -> ToolResult:
        """写入文件"""
        # 确保目录存在
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        async with aiofiles.open(path, 'w', encoding='utf-8') as f:
            await f.write(content)
        
        return ToolResult(
            success=True,
            output={"path": path, "written": len(content)}
        )
    
    async def _list(self, path: str, recursive: bool) -> ToolResult:
        """列出目录"""
        if not os.path.isdir(path):
            return ToolResult(success=False, output=None, error=f"Not a directory: {path}")
        
        items = []
        
        if recursive:
            for root, dirs, files in os.walk(path):
                for f in files:
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, path)
                    items.append({
                        "name": f,
                        "path": rel_path,
                        "type": "file",
                        "size": os.path.getsize(full_path)
                    })
        else:
            for item in os.listdir(path):
                full_path = os.path.join(path, item)
                items.append({
                    "name": item,
                    "type": "directory" if os.path.isdir(full_path) else "file",
                    "size": os.path.getsize(full_path) if os.path.isfile(full_path) else None
                })
        
        return ToolResult(
            success=True,
            output={"path": path, "items": items}
        )
    
    async def _copy(self, src: str, dst: str) -> ToolResult:
        """复制文件或目录"""
        if not os.path.exists(src):
            return ToolResult(success=False, output=None, error=f"Source not found: {src}")
        
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        
        return ToolResult(success=True, output={"copied": src, "to": dst})
    
    async def _move(self, src: str, dst: str) -> ToolResult:
        """移动文件或目录"""
        if not os.path.exists(src):
            return ToolResult(success=False, output=None, error=f"Source not found: {src}")
        
        shutil.move(src, dst)
        return ToolResult(success=True, output={"moved": src, "to": dst})
    
    async def _delete(self, path: str, recursive: bool) -> ToolResult:
        """删除文件或目录"""
        if not os.path.exists(path):
            return ToolResult(success=True, output={"deleted": path, "note": "did not exist"})
        
        if os.path.isdir(path):
            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)
        else:
            os.remove(path)
        
        return ToolResult(success=True, output={"deleted": path})
    
    async def _exists(self, path: str) -> ToolResult:
        """检查文件是否存在"""
        exists = os.path.exists(path)
        is_file = os.path.isfile(path) if exists else False
        is_dir = os.path.isdir(path) if exists else False
        
        return ToolResult(
            success=True,
            output={
                "exists": exists,
                "is_file": is_file,
                "is_directory": is_dir,
                "path": path
            }
        )
