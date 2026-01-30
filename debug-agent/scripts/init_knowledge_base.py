"""
知识库初始化脚本 - 导入历史 Case 和预定义的日志模式
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from src.storage.vector_store import VectorStore
from src.models.schemas import (
    HistoryCase,
    CaseProblem,
    CaseResolution,
    FixType
)


def init_log_patterns(vector_store: VectorStore):
    """初始化常见日志错误模式"""
    patterns = [
        {
            "id": "REDIS_TIMEOUT",
            "pattern": "redis connection timeout redis.exceptions.TimeoutError Connection timed out",
            "category": "DEPENDENCY_ERROR",
            "severity": "P1",
            "description": "Redis 连接超时",
            "solution": "检查 Redis 服务状态，确认网络连通性，检查连接池配置"
        },
        {
            "id": "REDIS_CONN_POOL",
            "pattern": "redis connection pool exhausted no connection available",
            "category": "DEPENDENCY_ERROR",
            "severity": "P1",
            "description": "Redis 连接池耗尽",
            "solution": "增加连接池大小，检查是否有连接泄漏，优化连接使用"
        },
        {
            "id": "LLM_RATE_LIMIT",
            "pattern": "rate limit exceeded RateLimitError 429 too many requests openai",
            "category": "DEPENDENCY_ERROR",
            "severity": "P2",
            "description": "LLM API 请求频率超限",
            "solution": "实现请求限流，增加重试机制，考虑升级 API 配额"
        },
        {
            "id": "LLM_TIMEOUT",
            "pattern": "openai timeout request timed out APITimeoutError",
            "category": "DEPENDENCY_ERROR",
            "severity": "P2",
            "description": "LLM API 请求超时",
            "solution": "检查网络状况，调整超时配置，实现超时重试"
        },
        {
            "id": "DB_CONN_ERROR",
            "pattern": "database connection failed OperationalError could not connect to server",
            "category": "DEPENDENCY_ERROR",
            "severity": "P0",
            "description": "数据库连接失败",
            "solution": "检查数据库服务状态，确认连接配置，检查网络和防火墙"
        },
        {
            "id": "NULL_POINTER",
            "pattern": "NoneType object has no attribute AttributeError None",
            "category": "LOGIC_ERROR",
            "severity": "P2",
            "description": "空指针异常",
            "solution": "添加空值检查，确认数据来源，检查对象初始化逻辑"
        },
        {
            "id": "KEY_ERROR",
            "pattern": "KeyError key not found dict",
            "category": "LOGIC_ERROR",
            "severity": "P2",
            "description": "字典键不存在",
            "solution": "使用 .get() 方法，添加键存在性检查，确认数据结构"
        },
        {
            "id": "AUTH_FAILED",
            "pattern": "authentication failed unauthorized 401 invalid token",
            "category": "API_ERROR",
            "severity": "P2",
            "description": "认证失败",
            "solution": "检查 token 有效性，确认认证配置，检查时钟同步"
        },
        {
            "id": "PERMISSION_DENIED",
            "pattern": "permission denied forbidden 403 access denied",
            "category": "API_ERROR",
            "severity": "P2",
            "description": "权限不足",
            "solution": "检查用户权限配置，确认资源访问策略"
        },
        {
            "id": "OOM_ERROR",
            "pattern": "out of memory MemoryError cannot allocate memory",
            "category": "PERFORMANCE",
            "severity": "P0",
            "description": "内存不足",
            "solution": "检查内存泄漏，优化内存使用，考虑扩容"
        },
        {
            "id": "CONFIG_MISSING",
            "pattern": "configuration not found missing config environment variable not set",
            "category": "CONFIG_ERROR",
            "severity": "P1",
            "description": "配置缺失",
            "solution": "检查环境变量，确认配置文件，检查配置中心连接"
        }
    ]
    
    vector_store.add_log_patterns(patterns)
    print(f"✅ 已添加 {len(patterns)} 个日志错误模式")


def init_sample_cases(vector_store: VectorStore):
    """初始化示例历史 Case"""
    sample_cases = [
        HistoryCase(
            case_id="CASE-2024-001",
            created_at=datetime(2024, 1, 15, 10, 30),
            resolved_at=datetime(2024, 1, 15, 14, 20),
            problem=CaseProblem(
                title="用户反馈代码补全响应超时",
                description="多个用户反馈代码补全接口响应时间超过 10 秒，部分请求直接超时。通过日志发现 Redis 相关的超时错误。",
                error_patterns=["timeout", "redis", "connection"],
                affected_service="copilot-server",
                affected_api="/v1/completions"
            ),
            resolution=CaseResolution(
                root_cause="Redis 连接池配置过小（默认10），在高并发场景下连接池耗尽",
                fix_type=FixType.CONFIG_CHANGE,
                fix_detail="将 Redis 连接池大小从 10 调整到 50，并增加连接超时重试逻辑",
                pr_link="https://github.com/example/copilot-server/pull/123"
            ),
            tags=["redis", "performance", "config", "timeout"],
            resolver="zhangsan"
        ),
        HistoryCase(
            case_id="CASE-2024-002",
            created_at=datetime(2024, 2, 20, 9, 0),
            resolved_at=datetime(2024, 2, 20, 11, 30),
            problem=CaseProblem(
                title="OpenAI API 频繁返回 429 错误",
                description="监控显示 OpenAI API 调用成功率下降到 70%，大量请求返回 429 Too Many Requests。",
                error_patterns=["429", "rate limit", "openai"],
                affected_service="copilot-server",
                affected_api="/v1/completions"
            ),
            resolution=CaseResolution(
                root_cause="新功能上线导致请求量激增，超出 OpenAI API 配额限制",
                fix_type=FixType.CODE_CHANGE,
                fix_detail="1. 实现请求队列和限流机制\n2. 添加指数退避重试\n3. 临时升级 API 配额",
                pr_link="https://github.com/example/copilot-server/pull/156"
            ),
            tags=["openai", "rate-limit", "api"],
            resolver="lisi"
        ),
        HistoryCase(
            case_id="CASE-2024-003",
            created_at=datetime(2024, 3, 5, 14, 0),
            resolved_at=datetime(2024, 3, 5, 16, 0),
            problem=CaseProblem(
                title="部分用户无法使用代码补全功能",
                description="用户反馈点击代码补全后没有响应，后端日志显示 'user_context is None' 错误。",
                error_patterns=["NoneType", "user_context", "AttributeError"],
                affected_service="copilot-server",
                affected_api="/v1/completions"
            ),
            resolution=CaseResolution(
                root_cause="新用户注册流程变更后，部分用户的 context 初始化失败，导致后续请求时 user_context 为空",
                fix_type=FixType.CODE_CHANGE,
                fix_detail="在补全接口入口添加 user_context 空值检查，如果为空则触发重新初始化",
                pr_link="https://github.com/example/copilot-server/pull/178"
            ),
            tags=["null-pointer", "user-context", "logic"],
            resolver="wangwu"
        )
    ]
    
    for case in sample_cases:
        embedding_text = case.generate_embedding_text()
        vector_store.add_cases([{
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
    
    print(f"✅ 已添加 {len(sample_cases)} 个示例历史 Case")


def main():
    """主函数"""
    print("🚀 初始化 Debug Agent 知识库...\n")
    
    vector_store = VectorStore(persist_directory="./data/chroma")
    
    # 初始化日志模式
    init_log_patterns(vector_store)
    
    # 初始化示例 Case
    init_sample_cases(vector_store)
    
    # 打印统计
    stats = vector_store.get_stats()
    print(f"\n📊 知识库统计:")
    print(f"   - 代码片段: {stats['code_snippets']}")
    print(f"   - 历史 Case: {stats['history_cases']}")
    print(f"   - 日志模式: {stats['log_patterns']}")
    
    print("\n✅ 知识库初始化完成！")


if __name__ == "__main__":
    main()
