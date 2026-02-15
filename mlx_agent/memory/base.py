"""
记忆系统抽象基类

提供统一的后端接口，支持多种存储实现 (ChromaDB, SQLite 等)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class MemoryLevel(str, Enum):
    """记忆优先级等级"""
    P0 = "P0"  # 永久记忆
    P1 = "P1"  # 长期记忆 (默认)
    P2 = "P2"  # 短期记忆


@dataclass
class MemoryEntry:
    """记忆条目数据类"""
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    level: MemoryLevel = MemoryLevel.P1
    embedding: Optional[List[float]] = None
    memory_id: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.memory_id is None:
            self.memory_id = self._generate_id()
        if self.created_at is None:
            self.created_at = datetime.now()
        # 确保 level 是 MemoryLevel 类型
        if isinstance(self.level, str):
            self.level = MemoryLevel(self.level)
    
    def _generate_id(self) -> str:
        """基于内容生成唯一 ID"""
        import hashlib
        content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{self.level.value}_{timestamp}_{content_hash}"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.memory_id,
            "content": self.content,
            "metadata": self.metadata,
            "level": self.level.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "embedding": self.embedding,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """从字典创建"""
        return cls(
            content=data["content"],
            metadata=data.get("metadata", {}),
            level=MemoryLevel(data.get("level", "P1")),
            embedding=data.get("embedding"),
            memory_id=data.get("id"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        )
    
    def is_expired(self, p1_max_days: int = 7, p2_max_days: int = 1) -> bool:
        """检查是否过期"""
        if self.level == MemoryLevel.P0:
            return False
        
        max_days = p1_max_days if self.level == MemoryLevel.P1 else p2_max_days
        if self.created_at is None:
            return False
        
        expiry_date = self.created_at + __import__('datetime').timedelta(days=max_days)
        return datetime.now() > expiry_date


class MemoryBackend(ABC):
    """记忆后端抽象基类"""
    
    @abstractmethod
    async def add(self, entry: MemoryEntry) -> str:
        """添加记忆条目
        
        Args:
            entry: 记忆条目
            
        Returns:
            记忆 ID
        """
        ...
    
    @abstractmethod
    async def search(
        self, 
        query: str, 
        limit: int = 5,
        level: Optional[MemoryLevel] = None,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """搜索记忆
        
        Args:
            query: 查询文本
            limit: 返回结果数量
            level: 筛选特定级别
            min_score: 最小相似度分数
            
        Returns:
            相关记忆列表
        """
        ...
    
    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """删除记忆
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否成功删除
        """
        ...
    
    @abstractmethod
    async def get_by_level(self, level: MemoryLevel) -> List[Dict[str, Any]]:
        """获取特定级别的所有记忆
        
        Args:
            level: 记忆级别
            
        Returns:
            记忆列表
        """
        ...
    
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息
        
        Returns:
            统计信息字典
        """
        ...
    
    @abstractmethod
    async def close(self):
        """关闭后端连接"""
        ...
    
    async def initialize(self):
        """初始化后端（可选）"""
        pass
