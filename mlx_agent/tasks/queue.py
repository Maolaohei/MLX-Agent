"""
任务队列

基于 asyncio.PriorityQueue 的优先级任务队列
"""

import asyncio
from typing import Optional, Dict, List, Callable, Any
from loguru import logger

from .base import Task, TaskPriority, TaskStatus, TaskResult


class TaskQueue:
    """优先级任务队列
    
    使用 asyncio.PriorityQueue 实现优先级调度
    支持任务取消、状态查询和统计信息
    """
    
    def __init__(self, maxsize: int = 1000):
        """初始化任务队列
        
        Args:
            maxsize: 队列最大容量
        """
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=maxsize)
        self._tasks: Dict[str, Task] = {}  # 所有任务索引
        self._pending: Dict[str, Task] = {}  # 等待中的任务
        self._running: Dict[str, Task] = {}  # 执行中的任务
        self._completed: Dict[str, Task] = {}  # 已完成的任务
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(0)  # 用于通知有新任务
        self._shutdown = False
        
        logger.info(f"TaskQueue initialized (maxsize={maxsize})")
    
    async def submit(
        self,
        func: Callable,
        *args,
        priority: TaskPriority = TaskPriority.NORMAL,
        task_type: str = "default",
        callback: Callable[[Task, TaskResult], Any] = None,
        progress_callback: Callable[[str, Any], Any] = None,
        timeout: Optional[float] = None,
        max_retries: int = 2,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        platform: Optional[str] = None,
        message_id: Optional[str] = None,
        payload: Optional[Dict] = None,
        **kwargs
    ) -> Task:
        """提交任务到队列
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            priority: 任务优先级
            task_type: 任务类型
            callback: 完成回调
            progress_callback: 进度回调
            timeout: 超时时间(秒)
            max_retries: 最大重试次数
            user_id: 用户ID
            chat_id: 聊天ID
            platform: 平台
            message_id: 消息ID
            payload: 额外数据
            **kwargs: 关键字参数
            
        Returns:
            创建的任务对象
        """
        if self._shutdown:
            raise RuntimeError("TaskQueue is shutdown")
        
        task = Task(
            type=task_type,
            payload=payload or {},
            priority=priority,
            func=func,
            args=args,
            kwargs=kwargs,
            callback=callback,
            progress_callback=progress_callback,
            timeout=timeout,
            max_retries=max_retries,
            user_id=user_id,
            chat_id=chat_id,
            platform=platform,
            message_id=message_id
        )
        
        async with self._lock:
            self._tasks[task.id] = task
            self._pending[task.id] = task
        
        # 放入优先级队列 (priority, created_at, task)
        # 使用 created_at 作为次级排序确保FIFO
        await self._queue.put((priority.value, task.created_at, task))
        self._semaphore.release()
        
        logger.debug(f"Task {task.id} submitted (type={task_type}, priority={priority.name})")
        return task
    
    async def get(self, timeout: Optional[float] = None) -> Optional[Task]:
        """获取一个待执行的任务
        
        Args:
            timeout: 超时时间(秒)
            
        Returns:
            任务对象，如果超时返回 None
        """
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        
        try:
            _, _, task = await self._queue.get()
        except asyncio.CancelledError:
            self._semaphore.release()
            raise
        
        async with self._lock:
            if task.id in self._pending:
                del self._pending[task.id]
            if task.status == TaskStatus.PENDING:
                self._running[task.id] = task
                task.status = TaskStatus.RUNNING
                task.started_at = asyncio.get_event_loop().time()
        
        return task
    
    async def complete(self, task: Task, result: TaskResult):
        """标记任务完成
        
        Args:
            task: 完成的任务
            result: 执行结果
        """
        async with self._lock:
            if task.id in self._running:
                del self._running[task.id]
            
            task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            task.result = result
            task.completed_at = asyncio.get_event_loop().time()
            self._completed[task.id] = task
            
            # 清理旧任务，防止内存无限增长
            if len(self._completed) > 1000:
                # 保留最近500个
                old_ids = list(self._completed.keys())[:-500]
                for old_id in old_ids:
                    del self._completed[old_id]
                    if old_id in self._tasks:
                        del self._tasks[old_id]
        
        logger.debug(f"Task {task.id} completed (success={result.success})")
    
    async def cancel(self, task_id: str) -> bool:
        """取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功取消
        """
        async with self._lock:
            if task_id in self._pending:
                task = self._pending[task_id]
                task.status = TaskStatus.CANCELLED
                del self._pending[task_id]
                return True
            
            if task_id in self._running:
                # 运行中的任务不能直接取消
                return False
            
            return False
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务对象，不存在返回 None
        """
        return self._tasks.get(task_id)
    
    def get_user_tasks(self, user_id: str, status: Optional[TaskStatus] = None) -> List[Task]:
        """获取用户的任务列表
        
        Args:
            user_id: 用户ID
            status: 筛选状态，None表示全部
            
        Returns:
            任务列表
        """
        tasks = []
        for task in self._tasks.values():
            if task.user_id == user_id:
                if status is None or task.status == status:
                    tasks.append(task)
        return tasks
    
    @property
    def size(self) -> int:
        """当前队列大小"""
        return self._queue.qsize()
    
    @property
    def pending_count(self) -> int:
        """等待中的任务数"""
        return len(self._pending)
    
    @property
    def running_count(self) -> int:
        """执行中的任务数"""
        return len(self._running)
    
    @property
    def completed_count(self) -> int:
        """已完成的任务数"""
        return len(self._completed)
    
    def get_stats(self) -> Dict:
        """获取队列统计信息"""
        return {
            'queue_size': self.size,
            'pending': self.pending_count,
            'running': self.running_count,
            'completed': self.completed_count,
            'total': len(self._tasks),
        }
    
    async def shutdown(self):
        """关闭队列，清空所有任务"""
        self._shutdown = True
        
        async with self._lock:
            # 取消所有等待中的任务
            for task in self._pending.values():
                task.status = TaskStatus.CANCELLED
            self._pending.clear()
        
        logger.info("TaskQueue shutdown")

