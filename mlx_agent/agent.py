"""
MLX-Agent 主类

核心功能：
- 记忆系统管理
- 平台适配器管理
- Skill 系统管理
- LLM 路由
"""

import asyncio
import signal
from pathlib import Path
from typing import Optional

import uvloop
from loguru import logger

from .config import Config
from .memory import MemorySystem
from .skills import SkillRegistry


class MLXAgent:
    """MLX-Agent 主类
    
    高性能、轻量级、多平台 AI Agent
    
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
        self.skills: Optional[SkillRegistry] = None
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
            # 初始化记忆系统
            self.memory = MemorySystem(self.config.memory)
            await self.memory.initialize()
            logger.info("Memory system initialized")
            
            # 初始化 Skill 系统
            self.skills = SkillRegistry(self)
            await self.skills.initialize()
            logger.info("Skill system initialized")
            
            # TODO: 初始化平台适配器
            
            logger.info("MLX-Agent started successfully!")
            
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
        
        logger.info("MLX-Agent stopped")
    
    async def handle_message(self, platform: str, user_id: str, text: str) -> str:
        """处理用户消息
        
        Args:
            platform: 平台名称 (telegram, qq, discord)
            user_id: 用户ID
            text: 消息内容
            
        Returns:
            回复内容
        """
        # 1. 搜索相关记忆
        memories = await self.memory.search(text, top_k=5)
        context = self._format_memories(memories)
        
        # 2. 识别意图并调用 Skill
        skill_result = await self.skills.execute(text, context=context)
        
        if skill_result.success:
            return skill_result.output
        
        # 3. 如果没有匹配的 Skill，使用默认回复
        return f"收到消息: {text}\n(默认回复，Skill 系统开发中...)"
    
    def _format_memories(self, memories: list) -> str:
        """格式化记忆为上下文"""
        if not memories:
            return ""
        return "\n".join(f"- {m['content'][:200]}" for m in memories)
