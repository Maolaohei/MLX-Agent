"""
记忆系统 - ChromaDB 版本

基于 ChromaDB 的向量存储架构：
- ChromaDB 向量语义搜索
- SQLite 元数据存储
- 支持本地嵌入 (sentence-transformers) 或 OpenAI/Ollama
- P0/P1/P2 分级记忆管理
- 自动归档和过期清理
"""

import hashlib
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict

from loguru import logger


@dataclass
class Memory:
    """单条记忆"""
    content: str
    metadata: Dict = None
    memory_id: Optional[str] = None
    created_at: Optional[datetime] = None
    level: str = "P1"  # P0, P1, P2
    embedding: Optional[List[float]] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.memory_id is None:
            self.memory_id = self._generate_id()
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def _generate_id(self) -> str:
        """基于内容生成唯一 ID"""
        content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{self.level}_{timestamp}_{content_hash}"
    
    def to_dict(self) -> dict:
        return {
            "id": self.memory_id,
            "content": self.content,
            "metadata": self.metadata,
            "level": self.level,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
    
    def is_expired(self, p1_max_days: int = 7, p2_max_days: int = 1) -> bool:
        """检查是否过期"""
        if self.level == "P0":
            return False  # P0 永不过期
        
        max_days = p1_max_days if self.level == "P1" else p2_max_days
        expiry_date = self.created_at + timedelta(days=max_days)
        return datetime.now() > expiry_date


class ChromaMemorySystem:
    """ChromaDB 记忆系统主类
    
    支持分级记忆 (P0/P1/P2) 和自动归档
    """
    
    # 嵌入模型配置
    EMBEDDING_MODELS = {
        "local": "BAAI/bge-m3",  # 本地 sentence-transformers
        "openai": "text-embedding-3-small",
        "ollama": "bge-m3"
    }
    
    def __init__(
        self,
        path: str = "./memory",
        embedding_provider: str = "local",
        embedding_model: Optional[str] = None,
        ollama_url: str = "http://localhost:11434",
        openai_api_key: Optional[str] = None,
        auto_archive: bool = True,
        p1_max_age_days: int = 7,
        p2_max_age_days: int = 1
    ):
        """初始化记忆系统
        
        Args:
            path: 记忆存储路径
            embedding_provider: 嵌入提供商 (local/openai/ollama)
            embedding_model: 自定义嵌入模型名称
            ollama_url: Ollama 服务地址
            openai_api_key: OpenAI API 密钥
            auto_archive: 是否启用自动归档
            p1_max_age_days: P1 记忆最大保留天数
            p2_max_age_days: P2 记忆最大保留天数
        """
        self.memory_path = Path(path).resolve()
        self.chroma_path = self.memory_path / "chroma"
        self.archive_path = self.memory_path / "archive"
        
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model or self.EMBEDDING_MODELS.get(embedding_provider)
        self.ollama_url = ollama_url
        self.openai_api_key = openai_api_key
        
        self.auto_archive = auto_archive
        self.p1_max_age_days = p1_max_age_days
        self.p2_max_age_days = p2_max_age_days
        
        self._initialized = False
        self._chroma_client = None
        self._collection = None
        self._embedding_func = None
        
        logger.info(f"ChromaMemorySystem configured:")
        logger.info(f"  Path: {self.memory_path}")
        logger.info(f"  Embedding: {embedding_provider} ({self.embedding_model})")
    
    async def initialize(self):
        """初始化记忆系统"""
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise RuntimeError("chromadb is required. Install: pip install chromadb")
        
        # 创建目录结构
        self.memory_path.mkdir(parents=True, exist_ok=True)
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self.archive_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化嵌入函数
        await self._init_embedding_function()
        
        # 初始化 ChromaDB
        try:
            self._chroma_client = chromadb.PersistentClient(
                path=str(self.chroma_path),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=False
                )
            )
            
            # 获取或创建集合
            self._collection = self._chroma_client.get_or_create_collection(
                name="memories",
                embedding_function=self._embedding_func,
                metadata={"hnsw:space": "cosine"}
            )
            
            logger.info(f"ChromaDB initialized with {self._collection.count()} memories")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            raise
        
        self._initialized = True
        
        # 启动自动归档任务
        if self.auto_archive:
            asyncio.create_task(self._auto_archive_loop())
        
        logger.info("ChromaMemorySystem initialized")
    
    async def _init_embedding_function(self):
        """初始化嵌入函数"""
        try:
            if self.embedding_provider == "local":
                from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
                self._embedding_func = SentenceTransformerEmbeddingFunction(
                    model_name=self.embedding_model
                )
                logger.info(f"Using local embedding: {self.embedding_model}")
                
            elif self.embedding_provider == "openai":
                from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
                if not self.openai_api_key:
                    raise ValueError("OpenAI API key required for OpenAI embeddings")
                self._embedding_func = OpenAIEmbeddingFunction(
                    api_key=self.openai_api_key,
                    model_name=self.embedding_model
                )
                logger.info(f"Using OpenAI embedding: {self.embedding_model}")
                
            elif self.embedding_provider == "ollama":
                # 自定义 Ollama 嵌入函数
                self._embedding_func = OllamaEmbeddingFunction(
                    model_name=self.embedding_model,
                    url=self.ollama_url
                )
                logger.info(f"Using Ollama embedding: {self.embedding_model}")
            else:
                raise ValueError(f"Unknown embedding provider: {self.embedding_provider}")
                
        except Exception as e:
            logger.warning(f"Failed to initialize embedding function: {e}")
            logger.warning("Falling back to default embedding")
            self._embedding_func = None
    
    async def add(
        self,
        content: str,
        metadata: Optional[Dict] = None,
        level: str = "P1",
        memory_id: Optional[str] = None
    ) -> Memory:
        """添加记忆
        
        Args:
            content: 记忆内容
            metadata: 元数据
            level: 记忆级别 (P0/P1/P2)
            memory_id: 可选的自定义 ID
            
        Returns:
            创建的记忆对象
        """
        if not self._initialized:
            raise RuntimeError("Memory system not initialized")
        
        memory = Memory(
            content=content,
            metadata=metadata or {},
            memory_id=memory_id,
            level=level
        )
        
        # 检查重复
        if await self._check_duplicate(content, level):
            logger.debug(f"Duplicate memory detected, skipping: {content[:50]}...")
            return memory
        
        try:
            # 准备元数据
            chroma_metadata = {
                "level": level,
                "created_at": memory.created_at.isoformat(),
                **{k: str(v) for k, v in (metadata or {}).items()}
            }
            
            # 添加到 ChromaDB
            self._collection.add(
                ids=[memory.memory_id],
                documents=[content],
                metadatas=[chroma_metadata]
            )
            
            logger.debug(f"Added memory: {memory.memory_id[:20]}... (level={level})")
            return memory
            
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            raise
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        level: Optional[str] = None,
        min_score: float = 0.0
    ) -> List[Dict]:
        """搜索记忆
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            level: 筛选特定级别 (P0/P1/P2)
            min_score: 最小相似度分数
            
        Returns:
            相关记忆列表
        """
        if not self._initialized:
            logger.warning("Memory system not initialized")
            return []
        
        try:
            # 构建过滤条件
            where_filter = None
            if level:
                where_filter = {"level": level}
            
            # 执行搜索
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k * 2,  # 多取一些用于过滤
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
            
            # 格式化结果
            memories = []
            if results['ids'] and results['ids'][0]:
                for i, memory_id in enumerate(results['ids'][0]):
                    distance = results['distances'][0][i] if results['distances'] else 1.0
                    # ChromaDB 返回的是距离 (0=相同, 2=完全不同)，转换为相似度
                    score = 1.0 - (distance / 2.0)
                    
                    if score < min_score:
                        continue
                    
                    memories.append({
                        "id": memory_id,
                        "content": results['documents'][0][i],
                        "score": score,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                        "level": results['metadatas'][0][i].get('level', 'unknown') if results['metadatas'] else 'unknown'
                    })
            
            # 按分数排序
            memories = sorted(memories, key=lambda x: x["score"], reverse=True)
            
            logger.debug(f"Found {len(memories)} memories for: {query[:50]}...")
            return memories[:top_k]
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    async def delete(self, memory_id: str) -> bool:
        """删除记忆
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否成功删除
        """
        if not self._initialized:
            return False
        
        try:
            self._collection.delete(ids=[memory_id])
            logger.debug(f"Deleted memory: {memory_id[:20]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False
    
    async def get_by_level(self, level: str) -> List[Dict]:
        """获取特定级别的所有记忆
        
        Args:
            level: 记忆级别 (P0/P1/P2)
            
        Returns:
            记忆列表
        """
        if not self._initialized:
            return []
        
        try:
            results = self._collection.get(
                where={"level": level},
                include=["documents", "metadatas"]
            )
            
            memories = []
            if results['ids']:
                for i, memory_id in enumerate(results['ids']):
                    memories.append({
                        "id": memory_id,
                        "content": results['documents'][i],
                        "metadata": results['metadatas'][i] if results['metadatas'] else {},
                        "level": level
                    })
            
            return memories
        except Exception as e:
            logger.error(f"Failed to get memories by level: {e}")
            return []
    
    async def _check_duplicate(self, content: str, level: str) -> bool:
        """检查是否已存在相似记忆"""
        try:
            # 搜索相似内容
            results = await self.search(content[:100], top_k=3, level=level, min_score=0.95)
            return len(results) > 0
        except Exception as e:
            logger.debug(f"Duplicate check failed: {e}")
            return False
    
    async def _auto_archive_loop(self):
        """自动归档循环"""
        while self._initialized:
            try:
                await asyncio.sleep(3600)  # 每小时检查一次
                await self._run_archive()
            except Exception as e:
                logger.error(f"Auto archive error: {e}")
    
    async def _run_archive(self):
        """执行归档"""
        logger.info("Running memory archive...")
        
        archived_count = 0
        deleted_count = 0
        
        # 获取所有 P1 和 P2 记忆
        for level, max_days in [("P1", self.p1_max_age_days), ("P2", self.p2_max_age_days)]:
            memories = await self.get_by_level(level)
            
            for mem in memories:
                try:
                    created_at = datetime.fromisoformat(mem['metadata'].get('created_at', datetime.now().isoformat()))
                    age_days = (datetime.now() - created_at).days
                    
                    if age_days > max_days:
                        if level == "P1":
                            # 归档 P1
                            await self._archive_memory(mem)
                            archived_count += 1
                        else:
                            # 删除 P2
                            await self.delete(mem['id'])
                            deleted_count += 1
                            
                except Exception as e:
                    logger.debug(f"Archive processing error: {e}")
        
        logger.info(f"Archive complete: {archived_count} archived, {deleted_count} deleted")
    
    async def _archive_memory(self, memory: Dict):
        """归档单条记忆"""
        try:
            # 保存到归档文件
            archive_file = self.archive_path / f"{datetime.now().strftime('%Y-%m')}.jsonl"
            with open(archive_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(memory, ensure_ascii=False) + "\n")
            
            # 从主存储删除
            await self.delete(memory['id'])
            
        except Exception as e:
            logger.error(f"Failed to archive memory: {e}")
    
    async def close(self):
        """关闭记忆系统"""
        if self._chroma_client:
            # ChromaDB 自动持久化，无需特别关闭
            pass
        
        self._initialized = False
        logger.info("ChromaMemorySystem closed")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self._initialized or not self._collection:
            return {"status": "not_initialized"}
        
        try:
            total = self._collection.count()
            
            # 按级别统计
            level_stats = {}
            for level in ["P0", "P1", "P2"]:
                try:
                    results = self._collection.get(where={"level": level})
                    level_stats[level] = len(results['ids']) if results['ids'] else 0
                except:
                    level_stats[level] = 0
            
            return {
                "status": "initialized",
                "total_memories": total,
                "by_level": level_stats,
                "embedding_provider": self.embedding_provider,
                "embedding_model": self.embedding_model
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    # 兼容性方法
    async def index_documents(self, documents: List[Dict[str, Any]], force: bool = False):
        """批量索引文档（兼容方法）"""
        for doc in documents:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            level = metadata.get("level", "P1")
            await self.add(content, metadata, level)


class OllamaEmbeddingFunction:
    """Ollama 嵌入函数适配器"""
    
    def __init__(self, model_name: str = "bge-m3", url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.url = url.rstrip('/')
    
    def __call__(self, input: Union[str, List[str]]) -> List[List[float]]:
        """生成嵌入向量"""
        import httpx
        
        texts = [input] if isinstance(input, str) else input
        embeddings = []
        
        for text in texts:
            try:
                response = httpx.post(
                    f"{self.url}/api/embeddings",
                    json={"model": self.model_name, "prompt": text},
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                embeddings.append(result.get("embedding", []))
            except Exception as e:
                logger.error(f"Ollama embedding failed: {e}")
                embeddings.append([])
        
        return embeddings


# 向后兼容：MemorySystem 别名
MemorySystem = ChromaMemorySystem
