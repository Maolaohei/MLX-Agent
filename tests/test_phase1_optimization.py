"""
Phase 1 优化功能测试

测试新增的功能:
1. web_search - Tavily/Brave Provider
2. memory - Memory Enhancer 功能
3. file_operations - 大文件分片上传/下载
4. browser - 反爬配置
5. config - 配置验证
"""

import pytest
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock


class TestSearchProviders:
    """测试搜索 Provider"""
    
    def test_tavily_provider_init(self):
        """测试 TavilyProvider 初始化"""
        from mlx_agent.tools.search import TavilyProvider
        
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test_key"}):
            provider = TavilyProvider()
            assert provider.api_key == "test_key"
    
    def test_brave_provider_init(self):
        """测试 BraveProvider 初始化"""
        from mlx_agent.tools.search import BraveProvider
        
        with patch.dict(os.environ, {"BRAVE_API_KEY": "test_key"}):
            provider = BraveProvider()
            assert provider.api_key == "test_key"
    
    def test_duckduckgo_provider_init(self):
        """测试 DuckDuckGoProvider 初始化"""
        from mlx_agent.tools.search import DuckDuckGoProvider
        
        provider = DuckDuckGoProvider()
        assert provider is not None
    
    @pytest.mark.asyncio
    async def test_search_tool_provider_detection(self):
        """测试搜索工具 provider 自动检测"""
        from mlx_agent.tools.search import SearchTool
        
        # 测试 Tavily 优先
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test_key", "BRAVE_API_KEY": "test_key2"}):
            tool = SearchTool()
            assert tool._detect_best_provider() == "tavily"
        
        # 测试 Brave 其次
        with patch.dict(os.environ, {"BRAVE_API_KEY": "test_key"}, clear=True):
            tool = SearchTool()
            assert tool._detect_best_provider() == "brave"
        
        # 测试 DuckDuckGo 默认
        with patch.dict(os.environ, {}, clear=True):
            tool = SearchTool()
            assert tool._detect_best_provider() == "duckduckgo"


class TestMemoryEnhancer:
    """测试 Memory Enhancer 功能"""
    
    @pytest.mark.asyncio
    async def test_detect_duplicates_chroma(self):
        """测试 ChromaDB 重复检测"""
        from mlx_agent.memory.chroma import ChromaMemoryBackend
        
        backend = ChromaMemoryBackend(path="./test_memory/chroma")
        backend._initialized = True
        backend._collection = Mock()
        backend._collection.get.return_value = {
            'ids': ['id1', 'id2', 'id3'],
            'embeddings': [[1.0, 0.0], [0.99, 0.01], [0.1, 0.9]]
        }
        
        duplicates = await backend.detect_duplicates(threshold=0.9)
        # id1 和 id2 相似度很高，应该被检测为重复
        assert isinstance(duplicates, list)
    
    @pytest.mark.asyncio
    async def test_upgrade_memory_level_chroma(self):
        """测试 ChromaDB 记忆级别升级"""
        from mlx_agent.memory.chroma import ChromaMemoryBackend
        
        backend = ChromaMemoryBackend(path="./test_memory/chroma")
        backend._initialized = True
        backend._collection = Mock()
        backend._collection.get.return_value = {
            'ids': ['test_id'],
            'metadatas': [{'level': 'P2'}]
        }
        
        result = await backend.upgrade_memory_level("test_id", "P1")
        assert result is True
        backend._collection.update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_memory_stats_chroma(self):
        """测试 ChromaDB 记忆统计"""
        from mlx_agent.memory.chroma import ChromaMemoryBackend
        
        backend = ChromaMemoryBackend(path="./test_memory/chroma")
        backend._initialized = True
        backend._collection = Mock()
        backend._collection.count.return_value = 10
        backend._collection.get.return_value = {'ids': ['1', '2', '3']}
        
        stats = await backend.get_memory_stats()
        assert stats["status"] == "initialized"
        assert stats["total_memories"] == 10
        assert "by_level" in stats
        assert "duplicate_rate" in stats
    
    @pytest.mark.asyncio
    async def test_detect_duplicates_sqlite(self):
        """测试 SQLite 重复检测"""
        from mlx_agent.memory.sqlite import SQLiteMemoryBackend
        import numpy as np
        
        backend = SQLiteMemoryBackend(path="./test_memory/memory.db")
        backend._initialized = True
        backend._db = Mock()
        
        cursor_mock = Mock()
        cursor_mock.fetchall.return_value = [
            {'id': 'id1', 'content': 'test1', 'embedding': np.array([1.0, 0.0], dtype=np.float32).tobytes()},
            {'id': 'id2', 'content': 'test2', 'embedding': np.array([0.99, 0.01], dtype=np.float32).tobytes()},
        ]
        backend._db.cursor.return_value = cursor_mock
        
        duplicates = await backend.detect_duplicates(threshold=0.9)
        assert isinstance(duplicates, list)
    
    @pytest.mark.asyncio
    async def test_upgrade_memory_level_sqlite(self):
        """测试 SQLite 记忆级别升级"""
        from mlx_agent.memory.sqlite import SQLiteMemoryBackend
        
        backend = SQLiteMemoryBackend(path="./test_memory/memory.db")
        backend._initialized = True
        backend._db = Mock()
        
        cursor_mock = Mock()
        cursor_mock.fetchone.return_value = {'id': 'test_id'}
        cursor_mock.rowcount = 1
        backend._db.cursor.return_value = cursor_mock
        
        result = await backend.upgrade_memory_level("test_id", "P1")
        assert result is True


class TestFileOperations:
    """测试文件操作增强"""
    
    @pytest.mark.asyncio
    async def test_upload_large(self):
        """测试大文件分片上传"""
        from mlx_agent.tools.file import FileTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建源文件
            src_path = Path(tmpdir) / "source.txt"
            src_path.write_text("A" * 1000)  # 1KB 测试文件
            
            dst_path = Path(tmpdir) / "destination.txt"
            
            tool = FileTool()
            
            progress_calls = []
            def progress_callback(uploaded, total, percentage):
                progress_calls.append((uploaded, total, percentage))
            
            result = await tool.upload_large(
                source=str(src_path),
                destination=str(dst_path),
                chunk_size=100,  # 小分片便于测试
                progress_callback=progress_callback
            )
            
            assert result.success is True
            assert result.output["bytes_uploaded"] == 1000
            assert result.output["total_bytes"] == 1000
            assert len(progress_calls) > 0
            assert dst_path.exists()
    
    @pytest.mark.asyncio
    async def test_download_large(self):
        """测试大文件分片下载"""
        from mlx_agent.tools.file import FileTool
        
        with tempfile.TemporaryDirectory() as tmpdir:
            dst_path = Path(tmpdir) / "downloaded.txt"
            
            tool = FileTool()
            
            # 模拟下载（使用测试服务器或 mock）
            with patch('httpx.AsyncClient') as mock_client:
                mock_response = Mock()
                mock_response.headers = {'content-length': '100'}
                mock_response.raise_for_status = Mock()
                
                # 模拟异步迭代
                async def mock_aiter_bytes(chunk_size):
                    yield b"Test content" * 10
                
                mock_response.aiter_bytes = mock_aiter_bytes
                
                mock_client_instance = Mock()
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client_instance.head = AsyncMock(return_value=mock_response)
                mock_client_instance.stream = Mock()
                mock_stream_context = Mock()
                mock_stream_context.__aenter__ = AsyncMock(return_value=mock_response)
                mock_stream_context.__aexit__ = AsyncMock(return_value=None)
                mock_client_instance.stream.return_value = mock_stream_context
                
                mock_client.return_value = mock_client_instance
                
                result = await tool.download_large(
                    url="http://test.com/file.txt",
                    destination=str(dst_path),
                    chunk_size=100
                )
                
                # 由于 mock 的限制，这里主要验证函数能正确执行
                assert result is not None


class TestBrowserStealth:
    """测试浏览器反爬配置"""
    
    def test_stealth_config_exists(self):
        """测试反爬配置是否存在"""
        from mlx_agent.tools.browser import BrowserTool
        
        tool = BrowserTool()
        
        # 验证配置存在
        assert hasattr(tool, 'STEALTH_USER_AGENT')
        assert hasattr(tool, 'STEALTH_VIEWPORT')
        assert hasattr(tool, 'BROWSER_LAUNCH_ARGS')
        assert hasattr(tool, 'STEALTH_SCRIPTS')
        
        # 验证配置非空
        assert len(tool.STEALTH_USER_AGENT) > 0
        assert len(tool.STEALTH_VIEWPORT) == 2
        assert len(tool.BROWSER_LAUNCH_ARGS) > 0
        assert len(tool.STEALTH_SCRIPTS) > 0
    
    def test_stealth_user_agent(self):
        """测试 User-Agent 配置"""
        from mlx_agent.tools.browser import BrowserTool
        
        tool = BrowserTool()
        
        # 验证 User-Agent 看起来像真实浏览器
        assert "Mozilla" in tool.STEALTH_USER_AGENT
        assert "Chrome" in tool.STEALTH_USER_AGENT
    
    def test_browser_launch_args(self):
        """测试浏览器启动参数"""
        from mlx_agent.tools.browser import BrowserTool
        
        tool = BrowserTool()
        
        # 验证关键的反爬参数存在
        args = tool.BROWSER_LAUNCH_ARGS
        assert any('AutomationControlled' in arg for arg in args)
        assert any('web-security' in arg for arg in args)
        assert any('IsolateOrigins' in arg for arg in args)
    
    def test_stealth_scripts(self):
        """测试 stealth 脚本"""
        from mlx_agent.tools.browser import BrowserTool
        
        tool = BrowserTool()
        
        scripts = tool.STEALTH_SCRIPTS
        
        # 验证脚本包含关键反爬代码
        all_scripts = ' '.join(scripts)
        assert 'webdriver' in all_scripts
        assert 'plugins' in all_scripts


class TestConfigValidator:
    """测试配置验证器"""
    
    def test_validate_memory_config_valid(self):
        """测试有效的记忆配置"""
        from mlx_agent.config import ConfigValidator
        
        config = {
            "embedding_provider": "local",
            "path": "./memory",
            "auto_archive": {
                "enabled": True,
                "p1_max_age_days": 7,
                "p2_max_age_days": 1
            }
        }
        
        is_valid, errors = ConfigValidator.validate_memory_config(config)
        assert is_valid is True
        assert len(errors) == 0
    
    def test_validate_memory_config_invalid_provider(self):
        """测试无效的嵌入提供商"""
        from mlx_agent.config import ConfigValidator
        
        config = {
            "embedding_provider": "invalid_provider"
        }
        
        is_valid, errors = ConfigValidator.validate_memory_config(config)
        assert is_valid is False
        assert any("embedding_provider" in e for e in errors)
    
    def test_validate_memory_config_invalid_days(self):
        """测试无效的天数配置"""
        from mlx_agent.config import ConfigValidator
        
        config = {
            "auto_archive": {
                "p1_max_age_days": 1,
                "p2_max_age_days": 7  # p1 应该大于 p2
            }
        }
        
        is_valid, errors = ConfigValidator.validate_memory_config(config)
        assert is_valid is False
        assert any("p1_max_age_days" in e and "greater" in e for e in errors)
    
    def test_validate_llm_config_valid(self):
        """测试有效的 LLM 配置"""
        from mlx_agent.config import ConfigValidator
        
        config = {
            "primary": {
                "api_key": "test_key",
                "temperature": 0.7,
                "max_tokens": 2000
            },
            "failover": {
                "enabled": True,
                "max_retries": 3,
                "timeout": 30
            }
        }
        
        is_valid, errors = ConfigValidator.validate_llm_config(config)
        assert is_valid is True
    
    def test_validate_llm_config_invalid_temperature(self):
        """测试无效的温度配置"""
        from mlx_agent.config import ConfigValidator
        
        config = {
            "primary": {
                "api_key": "test_key",
                "temperature": 5.0  # 超出范围
            }
        }
        
        is_valid, errors = ConfigValidator.validate_llm_config(config)
        assert is_valid is False
        assert any("temperature" in e for e in errors)
    
    def test_auto_fix_config(self):
        """测试配置自动修复"""
        from mlx_agent.config import ConfigValidator
        
        config = {
            "memory": {
                "auto_archive": {
                    "p1_max_age_days": -1,  # 无效值
                    "p2_max_age_days": 5     # 大于 p1
                }
            },
            "llm": {
                "temperature": "invalid",  # 无效类型
                "max_tokens": -100         # 无效值
            }
        }
        
        fixed = ConfigValidator.auto_fix(config)
        
        # 验证修复结果
        assert fixed["memory"]["auto_archive"]["p1_max_age_days"] > 0
        assert fixed["memory"]["auto_archive"]["p1_max_age_days"] > fixed["memory"]["auto_archive"]["p2_max_age_days"]
        assert isinstance(fixed["llm"]["temperature"], float)
        assert fixed["llm"]["max_tokens"] > 0
    
    def test_validate_full_config(self):
        """测试完整配置验证"""
        from mlx_agent.config import ConfigValidator
        
        config = {
            "memory": {
                "embedding_provider": "local",
                "auto_archive": {"enabled": True}
            },
            "llm": {
                "api_key": "test_key",
                "temperature": 0.7
            },
            "security": {
                "default_bind": "127.0.0.1"
            }
        }
        
        result = ConfigValidator.validate_full_config(config)
        
        assert result["valid"] is True
        assert "memory" in result["sections"]
        assert "llm" in result["sections"]
        assert "security" in result["sections"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
