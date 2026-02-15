"""
ChromaDB 记忆后端实现

基于 ChromaDB 的向量存储，支持语义搜索
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

from loguru import logger

from .base import MemoryBackend, MemoryEntry, MemoryLevel


class OllamaEmbeddingFunction:
    """Ollama 嵌入函数适配器 - 延迟导入"""
    
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


class ChromaMemoryBackend(MemoryBackend):
    """ChromaDB 记忆后端"""
    
    # 嵌入模型配置
    EMBEDDING_MODELS = {
        "local": "BAAI/bge-m3",
        "openai": "text-embedding-3-small",
        "ollama": "bge-m3"
    }
    
    def __init__(
        self,
        path: str = "./memory/chroma",
        embedding_provider: str = "local",
        embedding_model: Optional[str] = None,
        ollama_url: str = "http://localhost:11434",
        openai_api_key: Optional[str] = None,
        auto_archive: bool = True,
        p1_max_age_days: int = 7,
        p2_max_age_days: int = 1
    ):
        """初始化 ChromaDB 后端
        
        Args:
            path: ChromaDB 存储路径
            embedding_provider: 嵌入提供商 (local/openai/ollama)
            embedding_model: 自定义嵌入模型名称
            ollama_url: Ollama 服务地址
            openai_api_key: OpenAI API 密钥
            auto_archive: 是否启用自动归档
            p1_max_age_days: P1 记忆最大保留天数
            p2_max_age_days: P2 记忆最大保留天数
        """
        self.path = Path(path).resolve()
        self.archive_path = self.path.parent / "archive"
        
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model or self.EMBEDDING_MODELS.get(embedding_provider)
        self.ollama_url = ollama_url
        self.openai_api_key = openai_api_key
        
        self.auto_archive = auto_archive
        self.p1_max_age_days = p1_max_age_days
        self.p2_max_age_days = p2_max_age_days
        
        # 延迟初始化的属性
        self._client = None
        self._collection = None
        self._embedding_func = None
        self._initialized = False
        
        logger.info(f"ChromaMemoryBackend configured:")
        logger.info(f"  Path: {self.path}")
        logger.info(f"  Embedding: {embedding_provider} ({self.embedding_model})")
    
    def _init_client(self):
        """延迟初始化 ChromaDB 客户端"""
        if self._client is not None:
            return
        
        # 延迟导入
        import chromadb
        from chromadb.config import Settings
        
        # 创建目录
        self.path.mkdir(parents=True, exist_ok=True)
        self.archive_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化嵌入函数
        self._init_embedding_function()
        
        # 初始化 ChromaDB
        self._client = chromadb.PersistentClient(
            path=str(self.path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=False
            )
        )
        
        # 获取或创建集合
        self._collection = self._client.get_or_create_collection(
            name="memories",
            embedding_function=self._embedding_func,
            metadata={"hnsw:space": "cosine"}
        )
        
        logger.info(f"ChromaDB initialized with {self._collection.count()} memories")
    
    def _init_embedding_function(self):
        """初始化嵌入函数 - 延迟导入"""
        if self._embedding_func is not None:
            return
        
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
    
    async def initialize(self):
        """初始化后端"""
        if self._initialized:
            return
        
        try:
            # 延迟导入检查
            try:
                import chromadb
            except ImportError:
                raise RuntimeError("chromadb is required. Install: pip install chromadb")
            
            # 在异步线程中初始化
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._init_client)
            
            self._initialized = True
            
            # 启动自动归档任务
            if self.auto_archive:
                asyncio.create_task(self._auto_archive_loop())
            
            logger.info("ChromaMemoryBackend initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaMemoryBackend: {e}")
            raise
    
    async def add(self, entry: MemoryEntry) -> str:
        """添加记忆"""
        if not self._initialized:
            await self.initialize()
        
        # 检查重复
        if await self._check_duplicate(entry.content, entry.level):
            logger.debug(f"Duplicate memory detected, skipping: {entry.content[:50]}...")
            return entry.memory_id
        
        try:
            # 准备元数据
            chroma_metadata = {
                "level": entry.level.value,
                "created_at": entry.created_at.isoformat() if entry.created_at else datetime.now().isoformat(),
                **{k: str(v) for k, v in entry.metadata.items()}
            }
            
            # 添加到 ChromaDB
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._collection.add(
                    ids=[entry.memory_id],
                    documents=[entry.content],
                    metadatas=[chroma_metadata]
                )
            )
            
            logger.debug(f"Added memory: {entry.memory_id[:20]}... (level={entry.level.value})")
            return entry.memory_id
            
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            raise
    
    async def search(
        self, 
        query: str, 
        limit: int = 5,
        level: Optional[MemoryLevel] = None,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """搜索记忆"""
        if not self._initialized:
            logger.warning("ChromaMemoryBackend not initialized")
            return []
        
        try:
            # 构建过滤条件
            where_filter = None
            if level:
                where_filter = {"level": level.value}
            
            # 执行搜索
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: self._collection.query(
                    query_texts=[query],
                    n_results=limit * 2,  # 多取一些用于过滤
                    where=where_filter,
                    include=["documents", "metadatas", "distances"]
                )
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
            return memories[:limit]
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    async def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        if not self._initialized:
            return False
        
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._collection.delete(ids=[memory_id])
            )
            logger.debug(f"Deleted memory: {memory_id[:20]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False
    
    async def get_by_level(self, level: MemoryLevel) -> List[Dict[str, Any]]:
        """获取特定级别的所有记忆"""
        if not self._initialized:
            return []
        
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: self._collection.get(
                    where={"level": level.value},
                    include=["documents", "metadatas"]
                )
            )
            
            memories = []
            if results['ids']:
                for i, memory_id in enumerate(results['ids']):
                    memories.append({
                        "id": memory_id,
                        "content": results['documents'][i],
                        "metadata": results['metadatas'][i] if results['metadatas'] else {},
                        "level": level.value
                    })
            
            return memories
        except Exception as e:
            logger.error(f"Failed to get memories by level: {e}")
            return []
    
    async def _check_duplicate(self, content: str, level: MemoryLevel) -> bool:
        """检查是否已存在相似记忆"""
        try:
            results = await self.search(content[:100], limit=3, level=level, min_score=0.95)
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
        for level, max_days in [(MemoryLevel.P1, self.p1_max_age_days), (MemoryLevel.P2, self.p2_max_age_days)]:
            memories = await self.get_by_level(level)
            
            for mem in memories:
                try:
                    created_at = datetime.fromisoformat(mem['metadata'].get('created_at', datetime.now().isoformat()))
                    age_days = (datetime.now() - created_at).days
                    
                    if age_days > max_days:
                        if level == MemoryLevel.P1:
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

    # ===== Memory Enhancer 功能 =====
    
    async def auto_archive(self) -> Dict[str, int]:
        """手动触发自动归档
        
        Returns:
            归档统计信息
        """
        if not self._initialized:
            return {"archived": 0, "deleted": 0, "error": "not_initialized"}
        
        result = {"archived": 0, "deleted": 0}
        
        for level, max_days in [(MemoryLevel.P1, self.p1_max_age_days), (MemoryLevel.P2, self.p2_max_age_days)]:
            memories = await self.get_by_level(level)
            
            for mem in memories:
                try:
                    created_at = datetime.fromisoformat(mem['metadata'].get('created_at', datetime.now().isoformat()))
                    age_days = (datetime.now() - created_at).days
                    
                    if age_days > max_days:
                        if level == MemoryLevel.P1:
                            await self._archive_memory(mem)
                            result["archived"] += 1
                        else:
                            await self.delete(mem['id'])
                            result["deleted"] += 1
                except Exception as e:
                    logger.debug(f"Archive processing error: {e}")
        
        logger.info(f"Manual archive complete: {result['archived']} archived, {result['deleted']} deleted")
        return result
    
    async def detect_duplicates(self, threshold: float = 0.9) -> List[str]:
        """检测重复记忆
        
        Args:
            threshold: 相似度阈值，超过此值认为是重复
            
        Returns:
            重复的记忆 ID 列表（保留第一个，其余为重复）
        """
        if not self._initialized or not self._collection:
            return []
        
        try:
            loop = asyncio.get_event_loop()
            
            # 获取所有记忆
            all_memories = await loop.run_in_executor(
                None,
                lambda: self._collection.get(include=["documents", "embeddings"])
            )
            
            if not all_memories['ids']:
                return []
            
            duplicates = []
            seen = set()
            
            for i, mem_id in enumerate(all_memories['ids']):
                if mem_id in seen:
                    continue
                
                # 获取当前记忆的嵌入
                if not all_memories['embeddings'] or not all_memories['embeddings'][i]:
                    continue
                
                embedding_i = all_memories['embeddings'][i]
                
                # 与其他记忆比较
                for j, other_id in enumerate(all_memories['ids']):
                    if i >= j or other_id in seen:
                        continue
                    
                    if not all_memories['embeddings'] or not all_memories['embeddings'][j]:
                        continue
                    
                    embedding_j = all_memories['embeddings'][j]
                    
                    # 计算余弦相似度
                    similarity = self._cosine_similarity(embedding_i, embedding_j)
                    
                    if similarity >= threshold:
                        duplicates.append(other_id)
                        seen.add(other_id)
                
                seen.add(mem_id)
            
            logger.info(f"Detected {len(duplicates)} duplicate memories")
            return duplicates
            
        except Exception as e:
            logger.error(f"Duplicate detection failed: {e}")
            return []
    
    def _cosine_similarity(self, a, b) -> float:
        """计算余弦相似度"""
        import numpy as np
        a = np.array(a)
        b = np.array(b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    
    async def merge_duplicates(self, keep: str = "newest") -> Dict[str, int]:
        """合并重复记忆
        
        Args:
            keep: 保留策略，"newest" 或 "oldest"
            
        Returns:
            合并统计
        """
        duplicates = await self.detect_duplicates(threshold=0.9)
        
        if not duplicates:
            return {"merged": 0, "deleted": 0}
        
        deleted_count = 0
        for dup_id in duplicates:
            if await self.delete(dup_id):
                deleted_count += 1
        
        logger.info(f"Merged duplicates: kept {keep}, deleted {deleted_count}")
        return {"merged": len(duplicates), "deleted": deleted_count}
    
    async def upgrade_memory_level(self, memory_id: str, new_level: str) -> bool:
        """升级记忆级别 (P2 -> P1 -> P0)
        
        Args:
            memory_id: 记忆 ID
            new_level: 新级别 (P0, P1, P2)
            
        Returns:
            是否成功
        """
        if not self._initialized or not self._collection:
            return False
        
        try:
            # 获取当前记忆
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._collection.get(ids=[memory_id], include=["documents", "metadatas"])
            )
            
            if not result['ids']:
                logger.warning(f"Memory not found: {memory_id}")
                return False
            
            # 更新元数据
            metadata = result['metadatas'][0] if result['metadatas'] else {}
            metadata['level'] = new_level
            metadata['upgraded_at'] = datetime.now().isoformat()
            
            # 更新
            await loop.run_in_executor(
                None,
                lambda: self._collection.update(
                    ids=[memory_id],
                    metadatas=[metadata]
                )
            )
            
            logger.info(f"Upgraded memory {memory_id[:20]}... to {new_level}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upgrade memory: {e}")
            return False
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """获取详细记忆统计
        
        Returns:
            包含总数、各级别数量、重复率等统计信息
        """
        if not self._initialized or not self._collection:
            return {"status": "not_initialized"}
        
        try:
            loop = asyncio.get_event_loop()
            total = await loop.run_in_executor(None, self._collection.count)
            
            # 按级别统计
            level_stats = {}
            for level in MemoryLevel:
                try:
                    results = await loop.run_in_executor(
                        None,
                        lambda: self._collection.get(where={"level": level.value})
                    )
                    level_stats[level.value] = len(results['ids']) if results['ids'] else 0
                except:
                    level_stats[level.value] = 0
            
            # 计算重复率
            duplicates = await self.detect_duplicates(threshold=0.9)
            duplicate_rate = len(duplicates) / total if total > 0 else 0
            
            # 归档文件统计
            archive_count = 0
            if self.archive_path.exists():
                for archive_file in self.archive_path.glob("*.jsonl"):
                    with open(archive_file, 'r', encoding='utf-8') as f:
                        archive_count += sum(1 for _ in f)
            
            return {
                "status": "initialized",
                "backend": "chroma",
                "total_memories": total,
                "by_level": level_stats,
                "duplicate_count": len(duplicates),
                "duplicate_rate": round(duplicate_rate, 4),
                "archived_count": archive_count,
                "embedding_provider": self.embedding_provider,
                "embedding_model": self.embedding_model
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self._initialized or not self._collection:
            return {"status": "not_initialized"}
        
        try:
            loop = asyncio.get_event_loop()
            total = await loop.run_in_executor(None, self._collection.count)
            
            # 按级别统计
            level_stats = {}
            for level in MemoryLevel:
                try:
                    results = await loop.run_in_executor(
                        None,
                        lambda: self._collection.get(where={"level": level.value})
                    )
                    level_stats[level.value] = len(results['ids']) if results['ids'] else 0
                except:
                    level_stats[level.value] = 0
            
            return {
                "status": "initialized",
                "backend": "chroma",
                "total_memories": total,
                "by_level": level_stats,
                "embedding_provider": self.embedding_provider,
                "embedding_model": self.embedding_model
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def close(self):
        """关闭后端"""
        self._initialized = False
        # ChromaDB 自动持久化，无需特别关闭
        logger.info("ChromaMemoryBackend closed")
