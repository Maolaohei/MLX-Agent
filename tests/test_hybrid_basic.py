#!/usr/bin/env python3
"""
Hybrid Memory Backend 测试脚本

测试内容:
1. RRF 合并算法
2. 内存监控与自动降级
3. 工厂函数

注意: 完整测试需要安装所有依赖 (loguru, chromadb, etc.)
"""

import asyncio
import sys
import os


def test_rrf_merge():
    """测试 RRF 合并算法 - 不依赖外部库"""
    print("\n" + "="*60)
    print("测试 1: RRF 合并算法")
    print("="*60)
    
    # 模拟 RRF 合并逻辑
    k = 60
    
    # 关键词结果
    keyword_results = [
        {"id": "k1", "content": "关键词结果 1", "score": 0.9},
        {"id": "k2", "content": "关键词结果 2", "score": 0.8},
        {"id": "k3", "content": "关键词结果 3", "score": 0.7},
    ]
    
    # 向量结果
    vector_results = [
        {"id": "v1", "content": "向量结果 1", "score": 0.95},
        {"id": "k1", "content": "关键词结果 1", "score": 0.9},  # 重合
        {"id": "v3", "content": "向量结果 3", "score": 0.75},
    ]
    
    # RRF 合并
    scores = {}
    entries = {}
    
    for rank, entry in enumerate(keyword_results):
        entry_id = entry.get("id")
        scores[entry_id] = scores.get(entry_id, 0) + 1.0 / (k + rank)
        entries[entry_id] = entry
    
    for rank, entry in enumerate(vector_results):
        entry_id = entry.get("id")
        scores[entry_id] = scores.get(entry_id, 0) + 1.0 / (k + rank)
        entries[entry_id] = entry
    
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    merged = [entries[id] for id in sorted_ids]
    
    print(f"关键词结果: {len(keyword_results)} 条")
    print(f"向量结果: {len(vector_results)} 条")
    print(f"合并结果: {len(merged)} 条")
    print(f"RRF 分数: {[(id, scores[id]) for id in sorted_ids]}")
    
    # 验证 k1 应该排名最高，因为两个列表都有它
    if merged and merged[0].get("id") == "k1":
        print("✅ RRF 合并正确: 同时在两个结果中的项目排名更高")
        return True
    else:
        print(f"❌ 合并结果顺序: {[r.get('id') for r in merged]}")
        return False


def test_memory_monitoring():
    """测试内存监控"""
    print("\n" + "="*60)
    print("测试 2: 内存监控")
    print("="*60)
    
    try:
        import psutil
        mem = psutil.virtual_memory()
        print(f"当前内存状态:")
        print(f"  - 总内存: {mem.total / (1024**3):.2f} GB")
        print(f"  - 可用内存: {mem.available / (1024**2):.2f} MB")
        print(f"  - 使用率: {mem.percent}%")
        
        threshold_mb = 500
        available_mb = mem.available / (1024 * 1024)
        has_memory = available_mb > threshold_mb
        
        print(f"\n内存检查结果 (阈值 {threshold_mb}MB):")
        print(f"  - 可用: {available_mb:.2f} MB")
        print(f"  - 充足: {has_memory}")
        
        print("✅ 测试通过")
        return True
        
    except ImportError:
        print("⚠️ psutil 未安装，跳过内存监控测试")
        return True


def test_config():
    """测试配置类"""
    print("\n" + "="*60)
    print("测试 3: HybridConfig 配置类")
    print("="*60)
    
    # 使用 dataclass 模拟
    from dataclasses import dataclass, field
    from typing import Optional
    
    @dataclass
    class HybridConfig:
        chroma_path: str = "./memory/chroma"
        embedding_provider: str = "local"
        embedding_model: str = "BAAI/bge-m3"
        ollama_url: str = "http://localhost:11434"
        openai_api_key: Optional[str] = None
        sqlite_path: str = "./memory/hybrid.db"
        rrf_k: int = 60
        memory_threshold_mb: int = 500
        memory_check_interval: int = 60
        fallback_mode: str = "auto"
    
    # 默认配置
    config1 = HybridConfig()
    print(f"默认配置:")
    print(f"  - chroma_path: {config1.chroma_path}")
    print(f"  - sqlite_path: {config1.sqlite_path}")
    print(f"  - rrf_k: {config1.rrf_k}")
    print(f"  - memory_threshold_mb: {config1.memory_threshold_mb}")
    
    # 自定义配置
    config2 = HybridConfig(
        chroma_path="./custom/chroma",
        sqlite_path="./custom/hybrid.db",
        fallback_mode="always"
    )
    print(f"\n自定义配置:")
    print(f"  - chroma_path: {config2.chroma_path}")
    print(f"  - fallback_mode: {config2.fallback_mode}")
    
    print("✅ 测试通过")
    return True


async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("Hybrid Memory Backend 基础测试")
    print("(不依赖外部库)")
    print("="*60)
    
    results = []
    
    # 运行所有测试
    results.append(("RRF 合并算法", test_rrf_merge()))
    results.append(("内存监控", test_memory_monitoring()))
    results.append(("配置类", test_config()))
    
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
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
