"""
系统信息工具

获取系统状态、执行系统命令等
"""

import os
import platform
import subprocess
from datetime import datetime
from typing import List, Optional, Any
import asyncio

from loguru import logger

from .base import BaseTool, ToolCategory, ToolParameter, ToolResult, register_tool


try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


@register_tool
class SystemTool(BaseTool):
    """系统信息工具"""
    
    name = "system_info"
    description = "获取系统信息: CPU、内存、磁盘、进程等"
    category = ToolCategory.SYSTEM
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="info_type",
                description="信息类型: all(全部), cpu, memory, disk, network, processes, time",
                type="string",
                required=True,
                enum=["all", "cpu", "memory", "disk", "network", "processes", "time", "platform"]
            )
        ]
    
    async def execute(self, **params) -> ToolResult:
        info_type = params.get("info_type", "all")
        
        try:
            if info_type == "all":
                return await self._get_all_info()
            elif info_type == "cpu":
                return await self._get_cpu_info()
            elif info_type == "memory":
                return await self._get_memory_info()
            elif info_type == "disk":
                return await self._get_disk_info()
            elif info_type == "network":
                return await self._get_network_info()
            elif info_type == "processes":
                return await self._get_processes()
            elif info_type == "time":
                return await self._get_time()
            elif info_type == "platform":
                return await self._get_platform()
            else:
                return ToolResult(success=False, output=None, error=f"Unknown info_type: {info_type}")
        
        except Exception as e:
            logger.error(f"System info failed: {e}")
            return ToolResult(success=False, output=None, error=str(e))
    
    async def _get_all_info(self) -> ToolResult:
        """获取全部系统信息"""
        info = {
            "platform": await self._get_platform().execute().output,
            "cpu": (await self._get_cpu_info()).output,
            "memory": (await self._get_memory_info()).output,
            "disk": (await self._get_disk_info()).output,
            "time": (await self._get_time()).output
        }
        return ToolResult(success=True, output=info)
    
    async def _get_platform(self) -> ToolResult:
        """获取平台信息"""
        return ToolResult(
            success=True,
            output={
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "python_version": platform.python_version()
            }
        )
    
    async def _get_cpu_info(self) -> ToolResult:
        """获取 CPU 信息"""
        if PSUTIL_AVAILABLE:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            return ToolResult(
                success=True,
                output={
                    "cpu_percent": cpu_percent,
                    "cpu_count": cpu_count,
                    "cpu_freq_mhz": cpu_freq.current if cpu_freq else None
                }
            )
        else:
            # Fallback
            result = subprocess.run(["nproc"], capture_output=True, text=True)
            cpu_count = int(result.stdout.strip()) if result.returncode == 0 else None
            
            return ToolResult(
                success=True,
                output={
                    "cpu_count": cpu_count,
                    "note": "psutil not installed, limited info"
                }
            )
    
    async def _get_memory_info(self) -> ToolResult:
        """获取内存信息"""
        if PSUTIL_AVAILABLE:
            mem = psutil.virtual_memory()
            return ToolResult(
                success=True,
                output={
                    "total_mb": mem.total // (1024 * 1024),
                    "available_mb": mem.available // (1024 * 1024),
                    "used_mb": mem.used // (1024 * 1024),
                    "percent": mem.percent
                }
            )
        else:
            # Fallback to free command
            result = subprocess.run(["free", "-m"], capture_output=True, text=True)
            return ToolResult(success=True, output={"free_output": result.stdout})
    
    async def _get_disk_info(self) -> ToolResult:
        """获取磁盘信息"""
        if PSUTIL_AVAILABLE:
            disks = []
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks.append({
                        "device": partition.device,
                        "mountpoint": partition.mountpoint,
                        "total_gb": usage.total // (1024**3),
                        "used_gb": usage.used // (1024**3),
                        "free_gb": usage.free // (1024**3),
                        "percent": usage.percent
                    })
                except:
                    pass
            return ToolResult(success=True, output={"disks": disks})
        else:
            result = subprocess.run(["df", "-h"], capture_output=True, text=True)
            return ToolResult(success=True, output={"df_output": result.stdout})
    
    async def _get_network_info(self) -> ToolResult:
        """获取网络信息"""
        if PSUTIL_AVAILABLE:
            net_io = psutil.net_io_counters()
            return ToolResult(
                success=True,
                output={
                    "bytes_sent": net_io.bytes_sent,
                    "bytes_recv": net_io.bytes_recv,
                    "packets_sent": net_io.packets_sent,
                    "packets_recv": net_io.packets_recv
                }
            )
        else:
            return ToolResult(success=False, output=None, error="psutil required for network info")
    
    async def _get_processes(self) -> ToolResult:
        """获取进程列表"""
        if PSUTIL_AVAILABLE:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    processes.append(proc.info)
                except:
                    pass
            # 按 CPU 排序，取前 10
            processes.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
            return ToolResult(success=True, output={"processes": processes[:10]})
        else:
            result = subprocess.run(["ps", "aux", "--sort=-%cpu"], capture_output=True, text=True)
            lines = result.stdout.strip().split("\n")[:11]
            return ToolResult(success=True, output={"ps_output": "\n".join(lines)})
    
    async def _get_time(self) -> ToolResult:
        """获取时间信息"""
        now = datetime.now()
        return ToolResult(
            success=True,
            output={
                "timestamp": now.timestamp(),
                "iso": now.isoformat(),
                "utc": datetime.utcnow().isoformat(),
                "timezone": str(datetime.now().astimezone().tzinfo)
            }
        )


@register_tool
class ProcessTool(BaseTool):
    """进程管理工具"""
    
    name = "process_manager"
    description = "管理系统进程: 查看、终止等"
    category = ToolCategory.SYSTEM
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                description="操作: list(列出), kill(终止), info(详情)",
                type="string",
                required=True,
                enum=["list", "kill", "info"]
            ),
            ToolParameter(
                name="pid",
                description="进程 ID (kill/info 时必需)",
                type="integer",
                required=False
            ),
            ToolParameter(
                name="name",
                description="进程名称 (list 时可选过滤)",
                type="string",
                required=False
            )
        ]
    
    async def execute(self, **params) -> ToolResult:
        action = params.get("action")
        
        try:
            if action == "list":
                name_filter = params.get("name")
                return await self._list_processes(name_filter)
            elif action == "kill":
                pid = params.get("pid")
                if not pid:
                    return ToolResult(success=False, output=None, error="PID required")
                return await self._kill_process(pid)
            elif action == "info":
                pid = params.get("pid")
                if not pid:
                    return ToolResult(success=False, output=None, error="PID required")
                return await self._process_info(pid)
            else:
                return ToolResult(success=False, output=None, error=f"Unknown action: {action}")
        
        except Exception as e:
            return ToolResult(success=False, output=None, error=str(e))
    
    async def _list_processes(self, name_filter: Optional[str]) -> ToolResult:
        """列出进程"""
        if PSUTIL_AVAILABLE:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'status']):
                try:
                    info = proc.info
                    if not name_filter or name_filter.lower() in info.get('name', '').lower():
                        processes.append(info)
                except:
                    pass
            return ToolResult(success=True, output={"processes": processes})
        else:
            if name_filter:
                result = subprocess.run(["pgrep", "-a", name_filter], capture_output=True, text=True)
            else:
                result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
            return ToolResult(success=True, output={"output": result.stdout})
    
    async def _kill_process(self, pid: int) -> ToolResult:
        """终止进程"""
        if PSUTIL_AVAILABLE:
            try:
                proc = psutil.Process(pid)
                proc.terminate()
                gone, alive = psutil.wait_procs([proc], timeout=3)
                if proc in alive:
                    proc.kill()
                return ToolResult(success=True, output={"killed": pid})
            except psutil.NoSuchProcess:
                return ToolResult(success=False, output=None, error=f"Process {pid} not found")
        else:
            result = subprocess.run(["kill", str(pid)], capture_output=True)
            if result.returncode == 0:
                return ToolResult(success=True, output={"killed": pid})
            else:
                return ToolResult(success=False, output=None, error=result.stderr.decode())
    
    async def _process_info(self, pid: int) -> ToolResult:
        """获取进程详情"""
        if PSUTIL_AVAILABLE:
            try:
                proc = psutil.Process(pid)
                info = {
                    "pid": pid,
                    "name": proc.name(),
                    "status": proc.status(),
                    "cpu_percent": proc.cpu_percent(),
                    "memory_percent": proc.memory_percent(),
                    "create_time": proc.create_time(),
                    "cmdline": proc.cmdline()
                }
                return ToolResult(success=True, output=info)
            except psutil.NoSuchProcess:
                return ToolResult(success=False, output=None, error=f"Process {pid} not found")
        else:
            result = subprocess.run(["ps", "-p", str(pid), "-o", "pid,ppid,cmd,%cpu,%mem"], 
                                  capture_output=True, text=True)
            return ToolResult(success=True, output={"output": result.stdout})
