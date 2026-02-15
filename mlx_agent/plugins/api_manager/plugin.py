"""
API 密钥管理插件

功能:
- 集中管理 API 密钥
- 加密存储 (Fernet 对称加密)
- 密钥自动轮换
- 使用统计
"""

import os
import json
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from loguru import logger

from ..base import Plugin


@dataclass
class APIKeyInfo:
    """API 密钥信息"""
    name: str
    key_encrypted: str
    created_at: str
    updated_at: str
    last_used: Optional[str] = None
    use_count: int = 0
    rotation_enabled: bool = False
    rotation_days: int = 90
    expires_at: Optional[str] = None
    tags: List[str] = None
    notes: str = ""
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> "APIKeyInfo":
        return cls(**data)


class EncryptedStorage:
    """加密存储"""
    
    def __init__(self, storage_path: Path, password: str = None):
        self.storage_path = storage_path
        self.password = password or self._get_or_create_password()
        self._key = self._derive_key(self.password)
        self._fernet = Fernet(self._key)
    
    def _get_or_create_password(self) -> str:
        """获取或创建主密码"""
        env_key = "MLX_AGENT_API_PASSWORD"
        password = os.environ.get(env_key)
        
        if not password:
            # 生成随机密码并存储到文件
            password_file = self.storage_path.parent / ".api_master_key"
            if password_file.exists():
                with open(password_file, 'r') as f:
                    password = f.read().strip()
            else:
                password = base64.urlsafe_b64encode(os.urandom(32)).decode()
                with open(password_file, 'w') as f:
                    f.write(password)
                os.chmod(password_file, 0o600)
                logger.warning(f"Generated new API master key. Store {password_file} securely!")
        
        return password
    
    def _derive_key(self, password: str) -> bytes:
        """从密码派生加密密钥"""
        # 使用固定 salt (实际生产环境应该使用随机 salt 并存储)
        salt = b'mlx_agent_fixed_salt_v1'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def encrypt(self, plaintext: str) -> str:
        """加密字符串"""
        return self._fernet.encrypt(plaintext.encode()).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """解密字符串"""
        return self._fernet.decrypt(ciphertext.encode()).decode()


class APIManagerPlugin(Plugin):
    """API 密钥管理插件"""
    
    @property
    def name(self) -> str:
        return "api_manager"
    
    @property
    def description(self) -> str:
        return "API 密钥管理: 集中管理、加密存储、自动轮换"
    
    async def _setup(self):
        """初始化插件"""
        # 配置
        self.storage_dir = Path(self.get_config("storage_dir", "./data/api_keys"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 加密存储
        password = self.get_config("master_password")
        self.storage = EncryptedStorage(self.storage_dir / "keys.json", password)
        
        # 数据文件
        self.keys_file = self.storage_dir / "keys.json"
        self._keys: Dict[str, APIKeyInfo] = {}
        self._load_keys()
        
        # 自动轮换配置
        self.auto_rotation = self.get_config("auto_rotation", True)
        self.rotation_check_interval = self.get_config("rotation_check_hours", 24)
        
        if self.auto_rotation:
            import asyncio
            asyncio.create_task(self._rotation_scheduler())
        
        logger.info(f"API Manager plugin initialized: {len(self._keys)} keys")
    
    async def _cleanup(self):
        """清理资源"""
        logger.info("API Manager plugin shutdown")
    
    def _load_keys(self):
        """加载密钥数据"""
        if self.keys_file.exists():
            try:
                with open(self.keys_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for name, info_data in data.items():
                    self._keys[name] = APIKeyInfo.from_dict(info_data)
            except Exception as e:
                logger.error(f"Failed to load API keys: {e}")
    
    def _save_keys(self):
        """保存密钥数据"""
        try:
            data = {k: v.to_dict() for k, v in self._keys.items()}
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save API keys: {e}")
    
    async def add_key(self, name: str, key: str, rotation_days: int = 90, 
                      tags: List[str] = None, notes: str = "") -> Dict[str, Any]:
        """添加 API 密钥
        
        Args:
            name: 密钥名称 (唯一标识)
            key: API 密钥值
            rotation_days: 轮换周期 (天)
            tags: 标签列表
            notes: 备注
            
        Returns:
            操作结果
        """
        if name in self._keys:
            return {
                "success": False,
                "error": f"API key '{name}' already exists. Use update to modify."
            }
        
        now = datetime.now()
        expires = now + timedelta(days=rotation_days) if rotation_days > 0 else None
        
        key_info = APIKeyInfo(
            name=name,
            key_encrypted=self.storage.encrypt(key),
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            last_used=None,
            use_count=0,
            rotation_enabled=rotation_days > 0,
            rotation_days=rotation_days,
            expires_at=expires.isoformat() if expires else None,
            tags=tags or [],
            notes=notes
        )
        
        self._keys[name] = key_info
        self._save_keys()
        
        logger.info(f"API key added: {name}")
        
        return {
            "success": True,
            "name": name,
            "created_at": key_info.created_at,
            "expires_at": key_info.expires_at,
            "message": "API key stored securely"
        }
    
    async def get_key(self, name: str, increment_usage: bool = True) -> Dict[str, Any]:
        """获取 API 密钥
        
        Args:
            name: 密钥名称
            increment_usage: 是否增加使用计数
            
        Returns:
            包含密钥的结果 (仅在成功时返回密钥值)
        """
        key_info = self._keys.get(name)
        if not key_info:
            return {
                "success": False,
                "error": f"API key '{name}' not found"
            }
        
        # 检查是否过期
        if key_info.expires_at:
            expires = datetime.fromisoformat(key_info.expires_at)
            if datetime.now() > expires:
                return {
                    "success": False,
                    "error": f"API key '{name}' has expired"
                }
        
        # 解密密钥
        try:
            decrypted_key = self.storage.decrypt(key_info.key_encrypted)
        except Exception as e:
            logger.error(f"Failed to decrypt key '{name}': {e}")
            return {
                "success": False,
                "error": "Failed to decrypt API key"
            }
        
        # 更新使用统计
        if increment_usage:
            key_info.use_count += 1
            key_info.last_used = datetime.now().isoformat()
            self._save_keys()
        
        return {
            "success": True,
            "name": name,
            "key": decrypted_key,
            "created_at": key_info.created_at,
            "expires_at": key_info.expires_at,
            "use_count": key_info.use_count,
            "tags": key_info.tags,
            "notes": key_info.notes
        }
    
    async def list_keys(self, include_stats: bool = True) -> Dict[str, Any]:
        """列出所有 API 密钥
        
        Args:
            include_stats: 是否包含使用统计
            
        Returns:
            密钥列表
        """
        keys = []
        for name, info in self._keys.items():
            key_data = {
                "name": name,
                "created_at": info.created_at,
                "rotation_enabled": info.rotation_enabled,
                "rotation_days": info.rotation_days,
                "expires_at": info.expires_at,
                "tags": info.tags,
                "notes": info.notes
            }
            
            if include_stats:
                key_data.update({
                    "use_count": info.use_count,
                    "last_used": info.last_used
                })
            
            # 检查过期状态
            if info.expires_at:
                expires = datetime.fromisoformat(info.expires_at)
                key_data["is_expired"] = datetime.now() > expires
            else:
                key_data["is_expired"] = False
            
            keys.append(key_data)
        
        # 按创建时间排序
        keys.sort(key=lambda x: x["created_at"], reverse=True)
        
        return {
            "success": True,
            "keys": keys,
            "count": len(keys)
        }
    
    async def delete_key(self, name: str) -> Dict[str, Any]:
        """删除 API 密钥
        
        Args:
            name: 密钥名称
            
        Returns:
            操作结果
        """
        if name not in self._keys:
            return {
                "success": False,
                "error": f"API key '{name}' not found"
            }
        
        del self._keys[name]
        self._save_keys()
        
        logger.info(f"API key deleted: {name}")
        
        return {
            "success": True,
            "deleted": name
        }
    
    async def rotate_key(self, name: str, new_key: str = None) -> Dict[str, Any]:
        """轮换 API 密钥
        
        Args:
            name: 密钥名称
            new_key: 新的密钥值 (None=仅更新过期时间)
            
        Returns:
            操作结果
        """
        key_info = self._keys.get(name)
        if not key_info:
            return {
                "success": False,
                "error": f"API key '{name}' not found"
            }
        
        now = datetime.now()
        
        if new_key:
            key_info.key_encrypted = self.storage.encrypt(new_key)
            logger.info(f"API key rotated with new value: {name}")
        else:
            logger.info(f"API key expiration extended: {name}")
        
        # 更新过期时间
        if key_info.rotation_days > 0:
            expires = now + timedelta(days=key_info.rotation_days)
            key_info.expires_at = expires.isoformat()
        
        key_info.updated_at = now.isoformat()
        self._save_keys()
        
        return {
            "success": True,
            "name": name,
            "rotated_at": now.isoformat(),
            "expires_at": key_info.expires_at
        }
    
    async def get_stats(self, name: str = None) -> Dict[str, Any]:
        """获取使用统计
        
        Args:
            name: 密钥名称 (None=返回所有统计)
            
        Returns:
            统计数据
        """
        if name:
            key_info = self._keys.get(name)
            if not key_info:
                return {
                    "success": False,
                    "error": f"API key '{name}' not found"
                }
            
            return {
                "success": True,
                "stats": {
                    "name": name,
                    "use_count": key_info.use_count,
                    "last_used": key_info.last_used,
                    "created_at": key_info.created_at,
                    "updated_at": key_info.updated_at
                }
            }
        else:
            # 全局统计
            total = len(self._keys)
            total_uses = sum(k.use_count for k in self._keys.values())
            expired = sum(
                1 for k in self._keys.values()
                if k.expires_at and datetime.now() > datetime.fromisoformat(k.expires_at)
            )
            
            return {
                "success": True,
                "stats": {
                    "total_keys": total,
                    "total_uses": total_uses,
                    "expired_keys": expired,
                    "active_keys": total - expired
                }
            }
    
    async def _rotation_scheduler(self):
        """轮换调度器"""
        import asyncio
        
        logger.info("API key rotation scheduler started")
        
        while self._initialized:
            try:
                await asyncio.sleep(self.rotation_check_interval * 3600)
                
                if not self._initialized:
                    break
                
                await self._check_expired_keys()
                
            except Exception as e:
                logger.error(f"Rotation scheduler error: {e}")
    
    async def _check_expired_keys(self):
        """检查并通知过期密钥"""
        now = datetime.now()
        expired_soon = []
        
        for name, info in self._keys.items():
            if info.expires_at and info.rotation_enabled:
                expires = datetime.fromisoformat(info.expires_at)
                days_until = (expires - now).days
                
                if days_until <= 7 and days_until > 0:
                    expired_soon.append({
                        "name": name,
                        "expires_in_days": days_until
                    })
        
        if expired_soon:
            logger.warning(f"API keys expiring soon: {expired_soon}")
    
    def get_tools(self) -> List[Dict]:
        """返回工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "api_key_add",
                    "description": "添加新的 API 密钥，支持加密存储和自动轮换",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "密钥名称 (唯一标识，如 'openai', 'github')"
                            },
                            "key": {
                                "type": "string",
                                "description": "API 密钥值"
                            },
                            "rotation_days": {
                                "type": "integer",
                                "description": "自动轮换周期 (天)，0 表示不轮换",
                                "default": 90
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "标签列表 (如 ['production', 'openai'])"
                            },
                            "notes": {
                                "type": "string",
                                "description": "备注信息"
                            }
                        },
                        "required": ["name", "key"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "api_key_get",
                    "description": "获取指定名称的 API 密钥值",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "密钥名称"
                            }
                        },
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "api_key_list",
                    "description": "列出所有存储的 API 密钥 (不包含密钥值)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "include_stats": {
                                "type": "boolean",
                                "description": "是否包含使用统计",
                                "default": True
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "api_key_delete",
                    "description": "删除指定的 API 密钥",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "密钥名称"
                            }
                        },
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "api_key_rotate",
                    "description": "轮换 API 密钥 (更新密钥值或延长过期时间)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "密钥名称"
                            },
                            "new_key": {
                                "type": "string",
                                "description": "新的密钥值 (可选，不提供则仅延长过期时间)"
                            }
                        },
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "api_key_stats",
                    "description": "获取 API 密钥使用统计",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "密钥名称 (不提供则返回全局统计)"
                            }
                        }
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        if tool_name == "api_key_add":
            return await self.add_key(
                params.get("name"),
                params.get("key"),
                params.get("rotation_days", 90),
                params.get("tags"),
                params.get("notes", "")
            )
        
        elif tool_name == "api_key_get":
            return await self.get_key(params.get("name"))
        
        elif tool_name == "api_key_list":
            return await self.list_keys(params.get("include_stats", True))
        
        elif tool_name == "api_key_delete":
            return await self.delete_key(params.get("name"))
        
        elif tool_name == "api_key_rotate":
            return await self.rotate_key(
                params.get("name"),
                params.get("new_key")
            )
        
        elif tool_name == "api_key_stats":
            return await self.get_stats(params.get("name"))
        
        return await super().handle_tool(tool_name, params)
