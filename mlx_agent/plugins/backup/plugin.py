"""
备份恢复插件

功能:
- 每日自动备份 (记忆、配置、技能)
- WebDAV 上传到云端
- 一键恢复
- 多版本管理
"""

import os
import json
import shutil
import tarfile
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import asyncio
import aiohttp
from loguru import logger

from ..base import Plugin


@dataclass
class BackupInfo:
    """备份信息"""
    id: str
    created_at: str
    size_bytes: int
    files_count: int
    checksum: str
    sources: List[str]
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "BackupInfo":
        return cls(**data)


class BackupPlugin(Plugin):
    """备份恢复插件"""
    
    @property
    def name(self) -> str:
        return "backup"
    
    @property
    def description(self) -> str:
        return "自动备份与恢复: 记忆、配置、技能的备份管理与云端同步"
    
    async def _setup(self):
        """初始化备份插件"""
        # 配置
        self.backup_dir = Path(self.get_config("backup_dir", "./backups"))
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.sources = self.get_config("sources", [
            "./memory",
            "./config",
            "./skills"
        ])
        
        # WebDAV 配置
        self.webdav_config = self.get_config("webdav", {})
        self.webdav_enabled = self.webdav_config.get("enabled", False)
        self.webdav_url = self.webdav_config.get("url", "")
        self.webdav_username = self.webdav_config.get("username", "")
        self.webdav_password = self.webdav_config.get("password", "")
        self.webdav_path = self.webdav_config.get("path", "/mlx-agent/backups")
        
        # 自动备份配置
        self.auto_backup = self.get_config("auto_backup", {})
        self.auto_enabled = self.auto_backup.get("enabled", True)
        self.auto_time = self.auto_backup.get("time", "02:00")  # 每天凌晨2点
        self.keep_count = self.auto_backup.get("keep_count", 7)  # 保留7个版本
        
        # 元数据存储
        self.metadata_file = self.backup_dir / "backups.json"
        self._backups: Dict[str, BackupInfo] = {}
        self._load_metadata()
        
        # 启动自动备份调度
        if self.auto_enabled:
            asyncio.create_task(self._scheduler_loop())
        
        logger.info(f"Backup plugin initialized: {len(self._backups)} backups, auto_backup={self.auto_enabled}")
    
    async def _cleanup(self):
        """清理资源"""
        logger.info("Backup plugin shutdown")
    
    def _load_metadata(self):
        """加载备份元数据"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for backup_id, info_data in data.items():
                    self._backups[backup_id] = BackupInfo.from_dict(info_data)
            except Exception as e:
                logger.error(f"Failed to load backup metadata: {e}")
    
    def _save_metadata(self):
        """保存备份元数据"""
        try:
            data = {k: v.to_dict() for k, v in self._backups.items()}
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save backup metadata: {e}")
    
    def _generate_backup_id(self) -> str:
        """生成备份ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"backup_{timestamp}"
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """计算文件校验和"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    async def create_backup(self, sources: List[str] = None, metadata: Dict = None) -> Dict[str, Any]:
        """创建备份
        
        Args:
            sources: 要备份的源路径列表 (None=使用默认配置)
            metadata: 额外元数据
            
        Returns:
            备份结果
        """
        sources = sources or self.sources
        backup_id = self._generate_backup_id()
        backup_file = self.backup_dir / f"{backup_id}.tar.gz"
        
        logger.info(f"Creating backup: {backup_id}")
        
        try:
            # 收集所有要备份的文件
            files_to_backup = []
            for source in sources:
                source_path = Path(source)
                if source_path.exists():
                    if source_path.is_dir():
                        for file_path in source_path.rglob("*"):
                            if file_path.is_file():
                                files_to_backup.append(file_path)
                    else:
                        files_to_backup.append(source_path)
            
            if not files_to_backup:
                return {
                    "success": False,
                    "error": "No files to backup"
                }
            
            # 创建 tar.gz 归档
            with tarfile.open(backup_file, 'w:gz') as tar:
                for file_path in files_to_backup:
                    try:
                        arcname = str(file_path.relative_to(Path.cwd()))
                        tar.add(file_path, arcname=arcname)
                    except Exception as e:
                        logger.warning(f"Failed to add file {file_path}: {e}")
            
            # 计算校验和
            checksum = self._calculate_checksum(backup_file)
            
            # 创建备份信息
            backup_info = BackupInfo(
                id=backup_id,
                created_at=datetime.now().isoformat(),
                size_bytes=backup_file.stat().st_size,
                files_count=len(files_to_backup),
                checksum=checksum,
                sources=sources,
                metadata=metadata or {}
            )
            
            self._backups[backup_id] = backup_info
            self._save_metadata()
            
            # 上传到 WebDAV (如果启用)
            if self.webdav_enabled:
                await self._upload_to_webdav(backup_file, backup_id)
            
            # 清理旧备份
            await self._cleanup_old_backups()
            
            logger.info(f"Backup created: {backup_id} ({backup_info.size_bytes} bytes, {len(files_to_backup)} files)")
            
            return {
                "success": True,
                "backup_id": backup_id,
                "info": backup_info.to_dict()
            }
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            # 清理失败的备份文件
            if backup_file.exists():
                backup_file.unlink()
            return {
                "success": False,
                "error": str(e)
            }
    
    async def restore_backup(self, backup_id: str, target_dir: str = None) -> Dict[str, Any]:
        """恢复备份
        
        Args:
            backup_id: 备份ID
            target_dir: 恢复目标目录 (None=原地恢复)
            
        Returns:
            恢复结果
        """
        backup_info = self._backups.get(backup_id)
        if not backup_info:
            return {
                "success": False,
                "error": f"Backup not found: {backup_id}"
            }
        
        backup_file = self.backup_dir / f"{backup_id}.tar.gz"
        if not backup_file.exists():
            # 尝试从 WebDAV 下载
            if self.webdav_enabled:
                downloaded = await self._download_from_webdav(backup_id)
                if not downloaded:
                    return {
                        "success": False,
                        "error": f"Backup file not found: {backup_id}"
                    }
            else:
                return {
                    "success": False,
                    "error": f"Backup file not found: {backup_id}"
                }
        
        target = Path(target_dir) if target_dir else Path.cwd()
        target.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Restoring backup: {backup_id} to {target}")
        
        try:
            # 验证校验和
            current_checksum = self._calculate_checksum(backup_file)
            if current_checksum != backup_info.checksum:
                logger.warning(f"Backup checksum mismatch: {backup_id}")
            
            # 解压备份
            with tarfile.open(backup_file, 'r:gz') as tar:
                tar.extractall(target)
            
            logger.info(f"Backup restored: {backup_id}")
            
            return {
                "success": True,
                "backup_id": backup_id,
                "restored_to": str(target),
                "files_count": backup_info.files_count
            }
            
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def list_backups(self) -> List[Dict]:
        """列出所有备份"""
        return [
            {
                "id": b.id,
                "created_at": b.created_at,
                "size_bytes": b.size_bytes,
                "size_human": self._format_size(b.size_bytes),
                "files_count": b.files_count,
                "local_exists": (self.backup_dir / f"{b.id}.tar.gz").exists()
            }
            for b in sorted(self._backups.values(), key=lambda x: x.created_at, reverse=True)
        ]
    
    async def delete_backup(self, backup_id: str) -> Dict[str, Any]:
        """删除备份"""
        if backup_id not in self._backups:
            return {
                "success": False,
                "error": f"Backup not found: {backup_id}"
            }
        
        backup_file = self.backup_dir / f"{backup_id}.tar.gz"
        if backup_file.exists():
            backup_file.unlink()
        
        del self._backups[backup_id]
        self._save_metadata()
        
        logger.info(f"Backup deleted: {backup_id}")
        
        return {
            "success": True,
            "deleted": backup_id
        }
    
    async def _upload_to_webdav(self, file_path: Path, backup_id: str):
        """上传备份到 WebDAV"""
        if not self.webdav_enabled:
            return
        
        try:
            url = f"{self.webdav_url.rstrip('/')}{self.webdav_path}/{backup_id}.tar.gz"
            
            auth = aiohttp.BasicAuth(self.webdav_username, self.webdav_password) if self.webdav_username else None
            
            async with aiohttp.ClientSession() as session:
                with open(file_path, 'rb') as f:
                    async with session.put(url, data=f, auth=auth, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                        if resp.status in [200, 201, 204]:
                            logger.info(f"Backup uploaded to WebDAV: {backup_id}")
                        else:
                            logger.warning(f"WebDAV upload failed: {resp.status}")
        except Exception as e:
            logger.error(f"Failed to upload to WebDAV: {e}")
    
    async def _download_from_webdav(self, backup_id: str) -> bool:
        """从 WebDAV 下载备份"""
        if not self.webdav_enabled:
            return False
        
        try:
            url = f"{self.webdav_url.rstrip('/')}{self.webdav_path}/{backup_id}.tar.gz"
            backup_file = self.backup_dir / f"{backup_id}.tar.gz"
            
            auth = aiohttp.BasicAuth(self.webdav_username, self.webdav_password) if self.webdav_username else None
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, auth=auth, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status == 200:
                        with open(backup_file, 'wb') as f:
                            async for chunk in resp.content.iter_chunked(8192):
                                f.write(chunk)
                        logger.info(f"Backup downloaded from WebDAV: {backup_id}")
                        return True
                    else:
                        logger.warning(f"WebDAV download failed: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"Failed to download from WebDAV: {e}")
            return False
    
    async def _cleanup_old_backups(self):
        """清理旧备份，只保留指定数量"""
        if len(self._backups) <= self.keep_count:
            return
        
        # 按时间排序，保留最新的
        sorted_backups = sorted(self._backups.values(), key=lambda x: x.created_at, reverse=True)
        to_delete = sorted_backups[self.keep_count:]
        
        for backup in to_delete:
            await self.delete_backup(backup.id)
    
    async def _scheduler_loop(self):
        """自动备份调度循环"""
        logger.info(f"Auto-backup scheduler started (daily at {self.auto_time})")
        
        while self._initialized:
            try:
                now = datetime.now()
                target_time = datetime.strptime(self.auto_time, "%H:%M").time()
                target_datetime = datetime.combine(now.date(), target_time)
                
                if target_datetime <= now:
                    target_datetime += timedelta(days=1)
                
                wait_seconds = (target_datetime - now).total_seconds()
                logger.debug(f"Next backup scheduled in {wait_seconds/3600:.1f} hours")
                
                await asyncio.sleep(wait_seconds)
                
                if self._initialized:
                    await self.create_backup(metadata={"trigger": "scheduled"})
                    
            except Exception as e:
                logger.error(f"Backup scheduler error: {e}")
                await asyncio.sleep(3600)  # 出错后等待1小时重试
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f}KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f}MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f}GB"
    
    def get_tools(self) -> List[Dict]:
        """返回工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "backup_create",
                    "description": "创建新的备份，包含记忆、配置和技能数据",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sources": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "要备份的源路径列表 (可选，默认使用配置)"
                            },
                            "note": {
                                "type": "string",
                                "description": "备份备注"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "backup_restore",
                    "description": "从指定备份恢复数据",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "backup_id": {
                                "type": "string",
                                "description": "备份ID"
                            },
                            "target_dir": {
                                "type": "string",
                                "description": "恢复目标目录 (可选，默认原地恢复)"
                            }
                        },
                        "required": ["backup_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "backup_list",
                    "description": "列出所有可用的备份",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "backup_delete",
                    "description": "删除指定备份",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "backup_id": {
                                "type": "string",
                                "description": "备份ID"
                            }
                        },
                        "required": ["backup_id"]
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        if tool_name == "backup_create":
            sources = params.get("sources")
            note = params.get("note")
            metadata = {"note": note} if note else {}
            return await self.create_backup(sources, metadata)
        
        elif tool_name == "backup_restore":
            return await self.restore_backup(
                params.get("backup_id"),
                params.get("target_dir")
            )
        
        elif tool_name == "backup_list":
            backups = await self.list_backups()
            return {
                "success": True,
                "backups": backups,
                "count": len(backups)
            }
        
        elif tool_name == "backup_delete":
            return await self.delete_backup(params.get("backup_id"))
        
        return await super().handle_tool(tool_name, params)
