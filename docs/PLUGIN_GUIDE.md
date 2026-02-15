# MLX-Agent 插件开发指南

> 本文档介绍 MLX-Agent v0.4.0+ 插件系统的架构和开发方法

---

## 目录

- [概述](#概述)
- [插件架构](#插件架构)
- [Plugin 基类](#plugin-基类)
- [工具定义格式](#工具定义格式)
- [开发步骤](#开发步骤)
- [示例插件](#示例插件)
- [最佳实践](#最佳实践)

---

## 概述

MLX-Agent 插件系统采用**热插拔架构**，支持：

- ✅ 动态加载/卸载
- ✅ 配置驱动启用
- ✅ OpenAI Function 工具集成
- ✅ 定时任务调度
- ✅ 生命周期管理

### 已有插件

| 插件名 | 功能描述 |
|--------|----------|
| `backup-restore` | 自动备份、WebDAV 同步、定时任务 |
| `api-manager` | API 密钥加密存储、自动轮换 |
| `daily-briefing` | 每日晨报、天气、系统状态 |
| `remindme` | 自然语言提醒、定时调度 |

---

## 插件架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      MLX-Agent Core                             │
│                     (Agent / LLM / Memory)                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Plugin Manager                               │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  - 动态加载/卸载插件                                       │  │
│  │  - 配置验证                                                │  │
│  │  - 生命周期管理 (init/start/stop)                          │  │
│  │  - 工具注册到 LLM                                          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
    ┌───────────┐     ┌───────────┐     ┌───────────┐
    │ Plugin A  │     │ Plugin B  │     │ Plugin C  │
    │ ┌───────┐ │     │ ┌───────┐ │     │ ┌───────┐ │
    │ │ Tools │ │     │ │ Tools │ │     │ │ Tools │ │
    │ │ Tasks │ │     │ │ Tasks │ │     │ │ Tasks │ │
    │ └───────┘ │     │ └───────┘ │     │ └───────┘ │
    └───────────┘     └───────────┘     └───────────┘
```

---

## Plugin 基类

所有插件必须继承 `Plugin` 基类：

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass

@dataclass
class ToolDefinition:
    """工具定义结构"""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable

@dataclass
class TaskSchedule:
    """定时任务定义"""
    name: str
    schedule: str  # cron 表达式
    handler: Callable
    enabled: bool = True

class Plugin(ABC):
    """
    插件基类 - 所有插件必须继承
    """
    
    # 插件元数据
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化插件
        
        Args:
            config: 插件配置字典（来自 config.yaml）
        """
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self._tools: List[ToolDefinition] = []
        self._tasks: List[TaskSchedule] = []
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        初始化插件
        
        Returns:
            bool: 初始化是否成功
        """
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """启动插件（注册工具、启动定时任务）"""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """停止插件（清理资源）"""
        pass
    
    def register_tool(self, tool: ToolDefinition) -> None:
        """注册工具到 LLM"""
        self._tools.append(tool)
    
    def register_task(self, task: TaskSchedule) -> None:
        """注册定时任务"""
        self._tasks.append(task)
    
    @property
    def tools(self) -> List[ToolDefinition]:
        """获取所有注册的工具"""
        return self._tools
    
    @property
    def tasks(self) -> List[TaskSchedule]:
        """获取所有注册的任务"""
        return self._tasks
```

---

## 工具定义格式

插件工具使用 **OpenAI Function** 格式定义：

```python
def get_weather(city: str, units: str = "celsius") -> str:
    """
    获取指定城市的天气信息
    
    Args:
        city: 城市名称，如 "Beijing"
        units: 温度单位，celsius 或 fahrenheit
    
    Returns:
        天气信息字符串
    """
    # 实现...

# 工具定义
weather_tool = ToolDefinition(
    name="get_weather",
    description="获取指定城市的当前天气信息",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名称，如 'Beijing'"
            },
            "units": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "default": "celsius",
                "description": "温度单位"
            }
        },
        "required": ["city"]
    },
    handler=get_weather
)
```

### 参数类型映射

| OpenAI 类型 | Python 类型 | 示例 |
|-------------|-------------|------|
| `string` | `str` | `"hello"` |
| `number` | `float` | `3.14` |
| `integer` | `int` | `42` |
| `boolean` | `bool` | `true` |
| `array` | `list` | `[1, 2, 3]` |
| `object` | `dict` | `{"key": "value"}` |

---

## 开发步骤

### 1. 创建插件文件

在 `mlx_agent/plugins/` 目录创建新文件：

```bash
mlx_agent/plugins/
├── __init__.py
├── base.py          # Plugin 基类
├── backup_restore.py
├── api_manager.py
├── daily_briefing.py
├── remindme.py
└── my_plugin.py     # 你的新插件
```

### 2. 继承 Plugin 基类

```python
# mlx_agent/plugins/my_plugin.py
from .base import Plugin, ToolDefinition, TaskSchedule

class MyPlugin(Plugin):
    """我的示例插件"""
    
    name = "my-plugin"
    version = "1.0.0"
    description = "示例插件，展示如何开发 MLX-Agent 插件"
    author = "Your Name"
    
    async def initialize(self) -> bool:
        """初始化插件"""
        self.api_key = self.config.get("api_key")
        if not self.api_key:
            self.logger.error("Missing api_key in config")
            return False
        return True
    
    async def start(self) -> None:
        """启动插件"""
        # 注册工具
        self.register_tool(self._create_hello_tool())
        
        # 注册定时任务（可选）
        if self.config.get("enable_schedule", False):
            self.register_task(TaskSchedule(
                name="daily_hello",
                schedule="0 9 * * *",  # 每天9点
                handler=self._daily_hello
            ))
    
    async def stop(self) -> None:
        """停止插件"""
        pass
    
    def _create_hello_tool(self) -> ToolDefinition:
        """创建问候工具"""
        async def say_hello(name: str, enthusiastic: bool = False) -> str:
            """向指定用户发送问候"""
            greeting = "Hello" if not enthusiastic else "HELLO!!!"
            return f"{greeting}, {name}! Welcome to MLX-Agent!"
        
        return ToolDefinition(
            name="say_hello",
            description="向用户发送个性化问候",
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "用户名称"
                    },
                    "enthusiastic": {
                        "type": "boolean",
                        "default": False,
                        "description": "是否使用热情模式"
                    }
                },
                "required": ["name"]
            },
            handler=say_hello
        )
    
    async def _daily_hello(self) -> None:
        """定时任务处理"""
        print("Good morning! It's 9 AM!")
```

### 3. 添加配置到 config.yaml

```yaml
plugins:
  my-plugin:
    enabled: true
    api_key: ${MY_API_KEY}
    enable_schedule: true
```

### 4. 注册插件

在 `mlx_agent/plugins/__init__.py` 中注册：

```python
from .my_plugin import MyPlugin

__all__ = [
    "BackupRestorePlugin",
    "ApiManagerPlugin", 
    "DailyBriefingPlugin",
    "RemindMePlugin",
    "MyPlugin",  # 添加新插件
]
```

---

## 示例插件

### 完整示例: 天气查询插件

```python
# mlx_agent/plugins/weather_plugin.py
import aiohttp
from .base import Plugin, ToolDefinition, TaskSchedule

class WeatherPlugin(Plugin):
    """
    天气查询插件
    
    提供实时天气查询功能，支持多城市
    """
    
    name = "weather"
    version = "1.0.0"
    description = "查询全球城市实时天气"
    author = "MLX-Agent Team"
    
    async def initialize(self) -> bool:
        """初始化插件"""
        self.api_key = self.config.get("api_key")
        self.default_city = self.config.get("default_city", "Beijing")
        self.base_url = "https://api.weather.com/v1/current"
        
        if not self.api_key:
            # 使用免费 API 作为备选
            self.base_url = "https://wttr.in"
        
        return True
    
    async def start(self) -> None:
        """启动插件，注册工具"""
        self.register_tool(self._create_weather_tool())
    
    async def stop(self) -> None:
        """停止插件"""
        pass
    
    def _create_weather_tool(self) -> ToolDefinition:
        """创建天气查询工具"""
        
        async def get_weather(city: str, format: str = "simple") -> str:
            """
            获取指定城市的天气信息
            
            Args:
                city: 城市名称（中文或英文）
                format: 输出格式，simple 或 detailed
            
            Returns:
                天气信息字符串
            """
            try:
                # 使用 wttr.in 免费 API
                url = f"https://wttr.in/{city}?format=j1"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            return f"无法获取 {city} 的天气信息"
                        
                        data = await resp.json()
                        current = data["current_condition"][0]
                        
                        if format == "simple":
                            return (
                                f"🌤️ {city} 当前天气:\n"
                                f"温度: {current['temp_C']}°C\n"
                                f"体感: {current['FeelsLikeC']}°C\n"
                                f"湿度: {current['humidity']}%\n"
                                f"天气: {current['lang_zh'][0]['value']}"
                            )
                        else:
                            return (
                                f"🌤️ {city} 详细天气:\n"
                                f"温度: {current['temp_C']}°C (最高 {current['maxtempC']}°C / 最低 {current['mintempC']}°C)\n"
                                f"体感: {current['FeelsLikeC']}°C\n"
                                f"湿度: {current['humidity']}%\n"
                                f"气压: {current['pressure']} hPa\n"
                                f"能见度: {current['visibility']} km\n"
                                f"天气: {current['lang_zh'][0]['value']}\n"
                                f"风速: {current['windspeedKmph']} km/h ({current['winddir16Point']})"
                            )
                            
            except Exception as e:
                return f"查询天气时出错: {str(e)}"
        
        return ToolDefinition(
            name="get_weather",
            description="获取指定城市的实时天气信息",
            parameters={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，支持中文或英文，如 'Beijing' 或 '北京'"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["simple", "detailed"],
                        "default": "simple",
                        "description": "输出格式：simple（简洁）或 detailed（详细）"
                    }
                },
                "required": ["city"]
            },
            handler=get_weather
        )
```

### 配置示例

```yaml
plugins:
  weather:
    enabled: true
    api_key: ${WEATHER_API_KEY}  # 可选，使用免费 API 时可省略
    default_city: "Shanghai"
```

### 使用方式

```
用户: 北京今天天气怎么样？

AI: 我来为您查询北京的天气...
[调用 get_weather 工具]

🌤️ 北京当前天气:
温度: 15°C
体感: 13°C
湿度: 45%
天气: 晴
```

---

## 最佳实践

### 1. 错误处理

```python
async def safe_handler(param: str) -> str:
    try:
        result = await risky_operation(param)
        return f"✅ 成功: {result}"
    except ValueError as e:
        return f"❌ 参数错误: {str(e)}"
    except Exception as e:
        # 记录错误日志
        logger.error(f"Unexpected error: {e}")
        return "❌ 操作失败，请稍后重试"
```

### 2. 配置验证

```python
async def initialize(self) -> bool:
    # 验证必需配置
    required = ["api_key", "endpoint"]
    for key in required:
        if not self.config.get(key):
            logger.error(f"Missing required config: {key}")
            return False
    
    # 验证配置值
    timeout = self.config.get("timeout", 30)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        logger.error(f"Invalid timeout value: {timeout}")
        return False
    
    return True
```

### 3. 工具命名规范

```python
# ✅ 好的命名
name="create_reminder"      # 动词 + 名词
name="get_weather"          # 清晰明确
name="backup_data"          # 小写下划线

# ❌ 避免
name="reminder"             # 缺少动作
name="getWeather"           # 驼峰命名
name="myPlugin_function"    # 过于冗长
```

### 4. 文档字符串

```python
async def my_handler(param: str, count: int = 1) -> str:
    """
    简短的功能描述（一句话）
    
    更详细的说明，解释功能、使用场景、注意事项等。
    可以包含多行。
    
    Args:
        param: 参数说明，包含格式示例
        count: 参数说明，包含默认值
    
    Returns:
        返回值说明，包含可能的格式
    
    Example:
        >>> await my_handler("test", 3)
        "Result: test-test-test"
    """
```

### 5. 资源清理

```python
async def stop(self) -> None:
    """确保资源被正确释放"""
    # 关闭连接池
    if self.session:
        await self.session.close()
    
    # 取消定时任务
    for task in self._running_tasks:
        task.cancel()
    
    # 清理临时文件
    if os.path.exists(self.temp_dir):
        shutil.rmtree(self.temp_dir)
```

---

## 调试技巧

### 本地测试

```python
# test_plugin.py
import asyncio
from mlx_agent.plugins.weather_plugin import WeatherPlugin

async def test():
    plugin = WeatherPlugin(config={"enabled": True})
    
    # 初始化
    success = await plugin.initialize()
    print(f"初始化: {'✅ 成功' if success else '❌ 失败'}")
    
    # 启动
    await plugin.start()
    print(f"注册工具: {len(plugin.tools)} 个")
    
    # 测试工具
    if plugin.tools:
        tool = plugin.tools[0]
        result = await tool.handler(city="Beijing", format="simple")
        print(f"测试结果:\n{result}")

if __name__ == "__main__":
    asyncio.run(test())
```

---

*Happy Coding! 🚀*
