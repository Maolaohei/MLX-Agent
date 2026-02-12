"""
聊天会话管理

实现聊天线程与工作线程分离
- 快速响应：直接处理
- 慢速任务：丢入队列，异步通知
"""

import asyncio
import time
from typing import Optional, Callable, Any, Dict, AsyncGenerator
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
        text = message or f"⏳ 任务已创建 (ID: `{task_id}`)\n完成后我会通知你~"
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
    """
    
    def __init__(
        self,
        context: ChatContext,
        task_queue: TaskQueue,
        quick_handler: Optional[Callable] = None,
        slow_handler: Optional[Callable] = None,
        notify_callback: Optional[Callable] = None
    ):
        """初始化聊天会话
        
        Args:
            context: 聊天上下文
            task_queue: 任务队列
            quick_handler: 快速消息处理器
            slow_handler: 慢速消息处理器
            notify_callback: 通知回调函数
        """
        self.context = context
        self.queue = task_queue
        self.quick_handler = quick_handler
        self.slow_handler = slow_handler
        self.notify_callback = notify_callback
        self._task_callbacks: Dict[str, Callable] = {}  # 任务ID -> 回调
        
        logger.info(f"ChatSession created: {context.user_id}@{context.platform}")
    
    async def handle_message(self, text: str) -> ChatResponse:
        """处理用户消息
        
        自动判断是快速响应还是慢速任务
        
        Args:
            text: 用户消息
            
        Returns:
            聊天响应
        """
        # 1. 先尝试快速响应
        if self.quick_handler:
            try:
                start = time.time()
                result = await self._try_quick_handle(text)
                elapsed = time.time() - start
                
                if result is not None and elapsed < 1.0:
                    # 快速响应成功
                    logger.debug(f"Quick response in {elapsed*1000:.1f}ms")
                    return ChatResponse.quick(result)
            except Exception as e:
                logger.warning(f"Quick handler failed: {e}")
        
        # 2. 进入慢速任务队列
        if self.slow_handler:
            task = await self.queue.submit(
                self._wrap_slow_handler(text),
                priority=TaskPriority.NORMAL,
                task_type="chat",
                callback=self._on_task_complete,
                progress_callback=self._on_task_progress,
                timeout=300,  # 5分钟超时
                user_id=self.context.user_id,
                chat_id=self.context.chat_id,
                platform=self.context.platform,
                message_id=self.context.message_id,
                payload={'original_text': text}
            )
            
            # 保存通知回调
            if self.notify_callback:
                self._task_callbacks[task.id] = self.notify_callback
            
            return ChatResponse.task_created(task.id)
        
        # 3. 都没有处理器，返回默认响应
        return ChatResponse.quick(f"收到: {text}")
    
    async def _try_quick_handle(self, text: str) -> Optional[str]:
        """尝试快速处理"""
        if not self.quick_handler:
            return None
        
        result = self.quick_handler(text, context=self.context)
        
        # 如果是协程，等待结果
        if asyncio.iscoroutine(result):
            result = await result
        
        return result
    
    def _wrap_slow_handler(self, text: str) -> Callable:
        """包装慢速处理器"""
        def wrapper(_task: Task = None):
            if self.slow_handler:
                return self.slow_handler(text, context=self.context, task=_task)
            return None
        return wrapper
    
    async def _on_task_complete(self, task: Task, result: TaskResult):
        """任务完成回调"""
        logger.info(f"Task {task.id} completed for user {task.user_id}")
        
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

