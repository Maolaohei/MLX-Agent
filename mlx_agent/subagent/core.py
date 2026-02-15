import asyncio
import uuid
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from enum import Enum
from pathlib import Path

from loguru import logger


class SubAgentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class SubAgentConfig:
    """子代理配置"""
    model: str = "kimi-k2.5"
    thinking: str = "off"  # off | low | medium | high
    timeout: int = 3600  # 秒
    isolated_memory: bool = True
    tool_filter: Optional[List[str]] = None  # 限制可用工具
    max_iterations: int = 50  # 最大思考-行动循环次数
    system_prompt_override: Optional[str] = None


@dataclass
class SubAgentResult:
    """子代理执行结果"""
    success: bool
    output: Any = None
    error: Optional[str] = None
    status: SubAgentStatus = SubAgentStatus.PENDING
    duration_ms: float = 0.0
    iterations: int = 0
    tokens_used: int = 0
    metadata: Dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


class SubAgent:
    """
    真·子代理 - 完全隔离的 Agent 实例
    
    特性：
    - 独立的 MemoryBackend (可选)
    - 独立的 ToolRegistry (可过滤)
    - 独立的 LLMClient (可指定不同模型)
    - 完全隔离的执行环境
    - 超时控制和错误隔离
    """
    
    def __init__(
        self,
        task: str,
        config: Optional[SubAgentConfig] = None,
        parent_context: Optional[Dict] = None
    ):
        self.id = str(uuid.uuid4())[:8]
        self.task = task
        self.config = config or SubAgentConfig()
        self.parent_context = parent_context or {}
        
        # 状态
        self.status = SubAgentStatus.PENDING
        self.result: Optional[SubAgentResult] = None
        self._start_time: Optional[datetime] = None
        self._cancelled = False
        
        # 初始化隔离组件
        self._init_components()
    
    def _init_components(self):
        """初始化隔离组件"""
        # 1. 独立的记忆系统 (如果启用)
        if self.config.isolated_memory:
            from ..memory.sqlite import SQLiteMemoryBackend
            memory_path = Path(f"./memory/subagent_{self.id}.db")
            memory_path.parent.mkdir(parents=True, exist_ok=True)
            self.memory = SQLiteMemoryBackend(path=str(memory_path))
        else:
            self.memory = None
        
        # 2. 独立的 LLM 客户端
        from ..llm import LLMClient
        self.llm = LLMClient(
            primary_config={
                "model": self.config.model,
                "api_key": "",  # Will be set from parent context or env
                "temperature": 0.7,
                "max_tokens": 4000
            }
        )
        
        # 3. 工具注册表 (可过滤)
        from ..tools import tool_registry, ToolRegistry
        if self.config.tool_filter:
            self.tools = ToolRegistry()
            for tool_name in self.config.tool_filter:
                tool = tool_registry.get(tool_name)
                if tool:
                    self.tools.register(tool)
        else:
            self.tools = tool_registry
    
    async def run(self) -> SubAgentResult:
        """
        执行子代理任务
        
        Returns:
            SubAgentResult: 执行结果
        """
        self._start_time = datetime.now()
        self.status = SubAgentStatus.RUNNING
        
        try:
            # 设置超时
            result = await asyncio.wait_for(
                self._execute(),
                timeout=self.config.timeout
            )
            
            if not self._cancelled:
                self.status = SubAgentStatus.COMPLETED
                self.result = result
            
        except asyncio.TimeoutError:
            self.status = SubAgentStatus.TIMEOUT
            self.result = SubAgentResult(
                success=False,
                error=f"Task timed out after {self.config.timeout}s",
                status=SubAgentStatus.TIMEOUT
            )
        except Exception as e:
            logger.exception(f"SubAgent {self.id} failed")
            self.status = SubAgentStatus.FAILED
            self.result = SubAgentResult(
                success=False,
                error=str(e),
                status=SubAgentStatus.FAILED
            )
        
        finally:
            if self.result:
                self.result.status = self.status
                self.result.completed_at = datetime.now()
                if self._start_time:
                    self.result.duration_ms = (
                        self.result.completed_at - self._start_time
                    ).total_seconds() * 1000
        
        return self.result
    
    async def _execute(self) -> SubAgentResult:
        """实际执行逻辑"""
        # 构建系统提示
        system_prompt = self._build_system_prompt()
        
        # 初始化对话
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self.task}
        ]
        
        iterations = 0
        tokens_total = 0
        
        # 思考-行动循环
        while iterations < self.config.max_iterations:
            if self._cancelled:
                break
            
            iterations += 1
            
            # 调用 LLM
            response = await self.llm.chat(
                messages=messages,
                tools=self.tools.get_all_schemas() if self.tools else None
            )
            
            tokens_total += response.get("usage", {}).get("total_tokens", 0)
            
            # 处理响应
            message = response["choices"][0]["message"]
            content = message.get("content", "")
            tool_calls = message.get("tool_calls")
            
            # 添加到历史
            messages.append(message)
            
            # 如果有工具调用，执行它们
            if tool_calls:
                for tool_call in tool_calls:
                    if self._cancelled:
                        break
                    
                    result = await self._execute_tool(tool_call)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": str(result)
                    })
            else:
                # 没有工具调用，任务完成
                return SubAgentResult(
                    success=True,
                    output=content,
                    iterations=iterations,
                    tokens_used=tokens_total
                )
        
        # 达到最大迭代次数
        return SubAgentResult(
            success=False,
            error=f"Reached max iterations ({self.config.max_iterations})",
            iterations=iterations,
            tokens_used=tokens_total
        )
    
    def _build_system_prompt(self) -> str:
        """构建系统提示"""
        if self.config.system_prompt_override:
            return self.config.system_prompt_override
        
        return f"""You are a sub-agent tasked with: {self.task}

You have access to tools and can use them to complete the task.
Work autonomously and return a comprehensive result.
You are isolated from the main agent and have your own memory context.

Guidelines:
- Use tools when necessary
- Think step by step
- Provide detailed results
- If you need more information, use search tools
"""
    
    async def _execute_tool(self, tool_call: Dict) -> Any:
        """执行工具调用"""
        function_name = tool_call["function"]["name"]
        arguments = tool_call["function"].get("arguments", {})
        
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        
        # 执行工具
        result = await self.tools.execute(function_name, **arguments)
        return result.output if result.success else f"Error: {result.error}"
    
    def cancel(self):
        """取消任务"""
        self._cancelled = True
        self.status = SubAgentStatus.CANCELLED


# 便捷函数
async def create_sub_agent(
    task: str,
    model: str = "kimi-k2.5",
    thinking: str = "off",
    timeout: int = 3600,
    isolated_memory: bool = True,
    tool_filter: Optional[List[str]] = None,
    parent_context: Optional[Dict] = None
) -> SubAgent:
    """
    创建并运行子代理
    
    类似 OpenClaw 的 sessions_spawn
    """
    config = SubAgentConfig(
        model=model,
        thinking=thinking,
        timeout=timeout,
        isolated_memory=isolated_memory,
        tool_filter=tool_filter
    )
    
    sub_agent = SubAgent(
        task=task,
        config=config,
        parent_context=parent_context
    )
    
    return sub_agent
