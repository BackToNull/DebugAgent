"""
Debug Agent 主服务 - 编排预处理、检索、分析的完整流程
"""
import uuid
from typing import Dict, Any, Optional
from datetime import datetime

from src.models.schemas import BugInput, AnalysisResult, HistoryCase
from src.core.preprocessor import Preprocessor
from src.core.retriever import HybridRetriever
from src.core.analyzer import LLMAnalyzer
from src.storage.vector_store import VectorStore


class DebugAgentService:
    """Debug Agent 核心服务"""
    
    def __init__(
        self,
        openai_api_key: str,
        llm_model: str = "gpt-4-turbo-preview",
        openai_base_url: Optional[str] = None,
        chroma_persist_dir: str = "./data/chroma"
    ):
        """
        初始化 Debug Agent 服务
        
        Args:
            openai_api_key: OpenAI API Key
            llm_model: LLM 模型名称
            openai_base_url: OpenAI API 基础 URL
            chroma_persist_dir: ChromaDB 持久化目录
        """
        # 初始化组件
        self.preprocessor = Preprocessor()
        self.vector_store = VectorStore(persist_directory=chroma_persist_dir)
        self.retriever = HybridRetriever(self.vector_store)
        self.analyzer = LLMAnalyzer(
            api_key=openai_api_key,
            model=llm_model,
            base_url=openai_base_url,
            verify_ssl=False  # 禁用 SSL 验证以解决代理/证书问题
        )
        
        # 存储分析历史（简单内存存储，生产环境应使用数据库）
        self._analysis_history: Dict[str, AnalysisResult] = {}
    
    async def analyze_bug(self, bug_input: BugInput) -> AnalysisResult:
        """
        分析 Bug 的主入口
        
        Args:
            bug_input: Bug 输入信息
            
        Returns:
            分析结果
        """
        print(f"[DEBUG] 开始分析 Bug...")
        
        # 生成 bug_id（如果没有提供）
        if not bug_input.bug_id:
            bug_input.bug_id = f"BUG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        
        print(f"[DEBUG] Bug ID: {bug_input.bug_id}")
        
        # 1. 预处理
        print(f"[DEBUG] 1. 预处理...")
        bug_dict = bug_input.model_dump()
        preprocessed = self.preprocessor.process(bug_dict)
        
        # 2. 构建检索查询
        print(f"[DEBUG] 2. 构建检索查询...")
        error_info = bug_input.error_info
        query = self._build_search_query(bug_input, preprocessed)
        print(f"[DEBUG] 查询: {query[:100]}")
        
        # 3. 多路检索
        print(f"[DEBUG] 3. 多路检索...")
        retrieval_results = await self.retriever.search(
            query=query,
            error_message=error_info.error_message,
            stack_trace=error_info.stack_trace
        )
        print(f"[DEBUG] 检索结果: code={len(retrieval_results.get('code', []))}, "
              f"case={len(retrieval_results.get('case', []))}, "
              f"log_pattern={len(retrieval_results.get('log_pattern', []))}")
        
        # 4. LLM 分析
        print(f"[DEBUG] 4. LLM 分析...")
        result = await self.analyzer.analyze(
            bug_info=bug_dict,
            preprocessed=preprocessed,
            retrieval_results=retrieval_results
        )
        print(f"[DEBUG] 分析完成: {result.summary[:50]}")
        
        # 5. 保存分析结果
        self._analysis_history[result.analysis_id] = result
        
        return result
    
    def _build_search_query(
        self,
        bug_input: BugInput,
        preprocessed: Dict[str, Any]
    ) -> str:
        """构建检索查询"""
        parts = []
        
        # 错误信息
        parts.append(bug_input.error_info.error_message)
        
        # 异常类型
        if preprocessed.get("parsed_stack", {}).get("exception_type"):
            parts.append(preprocessed["parsed_stack"]["exception_type"])
        
        # 错误关键词
        if preprocessed.get("error_keywords"):
            parts.extend(preprocessed["error_keywords"][:3])
        
        # 用户描述
        if bug_input.context and bug_input.context.user_description:
            parts.append(bug_input.context.user_description)
        
        return " ".join(parts)
    
    def get_analysis(self, analysis_id: str) -> Optional[AnalysisResult]:
        """获取分析结果"""
        return self._analysis_history.get(analysis_id)
    
    def list_analyses(self, limit: int = 20) -> list:
        """列出最近的分析结果"""
        results = list(self._analysis_history.values())
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results[:limit]
    
    # ============ 知识库管理 ============
    
    def add_history_case(self, case: HistoryCase):
        """添加历史 Case 到知识库"""
        embedding_text = case.embedding_text or case.generate_embedding_text()
        
        self.vector_store.add_cases([{
            "id": case.case_id,
            "content": embedding_text,
            "metadata": {
                "title": case.problem.title,
                "root_cause": case.resolution.root_cause,
                "fix_type": case.resolution.fix_type.value,
                "fix_detail": case.resolution.fix_detail,
                "tags": ",".join(case.tags),
                "resolver": case.resolver or "",
                "created_at": case.created_at.isoformat()
            }
        }])
    
    def add_code_snippet(
        self,
        snippet_id: str,
        content: str,
        file_path: str,
        function_name: Optional[str] = None,
        start_line: Optional[int] = None
    ):
        """添加代码片段到知识库"""
        self.vector_store.add_code_snippets([{
            "id": snippet_id,
            "content": content,
            "metadata": {
                "file_path": file_path,
                "function_name": function_name or "",
                "start_line": start_line or 0
            }
        }])
    
    def get_knowledge_stats(self) -> Dict[str, int]:
        """获取知识库统计"""
        return self.vector_store.get_stats()
