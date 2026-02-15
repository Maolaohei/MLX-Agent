"""
技能系统 - v0.3.0 原生版

移除 OpenClaw 兼容层，纯 Python 原生实现
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, List, Tuple
from loguru import logger

from .native.base import NativeSkill, SkillContext, SkillResult, MemorySkill
from .manager import SkillManager


class CircuitBreaker:
    """熔断器 - 防止故障工具被无限调用"""
    
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures: Dict[str, int] = {}
        self.last_failure_time: Dict[str, float] = {}
        self.state: Dict[str, str] = {}  # "closed", "open", "half-open"
    
    def record_success(self, tool_name: str):
        """记录成功调用"""
        if tool_name in self.failures:
            del self.failures[tool_name]
            del self.last_failure_time[tool_name]
        self.state[tool_name] = "closed"
    
    def record_failure(self, tool_name: str) -> bool:
        """记录失败调用，返回是否触发熔断"""
        now = time.time()
        self.failures[tool_name] = self.failures.get(tool_name, 0) + 1
        self.last_failure_time[tool_name] = now
        
        if self.failures[tool_name] >= self.failure_threshold:
            self.state[tool_name] = "open"
            return True
        return False
    
    def can_execute(self, tool_name: str) -> bool:
        """检查是否可以执行工具"""
        if tool_name not in self.state or self.state[tool_name] == "closed":
            return True
        
        if self.state[tool_name] == "open":
            # 检查是否过了恢复时间
            last_fail = self.last_failure_time.get(tool_name, 0)
            if time.time() - last_fail > self.recovery_timeout:
                self.state[tool_name] = "half-open"
                return True
            return False
        
        return True
    
    def get_status(self, tool_name: str) -> str:
        """获取熔断器状态"""
        return self.state.get(tool_name, "closed")


class ToolExecutor:
    """自愈型工具执行器
    
    特性:
    - 熔断器保护
    - 指数退避重试
    - 优雅降级
    - 友好错误消息
    """
    
    def __init__(self, skill_manager: SkillManager):
        self.skill_manager = skill_manager
        self.circuit_breaker = CircuitBreaker()
        self.execution_stats: Dict[str, Dict] = {}
    
    async def execute(self, tool_name: str, arguments: Dict, context: Dict) -> Dict[str, Any]:
        """执行工具（带熔断器和重试）"""
        
        # 检查熔断器
        if not self.circuit_breaker.can_execute(tool_name):
            return {
                "success": False,
                "output": None,
                "error": f"工具 {tool_name} 暂时不可用，请稍后再试"
            }
        
        # 指数退避重试
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                result = await self.skill_manager.execute_tool(tool_name, arguments, context)
                
                # 检查是否成功
                if isinstance(result, dict):
                    success = result.get("success", True)
                    if success:
                        self.circuit_breaker.record_success(tool_name)
                        return result
                    else:
                        raise Exception(result.get("error", "Unknown error"))
                else:
                    # 插件返回非字典格式
                    self.circuit_breaker.record_success(tool_name)
                    return {
                        "success": True,
                        "output": result,
                        "error": None
                    }
                
            except Exception as e:
                logger.warning(f"Tool {tool_name} attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.info(f"Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    # 最终失败，记录熔断器
                    self.circuit_breaker.record_failure(tool_name)
                    
                    # 尝试降级
                    return await self._fallback(tool_name, arguments, context, str(e))
        
        return {
            "success": False,
            "output": None,
            "error": "Max retries exceeded"
        }
    
    async def _fallback(self, tool_name: str, arguments: Dict, context: Dict, error: str) -> Dict[str, Any]:
        """优雅降级"""
        logger.info(f"Tool {tool_name} failed, trying fallback...")
        
        # 降级策略 1: 使用替代工具
        fallbacks = {
            "web_search": "搜索功能暂时不可用",
            "browser": "浏览器功能暂时不可用",
            "execute_code": "代码执行功能暂时不可用"
        }
        
        friendly_message = fallbacks.get(tool_name, f"工具 {tool_name} 暂时不可用")
        
        return {
            "success": False,
            "output": None,
            "error": f"{friendly_message}，原因: {error}"
        }


__all__ = [
    "SkillManager",
    "ToolExecutor", 
    "CircuitBreaker",
    "NativeSkill",
    "SkillContext",
    "SkillResult",
    "MemorySkill"
]
