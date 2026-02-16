"""
子代理系统插件

功能:
- 创建子代理执行子任务
- 并行执行多个任务
- 结果汇总
"""

import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import uuid
from datetime import datetime

from loguru import logger

from ..base import Plugin


@dataclass
class SubAgentTask:
    """子代理任务定义"""
    id: str
    parent_id: str
    name: str
    task: str
    status: str = "pending"  # pending, running, completed, failed
    result: Any = None
    error: str = None
    created_at: str = ""
    started_at: str = None
    completed_at: str = None
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class SubAgentPlugin(Plugin):
    """子代理系统插件"""
    
    @property
    def name(self) -> str:
        return "subagent"
    
    @property
    def description(self) -> str:
        return "子代理系统: 并行执行多个子任务"
    
    async def _setup(self):
        """初始化"""
        self.data_dir = Path(self.get_config("data_dir", "./data/subagent"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.tasks_file = self.data_dir / "tasks.json"
        self._tasks: Dict[str, SubAgentTask] = {}
        self._load_tasks()
        
        # 最大并行数
        self.max_parallel = self.get_config("max_parallel", 3)
        
        logger.info(f"SubAgent plugin initialized: max_parallel={self.max_parallel}")
    
    async def _cleanup(self):
        """清理"""
        logger.info("SubAgent plugin shutdown")
    
    def _load_tasks(self):
        """加载任务历史"""
        if self.tasks_file.exists():
            try:
                with open(self.tasks_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for task_data in data:
                    task = SubAgentTask(**task_data)
                    self._tasks[task.id] = task
            except Exception as e:
                logger.error(f"Failed to load subagent tasks: {e}")
    
    def _save_tasks(self):
        """保存任务"""
        try:
            # 只保留最近100个完成的任务
            completed = [t for t in self._tasks.values() if t.status in ['completed', 'failed']]
            if len(completed) > 100:
                # 清理旧任务
                sorted_tasks = sorted(completed, key=lambda x: x.created_at, reverse=True)
                to_keep = {t.id: t for t in sorted_tasks[:100]}
                pending = {k: v for k, v in self._tasks.items() if v.status == 'pending'}
                running = {k: v for k, v in self._tasks.items() if v.status == 'running'}
                self._tasks = {**pending, **running, **to_keep}
            
            data = [asdict(task) for task in self._tasks.values()]
            with open(self.tasks_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save subagent tasks: {e}")
    
    async def spawn(self, tasks: List[Dict[str, str]], parallel: bool = True) -> Dict[str, Any]:
        """创建子代理执行任务
        
        Args:
            tasks: 任务列表，每个任务包含 name 和 task
            parallel: 是否并行执行
            
        Returns:
            执行结果
        """
        if not tasks:
            return {
                "success": False,
                "error": "任务列表不能为空"
            }
        
        # 生成父任务ID
        parent_id = str(uuid.uuid4())[:8]
        
        # 创建子任务
        sub_tasks = []
        for task_info in tasks:
            task_id = str(uuid.uuid4())[:8]
            task = SubAgentTask(
                id=task_id,
                parent_id=parent_id,
                name=task_info.get("name", f"任务{len(sub_tasks)+1}"),
                task=task_info.get("task", "")
            )
            sub_tasks.append(task)
            self._tasks[task_id] = task
        
        self._save_tasks()
        
        if parallel:
            # 并行执行
            results = await self._execute_parallel(sub_tasks)
        else:
            # 串行执行
            results = await self._execute_sequential(sub_tasks)
        
        return {
            "success": True,
            "parent_id": parent_id,
            "total": len(tasks),
            "completed": sum(1 for r in results if r.get("success")),
            "failed": sum(1 for r in results if not r.get("success")),
            "results": results
        }
    
    async def _execute_parallel(self, tasks: List[SubAgentTask]) -> List[Dict]:
        """并行执行任务"""
        results = []
        semaphore = asyncio.Semaphore(self.max_parallel)
        
        async def run_with_limit(task: SubAgentTask):
            async with semaphore:
                return await self._execute_single(task)
        
        # 创建所有任务
        coroutines = [run_with_limit(task) for task in tasks]
        
        # 等待所有任务完成
        task_results = await asyncio.gather(*coroutines, return_exceptions=True)
        
        for task, result in zip(tasks, task_results):
            if isinstance(result, Exception):
                results.append({
                    "id": task.id,
                    "name": task.name,
                    "success": False,
                    "error": str(result)
                })
            else:
                results.append(result)
        
        return results
    
    async def _execute_sequential(self, tasks: List[SubAgentTask]) -> List[Dict]:
        """串行执行任务"""
        results = []
        for task in tasks:
            result = await self._execute_single(task)
            results.append(result)
        return results
    
    async def _execute_single(self, task: SubAgentTask) -> Dict:
        """执行单个任务"""
        logger.info(f"Executing subagent task: {task.name} ({task.id})")
        
        try:
            task.status = "running"
            task.started_at = datetime.now().isoformat()
            self._save_tasks()
            
            # 调用 LLM 执行任务
            if self.agent and hasattr(self.agent, 'llm') and self.agent.llm:
                # 构建系统提示
                system_prompt = f"你是一个专注的助手，正在执行子任务: {task.name}"
                
                response = await self.agent.llm.simple_chat(
                    task.task,
                    system_prompt
                )
                
                task.result = response
                task.status = "completed"
                task.completed_at = datetime.now().isoformat()
                
                result = {
                    "id": task.id,
                    "name": task.name,
                    "success": True,
                    "result": response
                }
            else:
                task.status = "failed"
                task.error = "LLM not available"
                task.completed_at = datetime.now().isoformat()
                
                result = {
                    "id": task.id,
                    "name": task.name,
                    "success": False,
                    "error": "LLM not available"
                }
            
            self._save_tasks()
            return result
            
        except Exception as e:
            logger.error(f"Subagent task {task.id} failed: {e}")
            task.status = "failed"
            task.error = str(e)
            task.completed_at = datetime.now().isoformat()
            self._save_tasks()
            
            return {
                "id": task.id,
                "name": task.name,
                "success": False,
                "error": str(e)
            }
    
    async def get_task_status(self, task_id: str = None, parent_id: str = None) -> Dict[str, Any]:
        """获取任务状态
        
        Args:
            task_id: 单个任务ID
            parent_id: 父任务ID（查询该父任务下的所有子任务）
            
        Returns:
            任务状态
        """
        if task_id:
            task = self._tasks.get(task_id)
            if not task:
                return {
                    "success": False,
                    "error": f"任务 {task_id} 不存在"
                }
            
            return {
                "success": True,
                "task": {
                    "id": task.id,
                    "parent_id": task.parent_id,
                    "name": task.name,
                    "status": task.status,
                    "result": task.result,
                    "error": task.error,
                    "created_at": task.created_at,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at
                }
            }
        
        elif parent_id:
            tasks = [t for t in self._tasks.values() if t.parent_id == parent_id]
            return {
                "success": True,
                "parent_id": parent_id,
                "total": len(tasks),
                "tasks": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "status": t.status,
                        "result": t.result[:200] + "..." if t.result and len(str(t.result)) > 200 else t.result
                    }
                    for t in sorted(tasks, key=lambda x: x.created_at)
                ]
            }
        
        else:
            # 返回最近的10个任务
            recent_tasks = sorted(
                self._tasks.values(),
                key=lambda x: x.created_at,
                reverse=True
            )[:10]
            
            return {
                "success": True,
                "recent_tasks": [
                    {
                        "id": t.id,
                        "parent_id": t.parent_id,
                        "name": t.name,
                        "status": t.status
                    }
                    for t in recent_tasks
                ]
            }
    
    def get_tools(self) -> list:
        """返回工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "subagent_spawn",
                    "description": "创建子代理并行执行多个任务，适合需要同时处理多个子任务的场景",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "tasks": {
                                "type": "array",
                                "description": "任务列表，每个任务包含name和task",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string",
                                            "description": "任务名称"
                                        },
                                        "task": {
                                            "type": "string",
                                            "description": "任务描述"
                                        }
                                    },
                                    "required": ["name", "task"]
                                }
                            },
                            "parallel": {
                                "type": "boolean",
                                "description": "是否并行执行（默认true）",
                                "default": True
                            }
                        },
                        "required": ["tasks"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "subagent_status",
                    "description": "查询子代理任务状态",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "单个任务ID（可选）"
                            },
                            "parent_id": {
                                "type": "string",
                                "description": "父任务ID，查询该父任务下的所有子任务（可选）"
                            }
                        }
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        if tool_name == "subagent_spawn":
            return await self.spawn(
                tasks=params.get("tasks", []),
                parallel=params.get("parallel", True)
            )
        
        elif tool_name == "subagent_status":
            return await self.get_task_status(
                task_id=params.get("task_id"),
                parent_id=params.get("parent_id")
            )
        
        return await super().handle_tool(tool_name, params)
