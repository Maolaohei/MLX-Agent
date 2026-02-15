"""
API Manager 加密存储模块

使用 Fernet 对称加密保护 API 密钥
"""

from .plugin import EncryptedStorage

__all__ = ["EncryptedStorage"]
