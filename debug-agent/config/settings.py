"""
Debug Agent 配置管理
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """应用配置"""
    
    # 基础配置
    app_name: str = "Debug Agent"
    app_version: str = "0.1.0"
    debug: bool = True
    
    # API 配置
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # LLM 配置
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_base_url: Optional[str] = Field(default=None, env="OPENAI_BASE_URL")
    llm_model: str = Field(default="gpt-4-turbo-preview", env="LLM_MODEL")
    embedding_model: str = Field(default="text-embedding-3-small", env="EMBEDDING_MODEL")
    verify_ssl: bool = Field(default=False, env="VERIFY_SSL")  # SSL 证书验证（公司代理可能需要禁用）
    
    # 向量数据库配置
    chroma_persist_dir: str = "./data/chroma"
    
    # 数据库配置
    database_url: str = "sqlite+aiosqlite:///./data/debug_agent.db"
    
    # 知识库配置
    code_repo_path: Optional[str] = None  # copilot-server 代码路径
    max_code_chunk_size: int = 1000
    code_chunk_overlap: int = 200
    
    # 检索配置
    retrieval_top_k: int = 5
    similarity_threshold: float = 0.7
    
    # 日志配置
    log_level: str = "INFO"
    log_file: Optional[str] = "./logs/debug_agent.log"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 全局配置实例
settings = Settings()
