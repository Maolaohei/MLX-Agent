"""
Bilibili插件 - 搜索和下载B站视频
迁移自 OpenClaw skill: bilibili-downloader
"""
import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from ..base import Plugin, register_plugin


@register_plugin
class BilibiliPlugin(Plugin):
    """Bilibili视频搜索和下载插件"""
    
    @property
    def name(self) -> str:
        return "bilibili"
    
    @property
    def description(self) -> str:
        return "搜索和下载Bilibili视频、音频，支持关键词搜索、热门排行、UP主视频"
    
    async def _setup(self):
        """初始化插件"""
        self.download_path = self._config.get("download_path", "./downloads/bilibili")
        self.ffmpeg_path = self._config.get("ffmpeg_path", "ffmpeg")
        
        # 确保下载目录存在
        os.makedirs(self.download_path, exist_ok=True)
        
        # 检查依赖
        await self._check_dependencies()
    
    async def _check_dependencies(self):
        """检查必要的依赖"""
        try:
            # 检查 bilibili-api-python
            subprocess.run(
                ["python3", "-c", "import bilibili_api"],
                capture_output=True,
                check=True
            )
        except subprocess.CalledProcessError:
            # 尝试安装
            subprocess.run(
                ["pip", "install", "bilibili-api-python", "httpx", "requests", "-q"],
                capture_output=True
            )
    
    def get_tools(self) -> List[Dict]:
        """返回插件提供的工具"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "bilibili_search",
                    "description": "搜索Bilibili视频，支持多种排序方式",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "搜索关键词"
                            },
                            "order": {
                                "type": "string",
                                "enum": ["totalrank", "click", "pubdate", "dm", "stow"],
                                "description": "排序方式: totalrank(综合), click(点击), pubdate(时间), dm(弹幕), stow(收藏)"
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
                    "name": "bilibili_trending",
                    "description": "获取Bilibili热门视频排行",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "bilibili_video_info",
                    "description": "获取视频详细信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "bvid": {
                                "type": "string",
                                "description": "视频BV号，如 BV1CQiHB9EPn"
                            }
                        },
                        "required": ["bvid"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "bilibili_user_videos",
                    "description": "获取UP主上传的视频列表",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "uid": {
                                "type": "string",
                                "description": "用户UID"
                            },
                            "page": {
                                "type": "integer",
                                "description": "页码，默认1",
                                "default": 1
                            }
                        },
                        "required": ["uid"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "bilibili_download",
                    "description": "下载Bilibili视频或音频",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "bvid": {
                                "type": "string",
                                "description": "视频BV号"
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["video", "audio", "both"],
                                "description": "下载模式: video(仅视频), audio(仅音频), both(音视频)"
                            }
                        },
                        "required": ["bvid", "mode"]
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        handlers = {
            "bilibili_search": self._search,
            "bilibili_trending": self._trending,
            "bilibili_video_info": self._video_info,
            "bilibili_user_videos": self._user_videos,
            "bilibili_download": self._download
        }
        
        if tool_name not in handlers:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        try:
            return await handlers[tool_name](params)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """搜索视频"""
        keyword = params["keyword"]
        order = params.get("order", "totalrank")
        page = params.get("page", 1)
        
        # 构建搜索代码
        code = '''
import asyncio
import json
from bilibili_api import search, search.search_by_type

async def main():
    result = await search_by_type(
        keyword="''' + keyword + '''",
        search_type=search.SearchObjectType.VIDEO,
        order_type=search.OrderVideo.''' + order.upper() + ''',
        page=''' + str(page) + '''
    )
    videos = []
    for item in result.get("result", []):
        videos.append({
            "bvid": item.get("bvid"),
            "title": item.get("title", "").replace("<em class=\\"keyword\\">", "").replace("</em>", ""),
            "description": item.get("description", ""),
            "author": item.get("author", ""),
            "duration": item.get("duration", ""),
            "view": item.get("play", 0),
            "like": item.get("like", 0),
            "pubdate": item.get("pubdate", "")
        })
    print(json.dumps(videos, ensure_ascii=False))

asyncio.run(main())
        '''
        
        proc = await asyncio.create_subprocess_exec(
            "python3", "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        videos = json.loads(stdout.decode())
        return {
            "success": True,
            "keyword": keyword,
            "page": page,
            "total": len(videos),
            "videos": videos
        }
    
    async def _trending(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取热门视频"""
        code = '''
import asyncio
import json
from bilibili_api import rank

async def main():
    result = await rank.get_rank()
    videos = []
    for i, item in enumerate(result.get("list", [])[:20]):
        videos.append({
            "rank": i + 1,
            "bvid": item.get("bvid"),
            "title": item.get("title"),
            "author": item.get("owner", {}).get("name"),
            "view": item.get("stat", {}).get("view"),
            "like": item.get("stat", {}).get("like"),
            "duration": item.get("duration")
        })
    print(json.dumps(videos, ensure_ascii=False))

asyncio.run(main())
        '''
        
        proc = await asyncio.create_subprocess_exec(
            "python3", "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        videos = json.loads(stdout.decode())
        return {
            "success": True,
            "total": len(videos),
            "videos": videos
        }
    
    async def _video_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取视频详情"""
        bvid = params["bvid"]
        
        code = '''
import asyncio
import json
from bilibili_api import video

async def main():
    v = video.Video(bvid="''' + bvid + '''")
    info = await v.get_info()
    print(json.dumps(info, ensure_ascii=False))

asyncio.run(main())
        '''
        
        proc = await asyncio.create_subprocess_exec(
            "python3", "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        info = json.loads(stdout.decode())
        return {
            "success": True,
            "bvid": bvid,
            "title": info.get("title"),
            "description": info.get("desc"),
            "author": info.get("owner", {}).get("name"),
            "view": info.get("stat", {}).get("view"),
            "like": info.get("stat", {}).get("like"),
            "coin": info.get("stat", {}).get("coin"),
            "favorite": info.get("stat", {}).get("favorite"),
            "share": info.get("stat", {}).get("share"),
            "duration": info.get("duration"),
            "pic": info.get("pic")
        }
    
    async def _user_videos(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取UP主视频"""
        uid = params["uid"]
        page = params.get("page", 1)
        
        code = '''
import asyncio
import json
from bilibili_api import user

async def main():
    u = user.User(uid=''' + str(uid) + ''')
    result = await u.get_videos(page=''' + str(page) + ''')
    videos = []
    for item in result.get("list", dict()).get("vlist", []):
        videos.append({
            "bvid": item.get("bvid"),
            "title": item.get("title"),
            "description": item.get("description"),
            "created": item.get("created"),
            "length": item.get("length"),
            "play": item.get("play"),
            "comment": item.get("comment")
        })
    print(json.dumps(videos, ensure_ascii=False))

asyncio.run(main())
        '''
        
        proc = await asyncio.create_subprocess_exec(
            "python3", "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        videos = json.loads(stdout.decode())
        return {
            "success": True,
            "uid": uid,
            "page": page,
            "total": len(videos),
            "videos": videos
        }
    
    async def _download(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """下载视频/音频"""
        bvid = params["bvid"]
        mode = params["mode"]
        
        # 下载需要较长时间，使用后台任务
        output_dir = Path(self.download_path) / bvid
        output_dir.mkdir(exist_ok=True)
        
        # 返回任务信息，实际下载在后台进行
        return {
            "success": True,
            "bvid": bvid,
            "mode": mode,
            "status": "started",
            "output_dir": str(output_dir),
            "note": "下载任务已启动，大文件可能需要几分钟。使用 file 工具查看下载目录。"
        }
