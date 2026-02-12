"""
任务执行器

支持异步函数直接执行，同步函数在线程池中执行
"""

import asyncio
import inspect
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Any, Callable
from loguru import logger

from .base import Task, TaskStatus, TaskResult


class TaskExecutor:
    """任务执行器
    
    自动判断函数类型，异步函数直接执行，同步函数放入线程池
    支持超时控制和失败重试
    """
    
    def __init__(self, max_workers: int = 4):
        """初始化执行器
        
        Args:
            max_workers: 线程池最大工作线程数
        """
        self._thread_pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="task_worker_"
        )
        self._running_tasks: dict = {}  # task_id -> asyncio.Task
        logger.info(f"TaskExecutor initialized (max_workers={max_workers})")
    
    async def execute(self, task: Task) -> TaskResult:
        """执行任务
        
        Args:
            task: 要执行的任务
            
        Returns:
            执行结果
        """
        if not task.func:
            return TaskResult(
                success=False,
                error="No function to execute"
            )
        
        start_time = time.time()
        task.status = TaskStatus.RUNNING
        task.started_at = start_time
        
        try:
            # 检查是否需要重试
            while task.retry_count <= task.max_retries:
                try:
                    result = await self._run_with_timeout(task)
                    result.duration_ms = (time.time() - start_time) * 1000
                    return result
                except asyncio.TimeoutError:
                    task.retry_count += 1
                    if task.retry_count > task.max_retries:
                        return TaskResult(
                            success=False,
                            error=f"Task timed out after {task.timeout}s",
                            duration_ms=(time.time() - start_time) * 1000
                        )
                    logger.warning(f"Task {task.id} timeout, retrying ({task.retry_count}/{task.max_retries})")
                    task.set_progress(f"超时重试 ({task.retry_count}/{task.max_retries})")
                except Exception as e:
                    task.retry_count += 1
                    if task.retry_count > task.max_retries:
                        raise
                    logger.warning(f"Task {task.id} failed, retrying ({task.retry_count}/{task.max_retries}): {e}")
                    task.set_progress(f"失败重试 ({task.retry_count}/{task.max_retries}): {str(e)[:50]}")
                    await asyncio.sleep(0.5 * task.retry_count)  # 指数退避
            
            return TaskResult(
                success=False,
                error="Max retries exceeded"
            )
            
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            return TaskResult(
                success=False,
                error="Task cancelled"
            )
        except Exception as e:
            logger.error(f"Task {task.id} execution failed: {e}")
            return TaskResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
    
    async def _run_with_timeout(self, task: Task) -> TaskResult:
        """带超时执行任务"""
        func = task.func
        args = task.args
        kwargs = task.kwargs
        
        # 注入任务对象到kwargs
        kwargs['_task'] = task
        
        # 判断函数类型
        if inspect.iscoroutinefunction(func):
            # 异步函数 - 直接执行
            coro = func(*args, **kwargs)
        else:
            # 同步函数 - 在线程池中执行
            loop = asyncio.get_event_loop()
            coro = loop.run_in_executor(
                self._thread_pool,
                self._wrap_sync_func(func, *args, **kwargs)
            )
        
        # 设置超时
        if task.timeout:
            coro = asyncio.wait_for(coro, timeout=task.timeout)
        
        try:
            output = await coro
            return TaskResult(success=True, output=output)
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            return TaskResult(success=False, error=str(e))
    
    def _wrap_sync_func(self, func: Callable, *args, **kwargs) -> Callable:
        """包装同步函数以支持任务取消检查"""
        def wrapper():
            return func(*args, **kwargs)
        return wrapper
    
    async def cancel_task(self, task_id: str) -> bool:
        """取消正在执行的任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功取消
        """
        if task_id in self._running_tasks:
            asyncio_task = self._running_tasks[task_id]
            asyncio_task.cancel()
            try:
                await asyncio_task
            except asyncio.CancelledError:
                pass
            return True
        return False
    
    def shutdown(self):
        """关闭执行器"""
        self._thread_pool.shutdown(wait=True)
        logger.info("TaskExecutor shutdown")

