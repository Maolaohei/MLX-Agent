import importlib.util
import sys
import os
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger
from .plugin import BasePlugin, PluginMetadata

class SkillManager:
    """
    技能管理器 - 负责动态加载/卸载插件
    """
    def __init__(self, plugin_dir: str = "plugins"):
        self.plugin_dir = Path(plugin_dir)
        self.plugins: Dict[str, BasePlugin] = {}  # plugin_name -> instance
        self.tools_map: Dict[str, BasePlugin] = {} # tool_name -> plugin_instance
        self.context = None  # Agent 实例引用

    async def initialize(self, context: Any):
        """初始化并加载所有插件"""
        self.context = context
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        await self.reload_all()
        
        # 启动文件监控（简化版：轮询）
        # asyncio.create_task(self._watch_loop())

    async def reload_all(self):
        """重载所有插件"""
        logger.info(f"Reloading plugins from {self.plugin_dir}...")
        
        # 清理旧插件
        for name, plugin in self.plugins.items():
            await plugin.on_unload()
        
        self.plugins.clear()
        self.tools_map.clear()
        
        # 扫描目录
        if not self.plugin_dir.exists():
            return

        for file_path in self.plugin_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
                
            await self._load_plugin_from_file(file_path)
            
        logger.info(f"Loaded {len(self.plugins)} plugins with {len(self.tools_map)} tools")

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
                    
                    # 注册工具
                    tools = plugin.define_tools()
                    for tool in tools:
                        func_name = tool["function"]["name"]
                        self.tools_map[func_name] = plugin
                    
                    logger.debug(f"Loaded plugin: {meta.name} v{meta.version}")
                    
        except Exception as e:
            logger.error(f"Failed to load plugin {file_path.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def get_all_tools_schema(self) -> List[dict]:
        """获取所有已加载工具的 OpenAI Schema"""
        schemas = []
        for plugin in self.plugins.values():
            if not plugin._metadata.hidden:
                schemas.extend(plugin.define_tools())
        return schemas

    async def execute_tool(self, name: str, arguments: dict, context: dict) -> Any:
        """路由并执行工具"""
        if name not in self.tools_map:
            raise ValueError(f"Tool {name} not found")
            
        plugin = self.tools_map[name]
        return await plugin.execute(name, arguments, context)
