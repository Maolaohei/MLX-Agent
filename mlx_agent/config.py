"""
Configuration management

Type-safe configuration using Pydantic
"""

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class MemoryConfig(BaseModel):
    """Memory system configuration (index1-based)"""
    path: str = "./memory"
    index_path: str = "./memory/.index"
    embedding_model: str = "bge-m3"  # Default embedding model via Ollama
    ollama_url: str = "http://localhost:11434"
    force_reindex: bool = False
    index_on_startup: bool = True
    # Note: P0/P1/P2 levels are supported via directory structure


class PlatformConfig(BaseModel):
    """Platform adapter configuration"""
    enabled: bool = False
    bot_token: Optional[str] = None
    webhook_url: Optional[str] = None
    api_id: Optional[str] = None  # QQ Bot
    api_hash: Optional[str] = None  # QQ Bot


class PlatformsConfig(BaseModel):
    """Multi-platform configuration"""
    telegram: PlatformConfig = PlatformConfig()
    qqbot: PlatformConfig = PlatformConfig()
    discord: PlatformConfig = PlatformConfig()


class LLMConfig(BaseModel):
    """LLM provider configuration"""
    provider: str = "openai"  # openai, anthropic, deepseek, qwen
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2000
    
    def model_post_init(self, __context):
        """Expand environment variables in api_key and api_base"""
        import os
        if self.api_key and self.api_key.startswith('${') and self.api_key.endswith('}'):
            env_var = self.api_key[2:-1]
            self.api_key = os.environ.get(env_var)
        if self.api_base and self.api_base.startswith('${') and self.api_base.endswith('}'):
            env_var = self.api_base[2:-1]
            self.api_base = os.environ.get(env_var)


class PerformanceConfig(BaseModel):
    """Performance optimization configuration"""
    use_uvloop: bool = True
    json_library: str = "orjson"  # orjson, ujson, standard
    max_workers: int = 10
    connection_pool_size: int = 100


class Config(BaseSettings):
    """MLX-Agent main configuration"""
    
    # Basic info
    name: str = "MLX-Agent"
    version: str = "0.1.0"
    debug: bool = False
    
    # Sub-configs
    memory: MemoryConfig = MemoryConfig()
    platforms: PlatformsConfig = PlatformsConfig()
    llm: LLMConfig = LLMConfig()
    performance: PerformanceConfig = PerformanceConfig()
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """Load configuration from file
        
        Args:
            config_path: Path to config file, defaults to config/config.yaml
            
        Returns:
            Config instance
        """
        if config_path is None:
            # Default paths
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
        
        # Use default config
        return cls()
    
    def save(self, config_path: str = "config/config.yaml"):
        """Save configuration to file"""
        Path(config_path).parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(), f, allow_unicode=True, sort_keys=False)
