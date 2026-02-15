"""
API 密钥管理中心

统一管理所有外部服务的 API 密钥：
- 集中配置 (config/apis.yaml)
- 统一读取
- 启用/禁用状态管理
- 安全验证
"""

import os
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
import yaml
from loguru import logger


@dataclass
class APIConfig:
    """单个 API 的配置"""
    name: str
    key: str = ""
    enabled: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_available(self) -> bool:
        """检查 API 是否可用（已启用且有密钥）"""
        return self.enabled and bool(self.key)


class APIManager:
    """
    API 密钥管理中心
    
    用法：
        api_manager = APIManager()
        await api_manager.initialize()
        
        # 获取 API Key
        brave_key = api_manager.get_key("brave")
        
        # 检查是否可用
        if api_manager.is_available("tavily"):
            result = await tavily_search(...)
    """
    
    def __init__(self, config_path: str = "config/apis.yaml"):
        self.config_path = Path(config_path)
        self.apis: Dict[str, APIConfig] = {}
        self._initialized = False
    
    async def initialize(self):
        """初始化 API 管理器"""
        logger.info(f"Initializing API Manager from {self.config_path}")
        
        if not self.config_path.exists():
            logger.warning(f"API config not found: {self.config_path}")
            logger.info("Creating default API config...")
            self._create_default_config()
        
        self._load_config()
        self._initialized = True
        
        # 日志输出加载状态
        available = [name for name, api in self.apis.items() if api.is_available]
        disabled = [name for name, api in self.apis.items() if not api.enabled]
        no_key = [name for name, api in self.apis.items() if api.enabled and not api.key]
        
        logger.info(f"API Manager initialized: {len(available)} available, "
                   f"{len(disabled)} disabled, {len(no_key)} missing keys")
        
        if available:
            logger.debug(f"Available APIs: {', '.join(available)}")
    
    def _create_default_config(self):
        """创建默认配置文件"""
        default_config = {
            "brave": {"key": "", "enabled": False},
            "tavily": {"key": "", "enabled": False},
            "browser_cash": {"key": "", "enabled": False},
            "saucenao": {"key": "", "enabled": False},
        }
        
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
        
        logger.info(f"Created default API config at {self.config_path}")
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            for name, settings in config.items():
                if isinstance(settings, dict):
                    self.apis[name] = APIConfig(
                        name=name,
                        key=settings.get("key", ""),
                        enabled=settings.get("enabled", False),
                        extra={k: v for k, v in settings.items() 
                               if k not in ["key", "enabled"]}
                    )
                else:
                    # 简单的字符串格式（仅 key）
                    self.apis[name] = APIConfig(
                        name=name,
                        key=str(settings) if settings else "",
                        enabled=bool(settings)
                    )
            
            # 从环境变量补充（优先级更高）
            self._load_from_env()
            
        except Exception as e:
            logger.error(f"Failed to load API config: {e}")
            raise
    
    def _load_from_env(self):
        """从环境变量加载（覆盖配置文件）"""
        env_mappings = {
            "brave": ["BRAVE_API_KEY"],
            "tavily": ["TAVILY_API_KEY"],
            "browser_cash": ["BROWSER_CASH_KEY", "BROWSER_CASH_API_KEY"],
            "saucenao": ["SAUCENAO_API_KEY"],
        }
        
        for api_name, env_vars in env_mappings.items():
            for env_var in env_vars:
                value = os.environ.get(env_var)
                if value:
                    if api_name not in self.apis:
                        self.apis[api_name] = APIConfig(name=api_name)
                    
                    # 环境变量优先级更高
                    if not self.apis[api_name].key:
                        self.apis[api_name].key = value
                        logger.debug(f"Loaded {api_name} key from env var {env_var}")
                    break
    
    def get(self, name: str) -> Optional[APIConfig]:
        """获取 API 配置"""
        return self.apis.get(name)
    
    def get_key(self, name: str) -> str:
        """获取 API Key（如果不存在返回空字符串）"""
        api = self.apis.get(name)
        return api.key if api else ""
    
    def is_available(self, name: str) -> bool:
        """检查 API 是否可用"""
        api = self.apis.get(name)
        return api.is_available if api else False
    
    def is_enabled(self, name: str) -> bool:
        """检查 API 是否已启用"""
        api = self.apis.get(name)
        return api.enabled if api else False
    
    def list_available(self) -> list:
        """列出所有可用的 API"""
        return [name for name, api in self.apis.items() if api.is_available]
    
    def list_all(self) -> Dict[str, bool]:
        """列出所有 API 及其状态"""
        return {
            name: api.is_available 
            for name, api in self.apis.items()
        }
    
    async def reload(self):
        """重新加载配置"""
        logger.info("Reloading API config...")
        self.apis.clear()
        self._load_config()
    
    async def close(self):
        """关闭 API 管理器"""
        self._initialized = False
        logger.info("API Manager closed")
    
    def require(self, name: str) -> str:
        """
        要求必须使用某个 API，如果不可用则抛出异常
        
        用法：
            brave_key = api_manager.require("brave")
        """
        api = self.apis.get(name)
        if not api:
            raise ValueError(f"API '{name}' not configured")
        if not api.enabled:
            raise ValueError(f"API '{name}' is disabled")
        if not api.key:
            raise ValueError(f"API '{name}' key is missing")
        return api.key


# 全局实例（单例模式）
_api_manager: Optional[APIManager] = None


def get_api_manager() -> APIManager:
    """获取全局 API 管理器实例"""
    global _api_manager
    if _api_manager is None:
        _api_manager = APIManager()
    return _api_manager
