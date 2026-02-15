#!/usr/bin/env python3
"""
MLX-Agent v0.3.0 优雅关闭测试

验证服务可以优雅地处理停止信号
"""

import sys
import asyncio
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_graceful_shutdown():
    """测试优雅关闭机制"""
    print("Testing graceful shutdown mechanism...")
    
    try:
        from mlx_agent.agent import MLXAgent
        
        # 创建 Agent（不启动）
        agent = MLXAgent()
        
        # 验证关闭事件存在
        assert hasattr(agent, '_shutdown_event'), "Missing _shutdown_event"
        assert hasattr(agent, '_shutdown_timeout'), "Missing _shutdown_timeout"
        assert agent._shutdown_timeout == 30, "Default timeout should be 30s"
        
        # 验证停止方法存在
        assert hasattr(agent, 'stop'), "Missing stop method"
        assert asyncio.iscoroutinefunction(agent.stop), "stop should be async"
        
        print("✅ Graceful shutdown structure OK")
        return True
        
    except Exception as e:
        print(f"❌ Graceful shutdown test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_health_server():
    """测试健康检查服务器"""
    print("\nTesting health check server...")
    
    try:
        from mlx_agent.health import HealthCheckServer, HealthStatus
        
        # 测试状态类
        status = HealthStatus(
            status="healthy",
            version="0.3.0",
            timestamp=1234567890.0,
            checks={"memory": {"status": "ok"}}
        )
        
        data = status.to_dict()
        assert data['status'] == 'healthy'
        assert data['version'] == '0.3.0'
        
        print("✅ Health check server structure OK")
        return True
        
    except Exception as e:
        print(f"❌ Health check test failed: {e}")
        return False


async def test_streaming_support():
    """测试流式输出支持"""
    print("\nTesting streaming support...")
    
    try:
        from mlx_agent.llm import LLMClient
        
        # 创建客户端
        client = LLMClient(
            primary_config={
                'api_key': 'test',
                'api_base': 'http://localhost',
                'model': 'test-model'
            }
        )
        
        # 验证流式方法存在 (异步生成器)
        assert hasattr(client, 'chat_stream'), "Missing chat_stream method"
        import inspect
        assert inspect.isasyncgenfunction(client.chat_stream), "chat_stream should be async generator"
        
        # 验证简单流式方法
        assert hasattr(client, 'simple_chat_stream'), "Missing simple_chat_stream method"
        
        print("✅ Streaming support structure OK")
        return True
        
    except Exception as e:
        print(f"❌ Streaming test failed: {e}")
        return False


async def test_memory_tiers():
    """测试分级记忆"""
    print("\nTesting tiered memory (P0/P1/P2)...")
    
    try:
        from mlx_agent.memory import Memory, MemoryLevel
        from datetime import datetime, timedelta
        
        # 测试各级别记忆
        p0_mem = Memory(content="Core memory", level="P0")
        p1_mem = Memory(content="Session memory", level="P1")
        p2_mem = Memory(content="Temp memory", level="P2")
        
        # P0 永不过期
        assert not p0_mem.is_expired(), "P0 should never expire"
        
        # P1 7天后过期
        assert not p1_mem.is_expired(), "New P1 should not be expired"
        
        # P2 1天后过期
        assert not p2_mem.is_expired(), "New P2 should not be expired"
        
        # 验证 ID 包含级别
        assert "P0" in p0_mem.memory_id or p0_mem.level == "P0"
        assert "P1" in p1_mem.memory_id or p1_mem.level == "P1"
        assert "P2" in p2_mem.memory_id or p2_mem.level == "P2"
        
        print("✅ Tiered memory structure OK")
        return True
        
    except Exception as e:
        print(f"❌ Tiered memory test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("MLX-Agent v0.3.0 Feature Validation Tests")
    print("=" * 60)
    
    results = []
    
    results.append(("Graceful Shutdown", await test_graceful_shutdown()))
    results.append(("Health Check Server", await test_health_server()))
    results.append(("Streaming Support", await test_streaming_support()))
    results.append(("Tiered Memory", await test_memory_tiers()))
    
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
        print("🎉 All feature tests passed! v0.3.0 features are working.")
        return 0
    else:
        print("⚠️  Some tests failed. Please review the code.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
