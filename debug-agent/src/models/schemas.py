"""
数据模型定义 - Bug 输入、分析结果、历史 Case 等
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ============ 枚举定义 ============

class BugSource(str, Enum):
    """Bug 来源"""
    ALERT = "alert"          # 告警系统
    TICKET = "ticket"        # 工单系统
    MANUAL = "manual"        # 手动输入
    API = "api"              # API 调用


class BugSeverity(str, Enum):
    """Bug 严重程度"""
    P0 = "P0"  # 紧急
    P1 = "P1"  # 高
    P2 = "P2"  # 中
    P3 = "P3"  # 低


class BugCategory(str, Enum):
    """Bug 分类"""
    API_ERROR = "API_ERROR"                    # 接口错误
    DATA_ERROR = "DATA_ERROR"                  # 数据问题
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"      # 依赖服务问题
    LOGIC_ERROR = "LOGIC_ERROR"                # 逻辑错误
    CONFIG_ERROR = "CONFIG_ERROR"              # 配置问题
    PERFORMANCE = "PERFORMANCE"                # 性能问题
    UNKNOWN = "UNKNOWN"                        # 未知


class FixType(str, Enum):
    """修复类型"""
    CODE_CHANGE = "code_change"       # 代码修改
    CONFIG_CHANGE = "config_change"   # 配置修改
    ROLLBACK = "rollback"             # 回滚
    ESCALATE = "escalate"             # 升级处理
    NO_ACTION = "no_action"           # 无需处理


# ============ 输入模型 ============

class EnvironmentInfo(BaseModel):
    """环境信息"""
    service: str = "copilot-server"
    version: Optional[str] = None
    region: Optional[str] = None
    pod_name: Optional[str] = None
    
    
class ErrorInfo(BaseModel):
    """错误信息"""
    error_code: Optional[str] = None
    error_message: str
    stack_trace: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None


class BugContext(BaseModel):
    """Bug 上下文"""
    client_info: Optional[str] = None
    request_payload: Optional[Dict[str, Any]] = None
    response_payload: Optional[Dict[str, Any]] = None
    user_description: Optional[str] = None


class BugInput(BaseModel):
    """Bug 输入 Schema"""
    bug_id: Optional[str] = None
    source: BugSource = BugSource.MANUAL
    timestamp: datetime = Field(default_factory=datetime.now)
    severity: BugSeverity = BugSeverity.P2
    
    # 环境信息
    environment: EnvironmentInfo = Field(default_factory=EnvironmentInfo)
    
    # 错误信息
    error_info: ErrorInfo
    
    # 上下文
    context: Optional[BugContext] = None
    
    # 关联日志
    related_logs: List[str] = Field(default_factory=list)
    
    # 复现步骤
    reproduce_steps: List[str] = Field(default_factory=list)
    
    class Config:
        json_schema_extra = {
            "example": {
                "source": "manual",
                "severity": "P2",
                "environment": {
                    "service": "copilot-server",
                    "version": "1.2.3"
                },
                "error_info": {
                    "error_code": "500",
                    "error_message": "Redis connection timeout",
                    "stack_trace": "Traceback (most recent call last):\n  File ...",
                    "trace_id": "abc123"
                },
                "context": {
                    "user_description": "用户反馈代码补全接口响应超时"
                }
            }
        }


# ============ 分析结果模型 ============

class CodeLocation(BaseModel):
    """代码定位"""
    file: str
    line_start: Optional[int] = None  # 允许为空，LLM 可能无法确定具体行号
    line_end: Optional[int] = None
    function: Optional[str] = None
    code_snippet: Optional[str] = None


class RootCause(BaseModel):
    """根因分析"""
    description: str
    category: BugCategory
    confidence: float = Field(ge=0, le=1)


class FixSuggestion(BaseModel):
    """修复建议"""
    fix_type: FixType
    description: str
    code_diff: Optional[str] = None
    config_change: Optional[Dict[str, Any]] = None
    test_verification: Optional[str] = None


class ImpactAssessment(BaseModel):
    """影响评估"""
    affected_users: Optional[str] = None
    affected_features: List[str] = Field(default_factory=list)
    urgency: BugSeverity = BugSeverity.P2


class SimilarCase(BaseModel):
    """相似历史 Case"""
    case_id: str
    title: str
    similarity: float
    resolution: Optional[str] = None


class AnalysisResult(BaseModel):
    """分析结果"""
    analysis_id: str
    bug_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    
    # 问题总结
    summary: str
    
    # 根因分析
    root_cause: RootCause
    
    # 代码定位（可选）
    location: Optional[CodeLocation] = None
    
    # 修复建议
    fix_suggestion: FixSuggestion
    
    # 影响评估
    impact_assessment: ImpactAssessment
    
    # 相似历史 Case
    similar_cases: List[SimilarCase] = Field(default_factory=list)
    
    # 进一步排查建议
    additional_investigation: List[str] = Field(default_factory=list)
    
    # 原始检索结果（调试用）
    retrieval_context: Optional[Dict[str, Any]] = None


# ============ 历史 Case 模型 ============

class CaseProblem(BaseModel):
    """Case 问题描述"""
    title: str
    description: str
    error_patterns: List[str] = Field(default_factory=list)
    affected_service: str = "copilot-server"
    affected_api: Optional[str] = None


class CaseResolution(BaseModel):
    """Case 解决方案"""
    root_cause: str
    fix_type: FixType
    fix_detail: str
    pr_link: Optional[str] = None


class HistoryCase(BaseModel):
    """历史 Debug Case"""
    case_id: str
    created_at: datetime
    resolved_at: Optional[datetime] = None

    # 问题
    problem: CaseProblem
    
    # 解决方案
    resolution: CaseResolution
    
    # 标签
    tags: List[str] = Field(default_factory=list)
    
    # 处理人
    resolver: Optional[str] = None
    
    # 用于向量化的文本
    embedding_text: Optional[str] = None
    
    def generate_embedding_text(self) -> str:
        """生成用于向量化的文本"""
        parts = [
            f"问题: {self.problem.title}",
            f"描述: {self.problem.description}",
            f"错误模式: {', '.join(self.problem.error_patterns)}",
            f"根因: {self.resolution.root_cause}",
            f"解决方案: {self.resolution.fix_detail}",
            f"标签: {', '.join(self.tags)}"
        ]
        return "\n".join(parts)


# ============ 反馈模型 ============

class FeedbackType(str, Enum):
    """反馈类型"""
    CORRECT = "correct"          # 分析正确
    PARTIAL = "partial"          # 部分正确
    INCORRECT = "incorrect"      # 分析错误


class AnalysisFeedback(BaseModel):
    """分析结果反馈"""
    analysis_id: str
    feedback_type: FeedbackType
    actual_root_cause: Optional[str] = None
    actual_fix: Optional[str] = None
    comments: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
