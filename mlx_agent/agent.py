"""
MLX-Agent 主类

核心功能：
- 记忆系统管理
- 平台适配器管理
- Skill 系统管理
- LLM 路由
- 人设管理
- Token 压缩
- 异步任务队列
"""

import asyncio
import signal
import time
from pathlib import Path
from typing import Optional, Dict, Any, AsyncGenerator

import uvloop
from loguru import logger

from .config import Config
from .memory import MemorySystem
from .memory.consolidation import MemoryConsolidator
from .identity import IdentityManager
from .compression import TokenCompressor
from .skills import SkillRegistry
from .skills.compat.openclaw import OpenClawSkillAdapter
from .tasks import TaskQueue, TaskWorker, TaskExecutor, TaskPriority, Task, TaskResult
from .chat import ChatSessionManager, ChatResponse


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
        
        # 任务系统
        self.task_queue: Optional[TaskQueue] = None
        self.task_executor: Optional[TaskExecutor] = None
        self.task_worker: Optional[TaskWorker] = None
        self.chat_manager: Optional[ChatSessionManager] = None
        
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
            
            # 7. 初始化任务系统
            await self._init_task_system()
            logger.info("Task system initialized")
            
            # 8. 初始化平台适配器
            if self.config.platforms.telegram.enabled:
                from .platforms.telegram import TelegramAdapter
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
        
        # 停止任务系统
        if self.task_worker:
            await self.task_worker.stop()
        
        if self.task_executor:
            self.task_executor.shutdown()
        
        if self.task_queue:
            await self.task_queue.shutdown()
        
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
    
    async def _init_task_system(self):
        """初始化任务系统"""
        # 创建任务队列
        self.task_queue = TaskQueue(maxsize=1000)
        
        # 创建执行器（线程池）
        self.task_executor = TaskExecutor(max_workers=4)
        
        # 创建工作线程
        self.task_worker = TaskWorker(
            queue=self.task_queue,
            executor=self.task_executor,
            num_workers=2,
            default_callback=self._on_task_complete
        )
        
        # 启动工作线程
        await self.task_worker.start()
        
        # 创建聊天会话管理器
        self.chat_manager = ChatSessionManager(
            task_queue=self.task_queue,
            quick_handler=self._quick_handle_message,
            slow_handler=self._slow_handle_message
        )
    
    async def _quick_handle_message(self, text: str, context: dict = None, **kwargs) -> Optional[str]:
        """快速消息处理器
        
        处理简单、快速响应的请求
        
        Args:
            text: 用户消息
            context: 上下文信息
            
        Returns:
            响应文本，None 表示需要转入慢速处理
        """
        # 简单命令处理
        text_lower = text.lower().strip()
        
        # 帮助命令
        if text_lower in ['/help', 'help', '帮助']:
            return (
                "🤖 MLX-Agent 帮助\n\n"
                "💬 快速响应:\n"
                "• /help - 显示帮助\n"
                "• /status - 查看状态\n"
                "• /tasks - 查看进行中的任务\n\n"
                "⏳ 慢速任务会自动进入队列，完成后通知你~"
            )
        
        # 状态命令
        if text_lower in ['/status', 'status', '状态']:
            stats = await self.get_stats()
            queue_stats = self.task_queue.get_stats() if self.task_queue else {}
            return (
                f"📊 状态\n"
                f"• Agent: {'运行中' if stats['running'] else '已停止'}\n"
                f"• 任务队列: {queue_stats.get('pending', 0)} 等待 / "
                f"{queue_stats.get('running', 0)} 执行中\n"
                f"• Skills: {stats['skills']['native']} 原生 / "
                f"{stats['skills']['openclaw']} OpenClaw"
            )
        
        # 任务列表命令
        if text_lower in ['/tasks', 'tasks', '任务']:
            if context and self.task_queue:
                user_id = context.get('user_id')
                tasks = self.task_queue.get_user_tasks(user_id)
                if tasks:
                    task_list = "\n".join([
                        f"• {t.id}: {t.status.value} ({t.type})"
                        for t in tasks[:10]
                    ])
                    return f"📋 你的任务 ({len(tasks)}):\n{task_list}"
                return "📋 当前没有进行中的任务"
        
        # 简单的问候语
        greetings = ['hello', 'hi', '你好', '您好', '在吗', '在？']
        if any(g in text_lower for g in greetings):
            return "👋 你好！我是 MLX-Agent，有什么可以帮你的吗？"
        
        # 短消息快速响应
        if len(text) < 10:
            return f"收到: {text}"
        
        # 需要复杂处理的返回 None，转入慢速队列
        return None
    
    async def _slow_handle_message(
        self,
        text: str,
        context: dict = None,
        task: Task = None,
        **kwargs
    ) -> str:
        """慢速消息处理器
        
        在后台线程池中执行复杂任务
        
        Args:
            text: 用户消息
            context: 上下文信息
            task: 任务对象（用于进度更新）
            
        Returns:
            响应文本
        """
        if task:
            task.set_progress("🤔 正在理解你的问题...", 0.1)
        
        # 模拟耗时处理
        await asyncio.sleep(0.5)
        
        if task:
            task.set_progress("🔍 搜索相关记忆...", 0.3)
        
        # 搜索记忆
        memories = []
        if self.memory:
            try:
                memories = await self.memory.search(text, top_k=5)
            except Exception as e:
                logger.warning(f"Memory search failed: {e}")
        
        await asyncio.sleep(0.3)
        
        if task:
            task.set_progress("💭 思考回复...", 0.6)
        
        # 构建回复
        response_parts = [f"📝 处理完成！\n\n关于: {text[:100]}..."]
        
        if memories:
            response_parts.append(f"\n💡 找到 {len(memories)} 条相关记忆")
        
        await asyncio.sleep(0.2)
        
        if task:
            task.set_progress("✨ 完成", 1.0)
        
        response_parts.append(f"\n\n任务 ID: `{task.id if task else 'N/A'}`")
        
        return "\n".join(response_parts)
    
    async def _on_task_complete(self, task: Task, result: TaskResult):
        """任务完成回调
        
        主动推送结果给用户
        """
        logger.info(f"Task {task.id} completed, notifying user {task.user_id}")
        
        # 构建通知消息
        if result.success:
            icon = "✅"
            status = "完成"
        else:
            icon = "❌"
            status = "失败"
        
        message = (
            f"{icon} 任务 `{task.id}` {status}\n"
            f"⏱️ 耗时: {result.duration_ms/1000:.1f}s\n"
        )
        
        if result.output:
            output_text = str(result.output)
            if len(output_text) > 500:
                output_text = output_text[:500] + "..."
            message += f"\n📤 结果:\n{output_text}"
        
        if result.error:
            error_text = str(result.error)
            if len(error_text) > 200:
                error_text = error_text[:200] + "..."
            message += f"\n❗ 错误: {error_text}"
        
        # 发送到平台
        if task.platform == "telegram" and self.telegram:
            try:
                await self.telegram.send_message(task.chat_id, message)
                logger.debug(f"Task notification sent to {task.chat_id}")
            except Exception as e:
                logger.error(f"Failed to send task notification: {e}")
        
        # 保存到记忆
        if self.memory and result.success:
            try:
                await self.memory.add(
                    f"Task {task.id} completed: {result.output[:200] if result.output else 'No output'}",
                    metadata={
                        'platform': task.platform,
                        'user_id': task.user_id,
                        'task_type': task.type,
                        'task_id': task.id
                    },
                    level='P2'
                )
            except Exception as e:
                logger.warning(f"Failed to save task memory: {e}")
    
    async def handle_message(
        self,
        platform: str,
        user_id: str,
        text: str,
        chat_id: str = None,
        message_id: str = None,
        username: str = None
    ) -> str:
        """处理用户消息
        
        自动判断是快速响应还是慢速任务：
        - 快速响应：直接返回（<100ms）
        - 慢速任务：进入队列异步处理，立即返回任务ID
        
        Args:
            platform: 平台名称 (telegram, qq, discord)
            user_id: 用户ID
            text: 消息内容
            chat_id: 聊天ID（用于后续通知）
            message_id: 消息ID
            username: 用户名
            
        Returns:
            回复内容
        """
        try:
            # 1. 检查人设热重载
            if self.identity:
                await self.identity.check_reload()
            
            # 2. 使用聊天会话管理器处理
            if self.chat_manager:
                session = self.chat_manager.get_or_create(
                    platform=platform,
                    user_id=user_id,
                    chat_id=chat_id or user_id,
                    message_id=message_id,
                    username=username,
                    notify_callback=self._create_notify_callback(platform, chat_id or user_id)
                )
                
                response = await session.handle_message(text)
                return response.text
            
            # 3. 降级：直接处理（无任务系统）
            return await self._legacy_handle_message(platform, user_id, text)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return f"❌ 处理消息时出错: {e}"
    
    def _create_notify_callback(self, platform: str, chat_id: str):
        """创建通知回调函数"""
        async def notify_callback(task: Task, result: TaskResult):
            # 这里可以添加额外的通知逻辑
            pass
        return notify_callback
    
    async def _legacy_handle_message(self, platform: str, user_id: str, text: str) -> str:
        """传统的消息处理方式（降级方案）"""
        try:
            memories = await self.memory.search(text, top_k=5) if self.memory else []
            memory_context = self._format_memories(memories[:3])
            return f"收到: {text}\n\n相关记忆:\n{memory_context or '(无)'}"
        except Exception as e:
            return f"处理失败: {e}"
    
    async def handle_message_stream(
        self,
        platform: str,
        user_id: str,
        text: str,
        chat_id: str = None,
        message_id: str = None
    ) -> AsyncGenerator[str, None]:
        """流式处理用户消息
        
        Args:
            platform: 平台名称
            user_id: 用户ID
            text: 消息内容
            chat_id: 聊天ID
            message_id: 消息ID
            
        Yields:
            流式响应片段
        """
        # 先发送确认
        yield "⏳ 正在处理..."
        
        # 处理消息
        response = await self.handle_message(
            platform=platform,
            user_id=user_id,
            text=text,
            chat_id=chat_id,
            message_id=message_id
        )
        
        # 模拟流式输出（按段落分割）
        paragraphs = response.split('\n\n')
        for i, para in enumerate(paragraphs):
            if i > 0:
                yield '\n\n'
            yield para
    
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
            'memory': self.memory.get_stats() if self.memory else None,
            'tasks': self.task_queue.get_stats() if self.task_queue else None,
            'worker': self.task_worker.get_stats() if self.task_worker else None,
            'sessions': self.chat_manager.get_stats() if self.chat_manager else None
        }
        return stats
