"""
提醒插件

功能:
- 自然语言解析提醒时间
- 定时提醒调度
- 循环提醒支持
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

from ..base import Plugin
from .parser import TimeParser, format_relative_time
from .scheduler import ReminderScheduler, Reminder


class RemindmePlugin(Plugin):
    """提醒插件"""
    
    @property
    def name(self) -> str:
        return "remindme"
    
    @property
    def description(self) -> str:
        return "提醒助手: 自然语言设置定时提醒与循环提醒"
    
    async def _setup(self):
        """初始化插件"""
        # 配置
        self.data_dir = Path(self.get_config("data_dir", "./data/reminders"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化调度器
        self.scheduler = ReminderScheduler(
            data_dir=self.data_dir,
            callback=self._on_reminder_triggered
        )
        
        # 启动调度器
        self.scheduler.start()
        
        self._pending_notifications: List[Dict] = []
        
        logger.info(f"Remindme plugin initialized")
    
    async def _cleanup(self):
        """清理资源"""
        self.scheduler.stop()
        logger.info("Remindme plugin shutdown")
    
    async def _on_reminder_triggered(self, reminder: Reminder):
        """提醒触发回调"""
        notification = {
            "id": reminder.id,
            "content": reminder.content,
            "triggered_at": datetime.now().isoformat(),
            "repeat": reminder.repeat
        }
        self._pending_notifications.append(notification)
        
        logger.info(f"Reminder triggered: {reminder.id} - {reminder.content}")
    
    async def add_reminder(self, content: str, time_str: str, 
                          repeat: str = None, tags: List[str] = None,
                          priority: str = "normal") -> Dict[str, Any]:
        """添加提醒
        
        Args:
            content: 提醒内容
            time_str: 时间描述 (如 "10分钟后", "明天下午3点")
            repeat: 重复描述 (如 "每天", "每周一")
            tags: 标签
            priority: 优先级
            
        Returns:
            操作结果
        """
        # 解析时间
        parser = TimeParser()
        remind_at = parser.parse(time_str)
        
        if not remind_at:
            return {
                "success": False,
                "error": f"无法解析时间描述: '{time_str}'。支持的格式如: '10分钟后', '明天下午3点', '下周一早上'"
            }
        
        # 检查时间是否已过
        if remind_at < datetime.now():
            return {
                "success": False,
                "error": f"提醒时间已过: {remind_at.strftime('%Y-%m-%d %H:%M')}"
            }
        
        # 解析重复
        repeat_config = None
        if repeat:
            repeat_config = parser.parse_repeat(repeat)
            if not repeat_config:
                return {
                    "success": False,
                    "error": f"无法解析重复描述: '{repeat}'。支持的格式如: '每天', '每周', '每月'"
                }
        
        # 创建提醒
        reminder = self.scheduler.add_reminder(
            content=content,
            remind_at=remind_at,
            repeat=repeat_config,
            tags=tags or [],
            priority=priority
        )
        
        # 格式化响应
        time_desc = format_relative_time(remind_at)
        repeat_desc = f"，重复: {repeat}" if repeat_config else ""
        
        return {
            "success": True,
            "reminder": {
                "id": reminder.id,
                "content": reminder.content,
                "remind_at": reminder.remind_at,
                "time_description": time_desc,
                "repeat": reminder.repeat,
                "tags": reminder.tags,
                "priority": reminder.priority
            },
            "message": f"✅ 已设置提醒: {time_desc}{repeat_desc}"
        }
    
    async def list_reminders(self, active_only: bool = True) -> Dict[str, Any]:
        """列出提醒
        
        Args:
            active_only: 仅显示活动提醒
            
        Returns:
            提醒列表
        """
        reminders = self.scheduler.list_reminders(active_only=active_only)
        
        now = datetime.now()
        result = []
        
        for r in reminders:
            time_left = r.remind_at_datetime - now
            time_desc = format_relative_time(r.remind_at_datetime, now)
            
            result.append({
                "id": r.id,
                "content": r.content,
                "remind_at": r.remind_at,
                "time_description": time_desc,
                "is_overdue": time_left.total_seconds() < 0,
                "repeat": r.repeat,
                "tags": r.tags,
                "priority": r.priority
            })
        
        return {
            "success": True,
            "reminders": result,
            "count": len(result),
            "pending_notifications": len(self._pending_notifications)
        }
    
    async def delete_reminder(self, reminder_id: str) -> Dict[str, Any]:
        """删除提醒
        
        Args:
            reminder_id: 提醒ID
            
        Returns:
            操作结果
        """
        success = self.scheduler.delete_reminder(reminder_id)
        
        if not success:
            return {
                "success": False,
                "error": f"提醒不存在: {reminder_id}"
            }
        
        return {
            "success": True,
            "deleted": reminder_id
        }
    
    async def get_pending_notifications(self, clear: bool = True) -> Dict[str, Any]:
        """获取待处理的通知
        
        Args:
            clear: 获取后清除
            
        Returns:
            通知列表
        """
        notifications = self._pending_notifications.copy()
        
        if clear:
            self._pending_notifications.clear()
        
        return {
            "success": True,
            "notifications": notifications,
            "count": len(notifications)
        }
    
    async def snooze_reminder(self, reminder_id: str, minutes: int = 10) -> Dict[str, Any]:
        """延后提醒
        
        Args:
            reminder_id: 提醒ID
            minutes: 延后分钟数
            
        Returns:
            操作结果
        """
        reminder = self.scheduler.get_reminder(reminder_id)
        if not reminder:
            return {
                "success": False,
                "error": f"提醒不存在: {reminder_id}"
            }
        
        new_time = datetime.now() + timedelta(minutes=minutes)
        
        self.scheduler.update_reminder(
            reminder_id,
            remind_at=new_time.isoformat(),
            notified=False
        )
        
        return {
            "success": True,
            "message": f"⏰ 已延后 {minutes} 分钟",
            "new_time": new_time.isoformat()
        }
    
    async def parse_time_preview(self, time_str: str) -> Dict[str, Any]:
        """预览时间解析结果
        
        Args:
            time_str: 时间描述
            
        Returns:
            解析结果
        """
        parser = TimeParser()
        result = parser.parse(time_str)
        
        if result:
            return {
                "success": True,
                "original": time_str,
                "parsed": result.isoformat(),
                "formatted": result.strftime('%Y年%m月%d日 %H:%M')
            }
        else:
            return {
                "success": False,
                "error": f"无法解析: '{time_str}'"
            }
    
    def get_tools(self) -> List[Dict]:
        """返回工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "reminder_add",
                    "description": "添加新的提醒。支持自然语言时间描述，如 '10分钟后', '明天下午3点', '下周一早上9点'",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "提醒内容"
                            },
                            "time": {
                                "type": "string",
                                "description": "提醒时间描述 (如 '10分钟后', '明天下午3点', '2024-01-01 09:00')"
                            },
                            "repeat": {
                                "type": "string",
                                "description": "重复设置 (可选，如 '每天', '每周', '每月')"
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "标签列表 (如 ['工作', '重要'])"
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "normal", "high"],
                                "description": "优先级",
                                "default": "normal"
                            }
                        },
                        "required": ["content", "time"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "reminder_list",
                    "description": "列出所有待处理的提醒",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "active_only": {
                                "type": "boolean",
                                "description": "仅显示活动提醒",
                                "default": True
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "reminder_delete",
                    "description": "删除指定提醒",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reminder_id": {
                                "type": "string",
                                "description": "提醒ID"
                            }
                        },
                        "required": ["reminder_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "reminder_snooze",
                    "description": "延后提醒到指定时间后",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reminder_id": {
                                "type": "string",
                                "description": "提醒ID"
                            },
                            "minutes": {
                                "type": "integer",
                                "description": "延后分钟数",
                                "default": 10
                            }
                        },
                        "required": ["reminder_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "reminder_parse_preview",
                    "description": "预览时间解析结果，用于测试时间描述",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "time": {
                                "type": "string",
                                "description": "时间描述 (如 '明天下午3点')"
                            }
                        },
                        "required": ["time"]
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        if tool_name == "reminder_add":
            return await self.add_reminder(
                params.get("content"),
                params.get("time"),
                params.get("repeat"),
                params.get("tags"),
                params.get("priority", "normal")
            )
        
        elif tool_name == "reminder_list":
            return await self.list_reminders(params.get("active_only", True))
        
        elif tool_name == "reminder_delete":
            return await self.delete_reminder(params.get("reminder_id"))
        
        elif tool_name == "reminder_snooze":
            return await self.snooze_reminder(
                params.get("reminder_id"),
                params.get("minutes", 10)
            )
        
        elif tool_name == "reminder_parse_preview":
            return await self.parse_time_preview(params.get("time"))
        
        return await super().handle_tool(tool_name, params)
