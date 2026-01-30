"""
LLM 分析模块 - Prompt 模板、分析链、结果解析
"""
import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid

import httpx
from openai import AsyncOpenAI

from src.models.schemas import (
    AnalysisResult,
    RootCause,
    CodeLocation,
    FixSuggestion,
    ImpactAssessment,
    SimilarCase,
    BugCategory,
    BugSeverity,
    FixType
)
from src.core.retriever import RetrievalResult


# ============ Prompt 模板 ============

SYSTEM_PROMPT = """你是一个专业的后端服务 Debug 专家，专门负责分析 copilot-server（一个 AI 代码助手的后端服务）的问题。

你的职责是：
1. 基于提供的错误信息、堆栈、日志和历史案例，分析问题的根因
2. 定位问题代码位置
3. 提供具体可行的修复建议
4. 评估问题的影响范围

请保持专业、准确、简洁。如果信息不足，请明确说明需要哪些额外信息。"""

ANALYSIS_PROMPT_TEMPLATE = """## 分析任务

请基于以下信息，按步骤分析这个 Bug：

### 问题信息

**错误类型**: {exception_type}
**错误信息**: {error_message}
**严重程度**: {severity}
**发生时间**: {timestamp}

{stack_trace_section}

{context_section}

{related_logs_section}

### 相似历史案例

{similar_cases_section}

### 相关代码片段

{code_snippets_section}

---

## 分析要求

请按以下步骤进行分析：

1. **理解问题**：这个错误的核心表现是什么？
2. **定位根因**：结合代码和历史案例，最可能的原因是什么？
3. **评估影响**：这个问题影响了哪些功能和用户？
4. **修复建议**：具体应该怎么修复？

## 输出格式

请严格按照以下 JSON 格式输出（不要包含 markdown 代码块标记）：

{{
    "summary": "一句话总结问题",
    "root_cause": {{
        "description": "根因的详细描述",
        "category": "分类，必须是以下之一：API_ERROR, DATA_ERROR, DEPENDENCY_ERROR, LOGIC_ERROR, CONFIG_ERROR, PERFORMANCE, UNKNOWN",
        "confidence": 0.85
    }},
    "location": {{
        "file": "问题代码所在文件路径",
        "line_start": 行号,
        "line_end": 结束行号或null,
        "function": "函数名"
    }},
    "fix_suggestion": {{
        "fix_type": "修复类型，必须是以下之一：code_change, config_change, rollback, escalate, no_action",
        "description": "修复方案的详细描述",
        "code_diff": "如果是代码修改，给出 diff 格式的改动；否则为 null",
        "test_verification": "如何验证修复是否成功"
    }},
    "impact_assessment": {{
        "affected_users": "预估受影响的用户范围描述",
        "affected_features": ["受影响的功能列表"],
        "urgency": "紧急程度，必须是：P0, P1, P2, P3"
    }},
    "additional_investigation": ["如果需要进一步排查，列出建议的排查步骤"]
}}"""


def format_stack_trace_section(parsed_stack: Optional[Dict]) -> str:
    """格式化堆栈信息部分"""
    if not parsed_stack:
        return "**堆栈信息**: 无"
    
    lines = ["**堆栈信息**:\n```"]
    for frame in parsed_stack.get("frames", [])[:10]:  # 最多显示10帧
        prefix = "[框架] " if frame.get("is_framework") else "[业务] "
        lines.append(f"{prefix}{frame['file']}:{frame['line']} in {frame['function']}")
        if frame.get("code"):
            lines.append(f"    {frame['code']}")
    lines.append("```")
    
    if parsed_stack.get("root_frame"):
        rf = parsed_stack["root_frame"]
        lines.append(f"\n**关键位置**: {rf['file']}:{rf['line']} in {rf['function']}")
    
    return "\n".join(lines)


def format_context_section(context: Optional[Dict]) -> str:
    """格式化上下文部分"""
    if not context:
        return ""
    
    parts = []
    if context.get("user_description"):
        parts.append(f"**用户描述**: {context['user_description']}")
    if context.get("request_payload"):
        parts.append(f"**请求参数**: {json.dumps(context['request_payload'], ensure_ascii=False)[:500]}")
    if context.get("response_payload"):
        parts.append(f"**响应内容**: {json.dumps(context['response_payload'], ensure_ascii=False)[:500]}")
    
    return "\n".join(parts) if parts else ""


def format_logs_section(logs: List[str]) -> str:
    """格式化日志部分"""
    if not logs:
        return "**相关日志**: 无"
    
    lines = ["**相关日志**:\n```"]
    for log in logs[:20]:  # 最多20条
        lines.append(log[:500])  # 每条最多500字符
    lines.append("```")
    return "\n".join(lines)


def format_similar_cases_section(cases: List[RetrievalResult]) -> str:
    """格式化相似案例部分"""
    if not cases:
        return "无相似历史案例"
    
    lines = []
    for i, case in enumerate(cases[:3], 1):  # 最多3个
        lines.append(f"**案例 {i}** (相似度: {case.score:.2f})")
        lines.append(case.content[:800])
        lines.append("")
    
    return "\n".join(lines)


def format_code_section(code_results: List[RetrievalResult]) -> str:
    """格式化代码片段部分"""
    if not code_results:
        return "无相关代码"
    
    lines = []
    for i, code in enumerate(code_results[:5], 1):  # 最多5个
        metadata = code.metadata or {}
        file_path = metadata.get("file_path", "unknown")
        lines.append(f"**代码片段 {i}** - `{file_path}` (相似度: {code.score:.2f})")
        lines.append("```")
        lines.append(code.content[:1000])
        lines.append("```")
        lines.append("")
    
    return "\n".join(lines)


class LLMAnalyzer:
    """LLM 分析器"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4-turbo-preview",
        base_url: Optional[str] = None,
        temperature: float = 0.2,
        verify_ssl: bool = False
    ):
        """
        初始化 LLM 分析器
        
        Args:
            api_key: OpenAI API Key
            model: 模型名称
            base_url: API 基础 URL（用于代理）
            temperature: 生成温度
            verify_ssl: 是否验证 SSL 证书
        """
        # 创建自定义 HTTP 客户端（处理 SSL 问题）
        http_client = httpx.AsyncClient(verify=verify_ssl)
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client
        )
        self.model = model
        self.temperature = temperature
    
    async def analyze(
        self,
        bug_info: Dict[str, Any],
        preprocessed: Dict[str, Any],
        retrieval_results: Dict[str, List[RetrievalResult]]
    ) -> AnalysisResult:
        """
        分析 Bug
        
        Args:
            bug_info: 原始 Bug 输入
            preprocessed: 预处理后的信息
            retrieval_results: 检索结果
            
        Returns:
            分析结果
        """
        # 构建 Prompt
        error_info = bug_info.get("error_info", {})
        parsed_stack = preprocessed.get("parsed_stack", {})
        
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            exception_type=parsed_stack.get("exception_type", "Unknown") if parsed_stack else "Unknown",
            error_message=error_info.get("error_message", "No error message"),
            severity=bug_info.get("severity", "P2"),
            timestamp=bug_info.get("timestamp", datetime.now().isoformat()),
            stack_trace_section=format_stack_trace_section(parsed_stack),
            context_section=format_context_section(bug_info.get("context")),
            related_logs_section=format_logs_section(preprocessed.get("aggregated_logs", [])),
            similar_cases_section=format_similar_cases_section(
                retrieval_results.get("case", [])
            ),
            code_snippets_section=format_code_section(
                retrieval_results.get("code", [])
            )
        )
        
        # 调用 LLM
        try:
            print(f"[DEBUG] 开始调用 LLM: {self.model}")
            # 智谱 AI 可能不支持 response_format，需要兼容处理
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.temperature,
                    response_format={"type": "json_object"},
                    timeout=60.0  # 60秒超时
                )
                print(f"[DEBUG] LLM 调用成功 (with response_format)")
            except Exception as e1:
                print(f"[DEBUG] 使用 response_format 失败: {e1}, 尝试降级...")
                # 降级：不使用 response_format
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.temperature,
                    timeout=60.0  # 60秒超时
                )
                print(f"[DEBUG] LLM 调用成功 (without response_format)")
        except Exception as e:
            print(f"[DEBUG] LLM 调用失败: {type(e).__name__}: {str(e)}")
            raise ConnectionError(f"LLM API 调用失败: {str(e)}")
        
        # 解析响应
        response_text = response.choices[0].message.content
        result = self._parse_response(response_text, bug_info, retrieval_results)
        
        return result
    
    def _parse_response(
        self,
        response_text: str,
        bug_info: Dict[str, Any],
        retrieval_results: Dict[str, List[RetrievalResult]]
    ) -> AnalysisResult:
        """解析 LLM 响应"""
        try:
            # 尝试直接解析 JSON
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 块
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                # 返回默认结果
                return self._create_fallback_result(bug_info, response_text)
        
        # 构建结果
        root_cause = RootCause(
            description=data.get("root_cause", {}).get("description", "Unable to determine"),
            category=self._parse_category(data.get("root_cause", {}).get("category")),
            confidence=data.get("root_cause", {}).get("confidence", 0.5)
        )
        
        location = None
        if data.get("location") and data["location"].get("file"):
            line_start = data["location"].get("line_start")
            # 如果 line_start 是 None，尝试设为 None（现在模型支持了）
            location = CodeLocation(
                file=data["location"]["file"],
                line_start=line_start if isinstance(line_start, int) else None,
                line_end=data["location"].get("line_end"),
                function=data["location"].get("function")
            )
        
        fix_suggestion = FixSuggestion(
            fix_type=self._parse_fix_type(data.get("fix_suggestion", {}).get("fix_type")),
            description=data.get("fix_suggestion", {}).get("description", ""),
            code_diff=data.get("fix_suggestion", {}).get("code_diff"),
            test_verification=data.get("fix_suggestion", {}).get("test_verification")
        )
        
        impact = data.get("impact_assessment", {})
        impact_assessment = ImpactAssessment(
            affected_users=impact.get("affected_users"),
            affected_features=impact.get("affected_features", []),
            urgency=self._parse_severity(impact.get("urgency"))
        )
        
        # 转换相似案例
        similar_cases = []
        for case in retrieval_results.get("case", [])[:3]:
            similar_cases.append(SimilarCase(
                case_id=case.id,
                title=case.metadata.get("title", "Unknown"),
                similarity=case.score,
                resolution=case.metadata.get("resolution")
            ))
        
        return AnalysisResult(
            analysis_id=str(uuid.uuid4()),
            bug_id=bug_info.get("bug_id"),
            summary=data.get("summary", "Analysis completed"),
            root_cause=root_cause,
            location=location,
            fix_suggestion=fix_suggestion,
            impact_assessment=impact_assessment,
            similar_cases=similar_cases,
            additional_investigation=data.get("additional_investigation", []),
            retrieval_context={
                "code_count": len(retrieval_results.get("code", [])),
                "case_count": len(retrieval_results.get("case", [])),
                "log_pattern_count": len(retrieval_results.get("log_pattern", []))
            }
        )
    
    def _parse_category(self, category_str: Optional[str]) -> BugCategory:
        """解析 Bug 分类"""
        if not category_str:
            return BugCategory.UNKNOWN
        
        category_map = {
            "API_ERROR": BugCategory.API_ERROR,
            "DATA_ERROR": BugCategory.DATA_ERROR,
            "DEPENDENCY_ERROR": BugCategory.DEPENDENCY_ERROR,
            "LOGIC_ERROR": BugCategory.LOGIC_ERROR,
            "CONFIG_ERROR": BugCategory.CONFIG_ERROR,
            "PERFORMANCE": BugCategory.PERFORMANCE,
        }
        return category_map.get(category_str.upper(), BugCategory.UNKNOWN)
    
    def _parse_fix_type(self, fix_type_str: Optional[str]) -> FixType:
        """解析修复类型"""
        if not fix_type_str:
            return FixType.ESCALATE
        
        type_map = {
            "code_change": FixType.CODE_CHANGE,
            "config_change": FixType.CONFIG_CHANGE,
            "rollback": FixType.ROLLBACK,
            "escalate": FixType.ESCALATE,
            "no_action": FixType.NO_ACTION,
        }
        return type_map.get(fix_type_str.lower(), FixType.ESCALATE)
    
    def _parse_severity(self, severity_str: Optional[str]) -> BugSeverity:
        """解析严重程度"""
        if not severity_str:
            return BugSeverity.P2
        
        severity_map = {
            "P0": BugSeverity.P0,
            "P1": BugSeverity.P1,
            "P2": BugSeverity.P2,
            "P3": BugSeverity.P3,
        }
        return severity_map.get(severity_str.upper(), BugSeverity.P2)
    
    def _create_fallback_result(
        self,
        bug_info: Dict[str, Any],
        raw_response: str
    ) -> AnalysisResult:
        """创建降级结果"""
        return AnalysisResult(
            analysis_id=str(uuid.uuid4()),
            bug_id=bug_info.get("bug_id"),
            summary="Analysis completed but response parsing failed",
            root_cause=RootCause(
                description=f"Raw analysis: {raw_response[:500]}",
                category=BugCategory.UNKNOWN,
                confidence=0.3
            ),
            fix_suggestion=FixSuggestion(
                fix_type=FixType.ESCALATE,
                description="Unable to parse structured suggestion, please review raw analysis"
            ),
            impact_assessment=ImpactAssessment(
                urgency=BugSeverity.P2
            ),
            additional_investigation=["Review raw LLM response for details"]
        )
