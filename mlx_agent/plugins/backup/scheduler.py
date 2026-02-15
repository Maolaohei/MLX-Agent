"""
备份插件 - 调度器模块

提供定时备份功能
"""

import asyncio
from datetime import datetime, timedelta
from typing import Callable, Optional
from loguru import logger


class BackupScheduler:
    """备份调度器"""
    
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._callback: Optional[Callable] = None
        self._running = False
    
    def start(self, hour: int, minute: int, callback: Callable):
        """启动定时调度
        
        Args:
            hour: 小时 (0-23)
            minute: 分钟 (0-59)
            callback: 回调函数
        """
        if self._running:
            self.stop()
        
        self._callback = callback
        self._running = True
        self._task = asyncio.create_task(self._loop(hour, minute))
        logger.info(f"Backup scheduler started: daily at {hour:02d}:{minute:02d}")
    
    def stop(self):
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Backup scheduler stopped")
    
    async def _loop(self, hour: int, minute: int):
        """调度循环"""
        while self._running:
            try:
                # 计算下次执行时间
                now = datetime.now()
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                if target <= now:
                    target += timedelta(days=1)
                
                wait_seconds = (target - now).total_seconds()
                logger.debug(f"Next backup in {wait_seconds/3600:.1f} hours")
                
                await asyncio.sleep(wait_seconds)
                
                if self._running and self._callback:
                    try:
                        await self._callback()
                    except Exception as e:
                        logger.error(f"Backup callback error: {e}")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(3600)  # 出错后1小时重试
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running and self._task is not None
