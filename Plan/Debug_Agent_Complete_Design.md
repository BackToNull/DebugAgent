# Debug-Agent 完整设计方案

> 基于原有设计的增强版本，聚焦可落地性和实际效果

## 一、系统架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Debug Agent 系统架构                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────┐   ┌──────────────────────────────────────────────────┐  │
│  │    输入层      │   │                    知识库层                         │
│  │               │   │  ┌────────────┐ ┌────────────┐ ┌────────────┐   │  │
│  │ •模型服务调用   │   │  │ 代码索引库 │ │ 历史Case库 │ │ 日志模式库 │   │  │
│  │   工单         │   │  └────────────┘ └────────────┘ └────────────┘   │  │
│  │               │   │  ┌────────────┐ ┌────────────┐ ┌────────────┐   │  │
│  │               │   │  │ 配置文档库   │ │ API定义库  │ │    错误码映射 │    │  │
│  └───────┬───────┘   │  └────────────┘ └────────────┘ └────────────┘   │  │
│          │           └──────────────────────────────────────────────────┘  │
│          ▼                                   ▲                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         核心处理层                                   │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │   │
│  │  │ 预处理器   │→ │ 分类引擎 │→ │ 检索引擎 │→ │ 推理引擎 │           │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │   │
│  │       ↓              ↓             ↓             ↓                 │   │
│  │  信息提取      类型判断      多路召回      根因分析                 │   │
│  │  结构化解析    优先级评估    上下文聚合    修复建议                 │   │
│  │                                                                     │   │
│  │  ┌──────────────────────────────────────────────────────────────┐  │   │
│  │  │                    MCP 能力层                                 │  │   │
│  │  │  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐   │  │   │
│  │  │  │ Langfuse MCP   │  │ get_trace()    │  │ search_traces │   │  │   │
│  │  │  │ Server         │  │ get_session()  │  │ get_spans()   │   │  │   │
│  │  │  └────────────────┘  └────────────────┘  └───────────────┘   │  │   │
│  │  │  • 实时获取 Langfuse 日志数据                                 │  │   │
│  │  │  • LLM 推理时动态调用 MCP 工具                                │  │   │
│  │  └──────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         输出与反馈层                                  │   │
│  │  • 结构化报告（问题定位 + 根因 + 修复建议 + 置信度）                       │   │
│  │  • 自动创建修复 PR（可选）                                              │   │
│  │  • 反馈闭环（修复验证 → 知识库更新）                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 二、核心模块详细设计

### 2.1 输入标准化模块

**Bug 信息输入 Schema：**

```json
{
  "bug_id": "string",
  "source": "model_service_ticket",
  "timestamp": "ISO8601",
  "severity": "P0|P1|P2|P3",
  "environment": {
    "service": "copilot-server",
    "version": "string",
    "region": "string",
    "pod_name": "string"
  },
  "error_info": {
    "error_code": "string",
    "error_message": "string",
    "stack_trace": "string",
    "request_id": "string",
    "trace_id": "string"
  },
  "context": {
    "client_info": "string",
    "request_payload": "object",
    "response_payload": "object",
    "user_description": "string"
  },
  "related_logs": ["string"],
  "reproduce_steps": ["string"]
}
```

**模型服务调用工单适配器：**

| 来源 | 适配逻辑 |
|------|----------|
| 模型服务调用工单 | 解析工单内容，提取 trace_id/request_id，通过 MCP 调用 Langfuse 获取关联日志和调用链路 |

### 2.2 预处理模块

```
输入原始信息
    │
    ├─► 堆栈解析器
    │   ├─ 提取异常类型、文件路径、行号
    │   ├─ 识别框架层 vs 业务层堆栈
    │   └─ 标记关键调用链
    │
    ├─► 日志聚合器
    │   ├─ 基于 trace_id/request_id 聚合
    │   ├─ 时序排列，标记异常时间点
    │   └─ 提取关键日志模式
    │
    ├─► 实体提取器
    │   ├─ 识别：用户ID、请求参数、配置项
    │   ├─ 识别：服务名、接口名、依赖服务
    │   └─ 识别：错误码、HTTP状态码
    │
    └─► 上下文增强器
        ├─ 自动拉取相关配置（Apollo/Nacos）
        ├─ 查询最近部署记录
        └─ 检查依赖服务健康状态
```

### 2.3 智能分类模块

**Bug 分类体系（适配 copilot-server）：**

```
├── 接口错误 (API_ERROR)
│   ├── 参数校验失败
│   ├── 鉴权失败
│   ├── 限流/熔断
│   └── 超时
│
├── 数据问题 (DATA_ERROR)
│   ├── 数据不一致
│   ├── 缓存问题
│   └── DB 查询异常
│
├── 依赖服务问题 (DEPENDENCY_ERROR)
│   ├── LLM 服务异常
│   ├── 向量检索服务异常
│   └── 其他微服务异常
│
├── 逻辑错误 (LOGIC_ERROR)
│   ├── 空指针/越界
│   ├── 状态机异常
│   └── 并发问题
│
├── 配置问题 (CONFIG_ERROR)
│   ├── 配置缺失/错误
│   ├── 环境变量问题
│   └── 特性开关问题
│
└── 性能问题 (PERFORMANCE)
    ├── 内存泄漏
    ├── CPU 飙高
    └── 慢查询
```

**分类决策逻辑：**

```python
# 伪代码示意
def classify_bug(bug_info):
    # 规则优先（快速路径）
    if "rate limit" in error_message:
        return "API_ERROR.限流"
    if "connection timeout" in error_message:
        return "DEPENDENCY_ERROR"
    if "NullPointerException" in stack_trace:
        return "LOGIC_ERROR.空指针"
    
    # LLM 兜底（复杂情况）
    return llm_classify(bug_info)
```

### 2.4 MCP 能力层（Langfuse 日志接入）

**MCP 架构设计：**

```
┌────────────────────────────────────────────────────────────────┐
│                    Debug Agent (MCP Client)                     │
│                                                                 │
│  ┌─────────────┐    ┌─────────────────────────────────────┐   │
│  │  推理引擎   │───▶│        MCP Tool Calling              │   │
│  │  (LLM)      │◀───│  根据分析需要动态调用 MCP 工具       │   │
│  └─────────────┘    └─────────────────────────────────────┘   │
│                                   │                             │
└───────────────────────────────────│─────────────────────────────┘
                                    │ MCP Protocol
                                    ▼
┌────────────────────────────────────────────────────────────────┐
│                    Langfuse MCP Server                          │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐     │
│  │ get_trace()  │  │search_traces │  │ get_session()    │     │
│  │ 获取单个trace│  │ 搜索traces   │  │ 获取会话traces   │     │
│  └──────────────┘  └──────────────┘  └──────────────────┘     │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐     │
│  │ get_spans()  │  │get_generations│ │ get_observations │     │
│  │ 获取span详情 │  │ 获取LLM调用  │  │ 获取观测数据     │     │
│  └──────────────┘  └──────────────┘  └──────────────────┘     │
│                                   │                             │
└───────────────────────────────────│─────────────────────────────┘
                                    │ REST API
                                    ▼
                          ┌─────────────────┐
                          │    Langfuse     │
                          │    云端/自托管   │
                          └─────────────────┘
```

**MCP 工具定义：**

| 工具名称 | 参数 | 描述 |
|----------|------|------|
| `get_trace` | trace_id: string | 根据 trace_id 获取完整调用链路 |
| `search_traces` | query: string, time_range: object, limit: int | 搜索符合条件的 traces |
| `get_session_traces` | session_id: string | 获取某个会话的所有 traces |
| `get_spans` | trace_id: string | 获取 trace 下的所有 span 详情 |
| `get_generations` | trace_id: string | 获取 LLM 调用记录（输入/输出/token 用量） |
| `get_observations` | trace_id: string, type: string | 获取指定类型的观测数据 |

**典型调用场景：**

```python
# 场景1: 从工单 trace_id 获取完整调用链
trace = await mcp_client.call_tool("get_trace", {"trace_id": bug_input.trace_id})

# 场景2: 搜索相似错误
similar = await mcp_client.call_tool("search_traces", {
    "query": "error:timeout service:copilot-server",
    "time_range": {"from": "2024-01-01", "to": "2024-01-30"},
    "limit": 10
})

# 场景3: LLM 推理过程中动态调用（Agentic 模式）
# LLM 分析时可自主决定是否需要更多日志数据
```

**MCP Server 实现要点：**

1. **认证管理**：封装 Langfuse API Key，客户端无需感知
2. **数据脱敏**：可在 Server 层对敏感信息进行过滤
3. **缓存策略**：高频查询结果缓存，减少 API 调用
4. **错误处理**：优雅降级，Langfuse 不可用时返回空结果

### 2.5 多路检索模块

**检索策略矩阵：**

| 检索类型 | 数据源 | 检索方式 | 召回数量 | 权重 |
|----------|--------|----------|----------|------|
| 历史相似Case | Case知识库 | 向量相似度 | Top 5 | 0.35 |
| 相关代码 | 代码索引 | 混合检索(语义+关键字) | Top 10 | 0.25 |
| 错误模式匹配 | 日志模式库 | 精确+模糊匹配 | Top 3 | 0.15 |
| 配置关联 | 配置文档库 | 关键字匹配 | Top 3 | 0.1 |
| Langfuse 日志 | MCP 实时获取 | trace_id 精确查询 | 按需 | 0.15 |

**代码检索增强策略：**

```
1. 从堆栈提取的文件/函数 → 精确定位代码
2. 错误信息关键词 → 语义搜索相关代码
3. 上下游调用链 → 扩展检索调用方/被调用方
4. 最近变更 → git blame 定位最近修改者
```

### 2.6 LLM 推理模块（支持 MCP 工具调用）

**Prompt 工程设计（Chain of Thought + Tool Use）：**

```markdown
## 系统角色
你是一个专业的后端服务 Debug 专家，负责分析 copilot-server 的问题。
你可以使用以下工具获取更多信息：

### 可用工具
- get_trace(trace_id): 获取完整调用链路
- search_traces(query, time_range): 搜索相似错误
- get_generations(trace_id): 获取 LLM 调用详情
- get_spans(trace_id): 获取 span 级别详情

## 分析任务
基于以下信息，按步骤分析问题：

### 第一步：理解问题
- 错误的核心表现是什么？
- 影响范围有多大？

### 第二步：定位根因
- 结合代码和历史案例，最可能的原因是什么？
- 是代码 bug、配置问题、还是外部依赖问题？

### 第三步：验证假设
- 这个假设能解释所有观察到的现象吗？
- 有没有其他可能的原因？

### 第四步：给出修复方案
- 具体修改哪个文件的哪一行？
- 如何验证修复是否成功？

## 输入信息
【Bug 信息】
{bug_info_json}

【相似历史 Case】
{similar_cases}

【相关代码片段】
{code_snippets}

【关联日志】
{related_logs}

## 输出格式
请严格按照以下 JSON 格式输出：
{output_schema}
```

**输出 Schema：**

```json
{
  "summary": "一句话总结问题",
  "root_cause": {
    "description": "根因详细描述",
    "category": "分类标签",
    "confidence": 0.85
  },
  "location": {
    "file": "src/service/completion.py",
    "line_start": 142,
    "line_end": 145,
    "function": "handle_completion_request"
  },
  "fix_suggestion": {
    "type": "code_change|config_change|rollback|escalate",
    "description": "修复方案描述",
    "code_diff": "--- a/...\n+++ b/...",
    "test_verification": "验证步骤"
  },
  "impact_assessment": {
    "affected_users": "估计影响用户数",
    "affected_features": ["功能列表"],
    "urgency": "P0|P1|P2|P3"
  },
  "similar_cases": [
    {
      "case_id": "xxx",
      "similarity": 0.92,
      "resolution": "历史解决方案"
    }
  ],
  "additional_investigation": ["如需进一步排查的建议"]
}
```

## 三、知识库建设

### 3.1 代码索引库

**索引策略：**

```
copilot-server/
├── 模块级索引
│   ├─ 每个模块的功能描述
│   ├─ 模块间依赖关系图
│   └─ 关键入口点标记
│
├── 函数级索引
│   ├─ 函数签名 + 文档字符串
│   ├─ 输入输出类型
│   ├─ 调用关系（caller/callee）
│   └─ 异常处理分支
│
└── 变更历史索引
    ├─ 每个函数的变更频率
    ├─ 历史 bug 关联
    └─ 代码作者信息
```

**技术实现：**
- 使用 Tree-sitter 进行 AST 解析
- 代码切片策略：按函数/类为单位，包含上下文
- 向量化：使用 Code Embedding 模型（如 CodeBERT、StarCoder Embedding）
- 存储：Milvus/Qdrant + 元数据存储（PostgreSQL）

### 3.2 历史 Case 库

**Case 结构化设计：**

```json
{
  "case_id": "DEBUG-2024-001",
  "created_at": "2024-01-15T10:30:00Z",
  "resolved_at": "2024-01-15T14:20:00Z",
  
  "problem": {
    "title": "用户反馈代码补全响应慢",
    "description": "...",
    "error_patterns": ["timeout", "high latency"],
    "affected_service": "copilot-server",
    "affected_api": "/v1/completions"
  },
  
  "investigation": {
    "steps": ["检查日志", "分析 trace", "定位慢查询"],
    "findings": ["Redis 连接池耗尽"],
    "red_herrings": ["最初怀疑是 LLM 服务问题"]
  },
  
  "resolution": {
    "root_cause": "Redis 连接池配置不当",
    "fix_type": "config_change",
    "fix_detail": "增加连接池大小从 10 到 50",
    "pr_link": "https://github.com/xxx/pr/123",
    "rollback_plan": "恢复原配置"
  },
  
  "metadata": {
    "resolver": "zhangsan",
    "review_status": "verified",
    "reoccurrence_count": 0,
    "tags": ["redis", "performance", "config"]
  },
  
  "embedding_text": "合并的用于向量化的文本"
}
```

**来源整合：**
- 你现有的 debug 记录表格 → 批量导入
- 后续新 Case → 自动记录 + 人工审核补充
- PR 关联 → 从修复 PR 的描述中提取信息

### 3.3 日志模式库

**常见错误模式模板：**

```yaml
patterns:
  - id: "REDIS_CONN_TIMEOUT"
    regex: "redis\.exceptions\.TimeoutError|Connection timed out.*redis"
    category: "DEPENDENCY_ERROR"
    severity: "P1"
    likely_cause: "Redis 服务不可用或连接池耗尽"
    suggested_action: "检查 Redis 服务状态，查看连接池配置"
    
  - id: "LLM_RATE_LIMIT"
    regex: "RateLimitError|429.*openai|rate.?limit"
    category: "DEPENDENCY_ERROR"
    severity: "P2"
    likely_cause: "LLM API 请求频率超限"
    suggested_action: "检查请求频率，考虑增加限流配置或升级 API 配额"
    
  - id: "NULL_USER_CONTEXT"
    regex: "NoneType.*user_context|user_context is None"
    category: "LOGIC_ERROR"
    severity: "P2"
    likely_cause: "用户上下文未正确初始化"
    suggested_action: "检查用户鉴权流程，确认 session 管理"
```

## 四、工程实现建议

### 4.1 技术栈选型

| 组件 | 推荐方案 | 备选方案 |
|------|----------|----------|
| 后端框架 | FastAPI (Python) | Go + Gin |
| 向量数据库 | Milvus | Qdrant / Pinecone |
| 关系型存储 | PostgreSQL | MySQL |
| 缓存 | Redis | - |
| 消息队列 | Kafka / RabbitMQ | Redis Streams |
| LLM | GPT-4 / Claude | 智谱 AI / 自部署开源模型 |
| 代码解析 | Tree-sitter | - |
| Embedding | text-embedding-3-large | BGE / CodeBERT |
| 任务调度 | Celery | Temporal |
| 可观测性 | Prometheus + Grafana + Jaeger | - |
| MCP Server | Python mcp-sdk | TypeScript @modelcontextprotocol/sdk |
| 日志平台 | Langfuse | - |

### 4.2 项目结构

```
debug-agent/
├── src/
│   ├── api/                    # API 层
│   │   ├── routes/
│   │   │   ├── bug_submit.py   # Bug 提交接口
│   │   │   ├── analysis.py     # 分析结果查询
│   │   │   └── feedback.py     # 反馈接口
│   │   └── schemas/            # 请求/响应模型
│   │
│   ├── core/                   # 核心处理逻辑
│   │   ├── preprocessor/       # 预处理模块
│   │   │   ├── stack_parser.py
│   │   │   ├── log_aggregator.py
│   │   │   └── entity_extractor.py
│   │   ├── classifier/         # 分类模块
│   │   ├── retriever/          # 检索模块
│   │   │   ├── code_retriever.py
│   │   │   ├── case_retriever.py
│   │   │   └── hybrid_retriever.py
│   │   ├── analyzer/           # LLM 分析模块
│   │   │   ├── prompts/
│   │   │   └── chain.py
│   │   └── reporter/           # 报告生成
│   │
│   ├── mcp/                    # MCP 能力层
│   │   ├── server/             # Langfuse MCP Server
│   │   │   ├── langfuse_server.py
│   │   │   └── tools/
│   │   │       ├── get_trace.py
│   │   │       ├── search_traces.py
│   │   │       └── get_generations.py
│   │   └── client/             # MCP Client 封装
│   │       └── mcp_client.py
│   │
│   ├── knowledge/              # 知识库管理
│   │   ├── indexer/            # 索引构建
│   │   │   ├── code_indexer.py
│   │   │   └── case_indexer.py
│   │   ├── updater/            # 知识库更新
│   │   └── sync/               # 数据同步
│   │
│   ├── integrations/           # 外部集成
│   │   ├── ticket_parser.py    # 模型服务调用工单解析
│   │   └── git_service.py      # Git 操作
│   │
│   ├── storage/                # 存储层
│   │   ├── vector_store.py
│   │   ├── relational_store.py
│   │   └── cache.py
│   │
│   └── utils/                  # 工具类
│
├── scripts/                    # 运维脚本
│   ├── init_knowledge_base.py  # 初始化知识库
│   ├── sync_code_repo.py       # 同步代码仓
│   └── import_history_cases.py # 导入历史 Case
│
├── tests/                      # 测试
├── config/                     # 配置文件
├── docker/                     # Docker 相关
└── docs/                       # 文档
```

### 4.3 核心流程伪代码

```python
# 主处理流程
async def process_bug(bug_input: BugInput) -> AnalysisResult:
    # 1. 预处理
    structured_bug = await preprocessor.process(bug_input)
    
    # 2. 分类
    bug_category = await classifier.classify(structured_bug)
    
    # 3. 通过 MCP 获取 Langfuse 日志数据
    langfuse_data = None
    if structured_bug.trace_id:
        langfuse_data = await mcp_client.call_tool(
            "get_trace", 
            {"trace_id": structured_bug.trace_id}
        )
    
    # 4. 多路检索（并行）
    retrieval_tasks = [
        case_retriever.search(structured_bug),
        code_retriever.search(structured_bug),
        log_pattern_matcher.match(structured_bug),
    ]
    similar_cases, related_code, matched_patterns = await asyncio.gather(*retrieval_tasks)
    
    # 5. 构建上下文（包含 Langfuse 数据）
    context = build_analysis_context(
        bug=structured_bug,
        category=bug_category,
        cases=similar_cases,
        code=related_code,
        patterns=matched_patterns,
        langfuse_trace=langfuse_data  # 新增：Langfuse 调用链数据
    )
    
    # 6. LLM 推理分析（支持 Agentic MCP 工具调用）
    # LLM 可在分析过程中自主调用 MCP 工具获取更多日志信息
    analysis_result = await llm_analyzer.analyze(
        context,
        tools=mcp_client.get_available_tools()  # 注入 MCP 工具
    )
    
    # 7. 后处理 & 结果校验
    validated_result = await result_validator.validate(analysis_result)
    
    # 8. 异步：记录本次分析（用于后续反馈）
    await analysis_recorder.record(bug_input, validated_result)
    
    return validated_result
```

## 五、分阶段实施计划

### Phase 1: MVP（4-6 周）

**目标：** 跑通核心链路，验证可行性

| 任务 | 工作量 | 产出 |
|------|--------|------|
| 搭建基础框架 | 1 周 | API 服务骨架 |
| 代码索引（基础版） | 1 周 | copilot-server 代码可检索 |
| 历史 Case 导入 | 1 周 | 现有 debug 记录入库 |
| LLM 分析链路 | 1.5 周 | 基础分析能力 |
| 简单 UI/CLI | 0.5 周 | 可交互界面 |

**验收标准：**
- 输入 bug 信息，能输出结构化分析结果
- 对于典型 bug，能召回相似历史 Case
- 分析准确率 > 60%（人工评估）

### Phase 2: 增强（4-6 周）

**目标：** 提升准确率，增加 MCP 能力

| 任务 | 工作量 | 产出 |
|------|--------|------|
| 日志模式库 | 1 周 | 常见错误快速识别 |
| Langfuse MCP Server | 1.5 周 | 实时获取 Langfuse 日志数据 |
| 检索优化（混合检索） | 1.5 周 | 更精准的召回 |
| 反馈闭环 | 1 周 | 修复结果回写 |
| Prompt 优化（含工具调用） | 1 周 | 支持 Agentic 工具调用 |

**验收标准：**
- 分析准确率 > 75%
- 平均分析时间 < 30 秒
- LLM 可自主调用 MCP 工具获取 Langfuse 数据

### Phase 3: 自动化（6-8 周）

**目标：** 减少人工介入，提升效率

| 任务 | 工作量 | 产出 |
|------|--------|------|
| 自动 PR 生成 | 2 周 | 简单修复自动提 PR |
| 置信度分级处理 | 1 周 | 高置信度自动处理 |
| IM 机器人 | 1.5 周 | Slack/飞书交互 |
| 监控大盘 | 1 周 | Debug 效率可视化 |
| 多服务扩展 | 2 周 | 支持其他服务接入 |

**验收标准：**
- 30% 的常见 bug 可自动生成修复 PR
- 人工 debug 时间减少 50%

## 六、关键成功指标（KPI）

| 指标 | 定义 | 目标值 |
|------|------|--------|
| 分析准确率 | 根因定位正确的比例 | > 80% |
| 平均响应时间 | 从输入到输出结果 | < 30s |
| 历史命中率 | 召回相关历史 Case 的比例 | > 70% |
| 人工确认率 | 修复建议被采纳的比例 | > 60% |
| 效率提升 | Debug 平均耗时降低 | > 50% |
| 自动修复率 | 自动生成 PR 且合入的比例 | > 20% |

## 七、风险与应对

| 风险 | 影响 | 应对策略 |
|------|------|----------|
| LLM 幻觉导致误判 | 错误的修复建议 | 置信度阈值 + 人工审核兜底 |
| 知识库冷启动 | 初期效果差 | 优先导入高频 bug 类型 |
| 代码更新同步延迟 | 分析基于过时代码 | 增量同步 + git hook 触发 |
| 复杂 bug 难以处理 | 无法给出有效建议 | 明确边界，复杂问题升级人工 |
| LLM API 成本 | 费用过高 | 缓存 + 分级处理（简单问题用规则）|

## 八、扩展考虑

### 8.1 与现有工具集成

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  PagerDuty  │────▶│             │────▶│    Jira     │
│  (告警)     │     │ Debug Agent │     │  (工单)     │
└─────────────┘     │             │     └─────────────┘
                    │             │
┌─────────────┐     │             │     ┌─────────────┐
│   Grafana   │────▶│             │────▶│   GitHub    │
│  (监控)     │     │             │     │   (PR)      │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 8.2 多模态扩展

- **日志截图 OCR**：用户上传的截图自动提取文字
- **监控图表理解**：分析 Grafana 图表异常模式
- **语音输入**：支持语音描述 bug（接入 Whisper）

### 8.3 主动防御能力

- **变更影响预测**：PR 合入前预测可能引入的 bug
- **异常检测**：基于日志模式主动发现潜在问题
- **根因预判**：高频 bug 模式触发主动修复建议

---

## 附录：快速启动 Checklist

- [ ] 确定 copilot-server 代码仓访问权限
- [ ] 整理现有 debug 记录表格格式
- [ ] 确认日志服务（ELK/Loki）查询接口
- [ ] 申请 LLM API 额度
- [ ] 搭建向量数据库环境
- [ ] 部署 MVP 服务
- [ ] 接入第一个告警源
- [ ] 完成首次端到端测试
