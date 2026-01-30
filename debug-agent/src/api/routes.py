"""
API 路由 - Bug 分析接口
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional

from src.models.schemas import (
    BugInput,
    AnalysisResult,
    AnalysisFeedback,
    HistoryCase
)
from src.service import DebugAgentService


# 创建路由
router = APIRouter(prefix="/api/v1", tags=["debug"])

# 服务实例（将在 main.py 中注入）
_service: Optional[DebugAgentService] = None


def set_service(service: DebugAgentService):
    """设置服务实例"""
    global _service
    _service = service


def get_service() -> DebugAgentService:
    """获取服务实例"""
    if _service is None:
        raise HTTPException(status_code=500, detail="Service not initialized")
    return _service


# ============ Bug 分析接口 ============

@router.post("/analyze", response_model=AnalysisResult)
async def analyze_bug(bug_input: BugInput):
    """
    分析 Bug
    
    接收 Bug 信息，返回分析结果，包括：
    - 问题总结
    - 根因分析
    - 代码定位
    - 修复建议
    - 影响评估
    - 相似历史案例
    """
    service = get_service()
    try:
        result = await service.analyze_bug(bug_input)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/analysis/{analysis_id}", response_model=AnalysisResult)
async def get_analysis(analysis_id: str):
    """获取分析结果"""
    service = get_service()
    result = service.get_analysis(analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result


@router.get("/analyses")
async def list_analyses(limit: int = 20):
    """列出最近的分析结果"""
    service = get_service()
    return service.list_analyses(limit)


# ============ 反馈接口 ============

@router.post("/feedback")
async def submit_feedback(feedback: AnalysisFeedback):
    """
    提交分析结果反馈
    
    用于记录分析结果的准确性，帮助改进系统
    """
    service = get_service()
    
    # 获取原分析结果
    analysis = service.get_analysis(feedback.analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    
    # TODO: 保存反馈到数据库
    # TODO: 如果反馈包含正确的根因和修复方案，自动创建新的历史 Case
    
    return {
        "status": "success",
        "message": "Feedback received",
        "analysis_id": feedback.analysis_id
    }


# ============ 知识库管理接口 ============

@router.post("/cases")
async def add_case(case: HistoryCase):
    """添加历史 Case 到知识库"""
    service = get_service()
    service.add_history_case(case)
    return {"status": "success", "case_id": case.case_id}


@router.get("/stats")
async def get_stats():
    """获取知识库统计"""
    service = get_service()
    return service.get_knowledge_stats()
