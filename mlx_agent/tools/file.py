"""
文件操作工具

文件读写、目录操作等 - 增强安全版本
"""

import os
import re
import shutil
from pathlib import Path
from typing import List, Optional, Any, Tuple
import aiofiles

from loguru import logger

from .base import BaseTool, ToolCategory, ToolParameter, ToolResult, register_tool


@register_tool
class FileTool(BaseTool):
    """文件操作工具 - 增强安全版本"""

    name = "file_operations"
    description = "文件和目录操作：读取、写入、列出、复制、移动、删除"
    category = ToolCategory.FILE

    # 默认允许的基础目录
    DEFAULT_ALLOWED_PATHS = [
        "/tmp",
        "/var/tmp",
    ]

    # 危险路径模式（禁止访问）
    FORBIDDEN_PATTERNS = [
        r"^/etc/",
        r"^/proc/",
        r"^/sys/",
        r"^/dev/",
        r"^/root/",
        r"^/var/log/",
        r"~/.ssh",
        r"~/.gnupg",
        r"~/.aws",
        r"~/.kube",
        r"\.ssh/",
        r"\.gnupg/",
        r"\.aws/",
        r"id_rsa",
        r"id_ed25519",
        r"id_dsa",
        r"known_hosts",
        r"authorized_keys",
        r"credentials",
        r"token",
        r"secret",
        r"password",
        r"private_key",
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__()
        self.config = config or {}

        # 获取工作区路径
        self.workspace_path = self._get_workspace_path()

        # 构建允许路径列表
        self.allowed_paths = set(self.DEFAULT_ALLOWED_PATHS)
        self.allowed_paths.add(str(self.workspace_path))

        # 从配置添加额外的允许路径
        extra_paths = self.config.get("security", {}).get("allowed_paths", [])
        for path in extra_paths:
            self.allowed_paths.add(os.path.abspath(os.path.expanduser(path)))

        # 获取禁止路径
        self.forbidden_paths = self.config.get("security", {}).get("forbidden_paths", [])

        logger.debug(f"FileTool initialized with workspace: {self.workspace_path}")
        logger.debug(f"Allowed paths: {self.allowed_paths}")

    def _get_workspace_path(self) -> Path:
        """获取工作区路径"""
        # 优先使用配置的工作区
        if workspace := self.config.get("workspace_path"):
            return Path(workspace).resolve()

        # 使用 OPENCLAW_WORKSPACE 环境变量
        if env_workspace := os.getenv("OPENCLAW_WORKSPACE"):
            return Path(env_workspace).resolve()

        # 默认使用当前目录
        return Path(os.getcwd()).resolve()

    def _normalize_path(self, path: str) -> str:
        """规范化路径"""
        # 展开用户目录
        expanded = os.path.expanduser(path)
        # 转换为绝对路径
        abs_path = os.path.abspath(expanded)
        # 规范化路径（解析 .. 和 .）
        normalized = os.path.normpath(abs_path)
        return normalized

    def _is_path_traversal_attempt(self, path: str) -> bool:
        """检测路径遍历攻击"""
        # 检查是否包含 .. 序列
        if ".." in path:
            return True

        # 检查是否试图访问父目录
        normalized = self._normalize_path(path)
        workspace = str(self.workspace_path)

        # 如果在工作区内，检查是否超出工作区
        if normalized.startswith(workspace):
            return False

        return False

    def _matches_forbidden_pattern(self, path: str) -> Optional[str]:
        """检查路径是否匹配禁止模式"""
        normalized = path.lower()

        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                return pattern

        return None

    def _is_in_forbidden_path(self, path: str) -> bool:
        """检查路径是否在禁止目录内"""
        abs_path = self._normalize_path(path)

        for forbidden in self.forbidden_paths:
            expanded = os.path.expanduser(forbidden)
            abs_forbidden = os.path.abspath(expanded)

            # 检查是否是禁止路径的子目录或就是禁止路径本身
            if abs_path == abs_forbidden or abs_path.startswith(abs_forbidden + os.sep):
                return True

        return False

    def _validate_path(self, path: str) -> Tuple[bool, Optional[str]]:
        """验证路径安全性

        优先级: 工作区 > /tmp > 白名单 > 禁止模式检查

        Returns:
            (is_valid, error_message)
        """
        if not path:
            return False, "Path cannot be empty"

        # 规范化路径
        normalized = self._normalize_path(path)

        # 1. 检查路径遍历
        if ".." in path:
            return False, f"Path traversal detected in: {path}"

        # 2. 优先检查白名单（工作区和 /tmp 总是允许）
        # 检查是否在工作区内 - 工作区有最高优先级
        workspace = str(self.workspace_path)
        if normalized == workspace or normalized.startswith(workspace + os.sep):
            return True, None

        # 允许 /tmp 及其子目录
        if normalized.startswith("/tmp") or normalized.startswith("/var/tmp"):
            return True, None

        # 3. 检查禁止模式
        if pattern := self._matches_forbidden_pattern(normalized):
            return False, f"Path matches forbidden pattern '{pattern}': {path}"

        # 4. 检查禁止路径
        if self._is_in_forbidden_path(normalized):
            return False, f"Path is in a forbidden directory: {path}"

        # 5. 检查是否在额外的允许路径列表中
        for allowed in self.allowed_paths:
            if normalized == allowed or normalized.startswith(allowed + os.sep):
                return True, None

        return False, f"Path not in allowed directories: {path}. Allowed: {self.allowed_paths}"

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

    async def execute(self, **params) -> ToolResult:
        action = params.get("action")
        path = params.get("path", "")

        # 验证路径
        valid, error = self._validate_path(path)
        if not valid:
            return ToolResult(success=False, output=None, error=error)

        # 如果存在目标路径，也验证
        if destination := params.get("destination"):
            valid, error = self._validate_path(destination)
            if not valid:
                return ToolResult(success=False, output=None, error=f"Invalid destination: {error}")

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

        except PermissionError as e:
            logger.error(f"Permission denied: {e}")
            return ToolResult(success=False, output=None, error=f"Permission denied: {e}")
        except Exception as e:
            logger.error(f"File operation failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))

    async def _read(self, path: str) -> ToolResult:
        """读取文件"""
        normalized = self._normalize_path(path)

        if not os.path.isfile(normalized):
            return ToolResult(success=False, output=None, error=f"Not a file: {path}")

        async with aiofiles.open(normalized, 'r', encoding='utf-8', errors='replace') as f:
            content = await f.read()

        # 限制返回长度
        if len(content) > 50000:
            content = content[:50000] + "\n... (truncated)"

        return ToolResult(
            success=True,
            output={
                "path": path,
                "absolute_path": normalized,
                "content": content,
                "size": len(content)
            }
        )

    async def _write(self, path: str, content: str) -> ToolResult:
        """写入文件"""
        normalized = self._normalize_path(path)

        # 确保目录存在
        dir_path = os.path.dirname(normalized)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        async with aiofiles.open(normalized, 'w', encoding='utf-8') as f:
            await f.write(content)

        return ToolResult(
            success=True,
            output={"path": path, "absolute_path": normalized, "written": len(content)}
        )

    async def _list(self, path: str, recursive: bool) -> ToolResult:
        """列出目录"""
        normalized = self._normalize_path(path)

        if not os.path.isdir(normalized):
            return ToolResult(success=False, output=None, error=f"Not a directory: {path}")

        items = []

        if recursive:
            for root, dirs, files in os.walk(normalized):
                # 过滤掉隐藏目录
                dirs[:] = [d for d in dirs if not d.startswith('.')]

                for f in files:
                    if f.startswith('.'):
                        continue
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, normalized)
                    items.append({
                        "name": f,
                        "path": rel_path,
                        "type": "file",
                        "size": os.path.getsize(full_path)
                    })
        else:
            for item in os.listdir(normalized):
                # 跳过隐藏文件
                if item.startswith('.'):
                    continue

                full_path = os.path.join(normalized, item)
                items.append({
                    "name": item,
                    "type": "directory" if os.path.isdir(full_path) else "file",
                    "size": os.path.getsize(full_path) if os.path.isfile(full_path) else None
                })

        return ToolResult(
            success=True,
            output={"path": path, "absolute_path": normalized, "items": items}
        )

    async def _copy(self, src: str, dst: str) -> ToolResult:
        """复制文件或目录"""
        src_normalized = self._normalize_path(src)
        dst_normalized = self._normalize_path(dst)

        if not os.path.exists(src_normalized):
            return ToolResult(success=False, output=None, error=f"Source not found: {src}")

        # 确保目标目录存在
        dst_dir = os.path.dirname(dst_normalized)
        if dst_dir:
            os.makedirs(dst_dir, exist_ok=True)

        if os.path.isdir(src_normalized):
            shutil.copytree(src_normalized, dst_normalized)
        else:
            shutil.copy2(src_normalized, dst_normalized)

        return ToolResult(success=True, output={"copied": src, "to": dst})

    async def _move(self, src: str, dst: str) -> ToolResult:
        """移动文件或目录"""
        src_normalized = self._normalize_path(src)
        dst_normalized = self._normalize_path(dst)

        if not os.path.exists(src_normalized):
            return ToolResult(success=False, output=None, error=f"Source not found: {src}")

        # 确保目标目录存在
        dst_dir = os.path.dirname(dst_normalized)
        if dst_dir:
            os.makedirs(dst_dir, exist_ok=True)

        shutil.move(src_normalized, dst_normalized)
        return ToolResult(success=True, output={"moved": src, "to": dst})

    async def _delete(self, path: str, recursive: bool) -> ToolResult:
        """删除文件或目录"""
        normalized = self._normalize_path(path)

        if not os.path.exists(normalized):
            return ToolResult(success=True, output={"deleted": path, "note": "did not exist"})

        if os.path.isdir(normalized):
            if recursive:
                shutil.rmtree(normalized)
            else:
                os.rmdir(normalized)
        else:
            os.remove(normalized)

        return ToolResult(success=True, output={"deleted": path})

    async def _exists(self, path: str) -> ToolResult:
        """检查文件是否存在"""
        normalized = self._normalize_path(path)
        exists = os.path.exists(normalized)
        is_file = os.path.isfile(normalized) if exists else False
        is_dir = os.path.isdir(normalized) if exists else False

        return ToolResult(
            success=True,
            output={
                "exists": exists,
                "is_file": is_file,
                "is_directory": is_dir,
                "path": path,
                "absolute_path": normalized
            }
        )
