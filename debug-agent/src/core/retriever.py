"""
检索模块 - 代码检索、Case 检索、多路召回
"""
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

from src.storage.vector_store import VectorStore


@dataclass
class RetrievalResult:
    """检索结果"""
    source: str           # 来源：code, case, log_pattern
    id: str
    content: str
    score: float          # 相似度得分
    metadata: Dict[str, Any]


class BaseRetriever(ABC):
    """检索器基类"""
    
    @abstractmethod
    async def search(
        self, 
        query: str, 
        top_k: int = 5,
        **kwargs
    ) -> List[RetrievalResult]:
        """执行检索"""
        pass


class CodeRetriever(BaseRetriever):
    """代码检索器"""
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        file_filter: Optional[str] = None,
        **kwargs
    ) -> List[RetrievalResult]:
        """
        检索相关代码片段
        
        Args:
            query: 查询文本（错误信息、函数名等）
            top_k: 返回数量
            file_filter: 可选的文件路径过滤
        """
        where = None
        if file_filter:
            where = {"file_path": {"$contains": file_filter}}
        
        results = self.vector_store.search_code(
            query=query,
            n_results=top_k,
            where=where
        )
        
        return [
            RetrievalResult(
                source="code",
                id=r["id"],
                content=r["content"],
                score=r.get("similarity", 0.5),
                metadata=r.get("metadata", {})
            )
            for r in results
        ]
    
    async def search_by_file(
        self,
        file_path: str,
        function_name: Optional[str] = None
    ) -> List[RetrievalResult]:
        """按文件路径精确搜索"""
        # 构建查询
        query = file_path
        if function_name:
            query = f"{file_path} {function_name}"
        
        return await self.search(query, file_filter=file_path)


class CaseRetriever(BaseRetriever):
    """历史 Case 检索器"""
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        tags: Optional[List[str]] = None,
        **kwargs
    ) -> List[RetrievalResult]:
        """
        检索相似历史 Case
        
        Args:
            query: 查询文本（错误描述、异常类型等）
            top_k: 返回数量
            tags: 可选的标签过滤
        """
        # TODO: 支持标签过滤
        results = self.vector_store.search_cases(
            query=query,
            n_results=top_k
        )
        
        return [
            RetrievalResult(
                source="case",
                id=r["id"],
                content=r["content"],
                score=r.get("similarity", 0.5),
                metadata=r.get("metadata", {})
            )
            for r in results
        ]


class LogPatternRetriever(BaseRetriever):
    """日志模式检索器"""
    
    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store
    
    async def search(
        self,
        query: str,
        top_k: int = 3,
        **kwargs
    ) -> List[RetrievalResult]:
        """
        检索匹配的日志错误模式
        
        Args:
            query: 错误日志文本
            top_k: 返回数量
        """
        results = self.vector_store.search_log_patterns(
            error_text=query,
            n_results=top_k
        )
        
        return [
            RetrievalResult(
                source="log_pattern",
                id=r["id"],
                content=r["content"],
                score=r.get("similarity", 0.5),
                metadata=r.get("metadata", {})
            )
            for r in results
        ]


class HybridRetriever:
    """
    混合检索器 - 多路召回 + 结果融合
    """
    
    def __init__(
        self,
        vector_store: VectorStore,
        weights: Optional[Dict[str, float]] = None
    ):
        """
        Args:
            vector_store: 向量存储实例
            weights: 各检索器权重，默认为 {"code": 0.3, "case": 0.5, "log_pattern": 0.2}
        """
        self.code_retriever = CodeRetriever(vector_store)
        self.case_retriever = CaseRetriever(vector_store)
        self.log_pattern_retriever = LogPatternRetriever(vector_store)
        
        self.weights = weights or {
            "code": 0.3,
            "case": 0.5,
            "log_pattern": 0.2
        }
    
    async def search(
        self,
        query: str,
        error_message: Optional[str] = None,
        stack_trace: Optional[str] = None,
        top_k: int = 10,
        enable_code: bool = True,
        enable_case: bool = True,
        enable_log_pattern: bool = True
    ) -> Dict[str, List[RetrievalResult]]:
        """
        多路召回检索
        
        Args:
            query: 主查询（通常是问题描述）
            error_message: 错误信息（用于代码和日志模式检索）
            stack_trace: 堆栈信息（用于代码检索）
            top_k: 每路返回的数量
            enable_*: 是否启用对应检索路
            
        Returns:
            按来源分组的检索结果
        """
        tasks = []
        task_sources = []
        
        # 构建各路检索查询
        code_query = error_message or query
        if stack_trace:
            # 从堆栈中提取关键文件和函数
            code_query = f"{code_query} {stack_trace[:500]}"
        
        case_query = query
        log_query = error_message or query
        
        # 并行执行多路检索
        if enable_code:
            tasks.append(self.code_retriever.search(code_query, top_k))
            task_sources.append("code")
        
        if enable_case:
            tasks.append(self.case_retriever.search(case_query, top_k))
            task_sources.append("case")
        
        if enable_log_pattern:
            tasks.append(self.log_pattern_retriever.search(log_query, top_k))
            task_sources.append("log_pattern")
        
        # 并行执行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 组织结果
        retrieval_results = {}
        for source, result in zip(task_sources, results):
            if isinstance(result, Exception):
                print(f"Warning: {source} retrieval failed: {result}")
                retrieval_results[source] = []
            else:
                retrieval_results[source] = result
        
        return retrieval_results
    
    def merge_and_rerank(
        self,
        results: Dict[str, List[RetrievalResult]],
        top_k: int = 10
    ) -> List[RetrievalResult]:
        """
        合并多路结果并重排序
        
        Args:
            results: 各路检索结果
            top_k: 最终返回数量
            
        Returns:
            合并后的排序结果
        """
        # 应用权重
        scored_results = []
        for source, items in results.items():
            weight = self.weights.get(source, 0.1)
            for item in items:
                # 加权分数
                weighted_score = item.score * weight
                scored_results.append((weighted_score, item))
        
        # 排序
        scored_results.sort(key=lambda x: x[0], reverse=True)
        
        # 去重（基于 content 的前 100 字符）
        seen = set()
        unique_results = []
        for score, item in scored_results:
            key = item.content[:100] if item.content else item.id
            if key not in seen:
                seen.add(key)
                # 更新为加权后的分数
                item.score = score
                unique_results.append(item)
        
        return unique_results[:top_k]
    
    async def retrieve(
        self,
        query: str,
        error_message: Optional[str] = None,
        stack_trace: Optional[str] = None,
        top_k: int = 10
    ) -> List[RetrievalResult]:
        """
        完整的检索流程：多路召回 + 融合 + 排序
        
        Args:
            query: 查询
            error_message: 错误信息
            stack_trace: 堆栈
            top_k: 返回数量
            
        Returns:
            融合排序后的结果
        """
        # 多路召回
        multi_results = await self.search(
            query=query,
            error_message=error_message,
            stack_trace=stack_trace,
            top_k=top_k
        )
        
        # 融合重排
        merged = self.merge_and_rerank(multi_results, top_k)
        
        return merged
