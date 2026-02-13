from mlx_agent.skills.plugin import BasePlugin, PluginMetadata

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
                    "description": "获取当前天气（模拟）",
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
            return f"模拟数据：{location} 当前天气晴朗，气温 25°C，适合吃甜甜圈。"
        return f"Unknown tool: {name}"
