"""
记忆系统

基于 memsearch 的 Markdown 优先记忆架构：
- SHA-256 内容去重
- 文件监听自动索引
- 语义搜索
"""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import orjson
from loguru import logger

from mlx_agent.config import MemoryConfig
from mlx_agent.memory.embedding import EmbeddingProvider, EmbeddingFactory
from mlx_agent.memory.vector_db import VectorDB, MilvusDB, ZillizDB


class Memory:
    """单条记忆"""
    def __init__(
        self,
        content: str,
        metadata: Optional[Dict] = None,
        memory_id: Optional[str] = None,
        created_at: Optional[datetime] = None
    ):
        self.content = content
        self.metadata = metadata or {}
        self.id = memory_id or self._generate_id()
        self.created_at = created_at or datetime.now()
        self.embedding: Optional[List[float]] = None
    
    def _generate_id(self) -> str:
        """基于内容生成唯一 ID"""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


class MemorySystem:
    """记忆系统主类"""
    
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.memory_path = Path(config.path)
        self._initialized = False
        
        # 初始化组件
        self.vector_db: Optional[VectorDB] = None
        self.embedding: Optional[EmbeddingProvider] = None
        
        logger.info(f"Memory system configured with path: {self.memory_path}")
    
    async def initialize(self):
        """初始化记忆系统"""
        # 创建记忆目录
        self.memory_path.mkdir(parents=True, exist_ok=True)
        (self.memory_path / "core").mkdir(exist_ok=True)
        (self.memory_path / "session").mkdir(exist_ok=True)
        (self.memory_path / "archive").mkdir(exist_ok=True)
        
        # 初始化向量数据库
        if self.config.vector_db == "zilliz":
            # Zilliz Cloud
            self.vector_db = ZillizDB(
                uri=self.config.vector_db_host,
                token=self.config.get("vector_db_token", "")
            )
        else:
            # 本地 Milvus
            self.vector_db = MilvusDB(
                host=self.config.vector_db_host,
                port=self.config.vector_db_port
            )
        
        await self.vector_db.connect()
        
        # 创建集合
        await self.vector_db.create_collection(
            self.config.collection_name,
            dimension=1536  # 默认 OpenAI embedding 维度
        )
        
        # 初始化 embedding 提供商（默认使用 OpenAI）
        # 实际项目中从配置读取
        try:
            self.embedding = EmbeddingFactory.create(
                "openai",
                api_key="${OPENAI_API_KEY}",
                model="text-embedding-3-small"
            )
            logger.info(f"Using embedding provider: OpenAI (dim={self.embedding.dimension})")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI embedding: {e}")
            logger.warning("Falling back to local embedding...")
            self.embedding = EmbeddingFactory.create("local")
        
        self._initialized = True
        logger.info("Memory system initialized")
    
    async def add(
        self,
        content: str,
        metadata: Optional[Dict] = None,
        level: str = "P1"  # P0: 核心, P1: 会话, P2: 临时
    ) -> Memory:
        """添加记忆
        
        Args:
            content: 记忆内容
            metadata: 元数据
            level: 记忆级别 (P0/P1/P2)
            
        Returns:
            创建的记忆对象
        """
        memory = Memory(content, metadata)
        
        # 生成 embedding
        if self.embedding:
            embeddings = await self.embedding.embed([content])
            memory.embedding = embeddings[0]
            
            # 检查重复（基于向量相似度）
            similar = await self._check_duplicate(memory.embedding)
            if similar:
                logger.debug(f"Duplicate memory detected: {memory.id[:8]}")
                return memory
            
            # 插入向量数据库
            await self.vector_db.insert(
                collection=self.config.collection_name,
                ids=[memory.id],
                vectors=[memory.embedding],
                metadata=[{
                    "content": content,
                    "level": level,
                    **(metadata or {})
                }]
            )
        
        # 保存到文件
        await self._save_to_file(memory, level)
        
        logger.debug(f"Added memory: {memory.id[:8]}...")
        return memory
    
    async def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """搜索记忆
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            相关记忆列表
        """
        if not self.embedding or not self.vector_db:
            logger.warning("Memory system not fully initialized")
            return []
        
        # 生成 query embedding
        query_embedding = await self.embedding.embed([query])
        
        # 向量搜索
        results = await self.vector_db.search(
            collection=self.config.collection_name,
            vector=query_embedding[0],
            top_k=top_k
        )
        
        logger.debug(f"Found {len(results)} memories for: {query[:50]}...")
        return results
    
    async def delete(self, memory_id: str) -> bool:
        """删除记忆
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否成功删除
        """
        if self.vector_db:
            await self.vector_db.delete(
                collection=self.config.collection_name,
                ids=[memory_id]
            )
        
        logger.debug(f"Deleted memory: {memory_id[:8]}...")
        return True
    
    async def _check_duplicate(self, embedding: List[float], threshold: float = 0.95) -> bool:
        """检查是否已存在相似记忆"""
        results = await self.vector_db.search(
            collection=self.config.collection_name,
            vector=embedding,
            top_k=1
        )
        
        if results and results[0]["score"] > threshold:
            return True
        return False
    
    async def _save_to_file(self, memory: Memory, level: str):
        """保存记忆到 Markdown 文件"""
        # 根据级别选择目录
        if level == "P0":
            dir_path = self.memory_path / "core"
        elif level == "P1":
            dir_path = self.memory_path / "session"
        else:
            dir_path = self.memory_path / "archive"
        
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # 按日期组织文件
        today = datetime.now().strftime("%Y-%m-%d")
        file_path = dir_path / f"{today}.md"
        
        # 追加到文件
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"\n## [{memory.id[:8]}] {memory.created_at.strftime('%H:%M')}\n")
            f.write(f"{memory.content}\n")
            if memory.metadata:
                f.write(f"<!-- metadata: {orjson.dumps(memory.metadata).decode()} -->\n")
    
    async def close(self):
        """关闭记忆系统"""
        if self.vector_db:
            await self.vector_db.disconnect()
        logger.info("Memory system closed")
