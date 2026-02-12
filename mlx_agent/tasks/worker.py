"""
后台工作线程

消费任务队列，在后台执行任务
"""

import asyncio
from typing import Optional, List, Callable
from loguru import logger

from .base import Task, TaskResult, TaskStatus, TaskCallback
from .queue import TaskQueue
from .executor import TaskExecutor


class TaskWorker:
    """后台任务工作线程
    
    在后台持续消费任务队列并执行
    支持多个工作线程并发处理
    """
    
    def __init__(
        self,
        queue: TaskQueue,
        executor: TaskExecutor,
        num_workers: int = 2,
        default_callback: Optional[TaskCallback] = None
    ):
        """初始化工作线程
        
        Args:
            queue: 任务队列
            executor: 任务执行器
            num_workers: 工作线程数量
            default_callback: 默认完成回调
        """
        self.queue = queue
        self.executor = executor
        self.num_workers = num_workers
        self.default_callback = default_callback
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._shutdown_event = asyncio.Event()
        
        logger.info(f"TaskWorker initialized (num_workers={num_workers})")
    
    async def start(self):
        """启动工作线程"""
        if self._running:
            logger.warning("TaskWorker already running")
            return
        
        self._running = True
        self._shutdown_event.clear()
        
        # 启动多个工作线程
        for i in range(self.num_workers):
            worker = asyncio.create_task(
                self._worker_loop(i),
                name=f"task_worker_{i}"
            )
            self._workers.append(worker)
        
        logger.info(f"TaskWorker started with {self.num_workers} workers")
    
    async def stop(self):
        """停止工作线程"""
        if not self._running:
            return
        
        logger.info("Stopping TaskWorker...")
        self._running = False
        self._shutdown_event.set()
        
        # 取消所有工作线程
        for worker in self._workers:
            worker.cancel()
        
        # 等待完成
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        
        self._workers.clear()
        logger.info("TaskWorker stopped")
    
    async def _worker_loop(self, worker_id: int):
        """工作线程主循环
        
        Args:
            worker_id: 工作线程ID
        """
        logger.debug(f"Worker {worker_id} started")
        
        while self._running:
            try:
                # 等待新任务（带超时以便检查关闭信号）
                task = await self.queue.get(timeout=1.0)
                
                if task is None:
                    continue
                
                if task.status == TaskStatus.CANCELLED:
                    logger.debug(f"Task {task.id} was cancelled, skipping")
                    continue
                
                logger.debug(f"Worker {worker_id} processing task {task.id}")
                
                # 执行任务
                result = await self.executor.execute(task)
                
                # 更新队列状态
                await self.queue.complete(task, result)
                
                # 执行回调
                await self._invoke_callback(task, result)
                
            except asyncio.CancelledError:
                logger.debug(f"Worker {worker_id} cancelled")
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
        
        logger.debug(f"Worker {worker_id} stopped")
    
    async def _invoke_callback(self, task: Task, result: TaskResult):
        """调用任务回调
        
        Args:
            task: 任务对象
            result: 执行结果
        """
        callbacks = []
        
        # 任务特定回调
        if task.callback:
            callbacks.append(task.callback)
        
        # 默认回调
        if self.default_callback and task.callback != self.default_callback:
            callbacks.append(self.default_callback)
        
        # 执行所有回调
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(task, result)
                else:
                    callback(task, result)
            except Exception as e:
                logger.error(f"Task callback error: {e}")
    
    def get_stats(self) -> dict:
        """获取工作线程统计"""
        return {
            'running': self._running,
            'num_workers': self.num_workers,
            'active_workers': len([w for w in self._workers if not w.done()])
        }

