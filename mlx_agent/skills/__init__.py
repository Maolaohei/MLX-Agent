import asyncio
import json
import time
from typing import Dict, Any, Optional, List, Tuple
from loguru import logger

from .native.base import NativeSkill, SkillContext, SkillResult, MemorySkill, OpenClawRunnerSkill
from .compat.openclaw import OpenClawSkillAdapter
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
        
        return True  # half-open 允许一次尝试


class SkillRegistry:
    """技能注册表 - 统一管理 Native, OpenClaw 和 Custom Plugins
    
    新增特性：
    - 自动重试机制 (Exponential Backoff)
    - 熔断器保护 (Circuit Breaker)
    - 优雅降级 (Graceful Degradation)
    - 备用工具链 (Fallback Chain)
    """
    
    def __init__(self, agent):
        self.agent = agent
        self.skills: Dict[str, NativeSkill] = {}
        self.openclaw_adapter = OpenClawSkillAdapter()
        self.plugin_manager = SkillManager(plugin_dir="plugins")
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
        
        # 注册原生技能
        self._register_native_skill(MemorySkill())
        self._register_native_skill(OpenClawRunnerSkill())
        
        # 定义工具降级链：当主工具失败时，尝试的备用方案
        self.fallback_chain: Dict[str, List[str]] = {
            "get_current_weather": ["run_openclaw_skill"],  # 天气失败时，尝试用 OpenClaw 的 weather
        }
    
    async def initialize(self):
        """初始化所有技能系统"""
        # 1. 初始化 OpenClaw 适配器
        await self.openclaw_adapter.initialize()
        
        # 2. 初始化插件管理器
        await self.plugin_manager.initialize(self.agent)
        
        logger.info(f"SkillRegistry initialized: {len(self.skills)} native, "
                   f"{len(self.openclaw_adapter.list_skills())} openclaw, "
                   f"{len(self.plugin_manager.plugins)} custom plugins")

    def _register_native_skill(self, skill: NativeSkill):
        schema = skill.get_function_schema()
        name = schema["function"]["name"]
        self.skills[name] = skill

    def get_tools_schema(self) -> List[dict]:
        """获取所有可用工具的 Schema (合并三方来源)"""
        tools = []
        
        # 1. Native Skills
        for skill in set(self.skills.values()):
            tools.append(skill.get_function_schema())
            
        # 2. OpenClaw Skills (通过 run_openclaw_skill 统一调用，不再单独暴露)
        # tools.extend(self.openclaw_adapter.get_tools_schema())
        
        # 3. Custom Plugins
        tools.extend(self.plugin_manager.get_all_tools_schema())
        
        return tools

    async def execute_tool_call(self, tool_call: dict, **context_kwargs) -> SkillResult:
        """执行工具调用（带自动修复、重试、熔断、降级）
        
        Args:
            tool_call: OpenAI 格式的 tool_call
            **context_kwargs: 上下文参数
            
        Returns:
            SkillResult: 执行结果（成功或优雅降级后的结果）
        """
        function_name = tool_call.get("function", {}).get("name")
        arguments_str = tool_call.get("function", {}).get("arguments", "{}")
        
        # 解析参数
        try:
            if arguments_str.startswith("```"):
                lines = arguments_str.split('\n')
                if len(lines) >= 2:
                    arguments_str = '\n'.join(lines[1:-1])
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError as e:
            return SkillResult(
                success=False, 
                error=f"参数解析失败: {e}。请检查 JSON 格式。"
            )
        
        # 构建上下文
        context = SkillContext(
            agent=self.agent,
            user_id=context_kwargs.get("user_id"),
            chat_id=context_kwargs.get("chat_id"),
            platform=context_kwargs.get("platform")
        )
        
        # 1. 检查熔断器
        if not self.circuit_breaker.can_execute(function_name):
            logger.warning(f"[CircuitBreaker] Tool {function_name} is currently OPEN (failing)")
            # 尝试降级
            fallback_result = await self._try_fallback(function_name, arguments, context, context_kwargs)
            if fallback_result:
                return fallback_result
            return SkillResult(
                success=False,
                error=f"工具 {function_name} 暂时不可用（已触发熔断保护）。请稍后再试，或尝试其他方式。"
            )
        
        # 2. 执行主工具（带重试）
        result = await self._execute_with_retry(
            function_name, arguments, context, context_kwargs
        )
        
        # 3. 如果主工具成功，记录成功并返回
        if result.success:
            self.circuit_breaker.record_success(function_name)
            return result
        
        # 4. 主工具失败，记录失败
        is_failing = self.circuit_breaker.record_failure(function_name)
        if is_failing:
            logger.error(f"[CircuitBreaker] Tool {function_name} has reached failure threshold!")
        
        # 5. 尝试降级方案
        logger.info(f"[Fallback] Main tool {function_name} failed, trying fallback...")
        fallback_result = await self._try_fallback(function_name, arguments, context, context_kwargs)
        
        if fallback_result and fallback_result.success:
            logger.info(f"[Fallback] Successfully used fallback for {function_name}")
            return SkillResult(
                success=True,
                output=fallback_result.output,
                metadata={"used_fallback": True, "original_error": result.error}
            )
        
        # 6. 所有方案都失败，返回原始错误（但包装得更友好）
        return SkillResult(
            success=False,
            error=self._format_error_message(function_name, result.error, arguments),
            metadata={"retry_count": result.metadata.get("retry_count", 0) if result.metadata else 0}
        )
    
    async def _execute_with_retry(
        self, 
        function_name: str, 
        arguments: dict, 
        context: SkillContext,
        context_kwargs: dict,
        max_retries: int = 2
    ) -> SkillResult:
        """带指数退避重试的执行"""
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                logger.debug(f"[Execute] Attempt {attempt + 1}/{max_retries + 1} for {function_name}")
                
                result = await self._execute_single_tool(
                    function_name, arguments, context, context_kwargs
                )
                
                if result.success:
                    if attempt > 0:
                        logger.info(f"[Execute] Tool {function_name} succeeded after {attempt} retries")
                    return result
                
                last_error = result.error
                
                # 如果不是最后一次尝试，等待后重试
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # 指数退避: 1s, 2s
                    logger.warning(f"[Execute] Tool {function_name} failed (attempt {attempt + 1}), "
                                   f"retrying in {wait_time}s... Error: {last_error}")
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                last_error = str(e)
                logger.error(f"[Execute] Exception in attempt {attempt + 1}: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
        
        return SkillResult(
            success=False,
            error=f"工具 {function_name} 在 {max_retries + 1} 次尝试后仍然失败。最后一次错误: {last_error}",
            metadata={"retry_count": max_retries}
        )
    
    async def _execute_single_tool(
        self,
        function_name: str,
        arguments: dict,
        context: SkillContext,
        context_kwargs: dict
    ) -> SkillResult:
        """执行单个工具（无重试逻辑）"""
        # 1. 尝试 Native Skills
        if function_name in self.skills:
            return await self.skills[function_name].execute(context, **arguments)
        
        # 2. 尝试 Custom Plugins
        if function_name in self.plugin_manager.tools_map:
            result = await self.plugin_manager.execute_tool(
                function_name, arguments, 
                {"agent": self.agent, **context_kwargs}
            )
            if isinstance(result, SkillResult):
                return result
            return SkillResult(success=True, output=str(result))
        
        # 3. 尝试 OpenClaw Skills
        oc_skills = self.openclaw_adapter.list_skills()
        if function_name in oc_skills:
            return await self.openclaw_adapter.execute_tool(
                function_name, arguments, context_kwargs.get("user_id")
            )
        
        return SkillResult(success=False, error=f"工具未找到: {function_name}")
    
    async def _try_fallback(
        self,
        failed_tool: str,
        original_args: dict,
        context: SkillContext,
        context_kwargs: dict
    ) -> Optional[SkillResult]:
        """尝试备用方案"""
        fallback_tools = self.fallback_chain.get(failed_tool, [])
        
        for fallback_tool in fallback_tools:
            try:
                logger.info(f"[Fallback] Trying {fallback_tool} as fallback for {failed_tool}")
                
                # 转换参数格式（如果需要）
                fallback_args = self._adapt_arguments(failed_tool, fallback_tool, original_args)
                
                result = await self._execute_single_tool(
                    fallback_tool, fallback_args, context, context_kwargs
                )
                
                if result.success:
                    return result
                    
            except Exception as e:
                logger.warning(f"[Fallback] Fallback tool {fallback_tool} also failed: {e}")
                continue
        
        return None
    
    def _adapt_arguments(self, from_tool: str, to_tool: str, args: dict) -> dict:
        """转换参数格式以适应备用工具"""
        # 简单的参数映射
        if from_tool == "get_current_weather" and to_tool == "run_openclaw_skill":
            return {
                "skill_name": "weather",
                "action": "run",
                "params": {"location": args.get("location", "Unknown")}
            }
        return args
    
    def _format_error_message(self, tool_name: str, error: str, args: dict) -> str:
        """格式化错误消息，使其对用户更友好"""
        # 隐藏技术性错误，提供有用的建议
        user_friendly_errors = {
            "get_current_weather": 
                f"暂时无法获取 {args.get('location', '该地区')} 的天气信息。"
                f"可能的原因：网络连接问题、天气服务暂时不可用。"
                f"建议：请稍后重试，或手动查询天气网站。",
            "memory_tool":
                "记忆功能暂时不可用。这可能是因为存储空间不足或索引服务异常。",
            "run_openclaw_skill":
                "外部技能调用失败。请检查该技能是否已正确安装和配置。"
        }
        
        return user_friendly_errors.get(tool_name, f"工具 {tool_name} 执行失败: {error}")
    
    async def close(self):
        await self.openclaw_adapter.close()
