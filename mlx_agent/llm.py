"""
LLM 客户端 - 支持多模型、故障转移、工具调用和流式输出

调用 OpenAI-compatible API，支持主备模型切换和 SSE 流式
"""

import asyncio
import json
from typing import List, Dict, Optional, Any, Union, AsyncGenerator
import httpx
from loguru import logger


class LLMClient:
    """LLM 客户端 - 支持主备模型和流式输出"""
    
    def __init__(
        self,
        primary_config: Dict,
        fallback_config: Optional[Dict] = None,
        failover_enabled: bool = True,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Args:
            primary_config: 主模型配置
            fallback_config: 备用模型配置
            failover_enabled: 是否启用故障转移
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
        """
        self.primary_config = primary_config
        self.fallback_config = fallback_config
        self.failover_enabled = failover_enabled and fallback_config is not None
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self.current_config = primary_config
        self.client = httpx.AsyncClient(timeout=120.0)
        
        logger.info(f"LLMClient initialized")
        logger.info(f"  Primary: {primary_config.get('model', 'unknown')}")
        if self.failover_enabled:
            logger.info(f"  Fallback: {fallback_config.get('model', 'unknown')}")
    
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[Union[str, Dict]] = None,
        force_model: Optional[str] = None,
        reasoning: bool = False,
        auto_reasoning: bool = True
    ) -> Dict[str, Any]:
        """调用聊天接口，支持工具调用和故障转移
        
        Args:
            messages: 消息列表
            temperature: 温度
            max_tokens: 最大 token 数
            tools: 工具定义列表 (OpenAI 格式)
            tool_choice: 工具选择策略 ("auto", "none", 或指定工具)
            force_model: 强制使用指定模型 (primary/fallback)
            reasoning: 是否启用深度思考模式 (Kimi k2.5 支持)
            auto_reasoning: 是否自动根据工具调用启用思考模式 (默认 True)
            
        Returns:
            完整消息对象 (Dict)，包含 content 和 tool_calls
        """
        # 自动思考模式: 如果有工具，自动启用思考模式
        if auto_reasoning and not reasoning:
            if tools and len(tools) > 0:
                reasoning = True
                logger.debug(f"Auto-enabling reasoning mode (tools={len(tools)})")
        # 如果强制指定模型
        if force_model == "fallback" and self.fallback_config:
            config = self.fallback_config
        else:
            config = self.current_config
        
        # 指数退避重试
        for attempt in range(self.max_retries):
            try:
                response = await self._call_api(
                    config, messages, temperature, max_tokens, tools, tool_choice, reasoning
                )
                self.current_config = config  # 成功后更新当前配置
                return response
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed: {e}")
                
                # 如果是最后一次尝试，尝试故障转移
                if attempt == self.max_retries - 1:
                    if self.failover_enabled and config == self.primary_config:
                        logger.info(f"Switching to fallback model: {self.fallback_config['model']}")
                        try:
                            response = await self._call_api(
                                self.fallback_config, messages, temperature, max_tokens, 
                                tools, tool_choice, reasoning
                            )
                            self.current_config = self.fallback_config
                            logger.info("Fallback model succeeded")
                            return response
                        except Exception as e2:
                            logger.error(f"Fallback model also failed: {e2}")
                            raise Exception(f"所有模型均不可用。主: {e}, 备: {e2}")
                    else:
                        raise e
                
                # 等待后重试
                await asyncio.sleep(self.retry_delay * (2 ** attempt))
    
    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[Union[str, Dict]] = None,
        reasoning: bool = False,
        force_model: Optional[str] = None,
        auto_reasoning: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式调用聊天接口
        
        Args:
            messages: 消息列表
            temperature: 温度
            max_tokens: 最大 token 数
            tools: 工具定义列表
            tool_choice: 工具选择策略
            reasoning: 是否启用思考模式
            force_model: 强制使用指定模型
            auto_reasoning: 是否自动根据工具调用启用思考模式 (默认 True)
            
        Yields:
            流式响应片段，格式:
            - {"type": "content", "content": "文本片段"}
            - {"type": "reasoning", "content": "思考过程"}
            - {"type": "tool_call", "tool_call": {...}}
            - {"type": "done", "finish_reason": "..."}
            - {"type": "error", "error": "..."}
        """
        # 自动思考模式: 如果有工具，自动启用思考模式
        if auto_reasoning and not reasoning:
            if tools and len(tools) > 0:
                reasoning = True
                logger.debug(f"Auto-enabling reasoning mode for stream (tools={len(tools)})")
        
        config = self.fallback_config if force_model == "fallback" and self.fallback_config else self.current_config
        
        # 指数退避重试
        for attempt in range(self.max_retries):
            try:
                async for chunk in self._call_api_stream(
                    config, messages, temperature, max_tokens, tools, tool_choice, reasoning
                ):
                    yield chunk
                return
            except Exception as e:
                logger.warning(f"Stream attempt {attempt + 1}/{self.max_retries} failed: {e}")
                
                if attempt == self.max_retries - 1:
                    if self.failover_enabled and config == self.primary_config:
                        logger.info(f"Stream switching to fallback: {self.fallback_config['model']}")
                        try:
                            async for chunk in self._call_api_stream(
                                self.fallback_config, messages, temperature, max_tokens,
                                tools, tool_choice, reasoning
                            ):
                                yield chunk
                            self.current_config = self.fallback_config
                            return
                        except Exception as e2:
                            logger.error(f"Fallback stream also failed: {e2}")
                            yield {"type": "error", "error": f"所有模型流式调用均失败"}
                            return
                    else:
                        yield {"type": "error", "error": str(e)}
                        return
                
                await asyncio.sleep(self.retry_delay * (2 ** attempt))
    
    async def _call_api(
        self,
        config: Dict,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[Union[str, Dict]] = None,
        reasoning: bool = False
    ) -> Dict[str, Any]:
        """调用 API (非流式)"""
        api_base = config['api_base'].rstrip('/')
        url = f"{api_base}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json"
        }
        
        if config.get('auth_token'):
            headers['x-api-key'] = config['auth_token']
        
        data = {
            "model": config['model'],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        if tools:
            data["tools"] = tools
            if tool_choice:
                data["tool_choice"] = tool_choice
        
        if reasoning:
            data["reasoning"] = True
            logger.debug(f"[LLM] Reasoning mode enabled")
        
        logger.debug(f"[LLM] Calling {config['model']} at {api_base}")
        if tools:
            logger.debug(f"[LLM] Tools count: {len(tools)}")
        
        try:
            response = await self.client.post(url, headers=headers, json=data)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text[:200]}")
            raise
        
        result = response.json()
        message = result["choices"][0]["message"]
        
        content = message.get("content")
        tool_calls = message.get("tool_calls")
        
        if content:
            logger.debug(f"[LLM] Content: {content[:50]}...")
        if tool_calls:
            logger.debug(f"[LLM] Tool calls: {len(tool_calls)}")
            
        return message
    
    async def _call_api_stream(
        self,
        config: Dict,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[Union[str, Dict]] = None,
        reasoning: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """调用流式 API (SSE)"""
        api_base = config['api_base'].rstrip('/')
        url = f"{api_base}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream"
        }
        
        if config.get('auth_token'):
            headers['x-api-key'] = config['auth_token']
        
        data = {
            "model": config['model'],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }
        
        if tools:
            data["tools"] = tools
            if tool_choice:
                data["tool_choice"] = tool_choice
        
        if reasoning:
            data["reasoning"] = True
        
        logger.debug(f"[LLM Stream] Calling {config['model']}")
        
        accumulated_content = ""
        accumulated_reasoning = ""
        tool_calls_buffer = {}
        
        try:
            async with self.client.stream("POST", url, headers=headers, json=data, timeout=120.0) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    
                    # SSE 格式: data: {...}
                    if line.startswith("data: "):
                        json_str = line[6:]
                        
                        # 流结束标记
                        if json_str == "[DONE]":
                            yield {"type": "done", "finish_reason": "stop"}
                            break
                        
                        try:
                            chunk = json.loads(json_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            finish_reason = chunk.get("choices", [{}])[0].get("finish_reason")
                            
                            # 内容片段
                            content = delta.get("content")
                            if content:
                                accumulated_content += content
                                yield {"type": "content", "content": content}
                            
                            # 思考过程 (Kimi k2.5 支持)
                            reasoning_content = delta.get("reasoning_content")
                            if reasoning_content:
                                accumulated_reasoning += reasoning_content
                                yield {"type": "reasoning", "content": reasoning_content}
                            
                            # 工具调用
                            tool_calls = delta.get("tool_calls")
                            if tool_calls:
                                for tc in tool_calls:
                                    index = tc.get("index", 0)
                                    if index not in tool_calls_buffer:
                                        tool_calls_buffer[index] = {
                                            "id": tc.get("id", ""),
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""}
                                        }
                                    
                                    # 累积工具调用信息
                                    if tc.get("id"):
                                        tool_calls_buffer[index]["id"] = tc["id"]
                                    if tc.get("function", {}).get("name"):
                                        tool_calls_buffer[index]["function"]["name"] = tc["function"]["name"]
                                    if tc.get("function", {}).get("arguments"):
                                        tool_calls_buffer[index]["function"]["arguments"] += tc["function"]["arguments"]
                            
                            # 检查是否完成
                            if finish_reason:
                                # 如果有累积的工具调用，发送完整工具调用
                                if tool_calls_buffer:
                                    for tc in tool_calls_buffer.values():
                                        yield {"type": "tool_call", "tool_call": tc}
                                
                                yield {"type": "done", "finish_reason": finish_reason}
                                break
                                
                        except json.JSONDecodeError:
                            logger.debug(f"[LLM Stream] JSON decode error: {json_str[:100]}")
                            continue
                        except Exception as e:
                            logger.error(f"[LLM Stream] Error processing chunk: {e}")
                            continue
                            
        except httpx.HTTPStatusError as e:
            error_text = await e.response.aread()
            logger.error(f"[LLM Stream] HTTP error: {e.response.status_code} - {error_text[:200]}")
            yield {"type": "error", "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            logger.error(f"[LLM Stream] Error: {e}")
            yield {"type": "error", "error": str(e)}
    
    async def simple_chat(self, user_message: str, system_prompt: Optional[str] = None) -> str:
        """简单对话 (仅返回文本)"""
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": user_message})
        
        try:
            response = await self.chat(messages)
            return response.get("content", "") or ""
        except Exception as e:
            logger.error(f"Simple chat failed: {e}")
            return f"抱歉，遇到错误: {e}"
    
    async def simple_chat_stream(
        self, 
        user_message: str, 
        system_prompt: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """简单流式对话 (仅返回文本内容)"""
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": user_message})
        
        try:
            async for chunk in self.chat_stream(messages):
                if chunk["type"] == "content":
                    yield chunk["content"]
                elif chunk["type"] == "done":
                    break
                elif chunk["type"] == "error":
                    yield f"\n[错误: {chunk.get('error', 'unknown')}]"
                    break
        except Exception as e:
            logger.error(f"Simple chat stream failed: {e}")
            yield f"抱歉，遇到错误: {e}"
    
    def get_current_model(self) -> str:
        """获取当前使用的模型"""
        return self.current_config.get('model', 'unknown')
    
    def switch_to_primary(self):
        """切换回主模型"""
        if self.current_config != self.primary_config:
            logger.info(f"Switching back to primary: {self.primary_config['model']}")
            self.current_config = self.primary_config
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()
