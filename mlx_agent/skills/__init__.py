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
    - 友好错误消息 (支持人设动态生成)
    """
    
    def __init__(self, skill_manager: SkillManager, agent=None):
        self.skill_manager = skill_manager
        self.agent = agent  # 用于获取人设信息
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
    
    def _generate_error_message(self, error_type: str, error_detail: str, requires_admin: bool) -> str:
        """根据人设动态生成错误提示"""
        import random
        
        # 尝试从 agent 获取人设信息
        identity_vibe = ""
        speaking_style = ""
        if self.agent and hasattr(self.agent, 'identity') and self.agent.identity:
            try:
                identity_vibe = self.agent.identity.identity.get('vibe', '')
                speaking_style = self.agent.identity.identity.get('speaking_style', '')
                soul_content = self.agent.identity.soul or ""
            except:
                pass
        
        # 根据人设风格选择语气
        # 检测古风/玄幻风格
        is_fantasy = any(kw in (identity_vibe + speaking_style).lower() for kw in 
                        ['古风', '玄幻', '仙侠', '修仙', '道家', '佛家', '妖', '魔', '仙', '神', '鬼', '怪'])
        
        # 检测傲娇/萌系风格
        is_moe = any(kw in (identity_vibe + speaking_style).lower() for kw in 
                    ['傲娇', '萌', '可爱', '甜', '软', '喵', '汪', '兽', '娘'])
        
        # 检测高冷/冷酷风格
        is_cold = any(kw in (identity_vibe + speaking_style).lower() for kw in 
                     ['高冷', '冷酷', '冷', '酷', '拽', '傲', '霸', '帝', '王'])
        
        # 基础错误信息模板
        error_info = {
            "api_key_missing": {
                "problem": "需要API密钥但未配置",
                "action": "联系管理员配置API Key"
            },
            "network_error": {
                "problem": "网络连接不稳定", 
                "action": "稍后重试或检查网络"
            },
            "service_unavailable": {
                "problem": "服务器暂时不可用",
                "action": "稍后重试"
            },
            "quota_exceeded": {
                "problem": "达到使用限额",
                "action": "联系管理员升级或等待重置"
            },
            "configuration_error": {
                "problem": "配置有误",
                "action": "联系管理员检查配置"
            },
            "unknown_error": {
                "problem": "出现未知问题",
                "action": "联系管理员查看日志"
            }
        }
        
        info = error_info.get(error_type, error_info["unknown_error"])
        
        # 根据人设生成不同风格的提示
        if is_fantasy:
            # 古风/玄幻风格
            fantasy_templates = [
                f"啧...{info['problem']}，此术暂且施展不得。{info['action']}后方可如常。",
                f"唉，{info['problem']}，灵力受阻。{info['action']}罢。",
                f"{info['problem']}，阵法未全。{info['action']}，自可运转。"
            ]
            return random.choice(fantasy_templates)
        
        elif is_moe:
            # 傲娇/萌系风格
            moe_templates = [
                f"哼...{info['problem']}啦，才不是因为想帮你呢！{info['action']}就好啦~",
                f"哎呀，{info['problem']}...{info['action']}嘛，快点解决啦！",
                f"真是的，{info['problem']}...{info['action']}就能用了，不、不要误会哦！"
            ]
            return random.choice(moe_templates)
        
        elif is_cold:
            # 高冷/冷酷风格
            cold_templates = [
                f"{info['problem']}。{info['action']}。",
                f"{info['problem']}，自行解决。",
                f"{info['action']}。"
            ]
            return random.choice(cold_templates)
        
        else:
            # 默认友好风格
            default_templates = [
                f"哎呀，{info['problem']}...{info['action']}就好啦~",
                f"{info['problem']}，暂时没法用呢。{info['action']}解决一下？",
                f"出了点小状况：{info['problem']}。{info['action']}应该就能用了~"
            ]
            return random.choice(default_templates)
    
    async def _fallback(self, tool_name: str, arguments: Dict, context: Dict, error: str) -> Dict[str, Any]:
        """优雅降级 - 带人设的错误报告"""
        logger.info(f"Tool {tool_name} failed, trying fallback...")
        
        # 分析错误类型
        error_lower = error.lower()
        error_type = "unknown_error"
        requires_admin = False
        
        # API Key 相关错误
        if any(kw in error_lower for kw in ['api key', 'apikey', 'api_key', 'unauthorized', '401', '403']):
            error_type = "api_key_missing"
            requires_admin = True
        
        # 网络连接错误
        elif any(kw in error_lower for kw in ['connection', 'network', 'timeout', 'connect', 'dns', 'unreachable']):
            error_type = "network_error"
        
        # 服务不可用
        elif any(kw in error_lower for kw in ['service unavailable', '503', '502', 'bad gateway', 'maintenance']):
            error_type = "service_unavailable"
        
        # 配额/限制错误
        elif any(kw in error_lower for kw in ['quota', 'rate limit', 'too many requests', '429', 'limit exceeded']):
            error_type = "quota_exceeded"
            requires_admin = True
        
        # 配置错误
        elif any(kw in error_lower for kw in ['config', 'configuration', 'env', 'environment', 'not set']):
            error_type = "configuration_error"
            requires_admin = True
        
        # 根据人设动态生成错误提示
        message = self._generate_error_message(error_type, error, requires_admin)
        
        return {
            "success": False,
            "output": None,
            "error": message,
            "error_type": error_type,
            "requires_admin": requires_admin
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
