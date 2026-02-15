"""
三层记忆架构 - Tiered Memory System

热层 (Hot): ChromaDB - 活跃记忆，快速访问
温层 (Warm): SQLite - 中期归档，关键词搜索
冷层 (Cold): ChromaDB - 长期存档，深度检索
"""

from typing import Dict, List, Optional, Any, Literal
from datetime import datetime, timedelta
from pathlib import Path
import asyncio
from loguru import logger

from .base import MemoryBackend, MemoryEntry, MemoryLevel
from .chroma import ChromaMemoryBackend
from .sqlite import SQLiteMemoryBackend


class TieredMemoryBackend(MemoryBackend):
    """
    三层记忆后端
    
    自动根据记忆年龄分层存储：
    - Hot (0-7天): P0 + 活跃P1/P2 → ChromaDB (主)
    - Warm (7-30天): 过期P1 → SQLite
    - Cold (30天+): 长期存档 → ChromaDB (归档)
    """
    
    def __init__(
        self,
        hot_path: str = "./memory/hot",
        warm_path: str = "./memory/warm.db",
        cold_path: str = "./memory/cold",
        embedding_provider: str = "local",
        auto_tiering: bool = True
    ):
        """初始化三层记忆后端"""
        
        # 热层: ChromaDB (活跃记忆)
        self.hot = ChromaMemoryBackend(
            path=hot_path,
            embedding_provider=embedding_provider,
            collection_name="active",
            auto_archive=False  # 手动控制归档
        )
        
        # 温层: SQLite (中期归档)
        self.warm = SQLiteMemoryBackend(
            path=warm_path,
            embedding_provider=embedding_provider,
            auto_archive=False  # 手动控制归档
        )
        
        # 冷层: ChromaDB (长期存档)
        self.cold = ChromaMemoryBackend(
            path=cold_path,
            embedding_provider=embedding_provider,
            collection_name="archive",
            auto_archive=False  # 手动控制归档
        )
        
        self.auto_tiering = auto_tiering
        
        # 分层阈值 (天)
        self.hot_warm_threshold = 7    # P1: 7天后移到温层
        self.warm_cold_threshold = 30  # P1: 30天后移到冷层
        self.p2_hot_threshold = 1      # P2: 1天后归档
        
        self._initialized = False
        
        logger.info("TieredMemoryBackend configured:")
        logger.info(f"  Hot (ChromaDB): {hot_path}")
        logger.info(f"  Warm (SQLite): {warm_path}")
        logger.info(f"  Cold (ChromaDB): {cold_path}")
    
    async def initialize(self):
        """初始化三层后端"""
        if self._initialized:
            return
        
        # 并行初始化三层
        await asyncio.gather(
            self.hot.initialize(),
            self.warm.initialize(),
            self.cold.initialize()
        )
        
        self._initialized = True
        
        # 启动自动分层任务
        if self.auto_tiering:
            asyncio.create_task(self._auto_tier_loop())
        
        logger.info("TieredMemoryBackend initialized")
    
    async def add(self, entry: MemoryEntry) -> str:
        """添加记忆到热层"""
        if not self._initialized:
            await self.initialize()
        
        # 所有新记忆先进入热层
        # 确保 P0 记忆不会被自动归档
        return await self.hot.add(entry)
    
    async def search(
        self,
        query: str,
        limit: int = 5,
        level: Optional[MemoryLevel] = None,
        min_score: float = 0.0,
        depth: Literal["hot", "warm", "deep"] = "hot"
    ) -> List[Dict[str, Any]]:
        """
        分层搜索记忆
        
        Args:
            query: 搜索查询
            limit: 返回结果数量
            level: 筛选特定级别
            min_score: 最小相似度分数
            depth: 搜索深度
                - "hot": 只查热层 (最快)
                - "warm": 查热+温层 (较全)
                - "deep": 查全部包括冷层 (最全)
        """
        if not self._initialized:
            await self.initialize()
        
        if depth == "hot":
            # 只搜索热层
            return await self.hot.search(query, limit=limit, level=level, min_score=min_score)
        
        elif depth == "warm":
            # 热层 + 温层
            hot_results = await self.hot.search(query, limit=limit, level=level, min_score=min_score)
            if len(hot_results) >= limit:
                return hot_results[:limit]
            
            # 补充温层搜索
            warm_limit = limit - len(hot_results)
            warm_results = await self.warm.search(query, limit=warm_limit, level=level, min_score=min_score)
            
            return self._merge_results(hot_results, warm_results)[:limit]
        
        elif depth == "deep":
            # 全层搜索
            hot_results = await self.hot.search(query, limit=limit//2, level=level, min_score=min_score)
            warm_results = await self.warm.search(query, limit=limit//3, level=level, min_score=min_score)
            cold_results = await self.cold.search(query, limit=limit//3, level=level, min_score=min_score)
            
            return self._merge_results(hot_results, warm_results, cold_results)[:limit]
        
        else:
            raise ValueError(f"Unknown depth: {depth}")
    
    async def delete(self, memory_id: str) -> bool:
        """删除记忆（尝试从所有层删除）"""
        if not self._initialized:
            return False
        
        # 尝试从三层都删除
        results = await asyncio.gather(
            self.hot.delete(memory_id),
            self.warm.delete(memory_id),
            self.cold.delete(memory_id)
        )
        
        return any(results)
    
    async def get_by_level(self, level: MemoryLevel) -> List[Dict[str, Any]]:
        """获取特定级别的所有记忆（从所有层聚合）"""
        if not self._initialized:
            return []
        
        # 从三层获取
        hot_results = await self.hot.get_by_level(level)
        warm_results = await self.warm.get_by_level(level)
        cold_results = await self.cold.get_by_level(level)
        
        return self._merge_results(hot_results, warm_results, cold_results)
    
    async def auto_tier(self) -> Dict[str, int]:
        """
        自动分层归档
        
        Returns:
            归档统计 {"hot_to_warm": N, "warm_to_cold": N, "p2_to_cold": N}
        """
        if not self._initialized:
            return {"hot_to_warm": 0, "warm_to_cold": 0, "p2_to_cold": 0, "error": "not_initialized"}
        
        stats = {"hot_to_warm": 0, "warm_to_cold": 0, "p2_to_cold": 0}
        
        now = datetime.now()
        
        # 1. P2 记忆 (1天+) → 冷层
        p2_expired = await self._query_by_age_and_level(
            self.hot, 
            min_days=self.p2_hot_threshold,
            level=MemoryLevel.P2
        )
        for mem in p2_expired:
            entry = self._dict_to_entry(mem)
            await self.cold.add(entry)
            await self.hot.delete(mem['id'])
            stats["p2_to_cold"] += 1
        
        # 2. P1 记忆 (7天+) → 温层
        p1_warm = await self._query_by_age_and_level(
            self.hot,
            min_days=self.hot_warm_threshold,
            max_days=self.warm_cold_threshold,
            level=MemoryLevel.P1
        )
        for mem in p1_warm:
            entry = self._dict_to_entry(mem)
            await self.warm.add(entry)
            await self.hot.delete(mem['id'])
            stats["hot_to_warm"] += 1
        
        # 3. 温层 P1 (30天+) → 冷层
        warm_expired = await self._query_warm_by_age(min_days=self.warm_cold_threshold)
        for mem in warm_expired:
            entry = self._dict_to_entry(mem)
            await self.cold.add(entry)
            await self.warm.delete(mem['id'])
            stats["warm_to_cold"] += 1
        
        if any(stats.values()):
            logger.info(f"Auto-tier completed: {stats}")
        
        return stats
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取三层统计信息"""
        if not self._initialized:
            return {"status": "not_initialized"}
        
        hot_stats = await self.hot.get_stats()
        warm_stats = await self.warm.get_stats()
        cold_stats = await self.cold.get_stats()
        
        # 计算总计
        total_memories = (
            hot_stats.get("total_memories", 0) + 
            warm_stats.get("total_memories", 0) + 
            cold_stats.get("total_memories", 0)
        )
        
        return {
            "status": "initialized",
            "backend": "tiered",
            "hot": hot_stats,
            "warm": warm_stats,
            "cold": cold_stats,
            "total_memories": total_memories,
            "tiering_thresholds": {
                "hot_to_warm_days": self.hot_warm_threshold,
                "warm_to_cold_days": self.warm_cold_threshold,
                "p2_archive_days": self.p2_hot_threshold
            }
        }
    
    async def close(self):
        """关闭三层后端"""
        self._initialized = False
        await asyncio.gather(
            self.hot.close(),
            self.warm.close(),
            self.cold.close()
        )
        logger.info("TieredMemoryBackend closed")
    
    # ===== 辅助方法 =====
    
    def _merge_results(self, *result_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """合并多层搜索结果，去重"""
        seen_ids = set()
        merged = []
        
        for results in result_lists:
            for mem in results:
                mem_id = mem.get('id') or mem.get('memory_id')
                if mem_id and mem_id not in seen_ids:
                    seen_ids.add(mem_id)
                    merged.append(mem)
        
        # 按分数排序（如果有的话）
        merged.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        return merged
    
    def _dict_to_entry(self, data: Dict[str, Any]) -> MemoryEntry:
        """将字典转换为 MemoryEntry"""
        return MemoryEntry(
            content=data.get('content', ''),
            metadata=data.get('metadata', {}),
            level=MemoryLevel(data.get('level', 'P1')),
            memory_id=data.get('id') or data.get('memory_id'),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None
        )
    
    async def _query_by_age_and_level(
        self,
        backend: MemoryBackend,
        min_days: int,
        max_days: Optional[int] = None,
        level: Optional[MemoryLevel] = None
    ) -> List[Dict[str, Any]]:
        """按年龄和级别查询记忆"""
        results = []
        now = datetime.now()
        
        if level:
            memories = await backend.get_by_level(level)
        else:
            # 获取所有级别
            memories = []
            for lvl in MemoryLevel:
                memories.extend(await backend.get_by_level(lvl))
        
        for mem in memories:
            try:
                created_at_str = mem.get('metadata', {}).get('created_at') or mem.get('created_at')
                if not created_at_str:
                    continue
                
                created_at = datetime.fromisoformat(created_at_str)
                age_days = (now - created_at).days
                
                # 检查年龄范围
                if age_days >= min_days:
                    if max_days is None or age_days < max_days:
                        results.append(mem)
            except (ValueError, TypeError) as e:
                logger.debug(f"Failed to parse created_at for memory {mem.get('id')}: {e}")
                continue
        
        return results
    
    async def _query_warm_by_age(self, min_days: int) -> List[Dict[str, Any]]:
        """从温层查询指定年龄以上的记忆"""
        return await self._query_by_age_and_level(
            self.warm,
            min_days=min_days,
            level=MemoryLevel.P1
        )
    
    async def _auto_tier_loop(self):
        """自动分层循环"""
        while self._initialized:
            try:
                # 每小时检查一次
                await asyncio.sleep(3600)
                await self.auto_tier()
            except Exception as e:
                logger.error(f"Auto tier error: {e}")
    
    # ===== Memory Enhancer 功能 (代理到热层) =====
    
    async def upgrade_memory_level(self, memory_id: str, new_level: str) -> bool:
        """升级记忆级别"""
        # 优先尝试热层
        if await self.hot.upgrade_memory_level(memory_id, new_level):
            return True
        # 尝试温层
        if hasattr(self.warm, 'upgrade_memory_level'):
            if await self.warm.upgrade_memory_level(memory_id, new_level):
                return True
        return False
    
    async def detect_duplicates(self, threshold: float = 0.9) -> List[str]:
        """检测重复记忆（只在热层检测）"""
        return await self.hot.detect_duplicates(threshold)
    
    async def merge_duplicates(self, keep: str = "newest") -> Dict[str, int]:
        """合并重复记忆"""
        return await self.hot.merge_duplicates(keep)
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """获取详细记忆统计"""
        return await self.get_stats()
