"""
测试延迟导入和优化效果
"""

import sys
import time
from pathlib import Path


def test_lazy_import():
    """测试延迟导入 - 确保启动时不导入重型库"""
    print("Testing lazy imports...")

    # 记录初始模块状态
    heavy_modules = [
        'chromadb',
        'sentence_transformers',
        'duckduckgo_search',
        'playwright',
        'playwright.async_api',
    ]

    modules_before = {mod: mod in sys.modules for mod in heavy_modules}
    print(f"Modules before import: {modules_before}")

    # 导入 MLX-Agent 核心模块
    start_time = time.time()
    from mlx_agent.tools import file, http
    from mlx_agent.memory import base
    import_time = time.time() - start_time

    print(f"Core modules import time: {import_time:.3f}s")

    # 检查重型模块是否被导入
    modules_after = {mod: mod in sys.modules for mod in heavy_modules}
    print(f"Modules after import: {modules_after}")

    # 断言：重型模块不应被导入
    failures = []
    for mod in heavy_modules:
        if modules_after[mod]:
            failures.append(f"Heavy module '{mod}' was imported during startup!")

    if failures:
        print("❌ FAILED:")
        for f in failures:
            print(f"   - {f}")
        return False
    else:
        print("✅ PASSED: No heavy modules imported during startup")
        return True


def test_memory_backends():
    """测试记忆后端"""
    print("\nTesting memory backends...")

    from mlx_agent.memory import MemoryBackend, MemoryEntry, MemoryLevel
    from mlx_agent.memory import ChromaMemoryBackend, SQLiteMemoryBackend

    # 测试基类存在
    assert MemoryBackend is not None
    assert MemoryEntry is not None
    assert MemoryLevel is not None

    # 测试后端类存在
    assert ChromaMemoryBackend is not None
    assert SQLiteMemoryBackend is not None

    # 测试 MemoryEntry 创建
    entry = MemoryEntry(content="test content", level=MemoryLevel.P1)
    assert entry.content == "test content"
    assert entry.level == MemoryLevel.P1
    assert entry.memory_id is not None

    print("✅ PASSED: Memory backends available")
    return True


def test_config_security():
    """测试安全配置"""
    print("\nTesting security config...")

    from mlx_agent.config import Config, SecurityConfig

    # 测试默认安全配置
    config = Config()
    assert config.security is not None
    assert config.security.default_bind == "127.0.0.1"
    assert config.security.workspace_only == True
    assert len(config.security.forbidden_paths) > 0

    # 测试健康检查默认绑定
    assert config.health_check.host == "127.0.0.1"

    print("✅ PASSED: Security config initialized correctly")
    return True


def test_file_tool_security():
    """测试文件工具安全验证"""
    print("\nTesting file tool security...")

    from mlx_agent.tools.file import FileTool

    # 设置 OPENCLAW_WORKSPACE 以确保一致的工作区
    import os
    original_workspace = os.environ.get("OPENCLAW_WORKSPACE")
    os.environ["OPENCLAW_WORKSPACE"] = "/root/.openclaw/workspace"

    try:
        tool = FileTool()

        # 测试路径遍历检测
        assert tool._validate_path("../etc/passwd")[0] == False, "Path traversal should be blocked"
        assert tool._validate_path("/etc/passwd")[0] == False, "System paths should be blocked"
        assert tool._validate_path("~/.ssh/id_rsa")[0] == False, "SSH keys should be blocked"

        # 测试工作区内路径
        workspace = str(tool.workspace_path)
        result = tool._validate_path(workspace)
        assert result[0] == True, f"Workspace should be allowed: {result}"

        # 测试 /tmp 路径
        assert tool._validate_path("/tmp/test.txt")[0] == True, "/tmp should be allowed"

        print("✅ PASSED: File tool security validation works")
        return True
    except AssertionError as e:
        print(f"❌ FAILED: {e}")
        return False
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # 恢复环境变量
        if original_workspace is None:
            os.environ.pop("OPENCLAW_WORKSPACE", None)
        else:
            os.environ["OPENCLAW_WORKSPACE"] = original_workspace


def test_import_time():
    """测试导入时间"""
    print("\nTesting import time...")

    # 使用子进程测试导入时间
    import subprocess

    script = """
import time
start = time.time()
from mlx_agent.memory import create_memory_backend, MemoryEntry, MemoryLevel
from mlx_agent.tools import file, http, search, browser
from mlx_agent.config import Config
elapsed = time.time() - start
print(f"Import time: {elapsed:.3f}s")
exit(0 if elapsed < 2.0 else 1)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent)
    )

    print(f"   {result.stdout.strip()}")

    if result.returncode == 0:
        print("✅ PASSED: Import time under 2 seconds")
        return True
    else:
        print("❌ FAILED: Import time exceeds 2 seconds")
        return False


def main():
    """运行所有测试"""
    print("=" * 60)
    print("MLX-Agent Optimization Tests")
    print("=" * 60)

    tests = [
        ("Lazy Import", test_lazy_import),
        ("Memory Backends", test_memory_backends),
        ("Config Security", test_config_security),
        ("File Tool Security", test_file_tool_security),
        ("Import Time", test_import_time),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ EXCEPTION: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\nTotal: {passed}/{total} tests passed")

    return all(p for _, p in results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
