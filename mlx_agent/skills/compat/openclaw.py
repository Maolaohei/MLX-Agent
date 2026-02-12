"""
OpenClaw 兼容层

通过子进程调用 Node.js 的 OpenClaw 技能
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


class OpenClawAdapter:
    """OpenClaw 技能兼容层
    
    通过 npx skills 调用现有的 OpenClaw 技能
    需要 Node.js 环境
    """
    
    def __init__(self, skills_dir: str = "~/.agents/skills"):
        self.skills_dir = Path(skills_dir).expanduser()
        self._nodejs_available = False
        self._check_nodejs()
        
    def _check_nodejs(self):
        """检查 Node.js 环境"""
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info(f"Node.js available: {result.stdout.strip()}")
                self._nodejs_available = True
            else:
                logger.warning("Node.js check failed")
        except Exception as e:
            logger.warning(f"Node.js not available: {e}")
    
    async def execute(
        self, 
        skill_name: str, 
        action: str,
        args: List[str] = None,
        timeout: int = 60
    ) -> Dict[str, Any]:
        """执行 OpenClaw 技能
        
        Args:
            skill_name: 技能名称，如 "gh-cli"
            action: 动作，如 "search", "install"
            args: 参数列表
            timeout: 超时时间（秒）
            
        Returns:
            执行结果
        """
        if not self._nodejs_available:
            return {
                "success": False,
                "error": "Node.js not available. Cannot run OpenClaw skills."
            }
        
        cmd = ["npx", "skills", "run", skill_name, action]
        if args:
            cmd.extend(args)
            
        try:
            # 使用 asyncio 创建子进程
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "SKILLS_DIR": str(self.skills_dir)}
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            
            if proc.returncode != 0:
                return {
                    "success": False,
                    "error": stderr.decode().strip(),
                    "stdout": stdout.decode().strip()
                }
                
            # 尝试解析 JSON 输出
            try:
                output = json.loads(stdout.decode())
            except json.JSONDecodeError:
                output = stdout.decode().strip()
                
            return {
                "success": True,
                "output": output,
                "skill": skill_name,
                "action": action
            }
            
        except asyncio.TimeoutError:
            proc.kill()
            return {
                "success": False,
                "error": f"Skill execution timeout after {timeout}s"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def list_skills(self) -> List[str]:
        """列出已安装的 OpenClaw 技能"""
        result = await self.execute("list", "installed")
        if result["success"]:
            return result.get("output", [])
        return []


# 常用技能包装器
class GitHubSkill:
    """GitHub 技能包装器"""
    
    def __init__(self, adapter: OpenClawAdapter):
        self.adapter = adapter
        self.name = "gh-cli"
    
    async def search_repos(self, query: str, limit: int = 10):
        """搜索仓库"""
        return await self.adapter.execute(
            self.name,
            "search",
            ["repos", query, f"--limit={limit}"]
        )
    
    async def create_issue(self, repo: str, title: str, body: str = ""):
        """创建 Issue"""
        return await self.adapter.execute(
            self.name,
            "issue",
            ["create", "--repo", repo, "--title", title, "--body", body]
        )
    
    async def clone(self, repo: str, directory: Optional[str] = None):
        """克隆仓库"""
        args = ["repo", "clone", repo]
        if directory:
            args.append(directory)
        return await self.adapter.execute(self.name, "repo", args)


class BrowserSkill:
    """Browser Cash 技能包装器"""
    
    def __init__(self, adapter: OpenClawAdapter):
        self.adapter = adapter
        self.name = "browser-cash"
    
    async def create_session(self):
        """创建浏览器会话"""
        return await self.adapter.execute(
            self.name,
            "session",
            ["create"]
        )
    
    async def navigate(self, session_id: str, url: str):
        """导航到 URL"""
        return await self.adapter.execute(
            self.name,
            "navigate",
            ["--session", session_id, url]
        )
