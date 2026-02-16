"""
AniList插件 - 动漫、漫画、角色数据库查询
迁移自 OpenClaw skill: anilist
"""
import asyncio
import json
from typing import Any, Dict, List

from ..base import Plugin, register_plugin


@register_plugin  
class AniListPlugin(Plugin):
    """AniList动漫数据库插件"""
    
    API_URL = "https://graphql.anilist.co"
    
    @property
    def name(self) -> str:
        return "anilist"
    
    @property
    def description(self) -> str:
        return "搜索动漫、漫画、角色信息，使用AniList GraphQL API"
    
    async def _setup(self):
        """初始化插件"""
        pass  # 无需初始化，AniList API无需认证
    
    def get_tools(self) -> List[Dict]:
        """返回插件提供的工具"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "anilist_search_anime",
                    "description": "搜索动漫",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "动漫标题（支持日文、英文、罗马音）"
                            },
                            "page": {
                                "type": "integer",
                                "description": "页码，默认1",
                                "default": 1
                            }
                        },
                        "required": ["title"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "anilist_search_manga",
                    "description": "搜索漫画",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "漫画标题"
                            },
                            "page": {
                                "type": "integer",
                                "description": "页码，默认1",
                                "default": 1
                            }
                        },
                        "required": ["title"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "anilist_search_character",
                    "description": "搜索动漫角色",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "角色名字"
                            },
                            "page": {
                                "type": "integer",
                                "description": "页码，默认1",
                                "default": 1
                            }
                        },
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "anilist_get_anime",
                    "description": "通过ID获取动漫详细信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "integer",
                                "description": "AniList动漫ID"
                            }
                        },
                        "required": ["id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "anilist_get_manga",
                    "description": "通过ID获取漫画详细信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "integer",
                                "description": "AniList漫画ID"
                            }
                        },
                        "required": ["id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "anilist_trending",
                    "description": "获取当前热门动漫",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["ANIME", "MANGA"],
                                "default": "ANIME"
                            }
                        }
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        handlers = {
            "anilist_search_anime": self._search_anime,
            "anilist_search_manga": self._search_manga,
            "anilist_search_character": self._search_character,
            "anilist_get_anime": self._get_anime,
            "anilist_get_manga": self._get_manga,
            "anilist_trending": self._trending
        }
        
        if tool_name not in handlers:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        try:
            return await handlers[tool_name](params)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _graphql_request(self, query: str, variables: Dict) -> Dict:
        """发送GraphQL请求"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.API_URL,
                json={"query": query, "variables": variables},
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    raise Exception(f"API请求失败: {response.status}")
                return await response.json()
    
    async def _search_anime(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """搜索动漫"""
        title = params["title"]
        page = params.get("page", 1)
        
        query = """
        query ($search: String, $page: Int) {
            Page(page: $page, perPage: 10) {
                media(search: $search, type: ANIME) {
                    id
                    title { romaji english native }
                    description
                    episodes
                    status
                    season
                    seasonYear
                    format
                    genres
                    averageScore
                    popularity
                    coverImage { medium }
                    siteUrl
                }
            }
        }
        """
        
        result = await self._graphql_request(query, {"search": title, "page": page})
        
        if "errors" in result:
            return {"success": False, "error": result["errors"][0]["message"]}
        
        media_list = result["data"]["Page"]["media"]
        
        # 格式化结果
        anime_list = []
        for media in media_list:
            anime_list.append({
                "id": media["id"],
                "title": {
                    "romaji": media["title"]["romaji"],
                    "english": media["title"]["english"],
                    "native": media["title"]["native"]
                },
                "episodes": media.get("episodes"),
                "status": media.get("status"),
                "season": f"{media.get('season')} {media.get('seasonYear')}" if media.get("season") else None,
                "format": media.get("format"),
                "genres": media.get("genres", []),
                "average_score": media.get("averageScore"),
                "popularity": media.get("popularity"),
                "url": media.get("siteUrl")
            })
        
        return {
            "success": True,
            "title": title,
            "page": page,
            "total": len(anime_list),
            "results": anime_list
        }
    
    async def _search_manga(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """搜索漫画"""
        title = params["title"]
        page = params.get("page", 1)
        
        query = """
        query ($search: String, $page: Int) {
            Page(page: $page, perPage: 10) {
                media(search: $search, type: MANGA) {
                    id
                    title { romaji english native }
                    description
                    chapters
                    volumes
                    status
                    format
                    genres
                    averageScore
                    popularity
                    coverImage { medium }
                    siteUrl
                }
            }
        }
        """
        
        result = await self._graphql_request(query, {"search": title, "page": page})
        
        if "errors" in result:
            return {"success": False, "error": result["errors"][0]["message"]}
        
        media_list = result["data"]["Page"]["media"]
        
        manga_list = []
        for media in media_list:
            manga_list.append({
                "id": media["id"],
                "title": {
                    "romaji": media["title"]["romaji"],
                    "english": media["title"]["english"],
                    "native": media["title"]["native"]
                },
                "chapters": media.get("chapters"),
                "volumes": media.get("volumes"),
                "status": media.get("status"),
                "format": media.get("format"),
                "genres": media.get("genres", []),
                "average_score": media.get("averageScore"),
                "popularity": media.get("popularity"),
                "url": media.get("siteUrl")
            })
        
        return {
            "success": True,
            "title": title,
            "page": page,
            "total": len(manga_list),
            "results": manga_list
        }
    
    async def _search_character(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """搜索角色"""
        name = params["name"]
        page = params.get("page", 1)
        
        query = """
        query ($search: String, $page: Int) {
            Page(page: $page, perPage: 10) {
                characters(search: $search) {
                    id
                    name { full native }
                    gender
                    dateOfBirth { year month day }
                    description
                    image { medium }
                    media { nodes { id title { romaji } type } }
                    siteUrl
                }
            }
        }
        """
        
        result = await self._graphql_request(query, {"search": name, "page": page})
        
        if "errors" in result:
            return {"success": False, "error": result["errors"][0]["message"]}
        
        char_list = result["data"]["Page"]["characters"]
        
        characters = []
        for char in char_list:
            media_list = char.get("media", {}).get("nodes", [])
            characters.append({
                "id": char["id"],
                "name": char["name"]["full"],
                "name_native": char["name"]["native"],
                "gender": char.get("gender"),
                "birthday": f"{char.get('dateOfBirth', {}).get('month', '')}-{char.get('dateOfBirth', {}).get('day', '')}" if char.get("dateOfBirth") else None,
                "appears_in": [m["title"]["romaji"] for m in media_list[:3]],
                "url": char.get("siteUrl")
            })
        
        return {
            "success": True,
            "name": name,
            "page": page,
            "total": len(characters),
            "results": characters
        }
    
    async def _get_anime(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取动漫详情"""
        anime_id = params["id"]
        
        query = """
        query ($id: Int) {
            Media(id: $id, type: ANIME) {
                id
                title { romaji english native }
                description
                episodes
                duration
                status
                season
                seasonYear
                format
                genres
                tags { name rank }
                averageScore
                popularity
                favourites
                startDate { year month day }
                endDate { year month day }
                studios { nodes { name } }
                characters { nodes { id name { full } } }
                coverImage { large }
                bannerImage
                siteUrl
            }
        }
        """
        
        result = await self._graphql_request(query, {"id": anime_id})
        
        if "errors" in result:
            return {"success": False, "error": result["errors"][0]["message"]}
        
        media = result["data"]["Media"]
        
        return {
            "success": True,
            "id": media["id"],
            "title": media["title"],
            "description": media.get("description", "").replace("<br>", "\n"),
            "episodes": media.get("episodes"),
            "duration": media.get("duration"),
            "status": media.get("status"),
            "season": f"{media.get('season')} {media.get('seasonYear')}",
            "format": media.get("format"),
            "genres": media.get("genres", []),
            "tags": [t["name"] for t in media.get("tags", [])[:5]],
            "score": media.get("averageScore"),
            "popularity": media.get("popularity"),
            "favourites": media.get("favourites"),
            "studios": [s["name"] for s in media.get("studios", {}).get("nodes", [])],
            "main_characters": [c["name"]["full"] for c in media.get("characters", {}).get("nodes", [])[:5]],
            "url": media.get("siteUrl")
        }
    
    async def _get_manga(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取漫画详情"""
        manga_id = params["id"]
        
        query = """
        query ($id: Int) {
            Media(id: $id, type: MANGA) {
                id
                title { romaji english native }
                description
                chapters
                volumes
                status
                format
                genres
                tags { name rank }
                averageScore
                popularity
                favourites
                startDate { year month day }
                endDate { year month day }
                staff { nodes { name { full } primaryOccupations } }
                characters { nodes { id name { full } } }
                coverImage { large }
                siteUrl
            }
        }
        """
        
        result = await self._graphql_request(query, {"id": manga_id})
        
        if "errors" in result:
            return {"success": False, "error": result["errors"][0]["message"]}
        
        media = result["data"]["Media"]
        
        # 获取作者
        authors = []
        for staff in media.get("staff", {}).get("nodes", []):
            if "Mangaka" in staff.get("primaryOccupations", []) or "Writer" in staff.get("primaryOccupations", []):
                authors.append(staff["name"]["full"])
        
        return {
            "success": True,
            "id": media["id"],
            "title": media["title"],
            "description": media.get("description", "").replace("<br>", "\n"),
            "chapters": media.get("chapters"),
            "volumes": media.get("volumes"),
            "status": media.get("status"),
            "format": media.get("format"),
            "genres": media.get("genres", []),
            "tags": [t["name"] for t in media.get("tags", [])[:5]],
            "score": media.get("averageScore"),
            "popularity": media.get("popularity"),
            "favourites": media.get("favourites"),
            "authors": authors[:3],
            "main_characters": [c["name"]["full"] for c in media.get("characters", {}).get("nodes", [])[:5]],
            "url": media.get("siteUrl")
        }
    
    async def _trending(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取热门动漫/漫画"""
        media_type = params.get("type", "ANIME")
        
        query = """
        query ($type: MediaType) {
            Page(page: 1, perPage: 10) {
                media(type: $type, sort: TRENDING_DESC) {
                    id
                    title { romaji english }
                    description
                    averageScore
                    popularity
                    coverImage { medium }
                    siteUrl
                }
            }
        }
        """
        
        result = await self._graphql_request(query, {"type": media_type})
        
        if "errors" in result:
            return {"success": False, "error": result["errors"][0]["message"]}
        
        media_list = result["data"]["Page"]["media"]
        
        trending = []
        for media in media_list:
            trending.append({
                "id": media["id"],
                "title": media["title"]["romaji"] or media["title"]["english"],
                "average_score": media.get("averageScore"),
                "popularity": media.get("popularity"),
                "url": media.get("siteUrl")
            })
        
        return {
            "success": True,
            "type": media_type,
            "total": len(trending),
            "results": trending
        }
