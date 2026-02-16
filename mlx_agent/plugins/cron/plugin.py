"""
定时任务插件 - Cron 管理

功能:
- 添加定时任务
- 列出定时任务
- 删除定时任务
- 支持自然语言时间（如"明天下午3点"）
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import re

from loguru import logger

from ..base import Plugin


@dataclass
class CronTask:
    """定时任务定义"""
    id: str
    name: str
    schedule: str  # cron 表达式或自然语言描述
    task_type: str  # "briefing", "reminder", "custom"
    params: Dict[str, Any]
    enabled: bool = True
    created_at: str = ""
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class CronPlugin(Plugin):
    """定时任务管理插件"""
    
    @property
    def name(self) -> str:
        return "cron"
    
    @property
    def description(self) -> str:
        return "定时任务管理: 添加/列出/删除定时任务"
    
    async def _setup(self):
        """初始化"""
        self.data_dir = Path(self.get_config("data_dir", "./data/cron"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.tasks_file = self.data_dir / "tasks.json"
        self._tasks: Dict[str, CronTask] = {}
        self._load_tasks()
        
        # 启动调度器
        if self._tasks:
            asyncio.create_task(self._scheduler_loop())
        
        logger.info(f"Cron plugin initialized: {len(self._tasks)} tasks")
    
    async def _cleanup(self):
        """清理"""
        logger.info("Cron plugin shutdown")
    
    def _load_tasks(self):
        """加载任务"""
        if self.tasks_file.exists():
            try:
                with open(self.tasks_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for task_data in data:
                    task = CronTask(**task_data)
                    self._tasks[task.id] = task
            except Exception as e:
                logger.error(f"Failed to load cron tasks: {e}")
    
    def _save_tasks(self):
        """保存任务"""
        try:
            data = [asdict(task) for task in self._tasks.values()]
            with open(self.tasks_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save cron tasks: {e}")
    
    async def add_task(self, name: str, schedule: str, task_type: str, 
                       params: Dict[str, Any] = None) -> Dict[str, Any]:
        """添加定时任务
        
        Args:
            name: 任务名称
            schedule: 定时表达式 (cron格式或自然语言)
            task_type: 任务类型 (briefing, reminder, custom)
            params: 任务参数
            
        Returns:
            添加结果
        """
        import uuid
        
        task_id = str(uuid.uuid4())[:8]
        
        # 解析 schedule
        parsed_schedule = self._parse_schedule(schedule)
        if not parsed_schedule:
            return {
                "success": False,
                "error": f"无法解析时间表达式: {schedule}"
            }
        
        task = CronTask(
            id=task_id,
            name=name,
            schedule=parsed_schedule,
            task_type=task_type,
            params=params or {}
        )
        
        self._tasks[task_id] = task
        self._save_tasks()
        
        # 计算下次执行时间
        next_run = self._calculate_next_run(parsed_schedule)
        
        return {
            "success": True,
            "task": {
                "id": task_id,
                "name": name,
                "schedule": parsed_schedule,
                "next_run": next_run
            }
        }
    
    def _parse_schedule(self, schedule: str) -> str:
        """解析时间表达式
        
        支持格式:
        - Cron: "0 8 * * *" (每天8点)
        - 自然语言: "每天8点", "明天下午3点", "每周一"
        """
        schedule = schedule.strip()
        
        # 检查是否已经是 cron 表达式
        if re.match(r'^([0-9*,/-]+\s+){4}[0-9*,/-]+$', schedule):
            return schedule
        
        # 自然语言解析
        now = datetime.now()
        
        # 每天 X 点
        daily_match = re.match(r'每天\s*(\d+)[点:时]', schedule)
        if daily_match:
            hour = int(daily_match.group(1))
            return f"0 {hour} * * *"
        
        # 明天 X 点
        tomorrow_match = re.match(r'明天\s*(\d+)[点:时]', schedule)
        if tomorrow_match:
            hour = int(tomorrow_match.group(1))
            tomorrow = now + timedelta(days=1)
            return f"0 {hour} {tomorrow.day} {tomorrow.month} *"
        
        # 每周 X
        weekday_map = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 0, '天': 0,
            '周一': 1, '周二': 2, '周三': 3, '周四': 4, '周五': 5, '周六': 6, '周日': 0, '周天': 0
        }
        for cn_day, num in weekday_map.items():
            if f'每周{cn_day}' in schedule or f'每{cn_day}' in schedule:
                # 提取时间
                time_match = re.search(r'(\d+)[点:时]', schedule)
                hour = int(time_match.group(1)) if time_match else 8
                return f"0 {hour} * * {num}"
        
        # X 分钟后
        minutes_match = re.match(r'(\d+)\s*分钟?后', schedule)
        if minutes_match:
            minutes = int(minutes_match.group(1))
            future = now + timedelta(minutes=minutes)
            return f"{future.minute} {future.hour} {future.day} {future.month} *"
        
        # X 小时后
        hours_match = re.match(r'(\d+)\s*小时?后', schedule)
        if hours_match:
            hours = int(hours_match.group(1))
            future = now + timedelta(hours=hours)
            return f"{future.minute} {future.hour} {future.day} {future.month} *"
        
        return None
    
    def _calculate_next_run(self, schedule: str) -> Optional[str]:
        """计算下次执行时间"""
        try:
            # 简化计算，假设 schedule 是 cron 格式
            parts = schedule.split()
            if len(parts) == 5:
                minute, hour, day, month, weekday = parts
                now = datetime.now()
                
                # 简单的下次执行时间估算
                if day == '*' and month == '*':
                    # 每天执行
                    next_time = now.replace(hour=int(hour), minute=int(minute), second=0)
                    if next_time <= now:
                        next_time += timedelta(days=1)
                    return next_time.isoformat()
        except:
            pass
        return None
    
    async def list_tasks(self) -> Dict[str, Any]:
        """列出所有定时任务"""
        tasks = []
        for task in self._tasks.values():
            tasks.append({
                "id": task.id,
                "name": task.name,
                "schedule": task.schedule,
                "type": task.task_type,
                "enabled": task.enabled,
                "run_count": task.run_count,
                "last_run": task.last_run,
                "next_run": task.next_run or self._calculate_next_run(task.schedule)
            })
        
        return {
            "success": True,
            "tasks": tasks,
            "total": len(tasks)
        }
    
    async def delete_task(self, task_id: str) -> Dict[str, Any]:
        """删除定时任务"""
        if task_id not in self._tasks:
            return {
                "success": False,
                "error": f"任务 {task_id} 不存在"
            }
        
        del self._tasks[task_id]
        self._save_tasks()
        
        return {
            "success": True,
            "message": f"任务 {task_id} 已删除"
        }
    
    async def toggle_task(self, task_id: str, enabled: bool) -> Dict[str, Any]:
        """启用/禁用任务"""
        if task_id not in self._tasks:
            return {
                "success": False,
                "error": f"任务 {task_id} 不存在"
            }
        
        self._tasks[task_id].enabled = enabled
        self._save_tasks()
        
        return {
            "success": True,
            "message": f"任务 {task_id} 已{'启用' if enabled else '禁用'}"
        }
    
    async def _scheduler_loop(self):
        """调度循环"""
        logger.info("Cron scheduler started")
        
        while self._initialized:
            try:
                now = datetime.now()
                
                for task in self._tasks.values():
                    if not task.enabled:
                        continue
                    
                    # 检查是否应该执行
                    if self._should_run(task, now):
                        asyncio.create_task(self._execute_task(task))
                
                # 每分钟检查一次
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Cron scheduler error: {e}")
                await asyncio.sleep(60)
    
    def _should_run(self, task: CronTask, now: datetime) -> bool:
        """检查任务是否应该执行"""
        try:
            parts = task.schedule.split()
            if len(parts) != 5:
                return False
            
            minute, hour, day, month, weekday = parts
            
            # 简化匹配
            if minute != '*' and int(minute) != now.minute:
                return False
            if hour != '*' and int(hour) != now.hour:
                return False
            if day != '*' and int(day) != now.day:
                return False
            if month != '*' and int(month) != now.month:
                return False
            if weekday != '*' and int(weekday) != now.weekday():
                return False
            
            return True
        except:
            return False
    
    async def _execute_task(self, task: CronTask):
        """执行任务"""
        logger.info(f"Executing cron task: {task.name} ({task.id})")
        
        try:
            # 根据任务类型执行
            if task.task_type == "briefing":
                # 调用简报插件
                if hasattr(self.agent, 'plugin_manager'):
                    briefing_plugin = self.agent.plugin_manager.get('briefing')
                    if briefing_plugin:
                        result = await briefing_plugin.generate_briefing(
                            task.params.get('location')
                        )
                        # 发送结果到 Telegram
                        if result.get('success'):
                            await self._send_notification(result['text'])
            
            elif task.task_type == "reminder":
                # 发送提醒
                message = task.params.get('message', '提醒时间到了！')
                await self._send_notification(message)
            
            # 更新任务状态
            task.last_run = datetime.now().isoformat()
            task.run_count += 1
            task.next_run = self._calculate_next_run(task.schedule)
            self._save_tasks()
            
        except Exception as e:
            logger.error(f"Failed to execute cron task {task.id}: {e}")
    
    async def _send_notification(self, message: str):
        """发送通知"""
        # 这里会调用 Telegram 发送功能
        # 暂时记录日志，等 Telegram 插件完成
        logger.info(f"Cron notification: {message[:100]}...")
    
    def get_tools(self) -> List[Dict]:
        """返回工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "cron_add",
                    "description": "添加定时任务，支持自然语言时间如'每天8点'、'明天下午3点'、'每周一'",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "任务名称"
                            },
                            "schedule": {
                                "type": "string",
                                "description": "定时表达式，如'每天8点'、'明天下午3点'、'每周一'、'30分钟后'"
                            },
                            "task_type": {
                                "type": "string",
                                "enum": ["briefing", "reminder", "custom"],
                                "description": "任务类型: briefing=生成晨报, reminder=提醒, custom=自定义"
                            },
                            "params": {
                                "type": "object",
                                "description": "任务参数，如简报的位置、提醒的消息内容等"
                            }
                        },
                        "required": ["name", "schedule", "task_type"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cron_list",
                    "description": "列出所有定时任务",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cron_delete",
                    "description": "删除定时任务",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "任务ID"
                            }
                        },
                        "required": ["task_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cron_toggle",
                    "description": "启用或禁用定时任务",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "任务ID"
                            },
                            "enabled": {
                                "type": "boolean",
                                "description": "true=启用, false=禁用"
                            }
                        },
                        "required": ["task_id", "enabled"]
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        if tool_name == "cron_add":
            return await self.add_task(
                params.get("name"),
                params.get("schedule"),
                params.get("task_type"),
                params.get("params", {})
            )
        
        elif tool_name == "cron_list":
            return await self.list_tasks()
        
        elif tool_name == "cron_delete":
            return await self.delete_task(params.get("task_id"))
        
        elif tool_name == "cron_toggle":
            return await self.toggle_task(
                params.get("task_id"),
                params.get("enabled")
            )
        
        return await super().handle_tool(tool_name, params)
