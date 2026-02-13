"""
记忆系统 - Index1 版本

基于 index1 的 BM25 + 向量混合搜索架构：
- SQLite FTS5 全文搜索 (BM25)
- bge-m3 向量语义搜索 (Ollama)
- Ollama 不可用时自动降级为 BM25-only
- Markdown 文件持久化
"""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from loguru import logger

from mlx_agent.config import MemoryConfig


class Memory:
    """单条记忆"""
    def __init__(
        self,
        content: str,
        metadata: Optional[Dict] = None,
        memory_id: Optional[str] = None,
        created_at: Optional[datetime] = None
    ):
        self.content = content
        self.metadata = metadata or {}
        self.id = memory_id or self._generate_id()
        self.created_at = created_at or datetime.now()
    
    def _generate_id(self) -> str:
        """基于内容生成唯一 ID"""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


class MemorySystem:
    """记忆系统主类 - Index1 实现"""
    
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.memory_path = Path(config.path).resolve()  # 使用绝对路径
        self.index_path = self.memory_path / ".index1"
        self._initialized = False
        self._ollama_available = False
        
        logger.info(f"Memory system configured with path: {self.memory_path}")
    
    async def initialize(self):
        """初始化记忆系统"""
        # 创建记忆目录结构
        self.memory_path.mkdir(parents=True, exist_ok=True)
        (self.memory_path / "core").mkdir(exist_ok=True)
        (self.memory_path / "session").mkdir(exist_ok=True)
        (self.memory_path / "archive").mkdir(exist_ok=True)
        
        # 检查 index1 是否已安装
        if not self._check_index1():
            logger.warning("index1 not found. Please install: pip install index1[chinese]")
            raise RuntimeError("index1 is required for memory system")
        
        # 配置 index1
        self._setup_index1()
        
        # 检查 Ollama 可用性
        self._ollama_available = self._check_ollama()
        if self._ollama_available:
            logger.info("Ollama detected, vector search enabled")
        else:
            logger.warning("Ollama not available, using BM25-only mode")
        
        self._initialized = True
        logger.info("Memory system initialized with index1")
    
    def _check_index1(self) -> bool:
        """检查 index1 是否已安装"""
        try:
            result = subprocess.run(
                ["which", "index1"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_ollama(self) -> bool:
        """检查 Ollama 是否可用"""
        try:
            import httpx
            response = httpx.get("http://localhost:11434/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False
    
    def _setup_index1(self):
        """配置 index1"""
        try:
            # 配置 embedding 模型为 bge-m3
            subprocess.run(
                ["index1", "config", "embedding_model", "bge-m3"],
                capture_output=True,
                check=False
            )
            logger.info("index1 configured with bge-m3 embedding model")
        except Exception as e:
            logger.warning(f"Failed to configure index1: {e}")
    
    def _run_index1_index(self):
        """运行 index1 index 命令"""
        try:
            # 索引记忆目录
            for subdir in ["core", "session", "archive"]:
                dir_path = self.memory_path / subdir
                if dir_path.exists() and any(dir_path.iterdir()):
                    result = subprocess.run(
                        ["index1", "index", str(dir_path), "--force"],
                        capture_output=True,
                        text=True,
                        check=False,
                        cwd=str(self.memory_path)
                    )
                    if result.returncode != 0:
                        logger.error(f"Failed to index {subdir}: {result.stderr}")
                    else:
                        logger.debug(f"Indexed {subdir}")
        except Exception as e:
            logger.warning(f"Failed to index memories: {e}")
    
    async def add(
        self,
        content: str,
        metadata: Optional[Dict] = None,
        level: str = "P1"  # P0: 核心, P1: 会话, P2: 临时
    ) -> Memory:
        """添加记忆
        
        Args:
            content: 记忆内容
            metadata: 元数据
            level: 记忆级别 (P0/P1/P2)
            
        Returns:
            创建的记忆对象
        """
        memory = Memory(content, metadata)
        
        # 检查重复（基于内容哈希）
        if await self._check_duplicate(content):
            logger.debug(f"Duplicate memory detected: {memory.id[:8]}")
            return memory
        
        # 保存到 Markdown 文件
        await self._save_to_file(memory, level)
        
        # 重新索引
        self._run_index1_index()
        
        logger.debug(f"Added memory: {memory.id[:8]}...")
        return memory
    
    async def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """搜索记忆
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            相关记忆列表
        """
        if not self._initialized:
            logger.warning("Memory system not initialized")
            return []
        
        results = []
        
        # 对每个子目录进行搜索
        for subdir in ["core", "session", "archive"]:
            dir_path = self.memory_path / subdir
            if not dir_path.exists():
                continue
            
            try:
                # 构建 index1 search 命令
                cmd = ["index1", "search", query, "--limit", str(top_k), "--json"]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(dir_path)
                )
                
                if result.returncode == 0:
                    # 解析 JSON 输出
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if line:
                            try:
                                item = json.loads(line)
                                results.append({
                                    "id": item.get("id", ""),
                                    "content": item.get("content", ""),
                                    "score": item.get("score", 0),
                                    "metadata": item.get("metadata", {}),
                                    "source": subdir
                                })
                            except json.JSONDecodeError:
                                continue
                
            except Exception as e:
                logger.warning(f"Search failed in {subdir}: {e}")
        
        # 按分数排序并去重
        results = sorted(results, key=lambda x: x["score"], reverse=True)
        seen_ids = set()
        unique_results = []
        for r in results:
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                unique_results.append(r)
        
        logger.debug(f"Found {len(unique_results)} memories for: {query[:50]}...")
        return unique_results[:top_k]
    
    async def delete(self, memory_id: str) -> bool:
        """删除记忆
        
        Args:
            memory_id: 记忆 ID
            
        Returns:
            是否成功删除
        """
        # 从文件系统中删除
        deleted = False
        for subdir in ["core", "session", "archive"]:
            dir_path = self.memory_path / subdir
            if not dir_path.exists():
                continue
            
            # 查找包含该 ID 的文件
            for md_file in dir_path.glob("*.md"):
                content = md_file.read_text(encoding="utf-8")
                if memory_id in content:
                    # 移除该记忆条目
                    lines = content.split('\n')
                    new_lines = []
                    skip_until_next = False
                    
                    for line in lines:
                        if line.startswith(f"## [{memory_id[:8]}"):
                            skip_until_next = True
                            continue
                        if skip_until_next:
                            if line.startswith("## ["):
                                skip_until_next = False
                            else:
                                continue
                        new_lines.append(line)
                    
                    md_file.write_text('\n'.join(new_lines), encoding="utf-8")
                    deleted = True
                    break
        
        if deleted:
            # 重新索引
            self._run_index1_index()
            logger.debug(f"Deleted memory: {memory_id[:8]}...")
        
        return deleted
    
    async def _check_duplicate(self, content: str) -> bool:
        """检查是否已存在相似记忆"""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        # 搜索相似内容
        results = await self.search(content[:50], top_k=3)
        
        for result in results:
            if result["id"].startswith(content_hash):
                return True
            # 内容相似度检查
            result_content = result.get("content", "")
            if self._similarity(content, result_content) > 0.9:
                return True
        
        return False
    
    def _similarity(self, text1: str, text2: str) -> float:
        """简单的文本相似度计算"""
        # 使用简单的字符级相似度
        if not text1 or not text2:
            return 0.0
        
        # 转换为小写并分词
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union) if union else 0.0
    
    async def _save_to_file(self, memory: Memory, level: str):
        """保存记忆到 Markdown 文件"""
        # 根据级别选择目录
        if level == "P0":
            dir_path = self.memory_path / "core"
        elif level == "P1":
            dir_path = self.memory_path / "session"
        else:
            dir_path = self.memory_path / "archive"
        
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # 按日期组织文件
        today = datetime.now().strftime("%Y-%m-%d")
        file_path = dir_path / f"{today}.md"
        
        # 追加到文件
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"\n## [{memory.id[:8]}] {memory.created_at.strftime('%H:%M')}\n")
            f.write(f"{memory.content}\n")
            if memory.metadata:
                metadata_str = json.dumps(memory.metadata, ensure_ascii=False)
                f.write(f"<!-- metadata: {metadata_str} -->\n")
    
    async def close(self):
        """关闭记忆系统"""
        logger.info("Memory system closed")
    
    # 兼容性方法
    async def index_documents(self, documents: List[Dict[str, Any]], force: bool = False):
        """批量索引文档（兼容方法）"""
        for doc in documents:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            level = metadata.get("level", "P1")
            await self.add(content, metadata, level)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            "total_memories": 0,
            "by_level": {"P0": 0, "P1": 0, "P2": 0},
            "ollama_available": self._ollama_available
        }
        
        for subdir, level in [("core", "P0"), ("session", "P1"), ("archive", "P2")]:
            dir_path = self.memory_path / subdir
            if dir_path.exists():
                count = len(list(dir_path.glob("*.md")))
                stats["by_level"][level] = count
                stats["total_memories"] += count
        
        return stats
