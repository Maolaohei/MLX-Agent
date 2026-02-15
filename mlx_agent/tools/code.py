"""
代码执行工具

执行 Python、Shell 代码，可选 Docker 隔离
"""

import subprocess
import tempfile
import os
from typing import List, Optional, Any
import asyncio

from loguru import logger

from .base import BaseTool, ToolCategory, ToolParameter, ToolResult, register_tool


@register_tool
class CodeTool(BaseTool):
    """代码执行工具"""
    
    name = "execute_code"
    description = "执行 Python 或 Shell 代码。⚠️ 注意：此工具可执行任意代码，请确保代码来源可信。"
    category = ToolCategory.CODE
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="language",
                description="代码语言: python, bash, shell",
                type="string",
                required=True,
                enum=["python", "bash", "shell"]
            ),
            ToolParameter(
                name="code",
                description="要执行的代码",
                type="string",
                required=True
            ),
            ToolParameter(
                name="timeout",
                description="执行超时时间(秒)",
                type="integer",
                required=False,
                default=30
            ),
            ToolParameter(
                name="use_docker",
                description="是否使用 Docker 隔离 (需要 Docker 已安装)",
                type="boolean",
                required=False,
                default=False
            )
        ]
    
    async def execute(self, **params) -> ToolResult:
        language = params.get("language", "python")
        code = params.get("code", "")
        timeout = params.get("timeout", 30)
        use_docker = params.get("use_docker", False)
        
        if not code.strip():
            return ToolResult(
                success=False,
                output=None,
                error="No code provided"
            )
        
        try:
            if language == "python":
                if use_docker:
                    return await self._exec_python_docker(code, timeout)
                else:
                    return await self._exec_python(code, timeout)
            else:
                return await self._exec_shell(code, timeout)
        
        except Exception as e:
            logger.error(f"Code execution failed: {e}")
            return ToolResult(
                success=False,
                output=None,
                error=str(e)
            )
    
    async def _exec_python(self, code: str, timeout: int) -> ToolResult:
        """执行 Python 代码"""
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            proc = await asyncio.create_subprocess_exec(
                'python3', temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024*1024  # 限制输出 1MB
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Execution timed out after {timeout}s"
                )
            
            output = stdout.decode('utf-8', errors='replace')[:10000]
            error = stderr.decode('utf-8', errors='replace')[:5000]
            
            return ToolResult(
                success=proc.returncode == 0,
                output=output if output else None,
                error=error if error else None
            )
        
        finally:
            os.unlink(temp_path)
    
    async def _exec_python_docker(self, code: str, timeout: int) -> ToolResult:
        """在 Docker 中执行 Python 代码 (沙箱)"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            proc = await asyncio.create_subprocess_exec(
                'docker', 'run', '--rm',
                '-v', f'{temp_path}:/code.py:ro',
                '--network', 'none',  # 禁用网络
                '--memory', '256m',   # 内存限制
                '--cpus', '1',        # CPU 限制
                'python:3.13-alpine',
                'python3', '/code.py',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Docker execution timed out after {timeout}s"
                )
            
            output = stdout.decode('utf-8', errors='replace')[:10000]
            error = stderr.decode('utf-8', errors='replace')[:5000]
            
            return ToolResult(
                success=proc.returncode == 0,
                output=output if output else None,
                error=error if error else None
            )
        
        finally:
            os.unlink(temp_path)
    
    async def _exec_shell(self, code: str, timeout: int) -> ToolResult:
        """执行 Shell 命令"""
        proc = await asyncio.create_subprocess_shell(
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=1024*1024
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(
                success=False,
                output=None,
                error=f"Command timed out after {timeout}s"
            )
        
        output = stdout.decode('utf-8', errors='replace')[:10000]
        error = stderr.decode('utf-8', errors='replace')[:5000]
        
        return ToolResult(
            success=proc.returncode == 0,
            output=output if output else None,
            error=error if error else None
        )
