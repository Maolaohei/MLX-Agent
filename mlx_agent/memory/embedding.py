"""
Embedding 生成器

支持多种 embedding 提供商
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import asyncio

import httpx
from loguru import logger


class EmbeddingProvider(ABC):
    """Embedding 提供商抽象基类"""
    
    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """将文本列表转换为向量"""
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        pass


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI Embedding"""
    
    def __init__(self, api_key: str, model: str = "text-embedding-3-small", 
                 api_base: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.api_base = api_base or "https://api.openai.com/v1"
        self._dimension = 1536  # text-embedding-3-small
        
    @property
    def dimension(self) -> int:
        return self._dimension
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """生成 embedding"""
        if not texts:
            return []
            
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_base}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "input": texts
                },
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            
            # 按索引排序
            embeddings = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in embeddings]


class LocalEmbedding(EmbeddingProvider):
    """本地 Embedding（使用 sentence-transformers）"""
    
    def __init__(self, model_name: str = "BAAI/bge-large-zh-v1.5"):
        self.model_name = model_name
        self._model = None
        self._dimension = 1024  # bge-large-zh
        
    @property
    def dimension(self) -> int:
        return self._dimension
    
    def _load_model(self):
        """懒加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading local embedding model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
                logger.info("Model loaded successfully")
            except ImportError:
                logger.error("sentence-transformers not installed. "
                           "Run: pip install sentence-transformers")
                raise
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """生成 embedding（在线程池中运行）"""
        if not texts:
            return []
            
        self._load_model()
        
        # 在线程池中运行 CPU 密集型任务
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, self._model.encode, texts
        )
        
        return embeddings.tolist()


class OllamaEmbedding(EmbeddingProvider):
    """Ollama 本地 Embedding"""
    
    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self._dimension = 768  # nomic-embed-text
        
    @property
    def dimension(self) -> int:
        return self._dimension
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """生成 embedding"""
        if not texts:
            return []
            
        embeddings = []
        async with httpx.AsyncClient() as client:
            for text in texts:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                embeddings.append(data["embedding"])
                
        return embeddings


class EmbeddingFactory:
    """Embedding 工厂"""
    
    @staticmethod
    def create(provider: str, **kwargs) -> EmbeddingProvider:
        """创建 embedding 提供商
        
        Args:
            provider: 提供商名称 (openai, local, ollama)
            **kwargs: 提供商特定参数
        """
        if provider == "openai":
            return OpenAIEmbedding(**kwargs)
        elif provider == "local":
            return LocalEmbedding(**kwargs)
        elif provider == "ollama":
            return OllamaEmbedding(**kwargs)
        else:
            raise ValueError(f"Unknown embedding provider: {provider}")
