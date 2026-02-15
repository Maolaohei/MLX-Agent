"""
搜索工具 - 延迟导入版本

支持多种搜索 provider:
- Tavily (推荐)
- Brave
- DuckDuckGo (免费)
"""

import os
from typing import List, Optional, Any, Dict
import asyncio
from abc import ABC, abstractmethod

from loguru import logger

from .base import BaseTool, ToolCategory, ToolParameter, ToolResult, register_tool


class SearchProvider(ABC):
    """搜索 Provider 抽象基类"""
    
    @abstractmethod
    async def search(self, query: str, num: int = 5) -> List[Dict]:
        """执行搜索，返回格式化的结果列表"""
        pass


class TavilyProvider(SearchProvider):
    """Tavily 搜索 provider - 高质量 AI 搜索"""
    
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY")
    
    async def search(self, query: str, num: int = 5) -> List[Dict]:
        """Tavily API 搜索实现"""
        import httpx
        
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY not set")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "max_results": num,
                    "include_answer": True
                }
            )
            response.raise_for_status()
            data = response.json()
        
        results = []
        for result in data.get("results", []):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "snippet": result.get("content", "")[:300]
            })
        
        return {
            "query": query,
            "answer": data.get("answer", ""),
            "results": results
        }


class BraveProvider(SearchProvider):
    """Brave 搜索 provider"""
    
    def __init__(self):
        self.api_key = os.getenv("BRAVE_API_KEY")
    
    async def search(self, query: str, num: int = 5) -> List[Dict]:
        """Brave API 搜索实现"""
        import httpx
        
        if not self.api_key:
            raise ValueError("BRAVE_API_KEY not set")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": self.api_key},
                params={
                    "q": query,
                    "count": num,
                    "offset": 0
                }
            )
            response.raise_for_status()
            data = response.json()
        
        results = []
        for result in data.get("web", {}).get("results", []):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "snippet": result.get("description", "")
            })
        
        return {
            "query": query,
            "results": results
        }


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo 搜索 provider - 免费"""
    
    async def search(self, query: str, num: int = 5) -> List[Dict]:
        """DuckDuckGo 搜索实现"""
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            raise ImportError("duckduckgo_search not installed. Run: pip install duckduckgo-search")
        
        loop = asyncio.get_event_loop()
        
        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=num))
        
        results = await loop.run_in_executor(None, _search)
        
        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")[:300]
            })
        
        return {
            "query": query,
            "results": formatted
        }


@register_tool
class SearchTool(BaseTool):
    """Web 搜索工具 - 延迟导入版本"""

    name = "web_search"
    description = "搜索互联网获取最新信息。适用于查找事实、新闻、文档等。"
    category = ToolCategory.SEARCH

    DEFAULT_PROVIDER = "duckduckgo"

    def __init__(self):
        super().__init__()
        self._default_provider = None
        self._providers = {
            "duckduckgo": DuckDuckGoProvider(),
            "tavily": TavilyProvider(),
            "brave": BraveProvider()
        }

    @property
    def default_provider(self) -> str:
        """延迟检测默认 provider"""
        if self._default_provider is None:
            self._default_provider = self._detect_best_provider()
        return self._default_provider

    def _detect_best_provider(self) -> str:
        """自动检测最佳搜索 provider
        
        优先级: tavily > brave > duckduckgo
        """
        if os.getenv("TAVILY_API_KEY"):
            return "tavily"
        elif os.getenv("BRAVE_API_KEY"):
            return "brave"
        return self.DEFAULT_PROVIDER

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                description="搜索关键词",
                type="string",
                required=True
            ),
            ToolParameter(
                name="num",
                description="返回结果数量 (1-10)",
                type="integer",
                required=False,
                default=5
            ),
            ToolParameter(
                name="provider",
                description="搜索 provider (tavily/brave/duckduckgo/auto)",
                type="string",
                required=False,
                default="auto"
            )
        ]

    async def execute(self, **params) -> ToolResult:
        query = params.get("query", "")
        num = min(max(params.get("num", 5), 1), 10)
        provider_name = params.get("provider", "auto")

        if provider_name == "auto":
            provider_name = self.default_provider

        # 检查 provider 是否有效
        if provider_name not in self._providers:
            return ToolResult(
                success=False,
                output=None,
                error=f"Unknown provider: {provider_name}. Available: {list(self._providers.keys())}"
            )

        provider = self._providers[provider_name]

        try:
            result = await provider.search(query, num)
            return ToolResult(success=True, output=result)
        except ValueError as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Configuration error: {str(e)}"
            )
        except ImportError as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Missing dependency: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Search failed with {provider_name}: {e}")
            return ToolResult(
                success=False,
                output=None,
                error=f"Search failed: {str(e)}"
            )


@register_tool
class FetchTool(BaseTool):
    """网页抓取工具 - 延迟导入版本"""

    name = "fetch_webpage"
    description = "抓取网页内容并提取正文"
    category = ToolCategory.SEARCH

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="url",
                description="要抓取的网页 URL",
                type="string",
                required=True
            ),
            ToolParameter(
                name="extract_text",
                description="是否提取纯文本 (否则返回 HTML)",
                type="boolean",
                required=False,
                default=True
            )
        ]

    async def execute(self, **params) -> ToolResult:
        url = params.get("url", "")
        extract_text = params.get("extract_text", True)

        try:
            import httpx  # 延迟导入
            from readability import Document  # 延迟导入

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                html = response.text

            if extract_text:
                doc = Document(html)
                title = doc.title()
                text = doc.summary()

                # 简单清理 HTML 标签
                import re  # 延迟导入
                text = re.sub(r'<[^>]+>', '', text)
                text = re.sub(r'\n\s*\n', '\n\n', text)

                return ToolResult(
                    success=True,
                    output={
                        "title": title,
                        "url": url,
                        "content": text[:5000]  # 限制长度
                    }
                )
            else:
                return ToolResult(
                    success=True,
                    output={
                        "url": url,
                        "html": html[:10000]
                    }
                )

        except ImportError as e:
            missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
            return ToolResult(
                success=False,
                output=None,
                error=f"Required module not installed: {missing}. Run: pip install {missing}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Failed to fetch {url}: {str(e)}"
            )
