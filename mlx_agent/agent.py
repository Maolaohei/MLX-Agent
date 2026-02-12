"""
MLX-Agent 主类

核心功能：
- 记忆系统管理
- 平台适配器管理
- Skill 系统管理
- LLM 路由
- 人设管理
- Token 压缩
"""

import asyncio
import signal
from pathlib import Path
from typing import Optional

import uvloop
from loguru import logger

from .config import Config
from .memory import MemorySystem
from .memory.consolidation import MemoryConsolidator
from .identity import IdentityManager
from .compression import TokenCompressor
from .skills import SkillRegistry
from .skills.compat.openclaw import OpenClawSkillAdapter
from .platforms.telegram import TelegramAdapter


class MLXAgent:
    """MLX-Agent 主类
    
    高性能、轻量级、多平台 AI Agent
    带有人设守护、Token 压缩、记忆整合等高级特性
    
    Example:
        >>> agent = MLXAgent(config_path="config.yaml")
        >>> await agent.start()
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化 MLX-Agent
        
        Args:
            config_path: 配置文件路径，默认使用 config/config.yaml
        """
        # 使用 uvloop 加速 asyncio
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        self.loop = asyncio.get_event_loop()
        
        # 加载配置
        self.config = Config.load(config_path)
        
        # 初始化组件
        self.memory: Optional[MemorySystem] = None
        self.consolidator: Optional[MemoryConsolidator] = None
        self.identity: Optional[IdentityManager] = None
        self.compressor: Optional[TokenCompressor] = None
        self.skills: Optional[SkillRegistry] = None
        self.openclaw_skills: Optional[OpenClawSkillAdapter] = None
        self.telegram: Optional[TelegramAdapter] = None
        self._running = False
        
        # 设置信号处理
        self._setup_signal_handlers()
        
        logger.info(f"MLX-Agent v{self.config.version} initialized")
    
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        for sig in (signal.SIGTERM, signal.SIGINT):
            self.loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
    
    async def start(self):
        """启动 Agent"""
        if self._running:
            logger.warning("Agent already running")
            return
        
        logger.info("Starting MLX-Agent...")
        self._running = True
        
        try:
            # 1. 初始化人设管理器（最先加载，确保知道自己是谁）
            self.identity = IdentityManager(Path(self.config.memory.path).parent)
            await self.identity.load()
            logger.info(f"Identity loaded: {self.identity.get_identity_summary()}")
            
            # 2. 初始化 Token 压缩器
            self.compressor = TokenCompressor(model=self.config.llm.model)
            logger.info("Token compressor initialized")
            
            # 3. 初始化记忆系统
            self.memory = MemorySystem(self.config.memory)
            await self.memory.initialize()
            logger.info("Memory system initialized")
            
            # 4. 初始化记忆整合器
            self.consolidator = MemoryConsolidator(
                Path(self.config.memory.path),
                similarity_threshold=0.7
            )
            logger.info("Memory consolidator initialized")
            
            # 5. 初始化 Skill 系统
            self.skills = SkillRegistry(self)
            await self.skills.initialize()
            logger.info("Skill system initialized")
            
            # 6. 初始化 OpenClaw 兼容层
            self.openclaw_skills = OpenClawSkillAdapter()
            await self.openclaw_skills.initialize()
            oc_skills = self.openclaw_skills.list_skills()
            logger.info(f"OpenClaw adapter initialized with {len(oc_skills)} skills")
            
            # 7. 初始化平台适配器
            if self.config.platforms.telegram.enabled:
                self.telegram = TelegramAdapter(
                    self.config.platforms.telegram,
                    self
                )
                await self.telegram.initialize()
                # 在后台启动 Telegram
                asyncio.create_task(self.telegram.start())
                logger.info("Telegram adapter started")
            
            logger.info("MLX-Agent started successfully!")
            
            # 8. 启动定时任务
            asyncio.create_task(self._scheduled_tasks())
            
            # 保持运行
            while self._running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Failed to start agent: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """停止 Agent"""
        if not self._running:
            return
        
        logger.info("Stopping MLX-Agent...")
        self._running = False
        
        # 清理资源
        if self.memory:
            await self.memory.close()
        
        if self.skills:
            await self.skills.close()
        
        if self.telegram:
            await self.telegram.stop()
        
        logger.info("MLX-Agent stopped")
    
    async def _scheduled_tasks(self):
        """定时任务"""
        while self._running:
            try:
                # 每小时检查一次人设文件热重载
                await asyncio.sleep(3600)
                if self.identity:
                    await self.identity.check_reload()
                
                # 每天凌晨 2 点执行记忆整合
                now = asyncio.get_event_loop().time()
                # 简化：每24小时整合一次
                if hasattr(self, '_last_consolidation'):
                    if now - self._last_consolidation > 86400:
                        await self._run_consolidation()
                else:
                    self._last_consolidation = now
                    
            except Exception as e:
                logger.error(f"Scheduled task error: {e}")
    
    async def _run_consolidation(self):
        """运行记忆整合"""
        if not self.consolidator:
            return
        
        logger.info("Running memory consolidation...")
        report = await self.consolidator.consolidate(days_back=7, dry_run=False)
        logger.info(f"Consolidation report: {report}")
        self._last_consolidation = asyncio.get_event_loop().time()
    
    async def handle_message(self, platform: str, user_id: str, text: str) -> str:
        """处理用户消息
        
        Args:
            platform: 平台名称 (telegram, qq, discord)
            user_id: 用户ID
            text: 消息内容
            
        Returns:
            回复内容
        """
        try:
            # 1. 检查人设热重载
            if self.identity:
                await self.identity.check_reload()
            
            # 2. 搜索相关记忆
            memories = await self.memory.search(text, top_k=10)
            
            # 3. 构建基础系统提示
            base_system = "你是一个AI助手，帮助用户完成任务。使用工具时请直接调用。"
            
            # 4. 注入人设
            if self.identity:
                user_context = f"当前用户: {user_id} (来自 {platform})"
                system_prompt = self.identity.inject_to_prompt(base_system, user_context)
            else:
                system_prompt = base_system
            
            # 5. 计算 token 并压缩记忆
            max_context_tokens = 8000  # 根据模型调整
            if self.compressor:
                memory_context = self.compressor.compress_for_context(
                    memories,
                    max_tokens=max_context_tokens,
                    system_prompt=system_prompt,
                    user_message=text,
                    reserve_tokens=1000
                )
            else:
                memory_context = self._format_memories(memories[:5])
            
            # 6. 尝试使用 OpenClaw Skill
            if self.openclaw_skills:
                # 简单的意图匹配
                for skill_name in self.openclaw_skills.skills.keys():
                    if skill_name.lower() in text.lower():
                        result = await self.openclaw_skills.execute(
                            skill_name,
                            params={'query': text, 'user_id': user_id}
                        )
                        if result.success:
                            # 保存到记忆
                            await self.memory.add(
                                f"User asked about {skill_name}: {text}\nResponse: {result.output}",
                                metadata={'platform': platform, 'user_id': user_id},
                                level='P1'
                            )
                            return result.output
            
            # 7. 尝试使用原生 Skill
            if self.skills:
                skill_result = await self.skills.execute(text, context=memory_context)
                if skill_result.success:
                    return skill_result.output
            
            # 8. 默认回复
            return f"收到消息: {text}\n\n{memory_context[:500] if memory_context else '(暂无相关记忆)'}",
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return f"处理消息时出错: {e}"
    
    def _format_memories(self, memories: list) -> str:
        """格式化记忆为上下文"""
        if not memories:
            return ""
        return "\n".join(f"- {m['content'][:200]}" for m in memories)
    
    async def get_stats(self) -> dict:
        """获取 Agent 统计信息"""
        stats = {
            'version': self.config.version,
            'running': self._running,
            'identity': self.identity.get_identity_summary() if self.identity else None,
            'skills': {
                'native': len(self.skills.skills) if self.skills else 0,
                'openclaw': len(self.openclaw_skills.skills) if self.openclaw_skills else 0
            },
            'memory': self.memory.get_stats() if self.memory else None
        }
        return stats
