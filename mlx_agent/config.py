"""
Configuration management - v0.3.0

Type-safe configuration using Pydantic
"""

from pathlib import Path
from typing import List, Optional, Dict, Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class MemoryArchiveConfig(BaseModel):
    """自动归档配置"""
    enabled: bool = True
    interval_hours: int = 24
    p1_max_age_days: int = 7
    p2_max_age_days: int = 1


class MemoryConfig(BaseModel):
    """Memory system configuration (ChromaDB-based)"""
    path: str = "./memory"
    index_path: str = "./memory/.index"  # 向后兼容
    
    # ChromaDB 配置
    embedding_provider: str = "local"  # local, openai, ollama
    embedding_model: str = "BAAI/bge-m3"
    chroma_path: str = "./memory/chroma"
    ollama_url: str = "http://localhost:11434"
    openai_api_key: Optional[str] = None
    
    # 自动归档
    auto_archive: MemoryArchiveConfig = MemoryArchiveConfig()
    
    # 向后兼容
    force_reindex: bool = False
    index_on_startup: bool = True


class PlatformConfig(BaseModel):
    """Platform adapter configuration"""
    enabled: bool = False
    bot_token: Optional[str] = None
    admin_user_id: Optional[str] = None
    webhook_url: Optional[str] = None
    api_id: Optional[str] = None  # QQ Bot
    api_hash: Optional[str] = None  # QQ Bot
    
    def model_post_init(self, __context):
        """Expand environment variables"""
        import os
        if self.bot_token and self.bot_token.startswith('${') and self.bot_token.endswith('}'):
            env_var = self.bot_token[2:-1]
            self.bot_token = os.environ.get(env_var)
        if self.admin_user_id and self.admin_user_id.startswith('${') and self.admin_user_id.endswith('}'):
            env_var = self.admin_user_id[2:-1]
            self.admin_user_id = os.environ.get(env_var)


class PlatformsConfig(BaseModel):
    """Multi-platform configuration"""
    telegram: PlatformConfig = PlatformConfig()
    qqbot: PlatformConfig = PlatformConfig()
    discord: PlatformConfig = PlatformConfig()


class LLMModelConfig(BaseModel):
    """Single LLM model configuration"""
    provider: str = "openai"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    auth_token: Optional[str] = None
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2000
    
    def model_post_init(self, __context):
        """Expand environment variables"""
        import os
        if self.api_key and self.api_key.startswith('${') and self.api_key.endswith('}'):
            env_var = self.api_key[2:-1]
            self.api_key = os.environ.get(env_var)
        if self.auth_token and self.auth_token.startswith('${') and self.auth_token.endswith('}'):
            env_var = self.auth_token[2:-1]
            self.auth_token = os.environ.get(env_var)


class FailoverConfig(BaseModel):
    """Failover configuration"""
    enabled: bool = True
    max_retries: int = 3
    timeout: int = 30


class LLMConfig(BaseModel):
    """LLM provider configuration (supporting multi-model)"""
    # 兼容旧配置：直接作为字段
    provider: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    auth_token: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    
    # 新配置：主备模型
    primary: Optional[LLMModelConfig] = None
    fallback: Optional[LLMModelConfig] = None
    failover: FailoverConfig = FailoverConfig()
    
    def model_post_init(self, __context):
        """Expand environment variables and handle compatibility"""
        import os
        
        # 处理旧配置的变量替换
        if self.api_key and self.api_key.startswith('${') and self.api_key.endswith('}'):
            env_var = self.api_key[2:-1]
            self.api_key = os.environ.get(env_var)
        if self.auth_token and self.auth_token.startswith('${') and self.auth_token.endswith('}'):
            env_var = self.auth_token[2:-1]
            self.auth_token = os.environ.get(env_var)
            
        # 如果 primary 为空但旧字段有值，尝试构建 primary
        if not self.primary and self.api_key:
            self.primary = LLMModelConfig(
                provider=self.provider or "openai",
                api_key=self.api_key,
                api_base=self.api_base,
                auth_token=self.auth_token,
                model=self.model or "gpt-4o-mini",
                temperature=self.temperature or 0.7,
                max_tokens=self.max_tokens or 2000
            )


class PerformanceConfig(BaseModel):
    """Performance optimization configuration"""
    use_uvloop: bool = True
    json_library: str = "orjson"  # orjson, ujson, standard
    max_workers: int = 10
    connection_pool_size: int = 100


class SecurityConfig(BaseModel):
    """Security configuration"""
    default_bind: str = "127.0.0.1"  # 不是 0.0.0.0，更安全
    workspace_only: bool = True  # 文件操作限制在工作区
    forbidden_paths: List[str] = [
        "/etc", "/root", "/proc", "/sys",
        "~/.ssh", "~/.gnupg", "~/.aws",
        "/var/log", "/var/mail"
    ]
    allowed_paths: List[str] = []  # 额外的白名单路径


class HealthCheckConfig(BaseModel):
    """Health check server configuration"""
    enabled: bool = True
    host: str = "127.0.0.1"  # 默认改为 127.0.0.1 更安全
    port: int = 8080


class ShutdownConfig(BaseModel):
    """Graceful shutdown configuration"""
    timeout_seconds: int = 30


class Config(BaseSettings):
    """MLX-Agent main configuration"""

    # Basic info
    name: str = "MLX-Agent"
    version: str = "0.3.0"
    debug: bool = False

    # Sub-configs
    memory: MemoryConfig = MemoryConfig()
    platforms: PlatformsConfig = PlatformsConfig()
    llm: LLMConfig = LLMConfig()
    performance: PerformanceConfig = PerformanceConfig()
    security: SecurityConfig = SecurityConfig()
    health_check: HealthCheckConfig = HealthCheckConfig()
    shutdown: ShutdownConfig = ShutdownConfig()
    
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
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                return cls(**data)
            except Exception as e:
                logger.error(f"Failed to load config from {config_path}: {e}")
                logger.info("Using default configuration")
                return cls()
        
        # Use default config
        logger.info("No config file found, using default configuration")
        return cls()
    
    def save(self, config_path: str = "config/config.yaml"):
        """Save configuration to file"""
        Path(config_path).parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(), f, allow_unicode=True, sort_keys=False)
