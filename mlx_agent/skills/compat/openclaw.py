"""
OpenClaw 技能兼容层

桥接 MLX-Agent 与 OpenClaw 技能生态：
- 扫描本地 OpenClaw 技能
- 解析 SKILL.md 获取元数据
- 统一调用接口
"""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

from loguru import logger


@dataclass
class SkillInfo:
    """技能信息"""
    name: str
    description: str
    version: str
    author: str
    path: Path
    scripts: Dict[str, Path]
    requires: List[str]
    is_python: bool  # True = Python skill, False = Node.js skill


@dataclass
class SkillResult:
    """技能执行结果"""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0


class OpenClawSkillAdapter:
    """OpenClaw 技能适配器
    
    提供统一的技能调用接口，支持 Python 和 Node.js 技能
    """
    
    SKILL_DIRS = [
        Path.home() / ".openclaw" / "skills",
        Path.home() / ".openclaw" / "workspace" / "skills",
        Path("/usr/lib/node_modules/openclaw/skills"),
    ]
    
    def __init__(self, additional_paths: Optional[List[Path]] = None):
        """初始化适配器
        
        Args:
            additional_paths: 额外的技能搜索路径
        """
        self.skill_paths = self.SKILL_DIRS.copy()
        if additional_paths:
            self.skill_paths.extend(additional_paths)
        
        self.skills: Dict[str, SkillInfo] = {}
        self._initialized = False
    
    async def initialize(self):
        """初始化并扫描可用技能"""
        if self._initialized:
            return
        
        logger.info("Initializing OpenClaw skill adapter...")
        
        for skill_dir in self.skill_paths:
            if skill_dir.exists():
                await self._scan_directory(skill_dir)
        
        self._initialized = True
        logger.info(f"Loaded {len(self.skills)} OpenClaw skills")
    
    async def _scan_directory(self, directory: Path):
        """扫描技能目录
        
        Args:
            directory: 要扫描的目录
        """
        if not directory.exists():
            return
        
        for skill_path in directory.iterdir():
            if not skill_path.is_dir():
                continue
            
            skill_md = skill_path / "SKILL.md"
            if skill_md.exists():
                try:
                    skill_info = self._parse_skill(skill_path, skill_md)
                    if skill_info:
                        self.skills[skill_info.name] = skill_info
                        logger.debug(f"Found skill: {skill_info.name} @ {skill_path}")
                except Exception as e:
                    logger.warning(f"Failed to parse skill at {skill_path}: {e}")
    
    def _parse_skill(self, skill_path: Path, skill_md: Path) -> Optional[SkillInfo]:
        """解析 SKILL.md 文件
        
        Args:
            skill_path: 技能目录
            skill_md: SKILL.md 文件路径
            
        Returns:
            SkillInfo 或 None
        """
        content = skill_md.read_text(encoding='utf-8')
        
        # 解析 YAML frontmatter
        import re
        frontmatter_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        
        metadata = {}
        if frontmatter_match:
            try:
                import yaml
                metadata = yaml.safe_load(frontmatter_match.group(1))
            except ImportError:
                # 手动解析简单键值对
                for line in frontmatter_match.group(1).split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        metadata[key.strip()] = value.strip().strip('"\'')
        
        # 提取基本信息
        name = metadata.get('name', skill_path.name)
        description = metadata.get('description', 'No description')
        version = metadata.get('version', '0.1.0')
        author = metadata.get('author', 'Unknown')
        
        # 扫描 scripts 目录
        scripts_dir = skill_path / "scripts"
        scripts = {}
        if scripts_dir.exists():
            for script in scripts_dir.iterdir():
                if script.suffix in ['.py', '.sh', '.js']:
                    scripts[script.stem] = script
        
        # 检测技能类型
        is_python = (skill_path / "__init__.py").exists() or \
                    any(s.suffix == '.py' for s in scripts.values())
        
        # 依赖要求
        requires = metadata.get('requires', [])
        if isinstance(requires, dict):
            requires = requires.get('bins', [])
        
        return SkillInfo(
            name=name,
            description=description,
            version=version,
            author=author,
            path=skill_path,
            scripts=scripts,
            requires=requires,
            is_python=is_python
        )
    
    async def execute(
        self,
        skill_name: str,
        action: str = "run",
        params: Optional[Dict[str, Any]] = None,
        timeout: int = 60
    ) -> SkillResult:
        """执行技能
        
        Args:
            skill_name: 技能名称
            action: 动作/脚本名称
            params: 参数字典
            timeout: 超时时间（秒）
            
        Returns:
            SkillResult
        """
        if not self._initialized:
            await self.initialize()
        
        if skill_name not in self.skills:
            return SkillResult(
                success=False,
                output="",
                error=f"Skill not found: {skill_name}",
                exit_code=-1
            )
        
        skill = self.skills[skill_name]
        
        try:
            if skill.is_python:
                return await self._execute_python_skill(skill, action, params, timeout)
            else:
                return await self._execute_nodejs_skill(skill, action, params, timeout)
        except Exception as e:
            logger.error(f"Failed to execute skill {skill_name}: {e}")
            return SkillResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1
            )
    
    async def _execute_python_skill(
        self,
        skill: SkillInfo,
        action: str,
        params: Optional[Dict],
        timeout: int
    ) -> SkillResult:
        """执行 Python 技能
        
        尝试直接导入执行，失败则回退到 subprocess
        """
        # 方法1：尝试直接导入
        try:
            import sys
            if str(skill.path.parent) not in sys.path:
                sys.path.insert(0, str(skill.path.parent))
            
            module = __import__(skill.path.name, fromlist=['main', 'execute', 'run'])
            
            # 查找执行函数
            func = None
            for func_name in [action, 'execute', 'run', 'main']:
                if hasattr(module, func_name):
                    func = getattr(module, func_name)
                    break
            
            if func and callable(func):
                # 异步执行
                if asyncio.iscoroutinefunction(func):
                    result = await func(**(params or {}))
                else:
                    # 在线程池中执行
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, lambda: func(**(params or {})))
                
                return SkillResult(
                    success=True,
                    output=str(result) if result else "Success",
                    exit_code=0
                )
        
        except ImportError as e:
            logger.debug(f"Direct import failed for {skill.name}: {e}")
        
        # 方法2：通过脚本执行
        if action in skill.scripts:
            script_path = skill.scripts[action]
            
            if script_path.suffix == '.py':
                cmd = ['python3', str(script_path)]
            else:
                cmd = ['bash', str(script_path)]
            
            # 添加参数
            if params:
                for key, value in params.items():
                    cmd.extend([f'--{key}', str(value)])
            
            return await self._run_subprocess(cmd, timeout)
        
        return SkillResult(
            success=False,
            output="",
            error=f"Action '{action}' not found in skill '{skill.name}'",
            exit_code=-1
        )
    
    async def _execute_nodejs_skill(
        self,
        skill: SkillInfo,
        action: str,
        params: Optional[Dict],
        timeout: int
    ) -> SkillResult:
        """执行 Node.js 技能（通过 subprocess）"""
        
        # 检查是否有对应脚本
        if action in skill.scripts:
            script_path = skill.scripts[action]
        elif 'index' in skill.scripts:
            script_path = skill.scripts['index']
        else:
            return SkillResult(
                success=False,
                output="",
                error=f"No executable found for action '{action}' in skill '{skill.name}'",
                exit_code=-1
            )
        
        # 构建命令
        if script_path.suffix == '.js':
            cmd = ['node', str(script_path)]
        elif script_path.suffix == '.sh':
            cmd = ['bash', str(script_path)]
        else:
            cmd = [str(script_path)]
        
        # 添加参数
        if params:
            for key, value in params.items():
                cmd.extend([f'--{key}', str(value)])
        
        return await self._run_subprocess(cmd, timeout)
    
    async def _run_subprocess(
        self,
        cmd: List[str],
        timeout: int
    ) -> SkillResult:
        """运行子进程
        
        Args:
            cmd: 命令列表
            timeout: 超时时间
            
        Returns:
            SkillResult
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path(cmd[1]).parent) if len(cmd) > 1 else None
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            
            output = stdout.decode('utf-8', errors='replace')
            error = stderr.decode('utf-8', errors='replace')
            
            return SkillResult(
                success=proc.returncode == 0,
                output=output,
                error=error if error else None,
                exit_code=proc.returncode
            )
            
        except asyncio.TimeoutError:
            return SkillResult(
                success=False,
                output="",
                error=f"Skill execution timed out after {timeout}s",
                exit_code=-1
            )
        except Exception as e:
            return SkillResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1
            )
    
    def list_skills(self) -> List[Dict]:
        """列出所有可用技能"""
        return [
            {
                'name': s.name,
                'description': s.description,
                'version': s.version,
                'author': s.author,
                'type': 'Python' if s.is_python else 'Node.js',
                'actions': list(s.scripts.keys())
            }
            for s in self.skills.values()
        ]
    
    def get_skill_info(self, skill_name: str) -> Optional[Dict]:
        """获取技能详细信息"""
        if skill_name not in self.skills:
            return None
        
        s = self.skills[skill_name]
        return {
            'name': s.name,
            'description': s.description,
            'version': s.version,
            'author': s.author,
            'path': str(s.path),
            'type': 'Python' if s.is_python else 'Node.js',
            'actions': list(s.scripts.keys()),
            'requires': s.requires
        }
    
    async def check_skill_health(self, skill_name: str) -> Dict:
        """检查技能健康状态"""
        if skill_name not in self.skills:
            return {'healthy': False, 'error': 'Skill not found'}
        
        skill = self.skills[skill_name]
        
        # 检查依赖
        missing_deps = []
        for dep in skill.requires:
            result = subprocess.run(['which', dep], capture_output=True)
            if result.returncode != 0:
                missing_deps.append(dep)
        
        if missing_deps:
            return {
                'healthy': False,
                'error': f"Missing dependencies: {', '.join(missing_deps)}"
            }
        
        return {'healthy': True, 'dependencies': skill.requires}
