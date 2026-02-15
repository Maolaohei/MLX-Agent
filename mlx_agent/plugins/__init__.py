"""
MLX-Agent 插件系统

导出所有内置插件，提供自动发现机制
"""

from typing import List, Type, Dict, Any
import importlib
import pkgutil
from pathlib import Path

from .base import Plugin, PluginManager, PluginTool, register_plugin

# 导入所有内置插件
from .backup import BackupPlugin
from .api_manager import APIManagerPlugin
from .briefing import BriefingPlugin
from .remindme import RemindmePlugin


__all__ = [
    # 基类
    "Plugin",
    "PluginManager", 
    "PluginTool",
    "register_plugin",
    # 内置插件
    "BackupPlugin",
    "APIManagerPlugin",
    "BriefingPlugin",
    "RemindmePlugin",
    # 工具函数
    "get_all_plugins",
    "discover_plugins",
    "create_plugin_manager",
]


# 内置插件列表
BUILTIN_PLUGINS: List[Type[Plugin]] = [
    BackupPlugin,
    APIManagerPlugin,
    BriefingPlugin,
    RemindmePlugin,
]


def get_all_plugins() -> List[Type[Plugin]]:
    """获取所有可用的插件类 (包括内置插件)"""
    return BUILTIN_PLUGINS.copy()


def discover_plugins(package_path: str = None) -> List[Type[Plugin]]:
    """自动发现插件
    
    从指定包路径自动发现并加载插件类
    
    Args:
        package_path: 插件包路径 (默认当前包)
        
    Returns:
        发现的插件类列表
    """
    discovered = []
    
    if package_path is None:
        package_path = str(Path(__file__).parent)
    
    # 遍历包内所有模块
    for importer, modname, ispkg in pkgutil.iter_modules([package_path]):
        if ispkg and not modname.startswith('_'):
            try:
                # 尝试导入插件模块
                full_name = f"{__package__}.{modname}"
                module = importlib.import_module(full_name)
                
                # 查找插件类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, Plugin) and 
                        attr is not Plugin and
                        not getattr(attr, '_abstract', False)):
                        discovered.append(attr)
                        
            except Exception as e:
                # 静默处理导入错误
                pass
    
    return discovered


def create_plugin_manager(
    plugin_configs: Dict[str, Dict[str, Any]] = None,
    auto_discover: bool = False
) -> PluginManager:
    """创建并配置插件管理器
    
    Args:
        plugin_configs: 插件配置字典 {plugin_name: config}
        auto_discover: 是否自动发现插件
        
    Returns:
        配置好的 PluginManager 实例
    """
    manager = PluginManager()
    plugin_configs = plugin_configs or {}
    
    # 注册所有内置插件
    for plugin_class in BUILTIN_PLUGINS:
        try:
            plugin = plugin_class()
            manager.register(plugin)
        except Exception as e:
            # 记录错误但不中断
            print(f"Failed to register plugin {plugin_class.__name__}: {e}")
    
    # 自动发现额外插件
    if auto_discover:
        for plugin_class in discover_plugins():
            if plugin_class not in BUILTIN_PLUGINS:
                try:
                    plugin = plugin_class()
                    manager.register(plugin)
                except Exception as e:
                    print(f"Failed to register discovered plugin {plugin_class.__name__}: {e}")
    
    return manager


async def initialize_plugins(
    manager: PluginManager,
    configs: Dict[str, Dict[str, Any]] = None
) -> Dict[str, Any]:
    """初始化所有插件
    
    Args:
        manager: 插件管理器
        configs: 插件配置
        
    Returns:
        初始化结果统计
    """
    configs = configs or {}
    results = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "errors": {}
    }
    
    for name in manager.list_plugins():
        results["total"] += 1
        plugin = manager.get(name)
        
        # 检查插件是否启用
        plugin_config = configs.get(name, {})
        if plugin_config.get("enabled", True) is False:
            continue
            
        try:
            await plugin.initialize(plugin_config)
            results["success"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"][name] = str(e)
    
    return results