"""
Telegram 消息发送插件

功能:
- 发送文本消息
- 发送图片
- 发送通知
"""

from typing import Dict, Any, Optional
from pathlib import Path

from loguru import logger

from ..base import Plugin


class TelegramSenderPlugin(Plugin):
    """Telegram 消息发送插件"""
    
    @property
    def name(self) -> str:
        return "telegram_sender"
    
    @property
    def description(self) -> str:
        return "Telegram消息发送: 主动发送消息到指定聊天"
    
    async def _setup(self):
        """初始化"""
        # 获取 Telegram 适配器
        self.telegram = None
        if hasattr(self.agent, 'telegram'):
            self.telegram = self.agent.telegram
        
        # 默认聊天ID（从配置获取）
        self.default_chat_id = self.get_config("default_chat_id", "")
        
        logger.info("Telegram sender plugin initialized")
    
    async def _cleanup(self):
        """清理"""
        logger.info("Telegram sender plugin shutdown")
    
    async def send_message(self, chat_id: str = None, text: str = None, 
                          message: str = None) -> Dict[str, Any]:
        """发送文本消息
        
        Args:
            chat_id: 聊天ID (可选，默认使用配置中的ID)
            text: 消息内容
            message: 消息内容（与text二选一）
            
        Returns:
            发送结果
        """
        # 参数兼容处理
        content = text or message
        target_chat = chat_id or self.default_chat_id
        
        if not content:
            return {
                "success": False,
                "error": "消息内容不能为空"
            }
        
        if not target_chat:
            return {
                "success": False,
                "error": "未指定聊天ID，也未配置默认聊天ID"
            }
        
        if not self.telegram:
            return {
                "success": False,
                "error": "Telegram 适配器未初始化"
            }
        
        try:
            success = await self.telegram.send_message(target_chat, content)
            
            if success:
                return {
                    "success": True,
                    "message": "消息已发送",
                    "chat_id": target_chat,
                    "text": content[:100] + "..." if len(content) > 100 else content
                }
            else:
                return {
                    "success": False,
                    "error": "发送失败，请检查聊天ID是否正确"
                }
                
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return {
                "success": False,
                "error": f"发送失败: {str(e)}"
            }
    
    async def send_notification(self, message: str, chat_id: str = None) -> Dict[str, Any]:
        """发送通知（快捷方法）
        
        Args:
            message: 通知内容
            chat_id: 聊天ID (可选)
            
        Returns:
            发送结果
        """
        # 添加通知前缀
        notification = f"🔔 通知\n\n{message}"
        return await self.send_message(chat_id=chat_id, text=notification)
    
    async def broadcast(self, message: str, chat_ids: list = None) -> Dict[str, Any]:
        """广播消息到多个聊天
        
        Args:
            message: 消息内容
            chat_ids: 聊天ID列表 (可选，默认使用配置的列表)
            
        Returns:
            广播结果
        """
        targets = chat_ids or self.get_config("broadcast_chat_ids", [])
        
        if not targets:
            return {
                "success": False,
                "error": "未指定聊天ID列表"
            }
        
        results = []
        success_count = 0
        
        for chat_id in targets:
            result = await self.send_message(chat_id=chat_id, text=message)
            results.append({
                "chat_id": chat_id,
                "success": result.get("success"),
                "error": result.get("error")
            })
            if result.get("success"):
                success_count += 1
        
        return {
            "success": success_count > 0,
            "total": len(targets),
            "success_count": success_count,
            "failed_count": len(targets) - success_count,
            "details": results
        }
    
    def get_tools(self) -> list:
        """返回工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "telegram_send",
                    "description": "发送Telegram消息到指定聊天，如果不指定chat_id则发送到默认聊天",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "chat_id": {
                                "type": "string",
                                "description": "聊天ID（可选，默认使用配置中的ID）"
                            },
                            "text": {
                                "type": "string",
                                "description": "消息内容"
                            }
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "telegram_notify",
                    "description": "发送Telegram通知（带🔔前缀）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "通知内容"
                            },
                            "chat_id": {
                                "type": "string",
                                "description": "聊天ID（可选）"
                            }
                        },
                        "required": ["message"]
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        if tool_name == "telegram_send":
            return await self.send_message(
                chat_id=params.get("chat_id"),
                text=params.get("text")
            )
        
        elif tool_name == "telegram_notify":
            return await self.send_notification(
                message=params.get("message"),
                chat_id=params.get("chat_id")
            )
        
        return await super().handle_tool(tool_name, params)
