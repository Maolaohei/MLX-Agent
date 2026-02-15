"""
子代理管理器 - 高级子代理管理
"""

import asyncio
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
from loguru import logger

from .core import SubAgent, SubAgentConfig, SubAgentResult, SubAgentStatus
from .pool import SubAgentPool


@dataclass
class SubAgentTask:
    """子代理任务包装"""
    id: str
    task: str
    config: SubAgentConfig
    callback: Optional[Callable] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class SubAgentManager:
    """
    子代理管理器
    
    提供更高级的子代理管理功能：
    - 任务队列和调度
    - 批量执行
    - 结果聚合
    - 历史记录
    """
    
    def __init__(self, max_concurrent: int = 5):
        self.pool = SubAgentPool(max_concurrent=max_concurrent)
        self.task_history: List[SubAgentTask] = []
        self._callbacks: Dict[str, Callable] = {}
    
    async def submit(
        self,
        task: str,
        config: Optional[SubAgentConfig] = None,
        callback: Optional[Callable[[SubAgentResult], None]] = None
    ) -> str:
        """
        提交子代理任务
        
        Args:
            task: 任务描述
            config: 子代理配置
            callback: 完成回调
        
        Returns:
            agent_id: 子代理ID
        """
        config = config or SubAgentConfig()
        
        # 创建任务记录
        task_record = SubAgentTask(
            id="",  # Will be set after spawn
            task=task,
            config=config
        )
        
        # 创建子代理
        from .core import create_sub_agent
        agent = await create_sub_agent(
            task=task,
            model=config.model,
            thinking=config.thinking,
            timeout=config.timeout,
            isolated_memory=config.isolated_memory,
            tool_filter=config.tool_filter
        )
        
        task_record.id = agent.id
        self.task_history.append(task_record)
        
        if callback:
            self._callbacks[agent.id] = callback
        
        # 添加到池并启动
        self.pool.agents[agent.id] = agent
        asyncio.create_task(self._run_with_callback(agent))
        
        return agent.id
    
    async def _run_with_callback(self, agent: SubAgent):
        """运行子代理并触发回调"""
        try:
            result = await agent.run()
            self.pool.results[agent.id] = result
            
            # 触发回调
            callback = self._callbacks.get(agent.id)
            if callback:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(result)
                    else:
                        callback(result)
                except Exception as e:
                    logger.error(f"Callback for agent {agent.id} failed: {e}")
                finally:
                    del self._callbacks[agent.id]
                    
        except Exception as e:
            logger.error(f"SubAgent {agent.id} execution failed: {e}")
    
    async def submit_batch(
        self,
        tasks: List[str],
        config: Optional[SubAgentConfig] = None
    ) -> List[str]:
        """
        批量提交子代理任务
        
        Args:
            tasks: 任务列表
            config: 共享配置
        
        Returns:
            agent_ids: 子代理ID列表
        """
        agent_ids = []
        for task in tasks:
            agent_id = await self.submit(task, config)
            agent_ids.append(agent_id)
        return agent_ids
    
    async def wait_for_all(
        self,
        agent_ids: List[str],
        timeout: Optional[float] = None
    ) -> Dict[str, SubAgentResult]:
        """
        等待多个子代理完成
        
        Args:
            agent_ids: 子代理ID列表
            timeout: 总超时时间
        
        Returns:
            结果字典 {agent_id: result}
        """
        results = {}
        pending = set(agent_ids)
        
        start = datetime.now()
        
        while pending:
            for agent_id in list(pending):
                result = self.pool.get_result(agent_id)
                if result:
                    results[agent_id] = result
                    pending.remove(agent_id)
            
            if not pending:
                break
            
            if timeout:
                elapsed = (datetime.now() - start).total_seconds()
                if elapsed > timeout:
                    logger.warning(f"wait_for_all timeout after {elapsed}s")
                    break
            
            await asyncio.sleep(0.1)
        
        return results
    
    def get_result(self, agent_id: str) -> Optional[SubAgentResult]:
        """获取子代理结果"""
        return self.pool.get_result(agent_id)
    
    def cancel(self, agent_id: str) -> bool:
        """取消子代理"""
        return self.pool.cancel(agent_id)
    
    def get_history(self, limit: int = 10) -> List[SubAgentTask]:
        """获取任务历史"""
        return self.task_history[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取管理器统计信息"""
        pool_stats = self.pool.get_stats()
        
        return {
            **pool_stats,
            "total_submitted": len(self.task_history),
            "pending_callbacks": len(self._callbacks)
        }
