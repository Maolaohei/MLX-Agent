#!/usr/bin/env python3
"""
MLX-Agent v0.3.0 代码结构验证测试

验证所有核心组件是否正确加载
"""

import sys
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """测试所有模块是否可以导入"""
    print("Testing imports...")
    
    try:
        from mlx_agent.config import Config, MemoryConfig, HealthCheckConfig
        print("✅ Config module OK")
    except Exception as e:
        print(f"❌ Config module failed: {e}")
        return False
    
    try:
        from mlx_agent.health import HealthCheckServer, HealthStatus
        print("✅ Health module OK")
    except Exception as e:
        print(f"❌ Health module failed: {e}")
        return False
    
    try:
        from mlx_agent.llm import LLMClient
        print("✅ LLM module OK")
    except Exception as e:
        print(f"❌ LLM module failed: {e}")
        return False
    
    try:
        from mlx_agent.memory import Memory, ChromaMemorySystem
        print("✅ Memory module OK")
    except Exception as e:
        print(f"❌ Memory module failed: {e}")
        return False
    
    try:
        from mlx_agent.tasks import Task, TaskQueue, TaskWorker, TaskExecutor
        print("✅ Tasks module OK")
    except Exception as e:
        print(f"❌ Tasks module failed: {e}")
        return False
    
    return True

def test_config():
    """测试配置加载"""
    print("\nTesting config...")
    
    try:
        from mlx_agent.config import Config
        
        # 测试默认配置
        config = Config()
        assert config.version == "0.3.0", f"Expected version 0.3.0, got {config.version}"
        assert hasattr(config, 'health_check'), "Missing health_check config"
        assert hasattr(config.memory, 'embedding_provider'), "Missing embedding_provider config"
        
        print("✅ Config validation OK")
        return True
    except Exception as e:
        print(f"❌ Config validation failed: {e}")
        return False

def test_memory_system():
    """测试记忆系统结构"""
    print("\nTesting memory system...")
    
    try:
        from mlx_agent.memory import Memory, ChromaMemorySystem
        
        # 测试 Memory 类
        mem = Memory(content="Test content", level="P1")
        assert mem.level == "P1"
        assert mem.content == "Test content"
        assert mem.memory_id is not None
        
        # 测试过期检查
        assert not mem.is_expired()  # 新创建的不应过期
        
        print("✅ Memory system structure OK")
        return True
    except Exception as e:
        print(f"❌ Memory system test failed: {e}")
        return False

def test_llm_client():
    """测试 LLM 客户端结构"""
    print("\nTesting LLM client...")
    
    try:
        from mlx_agent.llm import LLMClient
        
        # 测试客户端初始化
        client = LLMClient(
            primary_config={
                'api_key': 'test',
                'api_base': 'http://localhost',
                'model': 'test-model'
            }
        )
        
        assert client.get_current_model() == 'test-model'
        
        print("✅ LLM client structure OK")
        return True
    except Exception as e:
        print(f"❌ LLM client test failed: {e}")
        return False

def test_health_server():
    """测试健康检查服务器结构"""
    print("\nTesting health server...")
    
    try:
        from mlx_agent.health import HealthCheckServer, HealthStatus
        
        # 测试状态类
        status = HealthStatus(
            status="healthy",
            version="0.3.0",
            timestamp=1234567890.0,
            checks={}
        )
        
        assert status.status == "healthy"
        
        print("✅ Health server structure OK")
        return True
    except Exception as e:
        print(f"❌ Health server test failed: {e}")
        return False

def main():
    """运行所有测试"""
    print("=" * 60)
    print("MLX-Agent v0.3.0 Code Structure Validation")
    print("=" * 60)
    
    results = []
    
    results.append(("Imports", test_imports()))
    results.append(("Config", test_config()))
    results.append(("Memory System", test_memory_system()))
    results.append(("LLM Client", test_llm_client()))
    results.append(("Health Server", test_health_server()))
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:.<40} {status}")
    
    print("=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! v0.3.0 code structure is valid.")
        return 0
    else:
        print("⚠️  Some tests failed. Please review the code.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
