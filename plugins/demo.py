from mlx_agent.skills.plugin import BasePlugin, PluginMetadata
from mlx_agent.api_manager import get_api_manager

class DemoPlugin(BasePlugin):
    def on_load(self) -> PluginMetadata:
        return PluginMetadata(
            name="demo_plugin",
            description="演示用插件",
            version="0.0.1",
            author="Shinobu"
        )

    def define_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_current_weather",
                    "description": "获取当前天气（演示 API Manager 用法）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "城市名称"},
                        },
                        "required": ["location"]
                    }
                }
            }
        ]

    async def execute(self, name: str, arguments: dict, context: dict) -> str:
        if name == "get_current_weather":
            location = arguments.get("location", "Unknown")
            
            # 演示：检查 API Manager 是否可用
            api_manager = get_api_manager()
            available_apis = api_manager.list_available()
            
            return (
                f"🌤️ 模拟天气数据：{location}\n"
                f"天气：晴朗\n"
                f"气温：25°C\n"
                f"适宜：吃甜甜圈 🍩\n\n"
                f"[调试] 当前可用 API: {', '.join(available_apis) if available_apis else '无'}"
            )
        return f"Unknown tool: {name}"
