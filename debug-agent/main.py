"""
Debug Agent - FastAPI 应用入口
"""
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from src.api.routes import router, set_service
from src.service import DebugAgentService


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化服务
    print(f"🚀 Starting {settings.app_name} v{settings.app_version}")
    
    service = DebugAgentService(
        openai_api_key=settings.openai_api_key,
        llm_model=settings.llm_model,
        openai_base_url=settings.openai_base_url,
        chroma_persist_dir=settings.chroma_persist_dir
    )
    set_service(service)
    
    # 打印知识库统计
    stats = service.get_knowledge_stats()
    print(f"📚 Knowledge base: {stats}")
    
    yield
    
    # 关闭时清理
    print("👋 Shutting down...")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="自动化 Debug 分析系统 - 基于 RAG + LLM 的智能 Bug 分析",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router)


# 健康检查
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.app_version}


# 根路径
@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug
    )
