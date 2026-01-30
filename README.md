# Debug Agent MVP

一个基于 RAG + LLM 的智能 Bug 分析系统，帮助快速定位问题根因并提供修复建议。

## 功能特点

- 🔍 **智能分析**：自动解析堆栈、提取关键实体、分类 Bug 类型
- 📚 **知识库检索**：多路召回（代码、历史Case、日志模式）
- 🤖 **LLM 推理**：结合上下文进行根因分析和修复建议
- 📊 **结构化输出**：问题定位、根因、修复建议、影响评估
- 💻 **多种交互**：API 服务 + CLI 工具

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
cd debug-agent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入 OpenAI API Key
# OPENAI_API_KEY=sk-your-api-key-here
```

### 3. 初始化知识库

```bash
python scripts/init_knowledge_base.py
```

### 4. 启动服务

**方式一：API 服务**

```bash
python main.py
# 或
python cli.py serve
```

访问 http://localhost:8000/docs 查看 API 文档

**方式二：命令行**

```bash
# 单次分析
python cli.py analyze -e "Redis connection timeout" -d "用户反馈接口超时"

# 交互模式
python cli.py interactive

# 查看知识库统计
python cli.py stats
```

**方式三：Docker**

```bash
docker-compose up -d
```

## API 使用

### 分析 Bug

```bash
curl -X POST "http://localhost:8000/api/v1/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "error_info": {
      "error_message": "Redis connection timeout",
      "stack_trace": "Traceback...",
      "trace_id": "abc123"
    },
    "context": {
      "user_description": "用户反馈代码补全接口响应超时"
    },
    "severity": "P2"
  }'
```

### 添加历史 Case

```bash
curl -X POST "http://localhost:8000/api/v1/cases" \
  -H "Content-Type: application/json" \
  -d '{
    "case_id": "CASE-2024-100",
    "created_at": "2024-01-15T10:00:00",
    "problem": {
      "title": "Redis 连接超时",
      "description": "高并发场景下 Redis 连接池耗尽"
    },
    "resolution": {
      "root_cause": "连接池配置过小",
      "fix_type": "config_change",
      "fix_detail": "增加连接池大小"
    },
    "tags": ["redis", "performance"]
  }'
```

## 项目结构

```
debug-agent/
├── main.py                 # FastAPI 应用入口
├── cli.py                  # CLI 工具
├── requirements.txt        # Python 依赖
├── config/
│   └── settings.py         # 配置管理
├── src/
│   ├── api/
│   │   └── routes.py       # API 路由
│   ├── core/
│   │   ├── preprocessor.py # 预处理（堆栈解析、实体提取）
│   │   ├── retriever.py    # 多路检索
│   │   └── analyzer.py     # LLM 分析
│   ├── models/
│   │   └── schemas.py      # 数据模型
│   ├── storage/
│   │   └── vector_store.py # 向量存储
│   └── service.py          # 核心服务
├── scripts/
│   └── init_knowledge_base.py  # 知识库初始化
├── Dockerfile
└── docker-compose.yml
```

## 下一步计划

- [ ] 接入代码仓索引（支持 Git 仓库扫描）
- [ ] 接入告警系统（Prometheus AlertManager / PagerDuty）
- [ ] 添加反馈闭环机制
- [ ] 支持自动生成修复 PR
- [ ] 添加 Slack/飞书机器人

## 配置说明

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `OPENAI_API_KEY` | OpenAI API Key | 必填 |
| `OPENAI_BASE_URL` | OpenAI API 代理地址 | - |
| `LLM_MODEL` | LLM 模型名称 | gpt-4-turbo-preview |
| `API_PORT` | API 服务端口 | 8000 |
| `LOG_LEVEL` | 日志级别 | INFO |

## License

MIT
