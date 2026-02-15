"""
每日晨报插件

功能:
- 每日晨报生成
- 天气获取
- 系统状态汇总
- 定时推送
"""

import os
import json
import psutil
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from loguru import logger

from ..base import Plugin
from .weather import WeatherService


@dataclass
class BriefingSchedule:
    """晨报定时配置"""
    enabled: bool = True
    time: str = "08:00"  # 每天几点推送
    days_of_week: List[int] = None  # 0=周一, 6=周日, None=每天
    location: str = ""  # 天气位置
    include_weather: bool = True
    include_system: bool = True
    include_tasks: bool = True
    
    def __post_init__(self):
        if self.days_of_week is None:
            self.days_of_week = [0, 1, 2, 3, 4, 5, 6]


class BriefingPlugin(Plugin):
    """每日晨报插件"""
    
    @property
    def name(self) -> str:
        return "briefing"
    
    @property
    def description(self) -> str:
        return "每日晨报: 天气、系统状态、待办事项汇总"
    
    async def _setup(self):
        """初始化插件"""
        # 配置
        self.data_dir = Path(self.get_config("data_dir", "./data/briefing"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.schedule_file = self.data_dir / "schedule.json"
        self.history_file = self.data_dir / "history.json"
        
        # 天气服务
        weather_provider = self.get_config("weather_provider", "openmeteo")
        weather_api_key = self.get_config("weather_api_key")
        self.weather = WeatherService(weather_provider, weather_api_key)
        
        # 加载配置
        self._schedule: BriefingSchedule = self._load_schedule()
        self._history: List[Dict] = self._load_history()
        self._last_briefing: Optional[datetime] = None
        
        # 启动调度器
        if self._schedule.enabled:
            asyncio.create_task(self._scheduler_loop())
        
        logger.info(f"Briefing plugin initialized: schedule={self._schedule.time}")
    
    async def _cleanup(self):
        """清理资源"""
        logger.info("Briefing plugin shutdown")
    
    def _load_schedule(self) -> BriefingSchedule:
        """加载定时配置"""
        if self.schedule_file.exists():
            try:
                with open(self.schedule_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return BriefingSchedule(**data)
            except Exception as e:
                logger.error(f"Failed to load schedule: {e}")
        
        # 默认配置
        return BriefingSchedule(
            enabled=self.get_config("auto_enabled", True),
            time=self.get_config("default_time", "08:00"),
            location=self.get_config("default_location", "")
        )
    
    def _save_schedule(self):
        """保存定时配置"""
        try:
            with open(self.schedule_file, 'w', encoding='utf-8') as f:
                json.dump(self._schedule.__dict__, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save schedule: {e}")
    
    def _load_history(self) -> List[Dict]:
        """加载历史记录"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load history: {e}")
        return []
    
    def _save_history(self):
        """保存历史记录"""
        try:
            # 只保留最近30条
            history = self._history[-30:]
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
    
    async def generate_briefing(self, location: str = None) -> Dict[str, Any]:
        """生成晨报
        
        Args:
            location: 天气位置 (None=使用配置中的位置)
            
        Returns:
            晨报内容
        """
        location = location or self._schedule.location
        now = datetime.now()
        
        briefing = {
            "generated_at": now.isoformat(),
            "title": f"📅 {now.strftime('%Y年%m月%d日')} 晨报",
            "sections": []
        }
        
        # 1. 问候语
        hour = now.hour
        if 5 <= hour < 12:
            greeting = "🌅 早上好！"
        elif 12 <= hour < 18:
            greeting = "☀️ 下午好！"
        else:
            greeting = "🌙 晚上好！"
        
        briefing["greeting"] = greeting
        
        # 2. 天气
        if self._schedule.include_weather and location:
            weather_data = await self.weather.get_weather(location)
            if "error" not in weather_data:
                briefing["weather"] = weather_data
                briefing["sections"].append({
                    "title": "🌤️ 今日天气",
                    "content": await self.weather.format_weather_text(location)
                })
        
        # 3. 系统状态
        if self._schedule.include_system:
            system_status = self._get_system_status()
            briefing["system"] = system_status
            briefing["sections"].append({
                "title": "🖥️ 系统状态",
                "content": self._format_system_status(system_status)
            })
        
        # 4. 保存到历史
        self._history.append({
            "timestamp": now.isoformat(),
            "title": briefing["title"],
            "has_weather": "weather" in briefing
        })
        self._save_history()
        
        self._last_briefing = now
        
        return {
            "success": True,
            "briefing": briefing,
            "text": self._format_briefing_text(briefing)
        }
    
    def _get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # 运行时间
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            
            return {
                "cpu_percent": cpu_percent,
                "memory_used_percent": memory.percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_used_percent": disk.percent,
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "uptime_hours": round(uptime.total_seconds() / 3600, 1),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return {"error": str(e)}
    
    def _format_system_status(self, status: Dict) -> str:
        """格式化系统状态"""
        if "error" in status:
            return f"❌ 获取失败: {status['error']}"
        
        # 获取状态表情
        cpu_emoji = "🟢" if status["cpu_percent"] < 50 else "🟡" if status["cpu_percent"] < 80 else "🔴"
        mem_emoji = "🟢" if status["memory_used_percent"] < 70 else "🟡" if status["memory_used_percent"] < 90 else "🔴"
        disk_emoji = "🟢" if status["disk_used_percent"] < 80 else "🟡" if status["disk_used_percent"] < 90 else "🔴"
        
        lines = [
            f"{cpu_emoji} CPU: {status['cpu_percent']}%",
            f"{mem_emoji} 内存: {status['memory_used_percent']}% (可用 {status['memory_available_gb']}GB)",
            f"{disk_emoji} 磁盘: {status['disk_used_percent']}% (剩余 {status['disk_free_gb']}GB)",
            f"⏱️ 运行时间: {status['uptime_hours']} 小时"
        ]
        
        return "\n".join(lines)
    
    def _format_briefing_text(self, briefing: Dict) -> str:
        """格式化晨报为文本"""
        lines = [
            briefing["title"],
            "",
            briefing["greeting"],
            ""
        ]
        
        for section in briefing["sections"]:
            lines.extend([section["title"], section["content"], ""])
        
        lines.append("— 由 MLX-Agent 生成 —")
        
        return "\n".join(lines)
    
    async def schedule_briefing(self, time: str = None, enabled: bool = None,
                                location: str = None, days: List[int] = None) -> Dict[str, Any]:
        """配置晨报定时
        
        Args:
            time: 推送时间 (HH:MM)
            enabled: 是否启用
            location: 天气位置
            days: 推送日期 [0-6]
            
        Returns:
            配置结果
        """
        if time:
            # 验证时间格式
            try:
                datetime.strptime(time, "%H:%M")
                self._schedule.time = time
            except ValueError:
                return {
                    "success": False,
                    "error": "Invalid time format. Use HH:MM"
                }
        
        if enabled is not None:
            self._schedule.enabled = enabled
        
        if location is not None:
            self._schedule.location = location
        
        if days is not None:
            self._schedule.days_of_week = days
        
        self._save_schedule()
        
        return {
            "success": True,
            "schedule": {
                "enabled": self._schedule.enabled,
                "time": self._schedule.time,
                "location": self._schedule.location,
                "days": self._schedule.days_of_week
            }
        }
    
    async def get_schedule(self) -> Dict[str, Any]:
        """获取当前定时配置"""
        return {
            "success": True,
            "schedule": {
                "enabled": self._schedule.enabled,
                "time": self._schedule.time,
                "location": self._schedule.location,
                "days": self._schedule.days_of_week,
                "include_weather": self._schedule.include_weather,
                "include_system": self._schedule.include_system
            }
        }
    
    async def get_history(self, limit: int = 10) -> Dict[str, Any]:
        """获取历史晨报记录"""
        history = self._history[-limit:]
        history.reverse()
        
        return {
            "success": True,
            "history": history,
            "total": len(self._history)
        }
    
    async def _scheduler_loop(self):
        """定时调度循环"""
        logger.info(f"Briefing scheduler started (daily at {self._schedule.time})")
        
        while self._initialized:
            try:
                now = datetime.now()
                target_time = datetime.strptime(self._schedule.time, "%H:%M").time()
                target_datetime = datetime.combine(now.date(), target_time)
                
                # 如果今天的时间已过，排到明天
                if target_datetime <= now:
                    target_datetime += timedelta(days=1)
                
                wait_seconds = (target_datetime - now).total_seconds()
                logger.debug(f"Next briefing scheduled in {wait_seconds/3600:.1f} hours")
                
                await asyncio.sleep(wait_seconds)
                
                if not self._initialized:
                    break
                
                # 检查是否是推送日
                weekday = target_datetime.weekday()
                if weekday in self._schedule.days_of_week:
                    # 生成晨报
                    result = await self.generate_briefing()
                    if result["success"]:
                        logger.info("Daily briefing generated successfully")
                        # TODO: 这里可以添加推送逻辑
                    else:
                        logger.error(f"Failed to generate briefing: {result.get('error')}")
                
            except Exception as e:
                logger.error(f"Briefing scheduler error: {e}")
                await asyncio.sleep(3600)  # 出错后1小时重试
    
    def get_tools(self) -> List[Dict]:
        """返回工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "briefing_generate",
                    "description": "立即生成每日晨报",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "天气位置 (城市名)"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "briefing_schedule",
                    "description": "配置每日晨报定时推送",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "time": {
                                "type": "string",
                                "description": "推送时间 (HH:MM 格式，如 '08:00')"
                            },
                            "enabled": {
                                "type": "boolean",
                                "description": "是否启用定时推送"
                            },
                            "location": {
                                "type": "string",
                                "description": "默认天气位置"
                            },
                            "days": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "推送日期 [0=周一, 6=周日]，默认每天"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "briefing_get_schedule",
                    "description": "获取当前定时配置",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "briefing_history",
                    "description": "查看历史晨报记录",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "返回记录数量",
                                "default": 10
                            }
                        }
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        if tool_name == "briefing_generate":
            return await self.generate_briefing(params.get("location"))
        
        elif tool_name == "briefing_schedule":
            return await self.schedule_briefing(
                params.get("time"),
                params.get("enabled"),
                params.get("location"),
                params.get("days")
            )
        
        elif tool_name == "briefing_get_schedule":
            return await self.get_schedule()
        
        elif tool_name == "briefing_history":
            return await self.get_history(params.get("limit", 10))
        
        return await super().handle_tool(tool_name, params)
