"""
技能管理器 - v0.3.0 原生工具版

集成原生工具系统，移除 OpenClaw 兼容层
"""

import importlib.util
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

from .plugin import BasePlugin, PluginMetadata
from ..tools import tool_registry, get_available_tools, execute_tool


class SkillManager:
    """
    技能管理器 - 负责动态加载/卸载插件 + 管理原生工具
    
    架构:
    - 原生工具: 通过 tool_registry 直接访问 (推荐)
    - 动态插件: 从 plugins/ 目录加载 (扩展)
    """
    
    def __init__(self, plugin_dir: str = "plugins"):
        self.plugin_dir = Path(plugin_dir)
        self.plugins: Dict[str, BasePlugin] = {}  # plugin_name -> instance
        self.context = None  # Agent 实例引用

    async def initialize(self, context: Any):
        """初始化技能管理器"""
        self.context = context
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载动态插件
        await self.reload_all()
        
        logger.info(f"SkillManager initialized")
        logger.info(f"  - Native tools: {len(get_available_tools())}")
        logger.info(f"  - Dynamic plugins: {len(self.plugins)}")

    async def reload_all(self):
        """重载所有动态插件"""
        logger.info(f"Reloading plugins from {self.plugin_dir}...")
        
        # 清理旧插件
        for name, plugin in self.plugins.items():
            try:
                await plugin.on_unload()
            except Exception as e:
                logger.warning(f"Error unloading plugin {name}: {e}")
        
        self.plugins.clear()
        
        # 扫描目录
        if not self.plugin_dir.exists():
            return

        for file_path in self.plugin_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
                
            await self._load_plugin_from_file(file_path)
            
        logger.info(f"Loaded {len(self.plugins)} dynamic plugins")

    async def _load_plugin_from_file(self, file_path: Path):
        """从文件加载插件"""
        try:
            module_name = f"plugins.{file_path.stem}"
            
            # 动态导入
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if not spec or not spec.loader:
                return
                
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # 查找 BasePlugin 子类
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BasePlugin) and 
                    attr is not BasePlugin):
                    
                    # 实例化
                    plugin = attr(self.context)
                    meta = plugin._metadata
                    
                    self.plugins[meta.name] = plugin
                    
                    # 注册插件的工具到全局 registry
                    tools = plugin.define_tools()
                    for tool_schema in tools:
                        func_name = tool_schema["function"]["name"]
                        # 插件工具通过插件实例执行
                        tool_registry.register(PluginToolWrapper(func_name, plugin))
                    
                    logger.debug(f"Loaded plugin: {meta.name} v{meta.version}")
                    
        except Exception as e:
            logger.error(f"Failed to load plugin {file_path.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def get_all_tools_schema(self) -> List[dict]:
        """获取所有可用工具的 OpenAI Schema
        
        包括:
        1. 原生工具 (tool_registry)
        2. 动态插件工具
        """
        schemas = []
        
        # 1. 原生工具
        schemas.extend(tool_registry.get_all_schemas())
        
        # 2. 动态插件工具
        for plugin in self.plugins.values():
            if not plugin._metadata.hidden:
                schemas.extend(plugin.define_tools())
        
        return schemas

    async def execute_tool(self, name: str, arguments: dict, context: dict) -> Any:
        """执行工具
        
        执行顺序:
        1. 先尝试原生工具
        2. 再尝试动态插件
        """
        # 1. 尝试原生工具
        if name in get_available_tools():
            result = await execute_tool(name, **arguments)
            return {
                "success": result.success,
                "output": result.output,
                "error": result.error
            }
        
        # 2. 尝试动态插件
        for plugin in self.plugins.values():
            tools = plugin.define_tools()
            tool_names = [t["function"]["name"] for t in tools]
            if name in tool_names:
                return await plugin.execute(name, arguments, context)
        
        raise ValueError(f"Tool {name} not found")


class PluginToolWrapper:
    """插件工具包装器
    
    将插件工具包装为 BaseTool 接口
    """
    
    def __init__(self, name: str, plugin: BasePlugin):
        self._name = name
        self._plugin = plugin
        self._schema = None
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return f"Plugin tool from {self._plugin._metadata.name}"
    
    def get_schema(self) -> dict:
        """获取工具的 OpenAI Schema"""
        if self._schema is None:
            # 从插件的 define_tools() 中查找对应工具的 schema
            for tool_schema in self._plugin.define_tools():
                func_name = tool_schema.get("function", {}).get("name")
                if func_name == self._name:
                    self._schema = tool_schema
                    break
            else:
                # 如果没找到，返回一个基本 schema
                self._schema = {
                    "type": "function",
                    "function": {
                        "name": self._name,
                        "description": self.description,
                        "parameters": {"type": "object", "properties": {}}
                    }
                }
        return self._schema
    
    async def execute(self, **params):
        """执行插件工具"""
        return await self._plugin.execute(self._name, params, {})
