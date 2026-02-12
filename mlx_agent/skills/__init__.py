"""
Skill 注册表

统一管理原生和兼容层 Skill
"""

from typing import Any, Dict, List, Optional, Type
import asyncio

from loguru import logger

from mlx_agent.skills.native.base import NativeSkill, SkillContext, SkillResult
from mlx_agent.skills.compat.openclaw import OpenClawSkillAdapter


class SkillRegistry:
    """技能注册表 - 统一入口
    
    自动路由到原生 Skill 或 OpenClaw 兼容层
    """
    
    def __init__(self, agent):
        self.agent = agent
        self.native_skills: Dict[str, NativeSkill] = {}
        self.compat_adapter: Optional[OpenClawAdapter] = None
        self._initialized = False
        
    async def initialize(self):
        """初始化 Skill 系统"""
        logger.info("Initializing skill system...")
        
        # 初始化 OpenClaw 兼容层
        try:
            self.compat_adapter = OpenClawSkillAdapter()
            await self.compat_adapter.initialize()
            logger.info("OpenClaw adapter initialized")
        except Exception as e:
            logger.warning(f"OpenClaw adapter not available: {e}")
        
        # 注册默认原生 Skill
        self._register_default_skills()
        
        self._initialized = True
        logger.info(f"Skill system initialized with {len(self.native_skills)} native skills")
    
    def _register_default_skills(self):
        """注册默认原生 Skill"""
        from mlx_agent.skills.native.base import EchoSkill, MemorySkill
        
        self.register_native(EchoSkill)
        self.register_native(MemorySkill)
        
        # TODO: 从 skills/ 目录动态加载更多 Skill
    
    def register_native(self, skill_class: Type[NativeSkill]):
        """注册原生 Skill"""
        skill = skill_class(self.agent)
        self.native_skills[skill.name] = skill
        logger.debug(f"Registered native skill: {skill.name}")
    
    async def execute(self, intent: str, **kwargs) -> SkillResult:
        """执行 Skill（自动选择原生或兼容层）
        
        Args:
            intent: 意图/技能名称
            **kwargs: 参数
            
        Returns:
            SkillResult
        """
        if not self._initialized:
            return SkillResult(success=False, error="Skill system not initialized")
        
        # 创建上下文
        context = SkillContext(agent=self.agent)
        
        # 1. 尝试匹配原生 Skill
        best_match = None
        best_score = 0.0
        
        for name, skill in self.native_skills.items():
            score = skill.match_intent(intent)
            if score > best_score:
                best_score = score
                best_match = skill
        
        if best_match and best_score > 0.5:
            logger.info(f"Executing native skill: {best_match.name}")
            try:
                await best_match.before_execute(context)
                result = await best_match.execute(context, **kwargs)
                await best_match.after_execute(context, result)
                return result
            except Exception as e:
                logger.error(f"Native skill execution failed: {e}")
                return SkillResult(success=False, error=str(e))
        
        # 2. 尝试兼容层
        if self.compat_adapter:
            logger.info(f"Trying OpenClaw skill for: {intent}")
            try:
                result = await self.compat_adapter.execute(
                    intent, "run", **kwargs
                )
                return SkillResult(
                    success=result["success"],
                    output=result.get("output"),
                    error=result.get("error")
                )
            except Exception as e:
                logger.error(f"OpenClaw skill execution failed: {e}")
        
        # 3. 都失败了
        return SkillResult(
            success=False,
            error=f"No skill found for intent: {intent}"
        )
    
    async def list_skills(self) -> Dict[str, List[str]]:
        """列出所有可用 Skill"""
        result = {
            "native": list(self.native_skills.keys()),
            "openclaw": []
        }
        
        if self.compat_adapter:
            try:
                openclaw_skills = await self.compat_adapter.list_skills()
                result["openclaw"] = openclaw_skills
            except Exception as e:
                logger.warning(f"Failed to list OpenClaw skills: {e}")
        
        return result
    
    async def close(self):
        """关闭 Skill 系统"""
        logger.info("Skill system closed")
