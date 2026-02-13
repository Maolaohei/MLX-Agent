"""
LLM 客户端 - 支持多模型、故障转移和工具调用

调用 OpenAI-compatible API，支持主备模型切换
"""

import asyncio
import json
from typing import List, Dict, Optional, Any, Union
import httpx
from loguru import logger


class LLMClient:
    """LLM 客户端 - 支持主备模型"""
    
    def __init__(
        self,
        primary_config: Dict,
        fallback_config: Optional[Dict] = None,
        failover_enabled: bool = True
    ):
        """
        Args:
            primary_config: 主模型配置
            fallback_config: 备用模型配置
            failover_enabled: 是否启用故障转移
        """
        self.primary_config = primary_config
        self.fallback_config = fallback_config
        self.failover_enabled = failover_enabled and fallback_config is not None
        
        self.current_config = primary_config
        self.client = httpx.AsyncClient(timeout=60.0)
        
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
        reasoning: bool = False
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
            
        Returns:
            完整消息对象 (Dict)，包含 content 和 tool_calls
        """
        # 如果强制指定模型
        if force_model == "fallback" and self.fallback_config:
            config = self.fallback_config
        else:
            config = self.current_config
        
        # 尝试主模型
        try:
            response = await self._call_api(
                config, messages, temperature, max_tokens, tools, tool_choice, reasoning
            )
            self.current_config = config  # 成功后更新当前配置
            return response
        except Exception as e:
            logger.warning(f"Primary model failed: {e}")
            
            # 如果主模型失败且启用了故障转移
            if self.failover_enabled and config == self.primary_config:
                logger.info(f"Switching to fallback model: {self.fallback_config['model']}")
                try:
                    # 注意：备用模型可能不支持 tools，如果不支持需要降级处理
                    # 这里假设备用模型也支持 tools，或者是 Kimi 2.5 (部分支持)
                    # 如果备用模型不支持 tools，调用者应该处理异常或不传 tools
                    response = await self._call_api(
                        self.fallback_config, messages, temperature, max_tokens, tools, tool_choice, reasoning
                    )
                    self.current_config = self.fallback_config
                    logger.info("Fallback model succeeded")
                    return response
                except Exception as e2:
                    logger.error(f"Fallback model also failed: {e2}")
                    raise Exception(f"所有模型均不可用。主: {e}, 备: {e2}")
            else:
                raise e
    
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
        """调用 API"""
        api_base = config['api_base'].rstrip('/')
        url = f"{api_base}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json"
        }
        
        # 如果有 auth_token，添加到 headers
        if config.get('auth_token'):
            headers['x-api-key'] = config['auth_token']
        
        data = {
            "model": config['model'],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        if tools:
            data["tools"] = tools
            if tool_choice:
                data["tool_choice"] = tool_choice
        
        # Kimi k2.5 思考模式
        if reasoning:
            data["reasoning"] = True
            logger.debug(f"[LLM] Reasoning mode enabled")
        
        logger.debug(f"[LLM] Calling {config['model']} at {api_base}")
        if tools:
            logger.debug(f"[LLM] Tools count: {len(tools)}")
        
        response = await self.client.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        message = result["choices"][0]["message"]
        
        # 记录响应
        content = message.get("content")
        tool_calls = message.get("tool_calls")
        
        if content:
            logger.debug(f"[LLM] Content: {content[:50]}...")
        if tool_calls:
            logger.debug(f"[LLM] Tool calls: {len(tool_calls)}")
            
        return message
    
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
