"""
配置管理

使用 Pydantic 进行类型安全的配置管理
"""

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class MemoryConfig(BaseModel):
    """记忆系统配置"""
    path: str = "./memory"
    vector_db: str = "milvus"  # 或 "zilliz"
    vector_db_host: str = "localhost"
    vector_db_port: int = 19530
    collection_name: str = "mlx_memories"
    index_on_startup: bool = True


class PlatformConfig(BaseModel):
    """平台适配器配置"""
    enabled: bool = False
    bot_token: Optional[str] = None
    webhook_url: Optional[str] = None
    api_id: Optional[str] = None  # QQ Bot
    api_hash: Optional[str] = None  # QQ Bot


class PlatformsConfig(BaseModel):
    """多平台配置"""
    telegram: PlatformConfig = PlatformConfig()
    qqbot: PlatformConfig = PlatformConfig()
    discord: PlatformConfig = PlatformConfig()


class LLMConfig(BaseModel):
    """LLM 提供商配置"""
    provider: str = "openai"  # openai, anthropic, deepseek, qwen
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2000


class PerformanceConfig(BaseModel):
    """性能优化配置"""
    use_uvloop: bool = True
    json_library: str = "orjson"  # orjson, ujson, standard
    max_workers: int = 10
    connection_pool_size: int = 100


class Config(BaseSettings):
    """MLX-Agent 主配置"""
    
    # 基本信息
    name: str = "MLX-Agent"
    version: str = "0.1.0"
    debug: bool = False
    
    # 子配置
    memory: MemoryConfig = MemoryConfig()
    platforms: PlatformsConfig = PlatformsConfig()
    llm: LLMConfig = LLMConfig()
    performance: PerformanceConfig = PerformanceConfig()
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """从文件加载配置
        
        Args:
            config_path: 配置文件路径，默认查找 config/config.yaml
            
        Returns:
            Config 实例
        """
        if config_path is None:
            # 默认路径
            paths = [
                Path("config/config.yaml"),
                Path("config.yaml"),
                Path.home() / ".mlx-agent/config.yaml",
            ]
            for path in paths:
                if path.exists():
                    config_path = str(path)
                    break
        
        if config_path and Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return cls(**data)
        
        # 使用默认配置
        return cls()
    
    def save(self, config_path: str = "config/config.yaml"):
        """保存配置到文件"""
        Path(config_path).parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(), f, allow_unicode=True, sort_keys=False)
