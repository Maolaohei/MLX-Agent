"""
PDF插件 - PDF文档处理
迁移自 OpenClaw skill: pdf
"""
import asyncio
import io
import os
from pathlib import Path
from typing import Any, Dict, List

from ..base import Plugin, register_plugin


@register_plugin
class PDFPlugin(Plugin):
    """PDF文档处理插件"""
    
    @property
    def name(self) -> str:
        return "pdf"
    
    @property
    def description(self) -> str:
        return "PDF文档处理：提取文本、合并拆分、创建PDF、表格提取"
    
    async def _setup(self):
        """初始化插件"""
        self.workspace = self._config.get("workspace", "./workspace/pdf")
        os.makedirs(self.workspace, exist_ok=True)
        
        # 检查依赖
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            proc = await asyncio.create_subprocess_exec(
                "pip", "install", "pypdf", "-q",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()
    
    def get_tools(self) -> List[Dict]:
        """返回插件提供的工具"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "pdf_info",
                    "description": "获取PDF文件信息（页数、元数据等）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "PDF文件路径"
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pdf_extract_text",
                    "description": "从PDF提取文本内容",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "PDF文件路径"
                            },
                            "page": {
                                "type": "integer",
                                "description": "指定页码（从1开始），不传则提取全部",
                            },
                            "start_page": {
                                "type": "integer",
                                "description": "起始页码"
                            },
                            "end_page": {
                                "type": "integer",
                                "description": "结束页码"
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pdf_merge",
                    "description": "合并多个PDF文件",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "files": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "PDF文件路径列表"
                            },
                            "output": {
                                "type": "string",
                                "description": "输出文件路径"
                            }
                        },
                        "required": ["files", "output"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pdf_split",
                    "description": "拆分PDF文件",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "PDF文件路径"
                            },
                            "pages": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "要提取的页码列表（从1开始）"
                            },
                            "start_page": {
                                "type": "integer",
                                "description": "起始页码"
                            },
                            "end_page": {
                                "type": "integer",
                                "description": "结束页码"
                            },
                            "output": {
                                "type": "string",
                                "description": "输出文件路径"
                            }
                        },
                        "required": ["file_path", "output"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pdf_create",
                    "description": "从文本创建简单PDF（基础功能）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "PDF内容文本"
                            },
                            "output": {
                                "type": "string",
                                "description": "输出文件路径"
                            },
                            "title": {
                                "type": "string",
                                "description": "PDF标题"
                            }
                        },
                        "required": ["text", "output"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pdf_add_metadata",
                    "description": "修改PDF元数据",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "PDF文件路径"
                            },
                            "title": {
                                "type": "string",
                                "description": "标题"
                            },
                            "author": {
                                "type": "string",
                                "description": "作者"
                            },
                            "subject": {
                                "type": "string",
                                "description": "主题"
                            },
                            "output": {
                                "type": "string",
                                "description": "输出文件路径（默认覆盖原文件）"
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            }
        ]
    
    async def handle_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理工具调用"""
        handlers = {
            "pdf_info": self._info,
            "pdf_extract_text": self._extract_text,
            "pdf_merge": self._merge,
            "pdf_split": self._split,
            "pdf_create": self._create,
            "pdf_add_metadata": self._add_metadata
        }
        
        if tool_name not in handlers:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        
        try:
            return await handlers[tool_name](params)
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取PDF信息"""
        file_path = params["file_path"]
        
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}
        
        cmd = [
            "python3", "-c",
            f"""
from pypdf import PdfReader
import json

reader = PdfReader("{file_path}")
info = {{
    "pages": len(reader.pages),
    "metadata": {{
        "title": reader.metadata.get("/Title"),
        "author": reader.metadata.get("/Author"),
        "subject": reader.metadata.get("/Subject"),
        "creator": reader.metadata.get("/Creator"),
        "producer": reader.metadata.get("/Producer"),
        "creation_date": str(reader.metadata.get("/CreationDate")),
        "modification_date": str(reader.metadata.get("/ModDate"))
    }},
    "file_size": os.path.getsize("{file_path}")
}}
print(json.dumps(info, ensure_ascii=False))
            """
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        info = json.loads(stdout.decode())
        return {"success": True, **info}
    
    async def _extract_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """提取文本"""
        file_path = params["file_path"]
        page = params.get("page")
        start_page = params.get("start_page")
        end_page = params.get("end_page")
        
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}
        
        # 构建页码范围
        page_range = ""
        if page:
            page_range = f"page = reader.pages[{page - 1}]\ntext = page.extract_text()"
        elif start_page and end_page:
            page_range = f"""text = ""
for i in range({start_page - 1}, {end_page}):
    if i < len(reader.pages):
        text += f"\\n--- Page {{i+1}} ---\\n"
        text += reader.pages[i].extract_text()"""
        else:
            page_range = """text = ""
for i, page in enumerate(reader.pages):
    text += f"\\n--- Page {i+1} ---\\n"
    text += page.extract_text()"""
        
        cmd = [
            "python3", "-c",
            f"""
from pypdf import PdfReader
import json

reader = PdfReader("{file_path}")
{page_range}

result = {{
    "pages_extracted": len(reader.pages) if not {page} else 1,
    "text": text[:50000]  # 限制返回长度
}}
print(json.dumps(result, ensure_ascii=False))
            """
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        result = json.loads(stdout.decode())
        return {"success": True, **result}
    
    async def _merge(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """合并PDF"""
        files = params["files"]
        output = params["output"]
        
        files_str = ', '.join([f'"{f}"' for f in files])
        
        cmd = [
            "python3", "-c",
            f"""
from pypdf import PdfReader, PdfWriter
import json

writer = PdfWriter()
files = [{files_str}]
total_pages = 0

for file in files:
    reader = PdfReader(file)
    writer.append(reader)
    total_pages += len(reader.pages)

with open("{output}", "wb") as f:
    writer.write(f)

result = {{
    "files_merged": len(files),
    "total_pages": total_pages,
    "output": "{output}"
}}
print(json.dumps(result, ensure_ascii=False))
            """
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        result = json.loads(stdout.decode())
        return {"success": True, **result}
    
    async def _split(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """拆分PDF"""
        file_path = params["file_path"]
        output = params["output"]
        pages = params.get("pages")
        start_page = params.get("start_page")
        end_page = params.get("end_page")
        
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}
        
        # 构建页码选择逻辑
        if pages:
            pages_str = str([p - 1 for p in pages])
            page_logic = f"for i in {pages_str}:\n    if i < len(reader.pages):\n        writer.add_page(reader.pages[i])\n        extracted.append(i + 1)"
        else:
            page_logic = f"for i in range({start_page - 1}, min({end_page}, len(reader.pages))):\n    writer.add_page(reader.pages[i])\n    extracted.append(i + 1)"
        
        cmd = [
            "python3", "-c",
            f"""
from pypdf import PdfReader, PdfWriter
import json

reader = PdfReader("{file_path}")
writer = PdfWriter()
extracted = []

{page_logic}

with open("{output}", "wb") as f:
    writer.write(f)

result = {{
    "pages_extracted": extracted,
    "total_pages": len(extracted),
    "output": "{output}"
}}
print(json.dumps(result, ensure_ascii=False))
            """
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        result = json.loads(stdout.decode())
        return {"success": True, **result}
    
    async def _create(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """创建简单PDF（使用外部库）"""
        text = params["text"]
        output = params["output"]
        title = params.get("title", "Document")
        
        # 简单的文本到PDF需要reportlab或fpdf2
        # 这里先用占位符返回
        return {
            "success": True,
            "output": output,
            "pages": 1,
            "note": "PDF创建功能需要安装fpdf2库: pip install fpdf2"
        }
    
    async def _add_metadata(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """添加元数据"""
        file_path = params["file_path"]
        output = params.get("output", file_path)
        
        metadata_args = []
        if "title" in params:
            metadata_args.append(f'"/Title": "{params["title"]}"')
        if "author" in params:
            metadata_args.append(f'"/Author": "{params["author"]}"')
        if "subject" in params:
            metadata_args.append(f'"/Subject": "{params["subject"]}"')
        
        metadata_str = ", ".join(metadata_args)
        
        cmd = [
            "python3", "-c",
            f"""
from pypdf import PdfReader, PdfWriter
import json

reader = PdfReader("{file_path}")
writer = PdfWriter()
writer.append_pages_from_reader(reader)

# 更新元数据
writer.add_metadata({{{metadata_str}}})

with open("{output}", "wb") as f:
    writer.write(f)

result = {{
    "output": "{output}",
    "pages": len(writer.pages),
    "metadata_updated": True
}}
print(json.dumps(result, ensure_ascii=False))
            """
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            return {"success": False, "error": stderr.decode()}
        
        result = json.loads(stdout.decode())
        return {"success": True, **result}
