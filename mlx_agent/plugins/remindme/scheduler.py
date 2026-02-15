"""
提醒调度器

管理提醒的添加、触发、循环
"""

import json
import asyncio
import uuid
import calendar
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class Reminder:
    """提醒项"""
    id: str
    content: str
    remind_at: str  # ISO format
    created_at: str
    repeat: Optional[Dict[str, Any]] = None  # {'type': 'daily'|'weekly'|'monthly', 'interval': int}
    tags: List[str] = None
    priority: str = "normal"  # low, normal, high
    is_active: bool = True
    notified: bool = False
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Reminder":
        return cls(**data)
    
    @property
    def remind_at_datetime(self) -> datetime:
        return datetime.fromisoformat(self.remind_at)


class ReminderScheduler:
    """提醒调度器"""
    
    def __init__(self, data_dir: Path, callback: Callable = None):
        """
        Args:
            data_dir: 数据存储目录
            callback: 提醒触发时的回调函数 (reminder: Reminder)
        """
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.reminders_file = data_dir / "reminders.json"
        self._reminders: Dict[str, Reminder] = {}
        self._callback = callback
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        self._load_reminders()
    
    def _load_reminders(self):
        """加载提醒数据"""
        if self.reminders_file.exists():
            try:
                with open(self.reminders_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for rid, reminder_data in data.items():
                    self._reminders[rid] = Reminder.from_dict(reminder_data)
                logger.info(f"Loaded {len(self._reminders)} reminders")
            except Exception as e:
                logger.error(f"Failed to load reminders: {e}")
    
    def _save_reminders(self):
        """保存提醒数据"""
        try:
            data = {k: v.to_dict() for k, v in self._reminders.items()}
            with open(self.reminders_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save reminders: {e}")
    
    def add_reminder(self, content: str, remind_at: datetime, 
                     repeat: Dict = None, tags: List[str] = None,
                     priority: str = "normal") -> Reminder:
        """添加提醒
        
        Args:
            content: 提醒内容
            remind_at: 提醒时间
            repeat: 重复设置
            tags: 标签
            priority: 优先级
            
        Returns:
            创建的提醒对象
        """
        reminder = Reminder(
            id=str(uuid.uuid4())[:8],
            content=content,
            remind_at=remind_at.isoformat(),
            created_at=datetime.now().isoformat(),
            repeat=repeat,
            tags=tags or [],
            priority=priority,
            is_active=True,
            notified=False
        )
        
        self._reminders[reminder.id] = reminder
        self._save_reminders()
        
        logger.info(f"Reminder added: {reminder.id} at {remind_at}")
        
        # 重新调度
        if self._running:
            self._reschedule()
        
        return reminder
    
    def delete_reminder(self, reminder_id: str) -> bool:
        """删除提醒
        
        Args:
            reminder_id: 提醒ID
            
        Returns:
            是否成功删除
        """
        if reminder_id not in self._reminders:
            return False
        
        del self._reminders[reminder_id]
        self._save_reminders()
        
        logger.info(f"Reminder deleted: {reminder_id}")
        return True
    
    def get_reminder(self, reminder_id: str) -> Optional[Reminder]:
        """获取提醒"""
        return self._reminders.get(reminder_id)
    
    def list_reminders(self, active_only: bool = True, 
                       tag: str = None) -> List[Reminder]:
        """列出提醒
        
        Args:
            active_only: 仅显示活动提醒
            tag: 按标签过滤
            
        Returns:
            提醒列表
        """
        reminders = list(self._reminders.values())
        
        if active_only:
            reminders = [r for r in reminders if r.is_active]
        
        if tag:
            reminders = [r for r in reminders if tag in r.tags]
        
        # 按时间排序
        reminders.sort(key=lambda r: r.remind_at_datetime)
        
        return reminders
    
    def update_reminder(self, reminder_id: str, **kwargs) -> Optional[Reminder]:
        """更新提醒
        
        Args:
            reminder_id: 提醒ID
            **kwargs: 要更新的字段
            
        Returns:
            更新后的提醒对象
        """
        reminder = self._reminders.get(reminder_id)
        if not reminder:
            return None
        
        for key, value in kwargs.items():
            if hasattr(reminder, key):
                setattr(reminder, key, value)
        
        self._save_reminders()
        
        # 重新调度
        if self._running:
            self._reschedule()
        
        return reminder
    
    def start(self):
        """启动调度器"""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._scheduler_loop())
            logger.info("Reminder scheduler started")
    
    def stop(self):
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Reminder scheduler stopped")
    
    def _reschedule(self):
        """重新调度"""
        if self._task:
            self._task.cancel()
        self._task = asyncio.create_task(self._scheduler_loop())
    
    async def _scheduler_loop(self):
        """调度循环"""
        while self._running:
            try:
                # 获取下一个需要触发的提醒
                next_reminder = self._get_next_reminder()
                
                if not next_reminder:
                    # 没有待处理的提醒，等待1分钟后重试
                    await asyncio.sleep(60)
                    continue
                
                now = datetime.now()
                wait_seconds = (next_reminder.remind_at_datetime - now).total_seconds()
                
                if wait_seconds <= 0:
                    # 立即触发
                    await self._trigger_reminder(next_reminder)
                else:
                    # 等待，但最长不超过60秒检查一次
                    wait_seconds = min(wait_seconds, 60)
                    await asyncio.sleep(wait_seconds)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)
    
    def _get_next_reminder(self) -> Optional[Reminder]:
        """获取下一个待触发的提醒"""
        now = datetime.now()
        active_reminders = [
            r for r in self._reminders.values()
            if r.is_active and not r.notified and r.remind_at_datetime > now
        ]
        
        if not active_reminders:
            return None
        
        return min(active_reminders, key=lambda r: r.remind_at_datetime)
    
    async def _trigger_reminder(self, reminder: Reminder):
        """触发提醒"""
        logger.info(f"Triggering reminder: {reminder.id}")
        
        # 调用回调
        if self._callback:
            try:
                if asyncio.iscoroutinefunction(self._callback):
                    await self._callback(reminder)
                else:
                    self._callback(reminder)
            except Exception as e:
                logger.error(f"Callback error: {e}")
        
        # 处理重复
        if reminder.repeat:
            next_time = self._calculate_next_repeat(reminder)
            if next_time:
                reminder.remind_at = next_time.isoformat()
                reminder.notified = False
                logger.info(f"Rescheduled reminder: {reminder.id} -> {next_time}")
            else:
                reminder.is_active = False
                reminder.notified = True
        else:
            reminder.notified = True
        
        self._save_reminders()
    
    def _calculate_next_repeat(self, reminder: Reminder) -> Optional[datetime]:
        """计算下次重复时间"""
        if not reminder.repeat:
            return None
        
        current = reminder.remind_at_datetime
        repeat_type = reminder.repeat.get('type')
        interval = reminder.repeat.get('interval', 1)
        
        if repeat_type == 'daily':
            return current + timedelta(days=interval)
        elif repeat_type == 'weekly':
            return current + timedelta(weeks=interval)
        elif repeat_type == 'monthly':
            # 简单处理：按月加
            year = current.year
            month = current.month + interval
            while month > 12:
                month -= 12
                year += 1
            
            # 处理月末日期
            last_day = calendar.monthrange(year, month)[1]
            day = min(current.day, last_day)
            
            return current.replace(year=year, month=month, day=day)
        
        return None
    
    def cleanup_expired(self, days: int = 30) -> int:
        """清理过期提醒
        
        Args:
            days: 删除多少天前的已过期提醒
            
        Returns:
            删除数量
        """
        cutoff = datetime.now() - timedelta(days=days)
        to_delete = []
        
        for rid, reminder in self._reminders.items():
            if reminder.notified and reminder.remind_at_datetime < cutoff:
                to_delete.append(rid)
        
        for rid in to_delete:
            del self._reminders[rid]
        
        if to_delete:
            self._save_reminders()
        
        return len(to_delete)
