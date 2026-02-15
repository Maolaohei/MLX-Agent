"""
健康检查服务器

提供 HTTP 端点用于监控和运维
"""

import asyncio
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass

from loguru import logger


@dataclass
class HealthStatus:
    """健康状态"""
    status: str  # "healthy", "degraded", "unhealthy"
    version: str
    timestamp: float
    checks: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            "status": self.status,
            "version": self.version,
            "timestamp": self.timestamp,
            "uptime": time.time() - self.timestamp if hasattr(self, '_start_time') else 0,
            "checks": self.checks
        }


class HealthCheckServer:
    """健康检查 HTTP 服务器
    
    提供以下端点:
    - GET /health - 基础健康状态
    - GET /health/ready - 服务就绪检查
    - GET /health/live - 存活检查
    - GET /health/metrics - 详细指标
    """
    
    def __init__(self, agent, host: str = "0.0.0.0", port: int = 8080):
        """初始化健康检查服务器
        
        Args:
            agent: MLXAgent 实例
            host: 监听地址
            port: 监听端口
        """
        self.agent = agent
        self.host = host
        self.port = port
        self._server = None
        self._start_time = time.time()
        self._running = False
        
    async def start(self):
        """启动健康检查服务器"""
        try:
            from aiohttp import web
            
            app = web.Application()
            app.router.add_get('/health', self._handle_health)
            app.router.add_get('/health/ready', self._handle_ready)
            app.router.add_get('/health/live', self._handle_live)
            app.router.add_get('/health/metrics', self._handle_metrics)
            
            runner = web.AppRunner(app)
            await runner.setup()
            
            site = web.TCPSite(runner, self.host, self.port)
            await site.start()
            
            self._server = runner
            self._running = True
            
            logger.info(f"Health check server started on http://{self.host}:{self.port}")
            
        except ImportError:
            logger.warning("aiohttp not installed, health check server disabled")
        except Exception as e:
            logger.error(f"Failed to start health check server: {e}")
    
    async def stop(self):
        """停止健康检查服务器"""
        if self._server:
            await self._server.cleanup()
            self._running = False
            logger.info("Health check server stopped")
    
    async def _handle_health(self, request):
        """处理健康检查请求"""
        from aiohttp import web
        
        status = await self._check_health()
        
        if status.status == "healthy":
            return web.json_response(status.to_dict(), status=200)
        elif status.status == "degraded":
            return web.json_response(status.to_dict(), status=200)
        else:
            return web.json_response(status.to_dict(), status=503)
    
    async def _handle_ready(self, request):
        """处理就绪检查"""
        from aiohttp import web
        
        # 检查关键组件是否就绪
        ready = True
        checks = {}
        
        if self.agent.memory:
            checks['memory'] = self.agent.memory._initialized
            ready = ready and checks['memory']
        
        if self.agent.llm:
            checks['llm'] = self.agent.llm.get_current_model() != 'unknown'
            ready = ready and checks['llm']
        
        if ready:
            return web.json_response({"ready": True, "checks": checks}, status=200)
        else:
            return web.json_response({"ready": False, "checks": checks}, status=503)
    
    async def _handle_live(self, request):
        """处理存活检查"""
        from aiohttp import web
        
        # 简单检查 Agent 是否运行
        if self.agent._running:
            return web.json_response({"alive": True}, status=200)
        else:
            return web.json_response({"alive": False}, status=503)
    
    async def _handle_metrics(self, request):
        """处理指标请求"""
        from aiohttp import web
        
        metrics = await self._collect_metrics()
        return web.json_response(metrics, status=200)
    
    async def _check_health(self) -> HealthStatus:
        """执行健康检查"""
        checks = {}
        status = "healthy"
        
        # 检查记忆系统
        try:
            if self.agent.memory:
                mem_stats = self.agent.memory.get_stats()
                checks['memory'] = {
                    "status": "ok" if mem_stats else "warning",
                    "stats": mem_stats
                }
            else:
                checks['memory'] = {"status": "not_initialized"}
        except Exception as e:
            checks['memory'] = {"status": "error", "error": str(e)}
            status = "degraded"
        
        # 检查任务队列
        try:
            if self.agent.task_queue:
                queue_stats = self.agent.task_queue.get_stats()
                checks['task_queue'] = {
                    "status": "ok",
                    "stats": queue_stats
                }
                # 如果队列积压过多，标记为 degraded
                if queue_stats.get('pending', 0) > 100:
                    status = "degraded"
            else:
                checks['task_queue'] = {"status": "not_initialized"}
        except Exception as e:
            checks['task_queue'] = {"status": "error", "error": str(e)}
        
        # 检查 LLM
        try:
            if self.agent.llm:
                current_model = self.agent.llm.get_current_model()
                checks['llm'] = {
                    "status": "ok",
                    "current_model": current_model
                }
            else:
                checks['llm'] = {"status": "not_initialized"}
                status = "degraded"
        except Exception as e:
            checks['llm'] = {"status": "error", "error": str(e)}
            status = "degraded"
        
        # 检查平台适配器
        try:
            if self.agent.telegram:
                checks['telegram'] = {
                    "status": "ok" if self.agent.telegram._running else "stopped"
                }
            else:
                checks['telegram'] = {"status": "disabled"}
        except Exception as e:
            checks['telegram'] = {"status": "error", "error": str(e)}
        
        # 检查工作线程
        try:
            if self.agent.task_worker:
                worker_stats = self.agent.task_worker.get_stats()
                checks['task_worker'] = {
                    "status": "ok" if worker_stats.get('running') else "stopped",
                    "stats": worker_stats
                }
            else:
                checks['task_worker'] = {"status": "not_initialized"}
        except Exception as e:
            checks['task_worker'] = {"status": "error", "error": str(e)}
        
        # 系统资源
        try:
            import psutil
            process = psutil.Process()
            checks['resources'] = {
                "status": "ok",
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "cpu_percent": process.cpu_percent(),
                "threads": process.num_threads()
            }
        except Exception as e:
            checks['resources'] = {"status": "error", "error": str(e)}
        
        return HealthStatus(
            status=status,
            version=getattr(self.agent.config, 'version', 'unknown'),
            timestamp=time.time(),
            checks=checks
        )
    
    async def _collect_metrics(self) -> Dict[str, Any]:
        """收集详细指标"""
        metrics = {
            "timestamp": time.time(),
            "uptime": time.time() - self._start_time,
            "version": getattr(self.agent.config, 'version', 'unknown'),
        }
        
        # Agent 统计
        try:
            agent_stats = await self.agent.get_stats()
            metrics['agent'] = agent_stats
        except Exception as e:
            metrics['agent'] = {"error": str(e)}
        
        # 系统指标
        try:
            import psutil
            metrics['system'] = {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory": dict(psutil.virtual_memory()._asdict()),
                "disk": dict(psutil.disk_usage('/')._asdict())
            }
        except Exception as e:
            metrics['system'] = {"error": str(e)}
        
        return metrics
