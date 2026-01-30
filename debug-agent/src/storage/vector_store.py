"""
向量存储 - 使用 ChromaDB 存储代码和历史 Case 的向量
"""
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings


class VectorStore:
    """向量数据库封装"""
    
    def __init__(self, persist_directory: str = "./data/chroma"):
        """
        初始化向量存储
        
        Args:
            persist_directory: 持久化目录
        """
        self.persist_directory = persist_directory
        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        
        # 初始化集合
        self._init_collections()
    
    def _init_collections(self):
        """初始化向量集合"""
        # 代码片段集合
        self.code_collection = self.client.get_or_create_collection(
            name="code_snippets",
            metadata={"description": "Code snippets from copilot-server"}
        )
        
        # 历史 Case 集合
        self.case_collection = self.client.get_or_create_collection(
            name="history_cases",
            metadata={"description": "Historical debug cases"}
        )
        
        # 日志模式集合
        self.log_pattern_collection = self.client.get_or_create_collection(
            name="log_patterns",
            metadata={"description": "Known error log patterns"}
        )
    
    # ============ 代码相关操作 ============
    
    def add_code_snippets(
        self,
        snippets: List[Dict[str, Any]],
        embeddings: Optional[List[List[float]]] = None
    ):
        """
        添加代码片段
        
        Args:
            snippets: 代码片段列表，每个包含 id, content, metadata
            embeddings: 可选的预计算向量
        """
        ids = [s["id"] for s in snippets]
        documents = [s["content"] for s in snippets]
        metadatas = [s.get("metadata", {}) for s in snippets]
        
        if embeddings:
            self.code_collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings
            )
        else:
            self.code_collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
    
    def search_code(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索代码片段
        
        Args:
            query: 查询文本
            n_results: 返回结果数量
            where: 过滤条件
            
        Returns:
            匹配的代码片段列表
        """
        results = self.code_collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where
        )
        
        return self._format_results(results)
    
    # ============ Case 相关操作 ============
    
    def add_cases(
        self,
        cases: List[Dict[str, Any]],
        embeddings: Optional[List[List[float]]] = None
    ):
        """
        添加历史 Case
        
        Args:
            cases: Case 列表，每个包含 id, content, metadata
            embeddings: 可选的预计算向量
        """
        ids = [c["id"] for c in cases]
        documents = [c["content"] for c in cases]
        metadatas = [c.get("metadata", {}) for c in cases]
        
        if embeddings:
            self.case_collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings
            )
        else:
            self.case_collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
    
    def search_cases(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        搜索相似历史 Case
        
        Args:
            query: 查询文本
            n_results: 返回结果数量
            where: 过滤条件
            
        Returns:
            匹配的 Case 列表
        """
        results = self.case_collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where
        )
        
        return self._format_results(results)
    
    def get_case_by_id(self, case_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取 Case"""
        results = self.case_collection.get(ids=[case_id])
        if results["ids"]:
            return {
                "id": results["ids"][0],
                "content": results["documents"][0] if results["documents"] else None,
                "metadata": results["metadatas"][0] if results["metadatas"] else {}
            }
        return None
    
    # ============ 日志模式相关操作 ============
    
    def add_log_patterns(self, patterns: List[Dict[str, Any]]):
        """添加日志错误模式"""
        ids = [p["id"] for p in patterns]
        documents = [p["pattern"] for p in patterns]
        metadatas = [
            {
                "category": p.get("category", ""),
                "severity": p.get("severity", ""),
                "description": p.get("description", ""),
                "solution": p.get("solution", "")
            }
            for p in patterns
        ]
        
        self.log_pattern_collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
    
    def search_log_patterns(
        self,
        error_text: str,
        n_results: int = 3
    ) -> List[Dict[str, Any]]:
        """搜索匹配的日志错误模式"""
        results = self.log_pattern_collection.query(
            query_texts=[error_text],
            n_results=n_results
        )
        
        return self._format_results(results)
    
    # ============ 工具方法 ============
    
    def _format_results(self, results: Dict) -> List[Dict[str, Any]]:
        """格式化查询结果"""
        formatted = []
        
        if not results["ids"] or not results["ids"][0]:
            return formatted
        
        for i, id_ in enumerate(results["ids"][0]):
            item = {
                "id": id_,
                "content": results["documents"][0][i] if results["documents"] else None,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results.get("distances") else None
            }
            # 转换距离为相似度分数 (ChromaDB 返回的是 L2 距离)
            if item["distance"] is not None:
                item["similarity"] = 1 / (1 + item["distance"])
            formatted.append(item)
        
        return formatted
    
    def get_stats(self) -> Dict[str, int]:
        """获取存储统计"""
        return {
            "code_snippets": self.code_collection.count(),
            "history_cases": self.case_collection.count(),
            "log_patterns": self.log_pattern_collection.count()
        }
    
    def clear_collection(self, collection_name: str):
        """清空指定集合"""
        if collection_name == "code_snippets":
            self.client.delete_collection("code_snippets")
            self.code_collection = self.client.create_collection(
                name="code_snippets",
                metadata={"description": "Code snippets from copilot-server"}
            )
        elif collection_name == "history_cases":
            self.client.delete_collection("history_cases")
            self.case_collection = self.client.create_collection(
                name="history_cases",
                metadata={"description": "Historical debug cases"}
            )
        elif collection_name == "log_patterns":
            self.client.delete_collection("log_patterns")
            self.log_pattern_collection = self.client.create_collection(
                name="log_patterns",
                metadata={"description": "Known error log patterns"}
            )
