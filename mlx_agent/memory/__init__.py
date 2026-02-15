"""
记忆系统

统一的记忆后端接口，支持多种存储实现：
- ChromaDB: 高性能向量搜索（推荐用于生产环境）
- SQLite: 轻量级，零额外依赖（适合资源受限环境）
- Hybrid: 混合模式（ChromaDB + SQLite），支持内存不足时自动降级
- Tiered: 三层架构（热/温/冷），优化存储和检索效率

使用方式:
    from mlx_agent.memory import create_memory_backend, MemoryEntry, MemoryLevel
    
    # 创建后端
    backend = await create_memory_backend({
        "provider": "hybrid",  # "chroma", "sqlite", "hybrid", "tiered"
        "hybrid": {
            "chroma": {"path": "./memory/chroma"},
            "sqlite": {"path": "./memory/hybrid.db"},
            "memory_threshold_mb": 500
        }
    })
    
    # 添加记忆
    entry = MemoryEntry(content="重要信息", level=MemoryLevel.P0)
    await backend.add(entry)
    
    # 搜索记忆
    results = await backend.search("查询", limit=5)
"""

from .base import MemoryBackend, MemoryEntry, MemoryLevel
from .chroma import ChromaMemoryBackend
from .sqlite import SQLiteMemoryBackend
from .hybrid import HybridMemoryBackend, HybridConfig, create_hybrid_backend
from .tiered import TieredMemoryBackend

# 向后兼容：Memory 别名
Memory = MemoryEntry

# 向后兼容：MemorySystem 别名
# 默认使用 ChromaDB 以保持向后兼容
MemorySystem = ChromaMemoryBackend


async def create_memory_backend(config: dict) -> MemoryBackend:
    """创建记忆后端
    
    Args:
        config: 配置字典
            - provider: "chroma", "sqlite", "hybrid" 或 "tiered" (默认: chroma)
            - chroma: ChromaDB 配置
            - sqlite: SQLite 配置
            - hybrid: Hybrid 配置 (包含 chroma 和 sqlite 子配置)
            - tiered: 三层架构配置 (热/温/冷)
    
    Returns:
        配置好的记忆后端实例
    
    Example:
        >>> backend = await create_memory_backend({
        ...     "provider": "hybrid",
        ...     "hybrid": {
        ...         "chroma": {"path": "./memory/chroma"},
        ...         "sqlite": {"path": "./memory/hybrid.db"},
        ...         "memory_threshold_mb": 500
        ...     }
        ... })
        
        >>> backend = await create_memory_backend({
        ...     "provider": "tiered",
        ...     "tiered": {
        ...         "hot_path": "./memory/hot",
        ...         "warm_path": "./memory/warm.db",
        ...         "cold_path": "./memory/cold",
        ...         "embedding_provider": "local",
        ...         "auto_tiering": True
        ...     }
        ... })
    """
    provider = config.get("provider", "chroma").lower()
    
    if provider == "hybrid":
        backend = await create_hybrid_backend(config.get("hybrid"))
    elif provider == "tiered":
        from .tiered import TieredMemoryBackend
        tiered_config = config.get("tiered", {})
        backend = TieredMemoryBackend(**tiered_config)
    elif provider == "sqlite":
        sqlite_config = config.get("sqlite", {})
        backend = SQLiteMemoryBackend(**sqlite_config)
    elif provider == "chroma":
        chroma_config = config.get("chroma", {})
        backend = ChromaMemoryBackend(**chroma_config)
    else:
        raise ValueError(f"Unknown memory provider: {provider}. Use 'chroma', 'sqlite', 'hybrid', or 'tiered'")
    
    # 自动初始化
    await backend.initialize()
    
    return backend


__all__ = [
    # 基类
    "MemoryBackend",
    "MemoryEntry",
    "MemoryLevel",
    # 后端实现
    "ChromaMemoryBackend",
    "SQLiteMemoryBackend",
    "HybridMemoryBackend",
    "HybridConfig",
    "TieredMemoryBackend",
    # 工厂函数
    "create_memory_backend",
    "create_hybrid_backend",
    # 向后兼容
    "Memory",
    "MemorySystem",
]
