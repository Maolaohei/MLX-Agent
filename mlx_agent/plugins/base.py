"""
MLX-Agent 插件基类

所有插件必须继承此类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import asyncio


@dataclass
class PluginTool:
    """插件提供的工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: str  # 处理函数名称


class Plugin(ABC):
    """MLX-Agent 插件基类"""
    
    def __init__(self):
        self._initialized = False
        self._config: Dict[str, Any] = {}
        self._metadata = {
            "version": "1.0.0",
            "author": "MLX-Agent",
            "created_at": datetime.now().isoformat()
        }
    
    @property
    @abstractmethod
    def name(self) -> str:
        """插件名称 (唯一标识)"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """插件描述"""
        pass
    
    @property
    def version(self) -> str:
        """插件版本"""
        return self._metadata.get("version", "1.0.0")
    
    @property
    def initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized
    
    async def initialize(self, config: Dict[str, Any] = None):
        """初始化插件
        
        Args:
            config: 插件配置字典
        """
        self._config = config or {}
        await self._setup()
        self._initialized = True
    
    @abstractmethod
    async def _setup(self):
        """子类实现的具体初始化逻辑"""
        pass
    
    async def shutdown(self):
        """关闭插件，释放资源"""
        await self._cleanup()
        self._initialized = False
    
    async def _cleanup(self):
        """子类实现的具体清理逻辑 (可选)"""
        pass
    
    def get_tools(self) -> List[Dict]:
        """返回插件提供的工具 (OpenAI Function Calling 格式)
        
        Returns:
            工具定义列表
        """
        return []
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用
        
        Args:
            tool_name: 工具名称
            params: 工具参数
            
        Returns:
            执行结果
        """
        return {
            "success": False,
            "error": f"Tool '{tool_name}' not implemented in plugin '{self.name}'"
        }
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        return self._config.get(key, default)
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查
        
        Returns:
            健康状态字典
        """
        return {
            "status": "healthy" if self._initialized else "not_initialized",
            "plugin": self.name,
            "version": self.version
        }


class PluginManager:
    """插件管理器"""
    
    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._tool_map: Dict[str, str] = {}  # tool_name -> plugin_name
    
    def register(self, plugin: Plugin):
        """注册插件
        
        Args:
            plugin: 插件实例
        """
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin '{plugin.name}' already registered")
        
        self._plugins[plugin.name] = plugin
        
        # 注册工具映射
        for tool in plugin.get_tools():
            tool_name = tool.get("function", {}).get("name")
            if tool_name:
                self._tool_map[tool_name] = plugin.name
    
    def unregister(self, plugin_name: str):
        """注销插件
        
        Args:
            plugin_name: 插件名称
        """
        if plugin_name not in self._plugins:
            return
        
        # 清理工具映射
        tools_to_remove = [
            name for name, plugin in self._tool_map.items()
            if plugin == plugin_name
        ]
        for tool_name in tools_to_remove:
            del self._tool_map[tool_name]
        
        del self._plugins[plugin_name]
    
    def get(self, name: str) -> Optional[Plugin]:
        """获取插件
        
        Args:
            name: 插件名称
            
        Returns:
            插件实例或 None
        """
        return self._plugins.get(name)
    
    def list_plugins(self) -> List[str]:
        """列出所有已注册插件"""
        return list(self._plugins.keys())
    
    def get_all_tools(self) -> List[Dict]:
        """获取所有插件的工具定义"""
        tools = []
        for plugin in self._plugins.values():
            tools.extend(plugin.get_tools())
        return tools
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用
        
        Args:
            tool_name: 工具名称
            params: 工具参数
            
        Returns:
            执行结果
        """
        plugin_name = self._tool_map.get(tool_name)
        if not plugin_name:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }
        
        plugin = self._plugins.get(plugin_name)
        if not plugin:
            return {
                "success": False,
                "error": f"Plugin '{plugin_name}' not found"
            }
        
        return await plugin.handle_tool(tool_name, params)
    
    async def initialize_all(self, configs: Dict[str, Dict] = None):
        """初始化所有插件
        
        Args:
            configs: 插件配置字典 {plugin_name: config}
        """
        configs = configs or {}
        for name, plugin in self._plugins.items():
            try:
                await plugin.initialize(configs.get(name, {}))
            except Exception as e:
                print(f"Failed to initialize plugin '{name}': {e}")
    
    async def shutdown_all(self):
        """关闭所有插件"""
        for name, plugin in self._plugins.items():
            try:
                await plugin.shutdown()
            except Exception as e:
                print(f"Error shutting down plugin '{name}': {e}")


# 全局插件管理器实例
plugin_manager = PluginManager()


def register_plugin(plugin_class: type):
    """插件注册装饰器
    
    用法:
        @register_plugin
        class MyPlugin(Plugin):
            ...
    """
    instance = plugin_class()
    plugin_manager.register(instance)
    return plugin_class
