"""
Pixiv插件 - Pixiv插画搜索和浏览
迁移自 OpenClaw skill: pixiv-skill
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from ..base import Plugin, register_plugin


@register_plugin
class PixivPlugin(Plugin):
    """Pixiv插画搜索和排行榜插件"""
    
    @property
    def name(self) -> str:
        return "pixiv"
    
    @property
    def description(self) -> str:
        return "搜索Pixiv插画、查看排行榜、浏览用户作品。支持关键词搜索和日/周/月排行"
    
    async def _setup(self):
        """初始化插件"""
        self.config_path = Path(__file__).parent / "config.json"
        self.refresh_token = self._config.get("refresh_token") or await self._load_token()
        
        # 检查pixivpy依赖
        try:
            import pixivpy3
        except ImportError:
            proc = await asyncio.create_subprocess_exec(
                "pip", "install", "pixivpy3", "-q",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
    
    async def _load_token(self) -> str:
        """从配置文件加载token"""
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                config = json.load(f)
                return config.get("refresh_token", "")
        return ""
    
    async def _save_token(self, token: str):
        """保存token到配置文件"""
        with open(self.config_path, "w") as f:
            json.dump({"refresh_token": token}, f)
    
    def get_tools(self) -> List[Dict]:
        """返回插件提供的工具"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "pixiv_search",
                    "description": "搜索Pixiv插画，支持分页",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "搜索关键词（日文/英文），如: 初音ミク, 風景, landscape"
                            },
                            "page": {
                                "type": "integer",
                                "description": "页码，默认1",
                                "default": 1
                            }
                        },
                        "required": ["keyword"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pixiv_ranking",
                    "description": "获取Pixiv排行榜",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mode": {
                                "type": "string",
                                "enum": ["day", "week", "month", "day_male", "day_female", "week_original", "week_rookie", "day_ai"],
                                "description": "排行榜类型: day(日榜), week(周榜), month(月榜), day_male(男性向), day_female(女性向), week_original(原创), week_rookie(新人), day_ai(AI)"
                            },
                            "page": {
                                "type": "integer",
                                "description": "页码，默认1",
                                "default": 1
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pixiv_user",
                    "description": "获取Pixiv用户信息和作品",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_id": {
                                "type": "integer",
                                "description": "Pixiv用户ID"
                            }
                        },
                        "required": ["user_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pixiv_illust",
                    "description": "获取插画详细信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "illust_id": {
                                "type": "integer",
                                "description": "插画ID"
                            }
                        },
                        "required": ["illust_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pixiv_set_token",
                    "description": "设置Pixiv Refresh Token（首次使用需要）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "token": {
                                "type": "string",
                                "description": "Pixiv Refresh Token"
                            }
                        },
                        "required": ["token"]
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        handlers = {
            "pixiv_search": self._search,
            "pixiv_ranking": self._ranking,
            "pixiv_user": self._user,
            "pixiv_illust": self._illust,
            "pixiv_set_token": self._set_token
        }
        
        if tool_name not in handlers:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        try:
            return await handlers[tool_name](params)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _set_token(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """设置refresh token"""
        token = params["token"]
        self.refresh_token = token
        await self._save_token(token)
        return {
            "success": True,
            "message": "Token已保存，现在可以使用其他Pixiv功能了"
        }
    
    async def _search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """搜索插画"""
        if not self.refresh_token:
            return {
                "success": False,
                "error": "请先使用 pixiv_set_token 设置 Refresh Token"
            }
        
        keyword = params["keyword"]
        page = params.get("page", 1)
        
        cmd = [
            "python3", "-c",
            f"""
from pixivpy3 import AppPixivAPI
import json

api = AppPixivAPI()
api.auth(refresh_token="{self.refresh_token}")

json_result = api.search_illust("{keyword}", search_target='partial_match_for_tags', sort='date_desc')
illusts = []
for idx, illust in enumerate(json_result.illusts[:10]):
    if idx >= (page - 1) * 10 and idx < page * 10:
        illusts.append({{
            'id': illust.id,
            'title': illust.title,
            'user': {{'id': illust.user.id, 'name': illust.user.name}},
            'image_urls': illust.image_urls.medium if hasattr(illust, 'image_urls') else None,
            'tags': [t.name for t in illust.tags],
            'page_count': illust.page_count,
            'create_date': illust.create_date
        }})

print(json.dumps(illusts, ensure_ascii=False))
            """
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        illusts = json.loads(stdout.decode())
        return {
            "success": True,
            "keyword": keyword,
            "page": page,
            "total": len(illusts),
            "illustrations": illusts
        }
    
    async def _ranking(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取排行榜"""
        if not self.refresh_token:
            return {
                "success": False,
                "error": "请先使用 pixiv_set_token 设置 Refresh Token"
            }
        
        mode = params.get("mode", "day")
        
        cmd = [
            "python3", "-c",
            f"""
from pixivpy3 import AppPixivAPI
import json

api = AppPixivAPI()
api.auth(refresh_token="{self.refresh_token}")

json_result = api.illust_ranking(mode="{mode}")
illusts = []
for idx, illust in enumerate(json_result.illusts[:20]):
    illusts.append({{
        'rank': idx + 1,
        'id': illust.id,
        'title': illust.title,
        'user': {{'id': illust.user.id, 'name': illust.user.name}},
        'image_urls': illust.image_urls.medium if hasattr(illust, 'image_urls') else None,
        'tags': [t.name for t in illust.tags],
        'page_count': illust.page_count
    }})

print(json.dumps(illusts, ensure_ascii=False))
            """
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        illusts = json.loads(stdout.decode())
        return {
            "success": True,
            "mode": mode,
            "total": len(illusts),
            "illustrations": illusts
        }
    
    async def _user(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取用户信息"""
        if not self.refresh_token:
            return {
                "success": False,
                "error": "请先使用 pixiv_set_token 设置 Refresh Token"
            }
        
        user_id = params["user_id"]
        
        cmd = [
            "python3", "-c",
            f"""
from pixivpy3 import AppPixivAPI
import json

api = AppPixivAPI()
api.auth(refresh_token="{self.refresh_token}")

# 获取用户信息
detail = api.user_detail({user_id})
user_info = {{
    'id': detail.user.id,
    'name': detail.user.name,
    'account': detail.user.account,
    'profile_image': detail.user.profile_image_urls.medium if hasattr(detail.user, 'profile_image_urls') else None,
    'comment': detail.user.comment,
    'followers': detail.profile.total_followers,
    'following': detail.profile.total_follow_users,
    'illusts': detail.profile.total_illusts,
    'manga': detail.profile.total_manga
}}

# 获取用户插画
illusts_result = api.user_illusts({user_id})
illusts = []
for illust in illusts_result.illusts[:10]:
    illusts.append({{
        'id': illust.id,
        'title': illust.title,
        'image_urls': illust.image_urls.medium if hasattr(illust, 'image_urls') else None,
        'tags': [t.name for t in illust.tags]
    }})

result = {{'user': user_info, 'illustrations': illusts}}
print(json.dumps(result, ensure_ascii=False))
            """
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        result = json.loads(stdout.decode())
        return {
            "success": True,
            **result
        }
    
    async def _illust(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取插画详情"""
        if not self.refresh_token:
            return {
                "success": False,
                "error": "请先使用 pixiv_set_token 设置 Refresh Token"
            }
        
        illust_id = params["illust_id"]
        
        cmd = [
            "python3", "-c",
            f"""
from pixivpy3 import AppPixivAPI
import json

api = AppPixivAPI()
api.auth(refresh_token="{self.refresh_token}")

json_result = api.illust_detail({illust_id})
illust = json_result.illust

result = {{
    'id': illust.id,
    'title': illust.title,
    'caption': illust.caption,
    'user': {{'id': illust.user.id, 'name': illust.user.name}},
    'image_urls': illust.image_urls.large if hasattr(illust, 'image_urls') else None,
    'tags': [t.name for t in illust.tags],
    'tools': illust.tools,
    'create_date': illust.create_date,
    'page_count': illust.page_count,
    'width': illust.width,
    'height': illust.height,
    'total_view': illust.total_view,
    'total_bookmarks': illust.total_bookmarks,
    'total_comments': illust.total_comments
}}

print(json.dumps(result, ensure_ascii=False))
            """
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        result = json.loads(stdout.decode())
        return {
            "success": True,
            **result
        }
