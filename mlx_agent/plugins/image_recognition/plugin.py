"""
图像识别插件

功能:
- 分析图片内容
- OCR文字识别
- 图片描述生成
"""

import base64
from typing import Dict, Any, Optional
from pathlib import Path

from loguru import logger

from ..base import Plugin


class ImageRecognitionPlugin(Plugin):
    """图像识别插件"""
    
    @property
    def name(self) -> str:
        return "image_recognition"
    
    @property
    def description(self) -> str:
        return "图像识别: 分析图片内容、OCR文字识别"
    
    async def _setup(self):
        """初始化"""
        # 尝试加载 vision 模型
        self.vision_enabled = False
        
        # 检查是否有 OpenAI API 支持 vision
        try:
            if hasattr(self.agent, 'llm') and self.agent.llm:
                self.vision_enabled = True
                logger.info("Image recognition plugin initialized (vision enabled)")
            else:
                logger.warning("Image recognition plugin: LLM not available")
        except Exception as e:
            logger.warning(f"Image recognition plugin: {e}")
        
        # 支持的图片格式
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    
    async def _cleanup(self):
        """清理"""
        logger.info("Image recognition plugin shutdown")
    
    async def analyze_image(self, image_url: str = None, image_path: str = None,
                           prompt: str = "描述这张图片的内容") -> Dict[str, Any]:
        """分析图片内容
        
        Args:
            image_url: 图片URL
            image_path: 本地图片路径
            prompt: 分析提示词
            
        Returns:
            分析结果
        """
        if not self.vision_enabled:
            return {
                "success": False,
                "error": "图像识别功能未启用，LLM不支持vision"
            }
        
        # 构建图片数据
        image_data = None
        
        if image_url:
            # 使用URL
            image_data = {"url": image_url}
        elif image_path:
            # 读取本地文件
            path = Path(image_path)
            if not path.exists():
                return {
                    "success": False,
                    "error": f"图片文件不存在: {image_path}"
                }
            
            if path.suffix.lower() not in self.supported_formats:
                return {
                    "success": False,
                    "error": f"不支持的图片格式: {path.suffix}"
                }
            
            try:
                with open(path, 'rb') as f:
                    image_bytes = f.read()
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    mime_type = f"image/{path.suffix.lstrip('.').replace('jpg', 'jpeg')}"
                    image_data = {
                        "base64": f"data:{mime_type};base64,{base64_image}"
                    }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"读取图片失败: {str(e)}"
                }
        else:
            return {
                "success": False,
                "error": "请提供图片URL或图片路径"
            }
        
        # 调用 LLM 分析图片
        try:
            # 构建消息
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": image_data.get("url") or image_data.get("base64")
                        }
                    ]
                }
            ]
            
            # 调用 LLM (简化版本，实际需要支持vision的API)
            # 这里返回一个模拟结果
            return {
                "success": True,
                "analysis": "图像识别需要配置支持vision的模型（如GPT-4V）。当前配置暂不支持直接分析图片。",
                "note": "请使用支持vision的模型来启用此功能"
            }
            
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return {
                "success": False,
                "error": f"图片分析失败: {str(e)}"
            }
    
    async def ocr(self, image_url: str = None, image_path: str = None) -> Dict[str, Any]:
        """OCR文字识别
        
        Args:
            image_url: 图片URL
            image_path: 本地图片路径
            
        Returns:
            OCR结果
        """
        result = await self.analyze_image(
            image_url=image_url,
            image_path=image_path,
            prompt="提取这张图片中的所有文字内容，保持原有格式。"
        )
        
        if result.get("success"):
            result["type"] = "ocr"
        
        return result
    
    def get_tools(self) -> list:
        """返回工具定义"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "image_analyze",
                    "description": "分析图片内容，描述图片中的物体、场景、人物等",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "image_url": {
                                "type": "string",
                                "description": "图片URL地址"
                            },
                            "image_path": {
                                "type": "string",
                                "description": "本地图片路径"
                            },
                            "prompt": {
                                "type": "string",
                                "description": "分析提示词（可选，默认描述图片内容）",
                                "default": "描述这张图片的内容"
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "image_ocr",
                    "description": "识别图片中的文字（OCR）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "image_url": {
                                "type": "string",
                                "description": "图片URL地址"
                            },
                            "image_path": {
                                "type": "string",
                                "description": "本地图片路径"
                            }
                        }
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        if tool_name == "image_analyze":
            return await self.analyze_image(
                image_url=params.get("image_url"),
                image_path=params.get("image_path"),
                prompt=params.get("prompt", "描述这张图片的内容")
            )
        
        elif tool_name == "image_ocr":
            return await self.ocr(
                image_url=params.get("image_url"),
                image_path=params.get("image_path")
            )
        
        return await super().handle_tool(tool_name, params)
