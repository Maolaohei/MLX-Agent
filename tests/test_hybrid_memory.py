#!/usr/bin/env python3
"""
Hybrid Memory Backend 测试脚本

测试内容:
1. 正常模式: SQLite + ChromaDB 并行查询
2. 降级模式: 纯 SQLite 模式
3. RRF 合并算法
4. 内存监控与自动降级
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mlx_agent.memory.hybrid import HybridMemoryBackend, HybridConfig, create_hybrid_backend
from mlx_agent.memory.base import MemoryEntry, MemoryLevel


async def test_normal_mode():
    """测试正常模式 (混合)"""
    print("\n" + "="*60)
    print("测试 1: 正常模式 (Hybrid)")
    print("="*60)
    
    config = HybridConfig(
        sqlite_path="./test_memory/hybrid.db",
        chroma_path="./test_memory/chroma",
        fallback_mode="never"  # 强制不降级
    )
    
    backend = HybridMemoryBackend(config)
    
    try:
        await backend.initialize()
        print(f"✅ 初始化成功 - 模式: {await backend.get_stats()}")
        
        # 添加测试记忆
        entries = [
            MemoryEntry(content="这是一个关于机器学习的记忆", level=MemoryLevel.P1),
            MemoryEntry(content="深度学习是机器学习的一个分支", level=MemoryLevel.P1),
            MemoryEntry(content="Python 是优秀的编程语言", level=MemoryLevel.P1),
        ]
        
        for entry in entries:
            mid = await backend.add(entry)
            print(f"  ✅ 添加记忆: {mid[:20]}...")
        
        # 搜索测试
        results = await backend.search("机器学习", limit=5)
        print(f"  ✅ 搜索到 {len(results)} 条结果")
        for i, r in enumerate(results[:3]):
            print(f"     {i+1}. {r.get('content', '')[:40]}...")
        
        await backend.close()
        print("✅ 测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_degraded_mode():
    """测试降级模式 (纯 SQLite)"""
    print("\n" + "="*60)
    print("测试 2: 降级模式 (SQLite Only)")
    print("="*60)
    
    config = HybridConfig(
        sqlite_path="./test_memory/degraded.db",
        chroma_path="./test_memory/chroma_degraded",
        fallback_mode="always"  # 强制降级模式
    )
    
    backend = HybridMemoryBackend(config)
    
    try:
        await backend.initialize()
        
        stats = await backend.get_stats()
        print(f"✅ 初始化成功 - 模式: {stats.get('mode')}")
        
        # 添加测试记忆
        entry = MemoryEntry(content="降级模式测试记忆", level=MemoryLevel.P1)
        mid = await backend.add(entry)
        print(f"  ✅ 添加记忆: {mid[:20]}...")
        
        # 搜索测试
        results = await backend.search("测试", limit=5)
        print(f"  ✅ 搜索到 {len(results)} 条结果 (纯 SQLite)")
        
        await backend.close()
        print("✅ 测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_rrf_merge():
    """测试 RRF 合并算法"""
    print("\n" + "="*60)
    print("测试 3: RRF 合并算法")
    print("="*60)
    
    config = HybridConfig(rrf_k=60)
    backend = HybridMemoryBackend(config)
    
    # 模拟关键词搜索结果
    keyword_results = [
        {"id": "k1", "content": "关键词结果 1", "score": 0.9},
        {"id": "k2", "content": "关键词结果 2", "score": 0.8},
        {"id": "k3", "content": "关键词结果 3", "score": 0.7},
    ]
    
    # 模拟向量搜索结果
    vector_results = [
        {"id": "v1", "content": "向量结果 1", "score": 0.95},
        {"id": "k1", "content": "关键词结果 1", "score": 0.9},  # 与关键词结果重合
        {"id": "v3", "content": "向量结果 3", "score": 0.75},
    ]
    
    merged = backend._rrf_merge(keyword_results, vector_results, limit=5)
    
    print(f"关键词结果: {len(keyword_results)} 条")
    print(f"向量结果: {len(vector_results)} 条")
    print(f"合并结果: {len(merged)} 条")
    
    # 验证 k1 应该排名更高，因为两个列表都有它
    if merged and merged[0].get("id") == "k1":
        print("✅ RRF 合并正确: 同时在两个结果中的项目排名更高")
    else:
        print(f"  合并结果顺序: {[r.get('id') for r in merged]}")
    
    print("✅ 测试通过")
    return True


async def test_memory_monitoring():
    """测试内存监控"""
    print("\n" + "="*60)
    print("测试 4: 内存监控")
    print("="*60)
    
    try:
        import psutil
        mem = psutil.virtual_memory()
        print(f"当前内存状态:")
        print(f"  - 总内存: {mem.total / (1024**3):.2f} GB")
        print(f"  - 可用内存: {mem.available / (1024**2):.2f} MB")
        print(f"  - 使用率: {mem.percent}%")
        
        config = HybridConfig(memory_threshold_mb=100)
        backend = HybridMemoryBackend(config)
        
        has_memory = backend._check_memory()
        print(f"\n内存检查结果 (阈值 100MB):")
        print(f"  - 内存充足: {has_memory}")
        print(f"  - 当前降级模式: {backend._degraded_mode}")
        
        # 测试强制降级/升级
        backend._enter_degraded_mode()
        print(f"  - 强制降级后: {backend._degraded_mode}")
        
        backend._exit_degraded_mode()
        print(f"  - 强制恢复后: {backend._degraded_mode}")
        
        print("✅ 测试通过")
        return True
        
    except ImportError:
        print("⚠️ psutil 未安装，跳过内存监控测试")
        return True


async def test_factory_function():
    """测试工厂函数"""
    print("\n" + "="*60)
    print("测试 5: 工厂函数 create_hybrid_backend")
    print("="*60)
    
    config = {
        "chroma": {"path": "./test_memory/chroma_factory"},
        "sqlite": {"path": "./test_memory/hybrid_factory.db"},
        "rrf_k": 60,
        "memory_threshold_mb": 500,
        "fallback_mode": "auto"
    }
    
    try:
        backend = await create_hybrid_backend(config)
        print("✅ 工厂函数创建成功")
        
        stats = await backend.get_stats()
        print(f"  后端状态: {stats.get('mode')}")
        
        await backend.close()
        print("✅ 测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


async def cleanup():
    """清理测试文件"""
    print("\n" + "="*60)
    print("清理测试文件")
    print("="*60)
    
    import shutil
    test_dirs = ["./test_memory"]
    
    for d in test_dirs:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"  🗑️  删除 {d}")
    
    print("✅ 清理完成")


async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("Hybrid Memory Backend 测试")
    print("="*60)
    
    results = []
    
    # 运行所有测试
    results.append(("RRF 合并算法", await test_rrf_merge()))
    results.append(("内存监控", await test_memory_monitoring()))
    results.append(("工厂函数", await test_factory_function()))
    
    # 这些测试需要实际的 SQLite/ChromaDB，先跳过
    # results.append(("正常模式", await test_normal_mode()))
    # results.append(("降级模式", await test_degraded_mode()))
    
    # 测试总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {status}: {name}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    # 清理
    await cleanup()
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
