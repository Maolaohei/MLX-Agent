"""
搜索技能 - 使用 API Manager 统一管理 API Key

示例：展示如何在技能中使用 APIManager 获取 API Key
"""

from mlx_agent.skills.plugin import BasePlugin, PluginMetadata
from mlx_agent.api_manager import get_api_manager
from loguru import logger


class SearchPlugin(BasePlugin):
    """
    搜索插件示例 - 展示如何使用 API Manager
    
    此插件演示如何：
    1. 从 API Manager 获取 API Key
    2. 检查 API 是否可用
    3. 优雅处理 API 缺失的情况
    """
    
    def on_load(self) -> PluginMetadata:
        return PluginMetadata(
            name="search_plugin",
            description="搜索插件（支持 Tavily 和 Brave）",
            version="0.1.0",
            author="Shinobu"
        )
    
    def define_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "使用搜索引擎查询信息。优先使用 Tavily，如果不可用则尝试 Brave。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索关键词"
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "返回结果数量（默认 5）",
                                "default": 5
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
    
    async def execute(self, name: str, arguments: dict, context: dict) -> str:
        if name == "web_search":
            return await self._web_search(arguments)
        return f"Unknown tool: {name}"
    
    async def _web_search(self, arguments: dict) -> str:
        """
        执行网页搜索
        
        演示如何使用 API Manager：
        1. 获取全局 API Manager 实例
        2. 检查 API 可用性
        3. 获取 API Key
        """
        query = arguments.get("query", "")
        num_results = arguments.get("num_results", 5)
        
        # 获取 API Manager 实例
        api_manager = get_api_manager()
        
        # 尝试使用 Tavily（优先）
        if api_manager.is_available("tavily"):
            try:
                key = api_manager.get_key("tavily")
                logger.debug(f"Using Tavily API for search: {query}")
                
                # 这里调用 Tavily 搜索（示例）
                result = await self._search_tavily(query, num_results, key)
                return result
                
            except Exception as e:
                logger.error(f"Tavily search failed: {e}")
                # 失败后尝试下一个
        
        # 尝试使用 Brave（备选）
        if api_manager.is_available("brave"):
            try:
                key = api_manager.get_key("brave")
                logger.debug(f"Using Brave API for search: {query}")
                
                # 这里调用 Brave 搜索（示例）
                result = await self._search_brave(query, num_results, key)
                return result
                
            except Exception as e:
                logger.error(f"Brave search failed: {e}")
        
        # 所有搜索 API 都不可用
        available = api_manager.list_available()
        logger.warning(f"No search API available. Available APIs: {available}")
        
        return (
            f"搜索功能暂时不可用。\n"
            f"原因：未配置搜索 API（Tavily 或 Brave）\n"
            f"解决方案：\n"
            f"1. 在 config/apis.yaml 中添加 API Key\n"
            f"2. 或使用环境变量 TAVILY_API_KEY / BRAVE_API_KEY\n"
            f"当前可用 API: {', '.join(available) if available else '无'}"
        )
    
    async def _search_tavily(self, query: str, num: int, key: str) -> str:
        """使用 Tavily 搜索（示例实现）"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": key,
                    "query": query,
                    "max_results": num
                }
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    
                    if not results:
                        return f"未找到关于 '{query}' 的结果。"
                    
                    output = f"找到 {len(results)} 个关于 '{query}' 的结果：\n\n"
                    for i, r in enumerate(results[:num], 1):
                        title = r.get("title", "无标题")
                        content = r.get("content", "")[:200]
                        url = r.get("url", "")
                        output += f"{i}. **{title}**\n{content}...\n{url}\n\n"
                    
                    return output
                else:
                    raise Exception(f"Tavily API error: {resp.status}")
    
    async def _search_brave(self, query: str, num: int, key: str) -> str:
        """使用 Brave 搜索（示例实现）"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": key},
                params={"q": query, "count": num}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("web", {}).get("results", [])
                    
                    if not results:
                        return f"未找到关于 '{query}' 的结果。"
                    
                    output = f"找到 {len(results)} 个关于 '{query}' 的结果：\n\n"
                    for i, r in enumerate(results[:num], 1):
                        title = r.get("title", "无标题")
                        desc = r.get("description", "")[:200]
                        url = r.get("url", "")
                        output += f"{i}. **{title}**\n{desc}...\n{url}\n\n"
                    
                    return output
                else:
                    raise Exception(f"Brave API error: {resp.status}")
