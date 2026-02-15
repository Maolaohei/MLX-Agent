"""
SQLite 记忆后端实现

纯 SQLite 记忆后端，零额外依赖（只需 Python 标准库 + numpy）

特点:
- 向量存储为 BLOB (numpy array)
- 余弦相似度纯 Python 计算
- FTS5 关键词搜索
- 轻量级，适合资源受限环境
"""

import sqlite3
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
from loguru import logger

from .base import MemoryBackend, MemoryEntry, MemoryLevel


class SQLiteMemoryBackend(MemoryBackend):
    """SQLite 记忆后端"""
    
    def __init__(
        self,
        path: str = "./memory/memory.db",
        embedding_provider: str = "local",
        embedding_model: str = "BAAI/bge-m3",
        ollama_url: str = "http://localhost:11434",
        openai_api_key: Optional[str] = None,
        auto_archive: bool = True,
        p1_max_age_days: int = 7,
        p2_max_age_days: int = 1,
        vector_weight: float = 0.7
    ):
        """初始化 SQLite 后端
        
        Args:
            path: SQLite 数据库路径
            embedding_provider: 嵌入提供商
            embedding_model: 嵌入模型名称
            ollama_url: Ollama 服务地址
            openai_api_key: OpenAI API 密钥
            auto_archive: 是否启用自动归档
            p1_max_age_days: P1 记忆最大保留天数
            p2_max_age_days: P2 记忆最大保留天数
            vector_weight: 向量搜索权重 (0-1)
        """
        self.path = Path(path).resolve()
        self.archive_path = self.path.parent / "archive"
        
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.ollama_url = ollama_url
        self.openai_api_key = openai_api_key
        
        self.auto_archive = auto_archive
        self.p1_max_age_days = p1_max_age_days
        self.p2_max_age_days = p2_max_age_days
        self.vector_weight = vector_weight
        
        # 延迟初始化的属性
        self._db = None
        self._embedding_model_obj = None
        self._initialized = False
        
        logger.info(f"SQLiteMemoryBackend configured:")
        logger.info(f"  Path: {self.path}")
        logger.info(f"  Embedding: {embedding_provider}")
    
    def _init_db(self):
        """延迟初始化数据库"""
        if self._db is not None:
            return
        
        # 创建目录
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_path.mkdir(parents=True, exist_ok=True)
        
        # 连接数据库
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        
        # 创建表
        self._create_tables()
        
        logger.info(f"SQLite database initialized at {self.path}")
    
    def _create_tables(self):
        """创建数据库表"""
        cursor = self._db.cursor()
        
        # 主记忆表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                level TEXT DEFAULT 'P1',
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_level ON memories(level)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_created ON memories(created_at)")
        
        # 尝试创建 FTS5 虚拟表用于全文搜索
        try:
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    content,
                    memory_id UNINDEXED,
                    content_rowid=rowid
                )
            """)
            
            # 创建触发器保持 FTS 同步
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memory_fts(content, memory_id) VALUES (new.content, new.id);
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memory_fts(memory_fts, rowid, content, memory_id) 
                    VALUES ('delete', old.rowid, old.content, old.id);
                END
            """)
            
            self._fts_enabled = True
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS5 not available: {e}")
            self._fts_enabled = False
        
        # 嵌入缓存表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                text_hash TEXT PRIMARY KEY,
                text_preview TEXT,
                embedding BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self._db.commit()
    
    def _init_embedding_model(self):
        """延迟初始化嵌入模型"""
        if self._embedding_model_obj is not None:
            return
        
        if self.embedding_provider == "local":
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model_obj = SentenceTransformer(self.embedding_model)
                logger.info(f"Loaded embedding model: {self.embedding_model}")
            except ImportError:
                logger.warning("sentence-transformers not installed, embeddings disabled")
                self._embedding_model_obj = None
        else:
            logger.warning(f"SQLite backend only supports local embeddings currently")
            self._embedding_model_obj = None
    
    async def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """获取文本的嵌入向量"""
        import hashlib
        
        # 检查缓存
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        
        cursor = self._db.cursor()
        cursor.execute(
            "SELECT embedding FROM embedding_cache WHERE text_hash = ?",
            (text_hash,)
        )
        row = cursor.fetchone()
        
        if row and row['embedding']:
            return np.frombuffer(row['embedding'], dtype=np.float32)
        
        # 生成嵌入
        if self._embedding_model_obj is None:
            return None
        
        try:
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: self._embedding_model_obj.encode(text, convert_to_numpy=True)
            )
            
            # 缓存嵌入
            cursor.execute(
                "INSERT OR REPLACE INTO embedding_cache (text_hash, text_preview, embedding) VALUES (?, ?, ?)",
                (text_hash, text[:100], embedding.astype(np.float32).tobytes())
            )
            self._db.commit()
            
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return None
    
    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    
    async def initialize(self):
        """初始化后端"""
        if self._initialized:
            return
        
        try:
            # 在异步线程中初始化
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._init_db)
            await loop.run_in_executor(None, self._init_embedding_model)
            
            self._initialized = True
            
            # 启动自动归档任务
            if self.auto_archive:
                asyncio.create_task(self._auto_archive_loop())
            
            logger.info("SQLiteMemoryBackend initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize SQLiteMemoryBackend: {e}")
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
            # 生成嵌入
            embedding = await self._get_embedding(entry.content)
            embedding_bytes = embedding.astype(np.float32).tobytes() if embedding is not None else None
            
            # 插入数据库
            cursor = self._db.cursor()
            cursor.execute(
                """INSERT INTO memories (id, content, metadata, level, embedding, created_at) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    entry.memory_id,
                    entry.content,
                    json.dumps(entry.metadata),
                    entry.level.value,
                    embedding_bytes,
                    entry.created_at.isoformat() if entry.created_at else datetime.now().isoformat()
                )
            )
            self._db.commit()
            
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
        """搜索记忆（向量 + 关键词混合搜索）"""
        if not self._initialized:
            logger.warning("SQLiteMemoryBackend not initialized")
            return []
        
        try:
            # 1. 向量搜索
            vector_results = await self._vector_search(query, limit * 2, level)
            
            # 2. 关键词搜索
            keyword_results = await self._keyword_search(query, limit * 2, level)
            
            # 3. 合并结果
            combined = self._merge_results(vector_results, keyword_results, limit, min_score)
            
            logger.debug(f"Found {len(combined)} memories for: {query[:50]}...")
            return combined
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    async def _vector_search(
        self, 
        query: str, 
        limit: int,
        level: Optional[MemoryLevel] = None
    ) -> Dict[str, Tuple[float, Dict]]:
        """向量相似度搜索"""
        query_embedding = await self._get_embedding(query)
        if query_embedding is None:
            return {}
        
        cursor = self._db.cursor()
        
        if level:
            cursor.execute(
                "SELECT id, content, metadata, level, embedding FROM memories WHERE level = ?",
                (level.value,)
            )
        else:
            cursor.execute("SELECT id, content, metadata, level, embedding FROM memories")
        
        results = {}
        for row in cursor.fetchall():
            if row['embedding'] is None:
                continue
            
            mem_embedding = np.frombuffer(row['embedding'], dtype=np.float32)
            similarity = self._cosine_similarity(query_embedding, mem_embedding)
            
            results[row['id']] = (
                similarity,
                {
                    "id": row['id'],
                    "content": row['content'],
                    "metadata": json.loads(row['metadata'] or '{}'),
                    "level": row['level']
                }
            )
        
        return results
    
    async def _keyword_search(
        self, 
        query: str, 
        limit: int,
        level: Optional[MemoryLevel] = None
    ) -> Dict[str, Tuple[float, Dict]]:
        """关键词搜索"""
        if not self._fts_enabled:
            # 简单的 LIKE 搜索作为后备
            return await self._fallback_keyword_search(query, limit, level)
        
        cursor = self._db.cursor()
        
        try:
            # 清理查询字符串
            clean_query = query.replace('"', '""').strip()
            
            cursor.execute(
                "SELECT memory_id, rank FROM memory_fts WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
                (clean_query, limit * 2)
            )
            
            results = {}
            for row in cursor.fetchall():
                memory_id = row['memory_id']
                
                # 获取完整记忆
                if level:
                    cursor.execute(
                        "SELECT id, content, metadata, level FROM memories WHERE id = ? AND level = ?",
                        (memory_id, level.value)
                    )
                else:
                    cursor.execute(
                        "SELECT id, content, metadata, level FROM memories WHERE id = ?",
                        (memory_id,)
                    )
                
                mem_row = cursor.fetchone()
                if mem_row:
                    # FTS rank 越小越相关，转换为 0-1 分数
                    score = 1.0 / (1.0 + abs(row['rank']))
                    results[memory_id] = (
                        score,
                        {
                            "id": mem_row['id'],
                            "content": mem_row['content'],
                            "metadata": json.loads(mem_row['metadata'] or '{}'),
                            "level": mem_row['level']
                        }
                    )
            
            return results
            
        except sqlite3.OperationalError as e:
            logger.debug(f"FTS search failed: {e}")
            return await self._fallback_keyword_search(query, limit, level)
    
    async def _fallback_keyword_search(
        self, 
        query: str, 
        limit: int,
        level: Optional[MemoryLevel] = None
    ) -> Dict[str, Tuple[float, Dict]]:
        """后备关键词搜索（使用 LIKE）"""
        cursor = self._db.cursor()
        keywords = [k.strip() for k in query.split() if len(k.strip()) > 2]
        
        if not keywords:
            return {}
        
        # 构建 LIKE 查询
        conditions = " OR ".join(["content LIKE ?" for _ in keywords])
        params = [f"%{k}%" for k in keywords]
        
        if level:
            sql = f"SELECT id, content, metadata, level FROM memories WHERE ({conditions}) AND level = ? LIMIT ?"
            params.append(level.value)
            params.append(limit * 2)
        else:
            sql = f"SELECT id, content, metadata, level FROM memories WHERE {conditions} LIMIT ?"
            params.append(limit * 2)
        
        cursor.execute(sql, params)
        
        results = {}
        for row in cursor.fetchall():
            # 简单的相关性评分：匹配的关键词越多分数越高
            score = sum(1 for k in keywords if k.lower() in row['content'].lower()) / len(keywords)
            
            results[row['id']] = (
                score,
                {
                    "id": row['id'],
                    "content": row['content'],
                    "metadata": json.loads(row['metadata'] or '{}'),
                    "level": row['level']
                }
            )
        
        return results
    
    def _merge_results(
        self,
        vector_results: Dict[str, Tuple[float, Dict]],
        keyword_results: Dict[str, Tuple[float, Dict]],
        limit: int,
        min_score: float
    ) -> List[Dict[str, Any]]:
        """合并向量搜索和关键词搜索结果"""
        combined = {}
        
        # 向量结果加权
        for mem_id, (score, data) in vector_results.items():
            combined[mem_id] = {
                "vector_score": score * self.vector_weight,
                "keyword_score": 0.0,
                "data": data
            }
        
        # 关键词结果加权
        for mem_id, (score, data) in keyword_results.items():
            if mem_id in combined:
                combined[mem_id]["keyword_score"] = score * (1 - self.vector_weight)
            else:
                combined[mem_id] = {
                    "vector_score": 0.0,
                    "keyword_score": score * (1 - self.vector_weight),
                    "data": data
                }
        
        # 计算最终分数并过滤
        results = []
        for mem_id, scores in combined.items():
            final_score = scores["vector_score"] + scores["keyword_score"]
            if final_score >= min_score:
                result = scores["data"].copy()
                result["score"] = final_score
                results.append(result)
        
        # 按分数排序并限制数量
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    async def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        if not self._initialized:
            return False
        
        try:
            cursor = self._db.cursor()
            cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self._db.commit()
            
            logger.debug(f"Deleted memory: {memory_id[:20]}...")
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False
    
    async def get_by_level(self, level: MemoryLevel) -> List[Dict[str, Any]]:
        """获取特定级别的所有记忆"""
        if not self._initialized:
            return []
        
        try:
            cursor = self._db.cursor()
            cursor.execute(
                "SELECT id, content, metadata, level, created_at FROM memories WHERE level = ?",
                (level.value,)
            )
            
            memories = []
            for row in cursor.fetchall():
                memories.append({
                    "id": row['id'],
                    "content": row['content'],
                    "metadata": json.loads(row['metadata'] or '{}'),
                    "level": row['level'],
                    "created_at": row['created_at']
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
                    created_at = datetime.fromisoformat(mem.get('created_at', datetime.now().isoformat()))
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
                    created_at = datetime.fromisoformat(mem.get('created_at', datetime.now().isoformat()))
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
        if not self._initialized or not self._db:
            return []
        
        try:
            cursor = self._db.cursor()
            cursor.execute("SELECT id, content, embedding FROM memories WHERE embedding IS NOT NULL")
            rows = cursor.fetchall()
            
            if not rows:
                return []
            
            duplicates = []
            seen = set()
            
            for i, row_i in enumerate(rows):
                mem_id_i = row_i['id']
                if mem_id_i in seen:
                    continue
                
                if row_i['embedding'] is None:
                    continue
                
                embedding_i = np.frombuffer(row_i['embedding'], dtype=np.float32)
                
                for j, row_j in enumerate(rows):
                    if i >= j:
                        continue
                    
                    mem_id_j = row_j['id']
                    if mem_id_j in seen or row_j['embedding'] is None:
                        continue
                    
                    embedding_j = np.frombuffer(row_j['embedding'], dtype=np.float32)
                    similarity = self._cosine_similarity(embedding_i, embedding_j)
                    
                    if similarity >= threshold:
                        duplicates.append(mem_id_j)
                        seen.add(mem_id_j)
                
                seen.add(mem_id_i)
            
            logger.info(f"Detected {len(duplicates)} duplicate memories")
            return duplicates
            
        except Exception as e:
            logger.error(f"Duplicate detection failed: {e}")
            return []
    
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
        if not self._initialized or not self._db:
            return False
        
        try:
            cursor = self._db.cursor()
            
            # 检查记忆是否存在
            cursor.execute("SELECT id FROM memories WHERE id = ?", (memory_id,))
            if not cursor.fetchone():
                logger.warning(f"Memory not found: {memory_id}")
                return False
            
            # 更新级别
            cursor.execute(
                "UPDATE memories SET level = ? WHERE id = ?",
                (new_level, memory_id)
            )
            self._db.commit()
            
            logger.info(f"Upgraded memory {memory_id[:20]}... to {new_level}")
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Failed to upgrade memory: {e}")
            return False
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """获取详细记忆统计
        
        Returns:
            包含总数、各级别数量、重复率等统计信息
        """
        if not self._initialized or not self._db:
            return {"status": "not_initialized"}
        
        try:
            cursor = self._db.cursor()
            
            # 总记忆数
            cursor.execute("SELECT COUNT(*) as total FROM memories")
            total = cursor.fetchone()['total']
            
            # 按级别统计
            level_stats = {}
            for level in MemoryLevel:
                cursor.execute("SELECT COUNT(*) as count FROM memories WHERE level = ?", (level.value,))
                level_stats[level.value] = cursor.fetchone()['count']
            
            # 计算重复率
            duplicates = await self.detect_duplicates(threshold=0.9)
            duplicate_rate = len(duplicates) / total if total > 0 else 0
            
            # 嵌入缓存统计
            cursor.execute("SELECT COUNT(*) as count FROM embedding_cache")
            cache_count = cursor.fetchone()['count']
            
            # 归档文件统计
            archive_count = 0
            if self.archive_path.exists():
                for archive_file in self.archive_path.glob("*.jsonl"):
                    with open(archive_file, 'r', encoding='utf-8') as f:
                        archive_count += sum(1 for _ in f)
            
            return {
                "status": "initialized",
                "backend": "sqlite",
                "total_memories": total,
                "by_level": level_stats,
                "duplicate_count": len(duplicates),
                "duplicate_rate": round(duplicate_rate, 4),
                "archived_count": archive_count,
                "embedding_provider": self.embedding_provider,
                "embedding_model": self.embedding_model,
                "fts_enabled": self._fts_enabled,
                "embedding_cache_size": cache_count
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self._initialized or not self._db:
            return {"status": "not_initialized"}
        
        try:
            cursor = self._db.cursor()
            
            # 总记忆数
            cursor.execute("SELECT COUNT(*) as total FROM memories")
            total = cursor.fetchone()['total']
            
            # 按级别统计
            level_stats = {}
            for level in MemoryLevel:
                cursor.execute("SELECT COUNT(*) as count FROM memories WHERE level = ?", (level.value,))
                level_stats[level.value] = cursor.fetchone()['count']
            
            # 嵌入缓存统计
            cursor.execute("SELECT COUNT(*) as count FROM embedding_cache")
            cache_count = cursor.fetchone()['count']
            
            return {
                "status": "initialized",
                "backend": "sqlite",
                "total_memories": total,
                "by_level": level_stats,
                "embedding_provider": self.embedding_provider,
                "embedding_model": self.embedding_model,
                "fts_enabled": self._fts_enabled,
                "embedding_cache_size": cache_count
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def close(self):
        """关闭后端"""
        self._initialized = False
        if self._db:
            self._db.close()
            self._db = None
        logger.info("SQLiteMemoryBackend closed")
