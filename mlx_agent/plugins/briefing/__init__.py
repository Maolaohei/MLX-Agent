"""
Daily Briefing Plugin

每日晨报生成与定时推送
"""

from .plugin import BriefingPlugin
from .weather import WeatherService, WeatherProvider, OpenMeteoProvider

__all__ = ["BriefingPlugin", "WeatherService", "WeatherProvider", "OpenMeteoProvider"]
