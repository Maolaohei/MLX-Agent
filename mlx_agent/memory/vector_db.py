"""
向量数据库接口

支持 Milvus 和 Zilliz Cloud
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
import asyncio

from loguru import logger


class VectorDB(ABC):
    """向量数据库抽象基类"""
    
    @abstractmethod
    async def connect(self): pass
    
    @abstractmethod
    async def disconnect(self): pass
    
    @abstractmethod
    async def create_collection(self, name: str, dimension: int): pass
    
    @abstractmethod
    async def insert(self, collection: str, ids: List[str], vectors: List[List[float]], 
                     metadata: List[Dict]): pass
    
    @abstractmethod
    async def search(self, collection: str, vector: List[float], top_k: int) -> List[Dict]: pass
    
    @abstractmethod
    async def delete(self, collection: str, ids: List[str]): pass


class MilvusDB(VectorDB):
    """Milvus 向量数据库实现"""
    
    def __init__(self, host: str = "localhost", port: int = 19530, 
                 user: str = "", password: str = "", token: str = ""):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.token = token
        self.client = None
        
    async def connect(self):
        """连接 Milvus"""
        try:
            from pymilvus import MilvusClient
            
            uri = f"http://{self.host}:{self.port}"
            if self.token:
                self.client = MilvusClient(uri=uri, token=self.token)
            else:
                self.client = MilvusClient(uri=uri, user=self.user, password=self.password)
                
            logger.info(f"Connected to Milvus at {self.host}:{self.port}")
        except ImportError:
            logger.error("pymilvus not installed. Run: pip install pymilvus")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise
    
    async def disconnect(self):
        """断开连接"""
        if self.client:
            self.client.close()
            logger.info("Disconnected from Milvus")
    
    async def create_collection(self, name: str, dimension: int = 1536):
        """创建集合"""
        if self.client.has_collection(collection_name=name):
            logger.info(f"Collection '{name}' already exists")
            return
            
        self.client.create_collection(
            collection_name=name,
            dimension=dimension,
            metric_type="COSINE"
        )
        logger.info(f"Created collection: {name} (dim={dimension})")
    
    async def insert(self, collection: str, ids: List[str], 
                     vectors: List[List[float]], metadata: List[Dict]):
        """插入向量"""
        data = [
            {"id": id_, "vector": vector, **meta}
            for id_, vector, meta in zip(ids, vectors, metadata)
        ]
        self.client.insert(collection_name=collection, data=data)
        logger.debug(f"Inserted {len(ids)} vectors into {collection}")
    
    async def search(self, collection: str, vector: List[float], 
                     top_k: int = 5) -> List[Dict]:
        """搜索相似向量"""
        results = self.client.search(
            collection_name=collection,
            data=[vector],
            limit=top_k,
            output_fields=["*"]  # 返回所有字段
        )
        
        # 格式化结果
        formatted = []
        for result in results[0]:  # 第一个查询的结果
            formatted.append({
                "id": result["id"],
                "score": result["distance"],
                "content": result.get("content", ""),
                "metadata": {k: v for k, v in result.items() 
                           if k not in ["id", "vector", "distance"]}
            })
        return formatted
    
    async def delete(self, collection: str, ids: List[str]):
        """删除向量"""
        self.client.delete(collection_name=collection, ids=ids)
        logger.debug(f"Deleted {len(ids)} vectors from {collection}")


class ZillizDB(MilvusDB):
    """Zilliz Cloud 实现（与 Milvus API 相同）"""
    
    def __init__(self, uri: str, token: str):
        super().__init__()
        self.uri = uri
        self.token = token
        
    async def connect(self):
        """连接 Zilliz Cloud"""
        try:
            from pymilvus import MilvusClient
            self.client = MilvusClient(uri=self.uri, token=self.token)
            logger.info(f"Connected to Zilliz Cloud")
        except Exception as e:
            logger.error(f"Failed to connect to Zilliz: {e}")
            raise
