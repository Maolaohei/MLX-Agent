"""
任务定义基类

定义任务的数据结构和回调接口
"""

import uuid
import time
import asyncio  # 新增
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Dict, List
from datetime import datetime


class TaskPriority(Enum):
    """任务优先级"""
    CRITICAL = 0   # 关键任务，立即执行
    HIGH = 1       # 高优先级
    NORMAL = 2     # 普通优先级
    LOW = 3        # 低优先级
    BACKGROUND = 4 # 后台任务


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"         # 等待中
    RUNNING = "running"         # 执行中
    COMPLETED = "completed"     # 已完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 已取消
    TIMEOUT = "timeout"         # 超时


@dataclass
class TaskResult:
    """任务执行结果"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            'success': self.success,
            'output': self.output,
            'error': self.error,
            'duration_ms': self.duration_ms,
            'metadata': self.metadata
        }


TaskCallback = Callable[['Task', TaskResult], Any]


@dataclass
class Task:
    """任务定义
    
    Attributes:
        id: 任务唯一ID
        type: 任务类型
        payload: 任务数据
        priority: 优先级
        func: 要执行的函数
        args: 位置参数
        kwargs: 关键字参数
        status: 当前状态
        result: 执行结果
        callback: 完成回调
        progress_callback: 进度回调
        created_at: 创建时间
        started_at: 开始时间
        completed_at: 完成时间
        retry_count: 重试次数
        max_retries: 最大重试次数
        timeout: 超时时间(秒)
        user_id: 关联用户ID
        chat_id: 关联聊天ID
        platform: 平台名称
        message_id: 关联消息ID
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = "default"
    payload: Dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    func: Optional[Callable] = None
    args: tuple = field(default_factory=tuple)
    kwargs: Dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[TaskResult] = None
    callback: Optional[TaskCallback] = None
    progress_callback: Optional[Callable[[str, Any], Any]] = None
    progress_updates: List[Dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 2
    timeout: Optional[float] = None
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    platform: Optional[str] = None
    message_id: Optional[str] = None
    
    def __lt__(self, other: 'Task') -> bool:
        """用于优先级队列比较"""
        if not isinstance(other, Task):
            return NotImplemented
        return self.priority.value < other.priority.value
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Task):
            return NotImplemented
        return self.id == other.id
    
    @property
    def wait_time(self) -> float:
        """等待时间(秒)"""
        if self.started_at:
            return self.started_at - self.created_at
        return time.time() - self.created_at
    
    @property
    def run_time(self) -> float:
        """执行时间(秒)"""
        if not self.started_at:
            return 0.0
        if self.completed_at:
            return self.completed_at - self.started_at
        return time.time() - self.started_at
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'id': self.id,
            'type': self.type,
            'priority': self.priority.name,
            'status': self.status.value,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'wait_time': self.wait_time,
            'run_time': self.run_time,
            'retry_count': self.retry_count,
            'result': self.result.to_dict() if self.result else None,
            'user_id': self.user_id,
            'platform': self.platform,
        }
    
    def set_progress(self, message: str, progress: float = None):
        """设置进度"""
        data = {'message': message}
        if progress is not None:
            data['progress'] = progress
        
        # 保存到更新列表
        self.progress_updates.append(data)
        
        # 调用回调函数
        if self.progress_callback:
            try:
                if asyncio.iscoroutinefunction(self.progress_callback):
                    # 如果是协程，尝试在当前循环中调度
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self.progress_callback(self.id, data))
                    except RuntimeError:
                        # 没有运行的循环，无法调度异步回调
                        pass
                else:
                    self.progress_callback(self.id, data)
            except Exception:
                pass
