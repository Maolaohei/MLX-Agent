"""
子代理池 - 管理多个子代理实例
"""

import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from loguru import logger

from .core import SubAgent, SubAgentResult, SubAgentStatus


class SubAgentPool:
    """
    子代理池
    
    管理多个子代理的生命周期：
    - 创建和销毁
    - 并发控制
    - 结果收集
    - 自动清理
    """
    
    def __init__(self, max_concurrent: int = 5, auto_cleanup: bool = True):
        self.max_concurrent = max_concurrent
        self.auto_cleanup = auto_cleanup
        
        self.agents: Dict[str, SubAgent] = {}
        self.results: Dict[str, SubAgentResult] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def spawn(
        self,
        task: str,
        **kwargs
    ) -> str:
        """
        创建并启动子代理
        
        Returns:
            agent_id: 子代理ID，可用于查询结果
        """
        from .core import create_sub_agent
        
        # 创建子代理
        agent = await create_sub_agent(task=task, **kwargs)
        
        # 记录
        self.agents[agent.id] = agent
        
        # 在信号量控制下启动
        async with self._semaphore:
            # 后台运行
            asyncio.create_task(self._run_agent(agent))
        
        return agent.id
    
    async def _run_agent(self, agent: SubAgent):
        """运行子代理并收集结果"""
        try:
            result = await agent.run()
            self.results[agent.id] = result
        except Exception as e:
            logger.error(f"SubAgent {agent.id} execution failed: {e}")
        finally:
            # 可选：完成后从池移除
            if self.auto_cleanup and agent.id in self.agents:
                del self.agents[agent.id]
    
    def get_result(self, agent_id: str) -> Optional[SubAgentResult]:
        """获取子代理结果"""
        return self.results.get(agent_id)
    
    def get_agent(self, agent_id: str) -> Optional[SubAgent]:
        """获取子代理实例"""
        return self.agents.get(agent_id)
    
    def cancel(self, agent_id: str) -> bool:
        """取消子代理"""
        agent = self.agents.get(agent_id)
        if agent:
            agent.cancel()
            return True
        return False
    
    def list_active(self) -> List[str]:
        """列出活动中的子代理"""
        return [
            aid for aid, agent in self.agents.items()
            if agent.status.value in ["pending", "running"]
        ]
    
    async def wait_for(self, agent_id: str, timeout: Optional[float] = None) -> Optional[SubAgentResult]:
        """等待子代理完成"""
        start = datetime.now()
        
        while True:
            result = self.get_result(agent_id)
            if result:
                return result
            
            if timeout and (datetime.now() - start).total_seconds() > timeout:
                return None
            
            await asyncio.sleep(0.1)
    
    def get_stats(self) -> Dict:
        """获取池统计信息"""
        active = self.list_active()
        completed = len([r for r in self.results.values() if r.status == SubAgentStatus.COMPLETED])
        failed = len([r for r in self.results.values() if r.status in [SubAgentStatus.FAILED, SubAgentStatus.TIMEOUT]])
        
        return {
            "active": len(active),
            "completed": completed,
            "failed": failed,
            "total": len(self.results),
            "max_concurrent": self.max_concurrent
        }
