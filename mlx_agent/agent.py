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
from .llm import LLMClient
from .api_manager import APIManager, get_api_manager


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
        # 使用 uvloop 加速 asyncio (如果支持)
        try:
            import uvloop
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        except ImportError:
            pass
        
        # 创建新的事件循环
        try:
            self.loop = asyncio.get_event_loop()
            if self.loop.is_closed():
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        
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
        self.api_manager: Optional[APIManager] = None  # API 管理器
        self._running = False
        
        # 任务系统
        self.task_queue: Optional[TaskQueue] = None
        self.task_executor: Optional[TaskExecutor] = None
        self.task_worker: Optional[TaskWorker] = None
        self.chat_manager: Optional[ChatSessionManager] = None
        
        # LLM 客户端
        self.llm: Optional[LLMClient] = None
        
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
            
            # 3. 初始化 API 管理器（必须在技能系统之前）
            self.api_manager = get_api_manager()
            await self.api_manager.initialize()
            logger.info("API manager initialized")
            
            # 4. 初始化记忆系统
            self.memory = MemorySystem(self.config.memory)
            await self.memory.initialize()
            logger.info("Memory system initialized")
            
            # 4. 初始化记忆整合器
            self.consolidator = MemoryConsolidator(
                Path(self.config.memory.path),
                similarity_threshold=0.7
            )
            logger.info("Memory consolidator initialized")
            
            # 5. 初始化 LLM 客户端
            try:
                # 尝试使用新配置结构
                primary_config = None
                fallback_config = None
                failover_enabled = False
                
                # 检查 config.llm 是否是 Pydantic 对象且有 primary 字段
                if hasattr(self.config.llm, 'primary') and self.config.llm.primary:
                    logger.info("Using multi-model configuration")
                    primary_data = self.config.llm.primary
                    primary_config = {
                        'api_key': primary_data.api_key,
                        'api_base': primary_data.api_base,
                        'auth_token': primary_data.auth_token,
                        'model': primary_data.model,
                        'temperature': primary_data.temperature,
                        'max_tokens': primary_data.max_tokens,
                    }
                    
                    if self.config.llm.fallback:
                        fallback_data = self.config.llm.fallback
                        fallback_config = {
                            'api_key': fallback_data.api_key,
                            'api_base': fallback_data.api_base,
                            'auth_token': fallback_data.auth_token,
                            'model': fallback_data.model,
                            'temperature': fallback_data.temperature,
                            'max_tokens': fallback_data.max_tokens,
                        }
                    
                    failover_enabled = self.config.llm.failover.enabled
                else:
                    # 兼容旧配置
                    logger.info("Using legacy LLM configuration")
                    primary_config = {
                        'api_key': self.config.llm.api_key,
                        'api_base': self.config.llm.api_base,
                        'auth_token': self.config.llm.auth_token,
                        'model': self.config.llm.model,
                        'temperature': self.config.llm.temperature,
                        'max_tokens': self.config.llm.max_tokens,
                    }
                
                if primary_config and primary_config.get('api_key'):
                    self.llm = LLMClient(
                        primary_config=primary_config,
                        fallback_config=fallback_config,
                        failover_enabled=failover_enabled
                    )
                    logger.info(f"LLM client initialized: {primary_config.get('model')}")
                else:
                    logger.error("LLM config missing API Key")
                    
            except Exception as e:
                logger.error(f"Failed to initialize LLM: {e}")
                import traceback
                logger.error(traceback.format_exc())
            
            # 6. 初始化 Skill 系统
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
    
    async def _quick_handle_message(self, text: str, context: dict = None, history: list = None, **kwargs) -> Optional[str]:
        """快速消息处理器
        
        处理简单、快速响应的请求
        
        Args:
            text: 用户消息
            context: 上下文信息
            history: 对话历史
            
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
        
        # 短消息也使用 LLM 回复（不是复读机）
        if len(text) < 50 and self.llm:
            # 使用 LLM 生成回复，不经过慢速队列
            try:
                base_prompt = "简短回复。"
                if self.identity:
                    system_prompt = self.identity.inject_to_prompt(base_prompt)
                else:
                    system_prompt = base_prompt
                
                response = await self.llm.simple_chat(text, system_prompt)
                return response
            except Exception as e:
                logger.error(f"Quick LLM call failed: {e}")
                # 如果 LLM 失败，转入慢速队列
                return None
        
        # 需要复杂处理的返回 None，转入慢速队列
        return None
    
    async def _slow_handle_message(
        self,
        text: str,
        context: dict = None,
        task: Task = None,
        history: list = None,
        **kwargs
    ) -> str:
        """慢速消息处理器 - 使用 LLM 生成智能回复 (支持工具调用和对话历史)"""
        
        if task:
            task.set_progress("🤔 正在理解你的问题...", 0.1)
        
        # 0. 准备对话历史
        messages = []
        history = history or []
        
        # 1. 准备上下文和系统提示
        # 搜索相关记忆 (作为 System Prompt 的补充)
        memories = []
        if self.memory:
            try:
                memories = await self.memory.search(text, top_k=3)
                if task:
                    task.set_progress("🔍 搜索相关记忆...", 0.3)
            except Exception as e:
                logger.warning(f"Memory search failed: {e}")
        
        # 构建基础 Prompt
        base_prompt = "你是 MLX-Agent，一个强大的 AI 助手。请保持对话连贯性，参考之前的对话历史。"
        
        # 使用 IdentityManager 生成完整 Prompt
        if self.identity:
            system_prompt = self.identity.inject_to_prompt(base_prompt)
        else:
            system_prompt = base_prompt
            
        # 补充模型信息
        current_model = "unknown"
        if self.llm:
            current_model = self.llm.get_current_model()
            system_prompt += f"\n\n当前使用的模型: {current_model}"
            
            # 如果是 Gemini-3 Pro，增加特定指令
            if "gemini-3" in current_model:
                system_prompt += "\n\n请充分利用 Gemini-3 Pro 的推理能力，回答要深入、全面。"

        # 如果有记忆，添加到系统提示
        if memories:
            memory_context = "\n\n相关记忆:\n" + "\n".join([f"- {m.get('content', '')[:100]}" for m in memories[:3]])
            system_prompt += memory_context
        
        # 构建消息列表：系统提示 + 历史 + 当前消息
        messages.append({"role": "system", "content": system_prompt})
        
        # 添加历史对话（最多保留最近10轮，避免超出上下文限制）
        if history:
            # 过滤掉 system 消息，只保留 user/assistant/tool
            history_to_use = [m for m in history if m.get("role") in ["user", "assistant", "tool"]][-20:]
            messages.extend(history_to_use)
            logger.debug(f"[LLM] Using {len(history_to_use)} history messages")
        
        # 添加当前用户消息
        messages.append({"role": "user", "content": text})
        
        # 2. 获取可用工具
        tools = None
        if self.skills:
            try:
                tools = self.skills.get_tools_schema()
                if tools:
                    logger.debug(f"Available tools: {len(tools)}")
            except Exception as e:
                logger.error(f"Failed to get tools: {e}")
        
        if task:
            task.set_progress("🧠 调用 AI 生成回复...", 0.6)
        
        # 3. LLM 交互循环 (支持多轮工具调用)
        max_turns = 5  # 防止无限循环
        turn_count = 0
        
        while turn_count < max_turns:
            turn_count += 1
            
            if not self.llm:
                return f"收到你的消息: {text[:100]}...\n\n（LLM 未配置，无法生成智能回复）"
                
            try:
                # 调用 LLM
                # 如果提供了工具，启用思考模式（Kimi k2.5 支持）
                use_reasoning = tools is not None and len(tools) > 0
                
                response_msg = await self.llm.chat(
                    messages=messages,
                    tools=tools,
                    tool_choice="auto" if tools else None,
                    reasoning=use_reasoning
                )
                
                # 检查是否有工具调用
                tool_calls = response_msg.get("tool_calls")
                content = response_msg.get("content")
                
                # 如果有内容，先添加到历史 (Assistant Message)
                # 注意：有些模型可能同时返回 content 和 tool_calls
                # OpenAI 规范要求 Assistant Message 必须包含 tool_calls 字段如果它被使用了
                assistant_msg = {
                    "role": "assistant",
                    "content": content
                }
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                
                messages.append(assistant_msg)
                
                if not tool_calls:
                    # 没有工具调用，直接返回内容
                    if task:
                        task.set_progress("✨ 完成", 1.0)
                    return content or "（AI 未返回任何内容）"
                
                # 有工具调用，执行工具
                if task:
                    task.set_progress(f"🔧 执行工具 ({len(tool_calls)} 个)...", 0.8)
                
                for tool_call in tool_calls:
                    function_name = tool_call.get("function", {}).get("name")
                    call_id = tool_call.get("id")
                    
                    # 执行工具
                    try:
                        result = await self.skills.execute_tool_call(
                            tool_call,
                            user_id=context.get("user_id") if context else None,
                            chat_id=context.get("chat_id") if context else None,
                            platform=context.get("platform") if context else None
                        )
                        
                        tool_output = result.output if result.success else f"Error: {result.error}"
                        
                    except Exception as e:
                        tool_output = f"Execution failed: {str(e)}"
                    
                    # 添加工具执行结果 (Tool Message)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": function_name,
                        "content": str(tool_output)
                    })
                
                # 继续下一轮循环，将工具结果传回 LLM
                continue
                
            except Exception as e:
                logger.error(f"LLM interaction failed: {e}")
                return f"抱歉，AI 服务暂时不可用: {str(e)[:100]}"
        
        return "交互次数过多，已终止。"
    
    async def _on_task_complete(self, task: Task, result: TaskResult):
        """任务完成回调
        
        主动推送结果给用户
        """
        logger.info(f"Task {task.id} completed, notifying user {task.user_id}")
        
        # 针对聊天任务的特殊处理：只发送结果，不发送状态头
        if task.type == "chat" and result.success:
            message = str(result.output)
        else:
            # 其他任务或失败时，保留详细信息
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
                # 先发消息
                await self.telegram.send_message(task.chat_id, message)
                logger.debug(f"Task notification sent to {task.chat_id}")
            except Exception as e:
                logger.error(f"Failed to send task notification: {e}")
            finally:
                # 无论成功失败，发完消息后才停止 Typing
                await self.telegram.stop_typing_loop(task.chat_id)
        
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
        """
        logger.debug(f"[AGENT] handle_message called: platform={platform}, user_id={user_id}, text={text[:50]}...")
        
        try:
            # 1. 检查人设热重载
            if self.identity:
                await self.identity.check_reload()
            
            # 2. 使用聊天会话管理器处理
            if self.chat_manager:
                logger.debug("[AGENT] Using chat_manager")
                session = self.chat_manager.get_or_create(
                    platform=platform,
                    user_id=user_id,
                    chat_id=chat_id or user_id,
                    message_id=message_id,
                    username=username,
                    notify_callback=self._create_notify_callback(platform, chat_id or user_id)
                )
                
                logger.debug("[AGENT] Calling session.handle_message")
                response = await session.handle_message(text)
                logger.debug(f"[AGENT] Got response: {response.text[:100] if response and response.text else 'None'}...")
                
                # 如果是任务创建，启动打字状态并返回空（让 adapter 保持沉默）
                if response.is_task:
                    if platform == "telegram" and self.telegram and (chat_id or user_id):
                        await self.telegram.start_typing_loop(chat_id or user_id)
                    return None
                    
                return response.text
            
            # 3. 降级：直接处理（无任务系统）
            logger.debug("[AGENT] Using legacy handler")
            return await self._legacy_handle_message(platform, user_id, text)
            
        except Exception as e:
            logger.error(f"[AGENT ERROR] {type(e).__name__}: {e}")
            logger.exception("[AGENT ERROR] Full traceback:")
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
