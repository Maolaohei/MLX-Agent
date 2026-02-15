"""
天气获取模块

支持多种天气数据源
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
import aiohttp
from loguru import logger


class WeatherProvider:
    """天气提供者基类"""
    
    async def get_weather(self, location: str) -> Dict[str, Any]:
        """获取天气信息
        
        Args:
            location: 城市名称或坐标
            
        Returns:
            天气数据
        """
        raise NotImplementedError


class OpenMeteoProvider(WeatherProvider):
    """Open-Meteo 免费天气 API (无需密钥)"""
    
    BASE_URL = "https://api.open-meteo.com/v1"
    GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
    
    async def get_weather(self, location: str) -> Dict[str, Any]:
        """获取天气信息"""
        try:
            # 1. 先获取坐标
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.GEO_URL,
                    params={"name": location, "count": 1}
                ) as resp:
                    if resp.status != 200:
                        return {"error": f"Geocoding failed: {resp.status}"}
                    
                    geo_data = await resp.json()
                    if not geo_data.get("results"):
                        return {"error": f"Location not found: {location}"}
                    
                    result = geo_data["results"][0]
                    lat, lon = result["latitude"], result["longitude"]
                    city_name = result.get("name", location)
                    country = result.get("country", "")
            
            # 2. 获取天气数据
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": ["temperature_2m", "relative_humidity_2m", 
                                   "weather_code", "wind_speed_10m", "apparent_temperature"],
                        "daily": ["temperature_2m_max", "temperature_2m_min", 
                                 "weather_code", "precipitation_probability_max"],
                        "timezone": "auto"
                    }
                ) as resp:
                    if resp.status != 200:
                        return {"error": f"Weather API failed: {resp.status}"}
                    
                    data = await resp.json()
                    
                    return self._format_weather(data, city_name, country)
                    
        except Exception as e:
            logger.error(f"Failed to get weather: {e}")
            return {"error": str(e)}
    
    def _format_weather(self, data: Dict, city: str, country: str) -> Dict[str, Any]:
        """格式化天气数据"""
        current = data.get("current", {})
        daily = data.get("daily", {})
        
        weather_code = current.get("weather_code", 0)
        
        return {
            "location": f"{city}, {country}" if country else city,
            "current": {
                "temperature": current.get("temperature_2m"),
                "feels_like": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "wind_speed": current.get("wind_speed_10m"),
                "condition": self._get_weather_description(weather_code),
                "icon": self._get_weather_icon(weather_code)
            },
            "forecast": [
                {
                    "date": daily["time"][i],
                    "max_temp": daily["temperature_2m_max"][i],
                    "min_temp": daily["temperature_2m_min"][i],
                    "condition": self._get_weather_description(daily["weather_code"][i]),
                    "precipitation_chance": daily.get("precipitation_probability_max", [0]*7)[i]
                }
                for i in range(min(3, len(daily.get("time", []))))
            ],
            "updated_at": datetime.now().isoformat()
        }
    
    def _get_weather_description(self, code: int) -> str:
        """根据天气代码获取描述"""
        weather_codes = {
            0: "晴", 1: "大部晴朗", 2: "多云", 3: "阴天",
            45: "雾", 48: "雾凇",
            51: "毛毛雨", 53: "小雨", 55: "中雨",
            61: "小雨", 63: "中雨", 65: "大雨",
            71: "小雪", 73: "中雪", 75: "大雪",
            80: "阵雨", 81: "强阵雨", 82: "暴雨",
            95: "雷雨", 96: "雷雨伴冰雹", 99: "强雷雨伴冰雹"
        }
        return weather_codes.get(code, "未知")
    
    def _get_weather_icon(self, code: int) -> str:
        """根据天气代码获取图标"""
        if code == 0:
            return "☀️"
        elif code in [1, 2]:
            return "⛅"
        elif code == 3:
            return "☁️"
        elif code in [45, 48]:
            return "🌫️"
        elif code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
            return "🌧️"
        elif code in [71, 73, 75]:
            return "🌨️"
        elif code in [95, 96, 99]:
            return "⛈️"
        return "🌡️"


class OpenWeatherProvider(WeatherProvider):
    """OpenWeatherMap API (需要 API Key)"""
    
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("OPENWEATHER_API_KEY")
    
    async def get_weather(self, location: str) -> Dict[str, Any]:
        """获取天气信息"""
        if not self.api_key:
            return {"error": "OpenWeatherMap API key not configured"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/weather",
                    params={
                        "q": location,
                        "appid": self.api_key,
                        "units": "metric",
                        "lang": "zh_cn"
                    }
                ) as resp:
                    if resp.status != 200:
                        return {"error": f"API error: {resp.status}"}
                    
                    data = await resp.json()
                    
                    return {
                        "location": f"{data['name']}, {data['sys'].get('country', '')}",
                        "current": {
                            "temperature": data["main"]["temp"],
                            "feels_like": data["main"]["feels_like"],
                            "humidity": data["main"]["humidity"],
                            "wind_speed": data["wind"]["speed"],
                            "condition": data["weather"][0]["description"],
                            "icon": self._get_icon_emoji(data["weather"][0]["icon"])
                        },
                        "updated_at": datetime.now().isoformat()
                    }
        except Exception as e:
            logger.error(f"Failed to get weather: {e}")
            return {"error": str(e)}
    
    def _get_icon_emoji(self, icon_code: str) -> str:
        """转换图标代码为 emoji"""
        icon_map = {
            "01d": "☀️", "01n": "🌙",
            "02d": "⛅", "02n": "☁️",
            "03d": "☁️", "03n": "☁️",
            "04d": "☁️", "04n": "☁️",
            "09d": "🌧️", "09n": "🌧️",
            "10d": "🌦️", "10n": "🌧️",
            "11d": "⛈️", "11n": "⛈️",
            "13d": "🌨️", "13n": "🌨️",
            "50d": "🌫️", "50n": "🌫️"
        }
        return icon_map.get(icon_code, "🌡️")


class WeatherService:
    """天气服务"""
    
    def __init__(self, provider: str = "openmeteo", api_key: str = None):
        """
        Args:
            provider: 天气提供者 ('openmeteo' 或 'openweather')
            api_key: API 密钥 (OpenWeather 需要)
        """
        if provider == "openweather":
            self.provider = OpenWeatherProvider(api_key)
        else:
            self.provider = OpenMeteoProvider()
    
    async def get_weather(self, location: str) -> Dict[str, Any]:
        """获取天气"""
        return await self.provider.get_weather(location)
    
    async def format_weather_text(self, location: str) -> str:
        """格式化为文本报告"""
        data = await self.get_weather(location)
        
        if "error" in data:
            return f"❌ 获取天气失败: {data['error']}"
        
        current = data["current"]
        lines = [
            f"🌍 {data['location']}",
            f"{current['icon']} 当前: {current['condition']}",
            f"🌡️ 温度: {current['temperature']}°C (体感 {current['feels_like']}°C)",
            f"💧 湿度: {current['humidity']}%",
            f"💨 风速: {current['wind_speed']} km/h"
        ]
        
        # 添加预报
        if "forecast" in data:
            lines.append("\n📅 未来3天:")
            for day in data["forecast"]:
                lines.append(
                    f"  {day['date']}: {day['condition']} "
                    f"{day['min_temp']}°C ~ {day['max_temp']}°C"
                )
        
        return "\n".join(lines)
