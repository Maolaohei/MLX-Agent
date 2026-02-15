"""
Configuration management - v0.3.0

Type-safe configuration using Pydantic
"""

from pathlib import Path
from typing import List, Optional, Dict, Any, Union

import yaml
from pydantic import BaseModel, Field, validator, ValidationError
from pydantic_settings import BaseSettings
from loguru import logger


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


# ============ Plugin Configurations ============

class BackupWebDAVConfig(BaseModel):
    """Backup WebDAV configuration"""
    enabled: bool = False
    url: str = ""
    username: str = ""
    password: str = ""
    path: str = "/mlx-agent/backups"


class BackupAutoConfig(BaseModel):
    """Backup auto backup configuration"""
    enabled: bool = True
    time: str = "02:00"
    keep_count: int = 7


class BackupConfig(BaseModel):
    """Backup plugin configuration"""
    enabled: bool = True
    backup_dir: str = "./backups"
    auto_backup: BackupAutoConfig = BackupAutoConfig()
    webdav: BackupWebDAVConfig = BackupWebDAVConfig()
    sources: List[str] = ["./memory", "./config", "./skills"]


class APIManagerConfig(BaseModel):
    """API Manager plugin configuration"""
    enabled: bool = True
    storage_dir: str = "./data/api_keys"
    master_password: Optional[str] = None
    auto_rotation: bool = True
    rotation_check_hours: int = 24


class BriefingConfig(BaseModel):
    """Briefing plugin configuration"""
    enabled: bool = True
    data_dir: str = "./data/briefing"
    auto_enabled: bool = True
    default_time: str = "08:00"
    default_location: str = ""
    weather_provider: str = "openmeteo"
    weather_api_key: Optional[str] = None


class RemindmeConfig(BaseModel):
    """Remindme plugin configuration"""
    enabled: bool = True
    data_dir: str = "./data/reminders"
    timezone: str = "Asia/Shanghai"


class PluginsConfig(BaseModel):
    """All plugins configuration"""
    backup: BackupConfig = BackupConfig()
    api_manager: APIManagerConfig = APIManagerConfig()
    briefing: BriefingConfig = BriefingConfig()
    remindme: RemindmeConfig = RemindmeConfig()
    
    # 允许动态插件配置
    class Config:
        extra = "allow"


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
    plugins: PluginsConfig = PluginsConfig()
    
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


class ConfigValidator:
    """配置验证器 - 验证和修复配置问题"""
    
    @staticmethod
    def validate_memory_config(config: dict) -> tuple[bool, List[str]]:
        """验证记忆配置
        
        Args:
            config: 记忆配置字典
            
        Returns:
            (是否有效, 错误信息列表)
        """
        errors = []
        
        if not isinstance(config, dict):
            errors.append("Memory config must be a dictionary")
            return False, errors
        
        # 验证嵌入提供商
        provider = config.get("embedding_provider", "local")
        valid_providers = ["local", "openai", "ollama"]
        if provider not in valid_providers:
            errors.append(f"Invalid embedding_provider: {provider}. Must be one of {valid_providers}")
        
        # 验证路径
        path = config.get("path", "./memory")
        if not path or not isinstance(path, str):
            errors.append("Memory path must be a non-empty string")
        
        # 验证归档配置
        auto_archive = config.get("auto_archive", {})
        if isinstance(auto_archive, dict):
            p1_days = auto_archive.get("p1_max_age_days", 7)
            p2_days = auto_archive.get("p2_max_age_days", 1)
            
            if not isinstance(p1_days, int) or p1_days < 1:
                errors.append("p1_max_age_days must be a positive integer")
            if not isinstance(p2_days, int) or p2_days < 1:
                errors.append("p2_max_age_days must be a positive integer")
            if p1_days <= p2_days:
                errors.append("p1_max_age_days should be greater than p2_max_age_days")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_llm_config(config: dict) -> tuple[bool, List[str]]:
        """验证 LLM 配置
        
        Args:
            config: LLM 配置字典
            
        Returns:
            (是否有效, 错误信息列表)
        """
        errors = []
        
        if not isinstance(config, dict):
            errors.append("LLM config must be a dictionary")
            return False, errors
        
        # 检查主模型配置
        primary = config.get("primary")
        if primary and isinstance(primary, dict):
            # 验证必需字段
            if not primary.get("api_key") and not config.get("api_key"):
                errors.append("API key is required for LLM (either in primary or root)")
            
            # 验证温度
            temp = primary.get("temperature")
            if temp is not None:
                if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                    errors.append(f"temperature must be between 0 and 2, got {temp}")
            
            # 验证 max_tokens
            max_tokens = primary.get("max_tokens")
            if max_tokens is not None:
                if not isinstance(max_tokens, int) or max_tokens < 1:
                    errors.append(f"max_tokens must be a positive integer, got {max_tokens}")
        
        # 验证故障转移配置
        failover = config.get("failover", {})
        if isinstance(failover, dict):
            max_retries = failover.get("max_retries", 3)
            if not isinstance(max_retries, int) or max_retries < 0 or max_retries > 10:
                errors.append(f"max_retries must be between 0 and 10, got {max_retries}")
            
            timeout = failover.get("timeout", 30)
            if not isinstance(timeout, int) or timeout < 1:
                errors.append(f"timeout must be a positive integer, got {timeout}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_security_config(config: dict) -> tuple[bool, List[str]]:
        """验证安全配置
        
        Args:
            config: 安全配置字典
            
        Returns:
            (是否有效, 错误信息列表)
        """
        errors = []
        
        if not isinstance(config, dict):
            errors.append("Security config must be a dictionary")
            return False, errors
        
        # 验证绑定地址
        bind = config.get("default_bind", "127.0.0.1")
        if bind == "0.0.0.0":
            errors.append("Warning: binding to 0.0.0.0 may expose the service to external networks")
        
        # 验证路径列表
        forbidden_paths = config.get("forbidden_paths", [])
        if not isinstance(forbidden_paths, list):
            errors.append("forbidden_paths must be a list")
        
        allowed_paths = config.get("allowed_paths", [])
        if not isinstance(allowed_paths, list):
            errors.append("allowed_paths must be a list")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def auto_fix(config: dict) -> dict:
        """自动修复常见问题
        
        Args:
            config: 原始配置字典
            
        Returns:
            修复后的配置字典
        """
        if not isinstance(config, dict):
            logger.warning("Config is not a dictionary, returning empty dict")
            return {}
        
        fixed = config.copy()
        fixes_applied = []
        
        # 修复记忆配置
        if "memory" in fixed and isinstance(fixed["memory"], dict):
            memory = fixed["memory"]
            
            # 确保 auto_archive 是字典
            if "auto_archive" in memory and not isinstance(memory["auto_archive"], dict):
                memory["auto_archive"] = {"enabled": bool(memory["auto_archive"])}
                fixes_applied.append("Converted auto_archive to dictionary format")
            
            # 修复负数的 max_age_days
            auto_archive = memory.get("auto_archive", {})
            if isinstance(auto_archive, dict):
                for key in ["p1_max_age_days", "p2_max_age_days"]:
                    value = auto_archive.get(key, 7 if "p1" in key else 1)
                    if not isinstance(value, int) or value < 1:
                        auto_archive[key] = 7 if "p1" in key else 1
                        fixes_applied.append(f"Fixed invalid {key}: {value} -> {auto_archive[key]}")
                
                # 确保 p1 > p2
                p1 = auto_archive.get("p1_max_age_days", 7)
                p2 = auto_archive.get("p2_max_age_days", 1)
                if p1 <= p2:
                    auto_archive["p1_max_age_days"] = max(p1, p2 + 1)
                    fixes_applied.append(f"Fixed p1_max_age_days to be greater than p2_max_age_days")
        
        # 修复 LLM 配置
        if "llm" in fixed and isinstance(fixed["llm"], dict):
            llm = fixed["llm"]
            
            # 修复温度
            for key in ["temperature"]:
                value = llm.get(key)
                if value is not None:
                    try:
                        temp = float(value)
                        if temp < 0 or temp > 2:
                            llm[key] = max(0, min(2, temp))
                            fixes_applied.append(f"Clamped {key} to valid range: {llm[key]}")
                    except (ValueError, TypeError):
                        llm[key] = 0.7
                        fixes_applied.append(f"Fixed invalid {key}, set to default 0.7")
            
            # 修复 max_tokens
            max_tokens = llm.get("max_tokens")
            if max_tokens is not None:
                try:
                    tokens = int(max_tokens)
                    if tokens < 1:
                        llm["max_tokens"] = 2000
                        fixes_applied.append(f"Fixed invalid max_tokens, set to default 2000")
                except (ValueError, TypeError):
                    llm["max_tokens"] = 2000
                    fixes_applied.append(f"Fixed invalid max_tokens, set to default 2000")
            
            # 确保 failover 是字典
            if "failover" in llm and not isinstance(llm["failover"], dict):
                llm["failover"] = {"enabled": bool(llm["failover"])}
                fixes_applied.append("Converted failover to dictionary format")
        
        # 修复性能配置
        if "performance" in fixed and isinstance(fixed["performance"], dict):
            perf = fixed["performance"]
            
            # 修复 max_workers
            max_workers = perf.get("max_workers")
            if max_workers is not None:
                try:
                    workers = int(max_workers)
                    if workers < 1 or workers > 100:
                        perf["max_workers"] = max(1, min(100, workers))
                        fixes_applied.append(f"Clamped max_workers to valid range: {perf['max_workers']}")
                except (ValueError, TypeError):
                    perf["max_workers"] = 10
                    fixes_applied.append("Fixed invalid max_workers, set to default 10")
        
        if fixes_applied:
            logger.info(f"Config auto-fix applied {len(fixes_applied)} fixes:")
            for fix in fixes_applied:
                logger.info(f"  - {fix}")
        
        return fixed
    
    @staticmethod
    def validate_plugins_config(config: dict) -> tuple[bool, List[str]]:
        """验证插件配置
        
        Args:
            config: 插件配置字典
            
        Returns:
            (是否有效, 错误信息列表)
        """
        errors = []
        
        if not isinstance(config, dict):
            errors.append("Plugins config must be a dictionary")
            return False, errors
        
        # 验证已知插件配置
        known_plugins = ["backup", "api_manager", "briefing", "remindme"]
        
        for plugin_name in config.keys():
            if plugin_name not in known_plugins:
                # 未知插件，只是警告
                pass
            
            plugin_config = config.get(plugin_name, {})
            if not isinstance(plugin_config, dict):
                errors.append(f"Plugin '{plugin_name}' config must be a dictionary")
                continue
            
            # 验证 enabled 字段
            enabled = plugin_config.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                errors.append(f"Plugin '{plugin_name}' enabled must be a boolean")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_full_config(config: dict) -> Dict[str, Any]:
        """验证完整配置
        
        Args:
            config: 完整配置字典
            
        Returns:
            验证结果字典
        """
        results = {
            "valid": True,
            "sections": {},
            "warnings": [],
            "errors": []
        }
        
        if not isinstance(config, dict):
            results["valid"] = False
            results["errors"].append("Config must be a dictionary")
            return results
        
        # 验证各个部分
        sections = {
            "memory": ConfigValidator.validate_memory_config,
            "llm": ConfigValidator.validate_llm_config,
            "security": ConfigValidator.validate_security_config,
            "plugins": ConfigValidator.validate_plugins_config,
        }
        
        for section_name, validator_func in sections.items():
            section_config = config.get(section_name, {})
            is_valid, errors = validator_func(section_config)
            results["sections"][section_name] = {
                "valid": is_valid,
                "errors": errors
            }
            if not is_valid:
                results["valid"] = False
                results["errors"].extend([f"[{section_name}] {e}" for e in errors])
        
        # 检查未知部分
        known_sections = set(sections.keys()) | {"name", "version", "debug", "platforms", "performance", "health_check", "shutdown"}
        unknown = set(config.keys()) - known_sections
        if unknown:
            results["warnings"].append(f"Unknown config sections: {unknown}")
        
        return results
