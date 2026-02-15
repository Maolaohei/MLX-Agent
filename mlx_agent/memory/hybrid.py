"""
混合记忆后端 - 功能分工模式

ChromaDB: 负责向量存储和语义搜索
SQLite: 负责关键词索引、元数据、缓存

支持内存不足时自动降级为纯 SQLite 模式
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any

import numpy as np

from .base import MemoryBackend, MemoryEntry, MemoryLevel

logger = logging.getLogger(__name__)

# 尝试导入 psutil，如果不可用则使用模拟
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil not installed, memory monitoring disabled")


@dataclass
class HybridConfig:
    """混合后端配置"""
    # ChromaDB 配置
    chroma_path: str = "./memory/chroma"
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-m3"
    ollama_url: str = "http://localhost:11434"
    openai_api_key: Optional[str] = None
    
    # SQLite 配置
    sqlite_path: str = "./memory/hybrid.db"
    
    # RRF 合并参数
    rrf_k: int = 60
    
    # 内存阈值 (MB)
    memory_threshold_mb: int = 500  # 可用内存 < 500MB 时降级
    memory_check_interval: int = 60  # 每 60 秒检查一次
    
    # 降级模式配置
    fallback_mode: str = "auto"  # "auto", "never", "always"


class HybridMemoryBackend(MemoryBackend):
    """混合记忆后端
    
    功能分工:
    - ChromaDB: 向量嵌入、语义相似度搜索
    - SQLite: BM25 关键词搜索、元数据、统计
    
    特性:
    - 并行查询两个后端
    - RRF 算法合并结果
    - 内存不足时自动降级为 SQLite-only
    """
    
    def __init__(self, config: Optional[HybridConfig] = None):
        self.config = config or HybridConfig()
        
        # 延迟导入具体实现
        from .sqlite import SQLiteMemoryBackend
        from .chroma import ChromaMemoryBackend
        
        self._SQLiteMemoryBackend = SQLiteMemoryBackend
        self._ChromaMemoryBackend = ChromaMemoryBackend
        
        # SQLite 始终可用 (轻量级)
        self.sqlite = SQLiteMemoryBackend(
            path=self.config.sqlite_path,
            embedding_provider=self.config.embedding_provider,
            embedding_model=self.config.embedding_model,
            ollama_url=self.config.ollama_url,
            openai_api_key=self.config.openai_api_key,
            auto_archive=True
        )
        
        # ChromaDB 延迟初始化
        self._chroma: Optional[Any] = None
        
        # 状态
        self._degraded_mode = False  # 降级模式标志
        self._last_memory_check = 0
        self._initialized = False
        
        logger.info(f"HybridMemoryBackend configured:")
        logger.info(f"  SQLite: {self.config.sqlite_path}")
        logger.info(f"  ChromaDB: {self.config.chroma_path}")
        logger.info(f"  Memory threshold: {self.config.memory_threshold_mb}MB")
    
    @property
    def chroma(self) -> Optional[Any]:
        """延迟初始化 ChromaDB"""
        if self._chroma is None and not self._degraded_mode:
            try:
                self._chroma = self._ChromaMemoryBackend(
                    path=self.config.chroma_path,
                    embedding_provider=self.config.embedding_provider,
                    embedding_model=self.config.embedding_model,
                    ollama_url=self.config.ollama_url,
                    openai_api_key=self.config.openai_api_key,
                    auto_archive=True
                )
            except Exception as e:
                logger.warning(f"Failed to init ChromaDB, switching to degraded mode: {e}")
                self._enter_degraded_mode()
        return self._chroma
    
    def _check_memory(self) -> bool:
        """检查内存是否充足
        
        Returns:
            True: 内存充足
            False: 内存不足，应降级
        """
        if not HAS_PSUTIL:
            return True  # 无法检测时假设充足
        
        try:
            mem = psutil.virtual_memory()
            available_mb = mem.available / (1024 * 1024)
            return available_mb > self.config.memory_threshold_mb
        except Exception:
            return True  # 无法检测时假设充足
    
    def _enter_degraded_mode(self):
        """进入降级模式 (纯 SQLite)"""
        if not self._degraded_mode:
            logger.warning("🔻 Entering degraded mode (SQLite only) due to low memory")
            self._degraded_mode = True
            self._chroma = None  # 释放 ChromaDB
    
    def _exit_degraded_mode(self):
        """退出降级模式 (恢复混合)"""
        if self._degraded_mode:
            logger.info("🔺 Exiting degraded mode (restoring hybrid)")
            self._degraded_mode = False
            # ChromaDB 会在下次访问时自动初始化
    
    async def _maybe_switch_mode(self):
        """根据需要切换模式"""
        if self.config.fallback_mode == "always":
            self._enter_degraded_mode()
            return
        
        if self.config.fallback_mode == "never":
            self._exit_degraded_mode()
            return
        
        # auto 模式
        has_memory = self._check_memory()
        if has_memory and self._degraded_mode:
            self._exit_degraded_mode()
        elif not has_memory and not self._degraded_mode:
            self._enter_degraded_mode()
    
    async def initialize(self):
        """初始化后端"""
        if self._initialized:
            return
        
        # 初始化 SQLite
        await self.sqlite.initialize()
        
        # 根据内存情况决定是否初始化 ChromaDB
        await self._maybe_switch_mode()
        
        if not self._degraded_mode and self.chroma:
            try:
                await self.chroma.initialize()
            except Exception as e:
                logger.warning(f"Failed to initialize ChromaDB: {e}")
                self._enter_degraded_mode()
        
        self._initialized = True
        
        mode_str = "degraded (SQLite only)" if self._degraded_mode else "hybrid (SQLite + ChromaDB)"
        logger.info(f"HybridMemoryBackend initialized in {mode_str} mode")
    
    async def add(self, entry: MemoryEntry) -> str:
        """添加记忆
        
        同时写入 SQLite 和 ChromaDB (如果可用)
        """
        if not self._initialized:
            await self.initialize()
        
        await self._maybe_switch_mode()
        
        # 始终写入 SQLite
        sqlite_id = await self.sqlite.add(entry)
        
        # 如果未降级，也写入 ChromaDB
        if not self._degraded_mode and self.chroma:
            try:
                await self.chroma.add(entry)
            except Exception as e:
                logger.warning(f"Failed to add to ChromaDB: {e}")
        
        return sqlite_id
    
    async def search(
        self, 
        query: str, 
        limit: int = 5,
        level: Optional[MemoryLevel] = None,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """搜索记忆
        
        降级模式: 仅使用 SQLite BM25
        正常模式: SQLite BM25 + ChromaDB 向量，RRF 合并
        """
        if not self._initialized:
            await self.initialize()
        
        await self._maybe_switch_mode()
        
        if self._degraded_mode:
            # 降级模式: 纯 SQLite
            logger.debug("Using SQLite only (degraded mode)")
            return await self.sqlite.search(query, limit=limit, level=level, min_score=min_score)
        
        # 正常模式: 并行查询
        sqlite_task = self.sqlite.search(query, limit=limit * 2, level=level, min_score=min_score)
        chroma_task = self.chroma.search(query, limit=limit * 2, level=level, min_score=min_score) if self.chroma else asyncio.sleep(0)
        
        try:
            sqlite_results, chroma_results = await asyncio.gather(
                sqlite_task, 
                chroma_task,
                return_exceptions=True
            )
            
            # 处理异常
            if isinstance(sqlite_results, Exception):
                logger.error(f"SQLite search failed: {sqlite_results}")
                sqlite_results = []
            
            if isinstance(chroma_results, Exception) or chroma_results is None:
                logger.warning(f"ChromaDB search failed, using SQLite only")
                return sqlite_results[:limit] if isinstance(sqlite_results, list) else []
            
            # RRF 合并
            return self._rrf_merge(sqlite_results, chroma_results, limit)
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            # 失败时回退到 SQLite
            return await self.sqlite.search(query, limit=limit, level=level, min_score=min_score)
    
    def _rrf_merge(self, 
                   keyword_results: List[Dict[str, Any]], 
                   vector_results: List[Dict[str, Any]], 
                   limit: int) -> List[Dict[str, Any]]:
        """RRF (Reciprocal Rank Fusion) 合并结果
        
        score = Σ 1/(k + rank)
        """
        k = self.config.rrf_k
        scores: Dict[str, float] = {}
        entries: Dict[str, Dict[str, Any]] = {}
        
        # 关键词结果打分 (SQLite)
        for rank, entry in enumerate(keyword_results):
            entry_id = entry.get("id") or str(hash(entry.get("content", "")))
            scores[entry_id] = scores.get(entry_id, 0) + 1.0 / (k + rank)
            entries[entry_id] = entry
        
        # 向量结果打分 (ChromaDB)
        for rank, entry in enumerate(vector_results):
            entry_id = entry.get("id") or str(hash(entry.get("content", "")))
            scores[entry_id] = scores.get(entry_id, 0) + 1.0 / (k + rank)
            entries[entry_id] = entry
        
        # 按分数排序
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        return [entries[id] for id in sorted_ids[:limit]]
    
    async def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        # 从两边都删除
        sqlite_ok = await self.sqlite.delete(memory_id)
        
        if not self._degraded_mode and self.chroma:
            try:
                await self.chroma.delete(memory_id)
            except Exception as e:
                logger.warning(f"Failed to delete from ChromaDB: {e}")
        
        return sqlite_ok
    
    async def get_by_level(self, level: MemoryLevel) -> List[Dict[str, Any]]:
        """获取特定级别的所有记忆"""
        # 从 SQLite 获取，因为它有更全面的元数据
        return await self.sqlite.get_by_level(level)
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        sqlite_stats = await self.sqlite.get_stats()
        
        stats = {
            "mode": "degraded" if self._degraded_mode else "hybrid",
            "sqlite": sqlite_stats,
            "chroma": None
        }
        
        if not self._degraded_mode and self.chroma:
            try:
                stats["chroma"] = await self.chroma.get_stats()
            except Exception as e:
                logger.warning(f"Failed to get ChromaDB stats: {e}")
        
        # 添加内存信息
        if HAS_PSUTIL:
            try:
                mem = psutil.virtual_memory()
                stats["system_memory"] = {
                    "available_mb": mem.available / (1024 * 1024),
                    "threshold_mb": self.config.memory_threshold_mb,
                    "percent_used": mem.percent
                }
            except Exception:
                pass
        
        return stats
    
    async def close(self):
        """关闭后端"""
        # 关闭 SQLite
        await self.sqlite.close()
        
        # 关闭 ChromaDB (如果已初始化)
        if self.chroma:
            await self.chroma.close()
        
        self._initialized = False
        logger.info("HybridMemoryBackend closed")


# 便捷函数
async def create_hybrid_backend(config: Optional[Dict] = None) -> HybridMemoryBackend:
    """创建混合记忆后端
    
    Args:
        config: 配置字典
    
    Returns:
        HybridMemoryBackend 实例
    """
    if config:
        hybrid_config = HybridConfig(
            chroma_path=config.get("chroma", {}).get("path", "./memory/chroma"),
            sqlite_path=config.get("sqlite", {}).get("path", "./memory/hybrid.db"),
            embedding_provider=config.get("embedding_provider", "local"),
            embedding_model=config.get("embedding_model", "BAAI/bge-m3"),
            ollama_url=config.get("ollama_url", "http://localhost:11434"),
            openai_api_key=config.get("openai_api_key"),
            rrf_k=config.get("rrf_k", 60),
            memory_threshold_mb=config.get("memory_threshold_mb", 500),
            memory_check_interval=config.get("memory_check_interval", 60),
            fallback_mode=config.get("fallback_mode", "auto")
        )
    else:
        hybrid_config = HybridConfig()
    
    return HybridMemoryBackend(hybrid_config)
