"""
MLX-Agent 主类 - v0.3.0 生产就绪版

核心功能：
- 优雅关闭机制
- 流式输出支持
- ChromaDB 记忆系统
- 健康检查端点
- 完善的错误处理
"""

import asyncio
import signal
import time
from pathlib import Path
from typing import Optional, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager

from loguru import logger

from .config import Config
from .memory import ChromaMemorySystem
from .memory.consolidation import MemoryConsolidator
from .identity import IdentityManager
from .compression import TokenCompressor
from .skills import SkillRegistry
from .skills.compat.openclaw import OpenClawSkillAdapter
from .tasks import TaskQueue, TaskWorker, TaskExecutor, TaskPriority, Task, TaskResult
from .chat import ChatSessionManager, ChatResponse
from .llm import LLMClient
from .api_manager import APIManager, get_api_manager
from .health import HealthCheckServer


class MLXAgent:
    """MLX-Agent 主类 - 生产就绪版本
    
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
            logger.debug("Using uvloop")
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
        try:
            self.config = Config.load(config_path)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}, using defaults")
            self.config = Config()
        
        # 关闭事件
        self._shutdown_event = asyncio.Event()
        self._shutdown_timeout = 30  # 优雅关闭超时（秒）
        self._running = False
        
        # 初始化组件（将在 start 中初始化）
        self.memory: Optional[ChromaMemorySystem] = None
        self.consolidator: Optional[MemoryConsolidator] = None
        self.identity: Optional[IdentityManager] = None
        self.compressor: Optional[TokenCompressor] = None
        self.skills: Optional[SkillRegistry] = None
        self.openclaw_skills: Optional[OpenClawSkillAdapter] = None
        self.telegram: Optional[Any] = None
        self.api_manager: Optional[APIManager] = None
        self.health_server: Optional[HealthCheckServer] = None
        
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
        """设置信号处理器 - 优雅关闭"""
        def signal_handler(sig):
            logger.info(f"Received signal {sig.name}, initiating graceful shutdown...")
            # 使用 call_soon_threadsafe 确保线程安全
            self.loop.call_soon_threadsafe(self._shutdown_event.set)
        
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                self.loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
            except Exception as e:
                logger.warning(f"Failed to set signal handler for {sig}: {e}")
    
    async def start(self):
        """启动 Agent - 带错误恢复"""
        if self._running:
            logger.warning("Agent already running")
            return
        
        logger.info("Starting MLX-Agent...")
        self._running = True
        self._shutdown_event.clear()
        
        start_time = time.time()
        
        try:
            # 1. 初始化 API 管理器（最先加载，其他组件依赖）
            await self._init_api_manager()
            
            # 2. 初始化人设管理器
            await self._init_identity()
            
            # 3. 初始化 Token 压缩器
            await self._init_compressor()
            
            # 4. 初始化记忆系统
            await self._init_memory()
            
            # 5. 初始化记忆整合器
            await self._init_consolidator()
            
            # 6. 初始化 LLM 客户端
            await self._init_llm()
            
            # 7. 初始化技能系统
            await self._init_skills()
            
            # 8. 初始化任务系统
            await self._init_task_system()
            
            # 9. 初始化平台适配器
            await self._init_platforms()
            
            # 10. 启动健康检查服务器
            await self._init_health_server()
            
            elapsed = time.time() - start_time
            logger.info(f"MLX-Agent started successfully in {elapsed:.2f}s!")
            
            # 启动定时任务
            asyncio.create_task(self._scheduled_tasks())
            
            # 保持运行，直到收到关闭信号
            await self._run_main_loop()
                
        except Exception as e:
            logger.error(f"Failed to start agent: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """优雅停止 Agent - 有序关闭所有资源"""
        if not self._running:
            return
        
        logger.info("Initiating graceful shutdown...")
        self._running = False
        self._shutdown_event.set()
        
        shutdown_tasks = []
        
        # 按依赖顺序关闭组件
        # 1. 停止接受新连接 (健康检查)
        if self.health_server:
            logger.info("Stopping health check server...")
            shutdown_tasks.append(asyncio.create_task(
                self._safe_stop("health_server", self.health_server.stop())
            ))
        
        # 2. 停止平台适配器
        if self.telegram:
            logger.info("Stopping Telegram adapter...")
            shutdown_tasks.append(asyncio.create_task(
                self._safe_stop("telegram", self.telegram.stop())
            ))
        
        # 3. 停止任务系统（等待任务完成或超时）
        if self.task_worker:
            logger.info("Stopping task worker...")
            shutdown_tasks.append(asyncio.create_task(
                self._safe_stop("task_worker", self.task_worker.stop())
            ))
        
        if self.task_queue:
            logger.info("Shutting down task queue...")
            shutdown_tasks.append(asyncio.create_task(
                self._safe_stop("task_queue", self.task_queue.shutdown())
            ))
        
        if self.task_executor:
            logger.info("Shutting down task executor...")
            shutdown_tasks.append(asyncio.create_task(
                self._safe_stop("task_executor", self.task_executor.shutdown())
            ))
        
        # 4. 关闭技能系统
        if self.skills:
            logger.info("Closing skills...")
            shutdown_tasks.append(asyncio.create_task(
                self._safe_stop("skills", self.skills.close())
            ))
        
        # 5. 关闭 LLM 客户端
        if self.llm:
            logger.info("Closing LLM client...")
            shutdown_tasks.append(asyncio.create_task(
                self._safe_stop("llm", self.llm.close())
            ))
        
        # 6. 关闭记忆系统
        if self.memory:
            logger.info("Closing memory system...")
            shutdown_tasks.append(asyncio.create_task(
                self._safe_stop("memory", self.memory.close())
            ))
        
        # 7. 关闭 API 管理器
        if self.api_manager:
            logger.info("Closing API manager...")
            shutdown_tasks.append(asyncio.create_task(
                self._safe_stop("api_manager", self.api_manager.close())
            ))
        
        # 等待所有关闭任务完成（带超时）
        if shutdown_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=self._shutdown_timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Shutdown timeout ({self._shutdown_timeout}s) exceeded")
        
        logger.info("MLX-Agent stopped")
    
    async def _safe_stop(self, name: str, coro):
        """安全停止组件（捕获异常）"""
        try:
            await coro
            logger.debug(f"{name} stopped successfully")
        except Exception as e:
            logger.warning(f"Error stopping {name}: {e}")
    
    async def _run_main_loop(self):
        """主运行循环"""
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
    
    # ============== 组件初始化 ==============
    
    async def _init_api_manager(self):
        """初始化 API 管理器"""
        self.api_manager = get_api_manager()
        await self.api_manager.initialize()
        logger.info("API manager initialized")
    
    async def _init_identity(self):
        """初始化人设管理器"""
        self.identity = IdentityManager(Path(self.config.memory.path).parent)
        await self.identity.load()
        logger.info(f"Identity loaded: {self.identity.get_identity_summary()}")
    
    async def _init_compressor(self):
        """初始化 Token 压缩器"""
        self.compressor = TokenCompressor(model=self.config.llm.model or "gpt-4")
        logger.info("Token compressor initialized")
    
    async def _init_memory(self):
        """初始化记忆系统"""
        # 从配置获取嵌入提供商
        embedding_provider = getattr(self.config.memory, 'embedding_provider', 'local')
        
        self.memory = ChromaMemorySystem(
            path=self.config.memory.path,
            embedding_provider=embedding_provider,
            auto_archive=True
        )
        await self.memory.initialize()
        logger.info("ChromaDB memory system initialized")
    
    async def _init_consolidator(self):
        """初始化记忆整合器"""
        self.consolidator = MemoryConsolidator(
            Path(self.config.memory.path),
            similarity_threshold=0.7
        )
        logger.info("Memory consolidator initialized")
    
    async def _init_llm(self):
        """初始化 LLM 客户端"""
        try:
            primary_config = None
            fallback_config = None
            failover_enabled = False
            
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
                    failover_enabled=failover_enabled,
                    max_retries=3
                )
                logger.info(f"LLM client initialized: {primary_config.get('model')}")
            else:
                logger.error("LLM config missing API Key")
                
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            raise
    
    async def _init_skills(self):
        """初始化技能系统"""
        self.skills = SkillRegistry(self)
        await self.skills.initialize()
        logger.info("Skill system initialized")
        
        # OpenClaw 兼容层
        self.openclaw_skills = OpenClawSkillAdapter()
        await self.openclaw_skills.initialize()
        oc_skills = self.openclaw_skills.list_skills()
        logger.info(f"OpenClaw adapter initialized with {len(oc_skills)} skills")
    
    async def _init_task_system(self):
        """初始化任务系统"""
        self.task_queue = TaskQueue(maxsize=1000)
        self.task_executor = TaskExecutor(max_workers=4)
        self.task_worker = TaskWorker(
            queue=self.task_queue,
            executor=self.task_executor,
            num_workers=2,
            default_callback=self._on_task_complete
        )
        await self.task_worker.start()
        
        self.chat_manager = ChatSessionManager(
            task_queue=self.task_queue,
            quick_handler=self._quick_handle_message,
            slow_handler=self._slow_handle_message
        )
        logger.info("Task system initialized")
    
    async def _init_platforms(self):
        """初始化平台适配器"""
        if self.config.platforms.telegram.enabled:
            from .platforms.telegram import TelegramAdapter
            self.telegram = TelegramAdapter(
                self.config.platforms.telegram,
                self
            )
            await self.telegram.initialize()
            asyncio.create_task(self.telegram.start())
            logger.info("Telegram adapter started")
    
    async def _init_health_server(self):
        """初始化健康检查服务器"""
        # 从配置获取健康检查端口
        health_port = getattr(self.config, 'health_check', {}).get('port', 8080)
        
        self.health_server = HealthCheckServer(self, port=health_port)
        await self.health_server.start()
    
    # ============== 消息处理 ==============
    
    async def _quick_handle_message(self, text: str, context: dict = None, history: list = None, **kwargs) -> Optional[str]:
        """快速消息处理器"""
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
        
        # 短消息使用 LLM 回复
        if len(text) < 50 and self.llm:
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
                return None
        
        return None
    
    async def _slow_handle_message(
        self,
        text: str,
        context: dict = None,
        task: Task = None,
        history: list = None,
        **kwargs
    ) -> str:
        """慢速消息处理器 - 使用 LLM 生成智能回复"""
        
        if task:
            task.set_progress("🤔 正在理解你的问题...", 0.1)
        
        messages = []
        history = history or []
        
        # 搜索相关记忆
        memories = []
        if self.memory:
            try:
                memories = await self.memory.search(text, top_k=3)
                if task:
                    task.set_progress("🔍 搜索相关记忆...", 0.3)
            except Exception as e:
                logger.warning(f"Memory search failed: {e}")
        
        # 构建系统提示
        base_prompt = "你是 MLX-Agent，一个强大的 AI 助手。请保持对话连贯性，参考之前的对话历史。"
        
        if self.identity:
            system_prompt = self.identity.inject_to_prompt(base_prompt)
        else:
            system_prompt = base_prompt
        
        current_model = "unknown"
        if self.llm:
            current_model = self.llm.get_current_model()
            system_prompt += f"\n\n当前使用的模型: {current_model}"
        
        if memories:
            memory_context = "\n\n相关记忆:\n" + "\n".join([f"- {m.get('content', '')[:100]}" for m in memories[:3]])
            system_prompt += memory_context
        
        messages.append({"role": "system", "content": system_prompt})
        
        # 添加历史对话
        if history:
            history_to_use = [m for m in history if m.get("role") in ["user", "assistant", "tool"]][-20:]
            messages.extend(history_to_use)
        
        messages.append({"role": "user", "content": text})
        
        # 获取可用工具
        tools = None
        if self.skills:
            try:
                tools = self.skills.get_tools_schema()
            except Exception as e:
                logger.error(f"Failed to get tools: {e}")
        
        if task:
            task.set_progress("🧠 调用 AI 生成回复...", 0.6)
        
        # LLM 交互循环
        max_turns = 5
        turn_count = 0
        
        while turn_count < max_turns:
            turn_count += 1
            
            if not self.llm:
                return f"收到你的消息: {text[:100]}...\n\n（LLM 未配置，无法生成智能回复）"
            
            try:
                use_reasoning = tools is not None and len(tools) > 0
                
                response_msg = await self.llm.chat(
                    messages=messages,
                    tools=tools,
                    tool_choice="auto" if tools else None,
                    reasoning=use_reasoning
                )
                
                tool_calls = response_msg.get("tool_calls")
                content = response_msg.get("content")
                
                assistant_msg = {
                    "role": "assistant",
                    "content": content
                }
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                
                messages.append(assistant_msg)
                
                if not tool_calls:
                    if task:
                        task.set_progress("✨ 完成", 1.0)
                    return content or "（AI 未返回任何内容）"
                
                # 执行工具调用
                if task:
                    task.set_progress(f"🔧 执行工具 ({len(tool_calls)} 个)...", 0.8)
                
                for tool_call in tool_calls:
                    function_name = tool_call.get("function", {}).get("name")
                    call_id = tool_call.get("id")
                    
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
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": function_name,
                        "content": str(tool_output)
                    })
                
                continue
                
            except Exception as e:
                logger.error(f"LLM interaction failed: {e}")
                return f"抱歉，AI 服务暂时不可用: {str(e)[:100]}"
        
        return "交互次数过多，已终止。"
    
    async def _slow_handle_message_stream(
        self,
        text: str,
        context: dict = None,
        history: list = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """慢速消息处理器 - 流式版本"""
        
        yield "⏳ 正在思考..."
        
        messages = []
        history = history or []
        
        # 构建系统提示
        base_prompt = "你是 MLX-Agent，一个强大的 AI 助手。"
        
        if self.identity:
            system_prompt = self.identity.inject_to_prompt(base_prompt)
        else:
            system_prompt = base_prompt
        
        # 搜索相关记忆
        if self.memory:
            try:
                memories = await self.memory.search(text, top_k=3)
                if memories:
                    memory_context = "\n\n相关记忆:\n" + "\n".join([f"- {m.get('content', '')[:100]}" for m in memories[:3]])
                    system_prompt += memory_context
            except Exception as e:
                logger.warning(f"Memory search failed: {e}")
        
        messages.append({"role": "system", "content": system_prompt})
        
        # 添加历史
        if history:
            history_to_use = [m for m in history if m.get("role") in ["user", "assistant", "tool"]][-20:]
            messages.extend(history_to_use)
        
        messages.append({"role": "user", "content": text})
        
        # 流式调用 LLM
        if not self.llm:
            yield "LLM 未配置"
            return
        
        try:
            buffer = ""
            async for chunk in self.llm.chat_stream(messages):
                if chunk["type"] == "content":
                    buffer += chunk["content"]
                    # 累积一定长度或遇到标点再输出
                    if len(buffer) > 20 or any(p in chunk["content"] for p in '。！？\n'):
                        yield buffer
                        buffer = ""
                elif chunk["type"] == "done":
                    if buffer:
                        yield buffer
                    break
                elif chunk["type"] == "error":
                    yield f"\n[错误: {chunk.get('error', 'unknown')}]"
                    break
        except Exception as e:
            logger.error(f"Stream handling failed: {e}")
            yield f"抱歉，流式输出失败: {str(e)[:100]}"
    
    async def _on_task_complete(self, task: Task, result: TaskResult):
        """任务完成回调"""
        logger.info(f"Task {task.id} completed, notifying user {task.user_id}")
        
        # 构建消息
        if task.type == "chat" and result.success:
            message = str(result.output)
        else:
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
            except Exception as e:
                logger.error(f"Failed to send task notification: {e}")
            finally:
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
        """处理用户消息"""
        logger.debug(f"[AGENT] handle_message: platform={platform}, user_id={user_id}, text={text[:50]}...")
        
        try:
            if self.identity:
                await self.identity.check_reload()
            
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
                
                if response.is_task:
                    if platform == "telegram" and self.telegram and (chat_id or user_id):
                        await self.telegram.start_typing_loop(chat_id or user_id)
                    return None
                
                return response.text
            
            return await self._legacy_handle_message(platform, user_id, text)
            
        except Exception as e:
            logger.error(f"[AGENT ERROR] {type(e).__name__}: {e}")
            logger.exception("[AGENT ERROR] Full traceback:")
            return f"❌ 处理消息时出错: {e}"
    
    async def handle_message_stream(
        self,
        platform: str,
        user_id: str,
        text: str,
        chat_id: str = None,
        message_id: str = None
    ) -> AsyncGenerator[str, None]:
        """流式处理用户消息"""
        # 使用新的流式处理器
        async for chunk in self._slow_handle_message_stream(
            text=text,
            context={"platform": platform, "user_id": user_id, "chat_id": chat_id},
            history=[]
        ):
            yield chunk
    
    def _create_notify_callback(self, platform: str, chat_id: str):
        """创建通知回调函数"""
        async def notify_callback(task: Task, result: TaskResult):
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
    
    def _format_memories(self, memories: list) -> str:
        """格式化记忆为上下文"""
        if not memories:
            return ""
        return "\n".join(f"- {m['content'][:200]}" for m in memories)
    
    async def _scheduled_tasks(self):
        """定时任务"""
        while self._running:
            try:
                # 每小时检查一次人设文件热重载
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=3600)
                if not self._running:
                    break
                    
                if self.identity:
                    await self.identity.check_reload()
                
                # 每天执行记忆整合
                now = time.time()
                if hasattr(self, '_last_consolidation'):
                    if now - self._last_consolidation > 86400:
                        await self._run_consolidation()
                else:
                    self._last_consolidation = now
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Scheduled task error: {e}")
    
    async def _run_consolidation(self):
        """运行记忆整合"""
        if not self.consolidator:
            return
        
        logger.info("Running memory consolidation...")
        report = await self.consolidator.consolidate(days_back=7, dry_run=False)
        logger.info(f"Consolidation report: {report}")
        self._last_consolidation = time.time()
    
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
