"""
聊天会话管理

实现聊天线程与工作线程分离
- 快速响应：直接处理
- 慢速任务：丢入队列，异步通知
"""

import asyncio
import time
from typing import Optional, Callable, Any, Dict, List, AsyncGenerator
from dataclasses import dataclass, field
from loguru import logger

from mlx_agent.tasks import TaskQueue, TaskWorker, TaskExecutor, Task, TaskResult, TaskPriority


@dataclass
class ChatContext:
    """聊天上下文"""
    platform: str
    user_id: str
    chat_id: str
    message_id: Optional[str] = None
    username: Optional[str] = None
    session_id: str = field(default_factory=lambda: str(int(time.time())))
    metadata: Dict = field(default_factory=dict)


@dataclass
class ChatMessage:
    """单条聊天消息"""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)


@dataclass
class ChatResponse:
    """聊天响应"""
    text: str
    is_task: bool = False  # 是否是任务创建响应
    task_id: Optional[str] = None
    stream: bool = False  # 是否是流式响应
    
    @classmethod
    def quick(cls, text: str) -> 'ChatResponse':
        """快速响应"""
        return cls(text=text, is_task=False)
    
    @classmethod
    def task_created(cls, task_id: str, message: str = None) -> 'ChatResponse':
        """任务已创建响应"""
        # 默认不返回文本，保持静默（typing状态会由适配器维护）
        text = message or ""
        return cls(text=text, is_task=True, task_id=task_id)
    
    @classmethod
    def stream_start(cls, initial_text: str = "") -> 'ChatResponse':
        """流式响应开始"""
        return cls(text=initial_text, stream=True)


class ChatSession:
    """聊天会话
    
    管理单个用户的聊天会话，实现：
    - 快速响应（<100ms）直接返回
    - 慢速任务（>1s）进入队列异步处理
    - 任务状态通知
    - 对话历史维护（解决前言不搭后语问题）
    """
    
    def __init__(
        self,
        context: ChatContext,
        task_queue: TaskQueue,
        quick_handler: Optional[Callable] = None,
        slow_handler: Optional[Callable] = None,
        notify_callback: Optional[Callable] = None,
        max_history: int = 20  # 保留最近20轮对话
    ):
        """初始化聊天会话
        
        Args:
            context: 聊天上下文
            task_queue: 任务队列
            quick_handler: 快速消息处理器
            slow_handler: 慢速消息处理器
            notify_callback: 通知回调函数
            max_history: 最大历史轮数
        """
        self.context = context
        self.queue = task_queue
        self.quick_handler = quick_handler
        self.slow_handler = slow_handler
        self.notify_callback = notify_callback
        self._task_callbacks: Dict[str, Callable] = {}  # 任务ID -> 回调
        self._history: List[ChatMessage] = []  # 对话历史
        self._max_history = max_history
        
        logger.info(f"ChatSession created: {context.user_id}@{context.platform}")
    
    def add_message(self, role: str, content: str, metadata: Dict = None):
        """添加消息到历史"""
        msg = ChatMessage(role=role, content=content, metadata=metadata or {})
        self._history.append(msg)
        
        # 限制历史长度
        if len(self._history) > self._max_history * 2:  # *2 因为每轮有 user + assistant
            self._history = self._history[-self._max_history * 2:]
    
    def get_history(self, limit: int = 10) -> List[Dict]:
        """获取历史消息（用于传给 LLM）"""
        result = []
        for msg in self._history[-limit * 2:]:  # 最近 limit 轮
            result.append({
                "role": msg.role,
                "content": msg.content
            })
        return result
    
    def clear_history(self):
        """清空历史"""
        self._history.clear()
        
    async def handle_message(self, text: str) -> ChatResponse:
        """处理用户消息"""
        logger.debug(f"[CHAT] handle_message: text={text[:50]}...")
        
        # 记录用户消息
        self.add_message("user", text)
        
        # 1. 先尝试快速响应
        if self.quick_handler:
            try:
                logger.debug("[CHAT] Trying quick handler...")
                start = time.time()
                result = await self._try_quick_handle(text)
                elapsed = time.time() - start
                
                if result is not None and elapsed < 1.0:
                    logger.debug(f"[CHAT] Quick response success in {elapsed*1000:.1f}ms")
                    # 记录助手回复
                    self.add_message("assistant", result)
                    return ChatResponse.quick(result)
                else:
                    logger.debug(f"[CHAT] Quick handler returned None or too slow")
            except Exception as e:
                logger.warning(f"[CHAT] Quick handler failed: {e}")
        else:
            logger.debug("[CHAT] No quick handler configured")
        
        # 2. 进入慢速任务队列
        if self.slow_handler:
            logger.debug("[CHAT] Submitting to slow task queue...")
            task = await self.queue.submit(
                self._wrap_slow_handler(text),
                priority=TaskPriority.NORMAL,
                task_type="chat",
                callback=self._on_task_complete,
                progress_callback=self._on_task_progress,
                timeout=300,
                user_id=self.context.user_id,
                chat_id=self.context.chat_id,
                platform=self.context.platform,
                message_id=self.context.message_id,
                payload={'original_text': text}
            )
            
            logger.debug(f"[CHAT] Task created: {task.id}")
            
            # 保存通知回调
            if self.notify_callback:
                self._task_callbacks[task.id] = self.notify_callback
            
            return ChatResponse.task_created(task.id)
        else:
            logger.debug("[CHAT] No slow handler configured")
        
        # 3. 都没有处理器，返回默认响应
        logger.debug("[CHAT] Returning default response")
        return ChatResponse.quick(f"收到: {text}")
    
    async def _try_quick_handle(self, text: str) -> Optional[str]:
        """尝试快速处理"""
        if not self.quick_handler:
            return None
        
        # 传递历史和上下文
        result = self.quick_handler(
            text, 
            context=self.context,
            history=self.get_history(limit=5)
        )
        
        # 如果是协程，等待结果
        if asyncio.iscoroutine(result):
            result = await result
        
        return result
    
    def _wrap_slow_handler(self, text: str) -> Callable:
        """包装慢速处理器"""
        async def wrapper(_task: Task = None):
            if self.slow_handler:
                # 获取当前历史快照
                history = self.get_history(limit=10)
                
                # 检查 handler 是否是协程
                result = self.slow_handler(
                    text, 
                    context=self.context, 
                    task=_task,
                    history=history
                )
                if asyncio.iscoroutine(result):
                    result = await result
                
                # 如果是字符串结果，记录到历史
                if isinstance(result, str):
                    self.add_message("assistant", result)
                
                return result
            return None
        return wrapper
    
    async def _on_task_complete(self, task: Task, result: TaskResult):
        """任务完成回调"""
        logger.info(f"Task {task.id} completed for user {task.user_id}")
        
        # 记录助手回复到历史
        if result.success and result.output:
            self.add_message("assistant", str(result.output))
        
        # 调用保存的通知回调
        if task.id in self._task_callbacks:
            callback = self._task_callbacks[task.id]
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(task, result)
                else:
                    callback(task, result)
            except Exception as e:
                logger.error(f"Notify callback error: {e}")
            finally:
                del self._task_callbacks[task.id]
    
    async def _on_task_progress(self, task_id: str, data: Dict):
        """任务进度回调"""
        logger.debug(f"Task {task_id} progress: {data}")
        # 可以通过 notify_callback 发送进度更新
        if task_id in self._task_callbacks:
            callback = self._task_callbacks[task_id]
            # 这里可以扩展支持进度通知
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        return await self.queue.cancel(task_id)
    
    def get_active_tasks(self) -> list:
        """获取当前进行中的任务"""
        return self.queue.get_user_tasks(
            self.context.user_id,
            status=None  # 获取所有状态
        )


class ChatSessionManager:
    """聊天会话管理器
    
    管理所有用户的聊天会话
    """
    
    def __init__(
        self,
        task_queue: TaskQueue,
        quick_handler: Optional[Callable] = None,
        slow_handler: Optional[Callable] = None
    ):
        """初始化会话管理器
        
        Args:
            task_queue: 任务队列
            quick_handler: 快速消息处理器
            slow_handler: 慢速消息处理器
        """
        self.queue = task_queue
        self.quick_handler = quick_handler
        self.slow_handler = slow_handler
        self._sessions: Dict[str, ChatSession] = {}
    
    def _get_session_key(self, platform: str, user_id: str) -> str:
        """生成会话键"""
        return f"{platform}:{user_id}"
    
    def get_or_create(
        self,
        platform: str,
        user_id: str,
        chat_id: str,
        message_id: Optional[str] = None,
        username: Optional[str] = None,
        notify_callback: Optional[Callable] = None
    ) -> ChatSession:
        """获取或创建会话
        
        Args:
            platform: 平台名称
            user_id: 用户ID
            chat_id: 聊天ID
            message_id: 消息ID
            username: 用户名
            notify_callback: 通知回调
            
        Returns:
            聊天会话
        """
        key = self._get_session_key(platform, user_id)
        
        if key not in self._sessions:
            context = ChatContext(
                platform=platform,
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                username=username
            )
            
            self._sessions[key] = ChatSession(
                context=context,
                task_queue=self.queue,
                quick_handler=self.quick_handler,
                slow_handler=self.slow_handler,
                notify_callback=notify_callback
            )
        
        return self._sessions[key]
    
    def get_session(self, platform: str, user_id: str) -> Optional[ChatSession]:
        """获取现有会话"""
        key = self._get_session_key(platform, user_id)
        return self._sessions.get(key)
    
    def remove_session(self, platform: str, user_id: str):
        """移除会话"""
        key = self._get_session_key(platform, user_id)
        if key in self._sessions:
            del self._sessions[key]
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'active_sessions': len(self._sessions),
            'sessions_by_platform': {}
        }
