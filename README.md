# 智能研报生成系统

> 基于 LangGraph 的多 Agent 协作式智能研报自动生成平台。

## 这是什么项目？

输入一个研究主题，系统自动完成 **意图识别 → 研究规划 → 数据采集（Tavily 搜索 + RAG 知识库）→ 数据处理 → 数据分析 → 报告撰写 → 编辑润色 → 质量审核 → 发布输出** 的全流程，最终生成结构化的 Markdown 研报。

**核心能力**：
- 支持 3 种报告类型：深度研报、快讯、财报分析
- 多 LLM 可选：DeepSeek Flash / Pro、Qwen 8B / 32B / Max
- RAG 知识库检索（Qdrant 向量库 + BGE 嵌入），增强报告信息密度
- 语义缓存减少重复 LLM 调用成本
- SSE 实时推送节点进度，前端可视化展示执行过程
- 治理层责任链安检：输入安全、事实核查、幻觉检测
- 图片维度对比表格、AI 图表渲染（`chart_server`）

## 怎么快速跑起来？

### 环境要求

- Python >= 3.11
- Node.js >= 18（前端）
- PostgreSQL（Docker 或本地）
- Qdrant（Docker 或本地）
- Redis

### 1. 启动依赖服务

```bash
# PostgreSQL
docker run -d --name pg-research -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16

# Qdrant
docker run -d --name qdrant-research -p 6333:6333 -p 6334:6334 qdrant/qdrant

# Redis（Windows 本地服务或 Docker）
docker run -d --name redis-research -p 6379:6379 redis:7
```

### 2. 安装后端依赖

```powershell
# 创建虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python scripts/init_db.py
```

### 2.5 配置 API Key

在项目根目录创建 `.env` 文件（已加入 `.gitignore`，不会提交）：

```ini
TAVILY_API_KEY=你的Tavily密钥        # https://tavily.com 免费注册
DEEPSEEK_API_KEY=你的DeepSeek密钥     # https://platform.deepseek.com
QWEN_API_KEY=你的通义千问密钥          # https://dashscope.aliyun.com
```

项目通过 `config/settings.py` 自动从 `.env` 加载配置，无需手动修改脚本。

### 3. 启动后端

```powershell
python app.py
# 后端运行在 http://localhost:8010
# MCP search_server → http://localhost:8001
# MCP chart_server  → http://localhost:8003
```

### 4. 启动前端

```powershell
cd frontend
npm install
npm run dev
# 前端运行在 http://localhost:3000
```

### 5. API 健康检查

```bash
curl http://localhost:8010/health
# → {"status":"healthy"}
```

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **编排引擎** | LangGraph 0.2+ | 状态图工作流，PostgreSQL Checkpointer |
| **后端框架** | FastAPI + SSE (sse-starlette) | REST + 流式事件推送 |
| **LLM** | DeepSeek v4、Qwen（通义千问） | 通过 `resolver.py` 按 task 动态路由 |
| **搜索引擎** | Tavily API | 实时网页搜索 |
| **向量检索** | Qdrant + BGE/Chroma | chunk → embed → RAG |
| **缓存** | Redis + 语义缓存 | 减少重复 LLM 调用 |
| **数据库** | PostgreSQL (SQLAlchemy Core + Alembic) | 工作流状态、会话、运营数据 |
| **前端** | Next.js 14 + TypeScript + Tailwind CSS + Zustand | SSE 流式接收、Markdown 实时渲染 |
| **可观测性** | structured logging + Prometheus + Docker Compose 集成 Grafana | 指标、追踪 |
| **测试** | pytest (unit / integration / e2e / contract / chaos) | 覆盖核心链路 |

### 架构概览

```
用户输入 → chat.py (SSE endpoint)
              │
              ▼
┌─────────────────────────────────────────┐
│          Harness (治理层)                │
│  输入安检 → 事实核查1 → 事实核查2        │
│  → 幻觉检测 → 结构审查 → 审计日志        │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│   Agents Workflow (9 节点 LangGraph)     │
│                                          │
│  intent_classifier  →  research_planner  │
│       ↓                       ↓          │
│  data_collector      data_processor     │
│  (Tavily + RAG)            ↓             │
│       ↓              data_analyst        │
│       ↓──────────────────┘              │
│  writer  →  editor  →  reviewer         │
│                    →  publisher         │
└─────────────────────────────────────────┘
              │
              ▼
          SSE 实时推送 → 前端渲染
```

### 效果数据

| 工作流 | 输出字符数 | 章节数 | 节点通过率 | 平均耗时 |
|--------|---------|-------|-----------|---------|
| `flash_news` | ~1,000 | 1 | 6/6 | ~20s |
| `deep_report` | ~4,600 | 5 | 9/9 | ~60s |
| `earnings_analysis` | 待测试 | — | — | — |

## 项目结构

```
multiAgent/
├── app.py                  # FastAPI 启动入口 (port 8010)
├── agents/                 # LangGraph 节点 + 工作流构建器
│   ├── nodes/              # 9 个 Agent 节点
│   ├── workflows/          # builder.py + templates/
│   └── state/              # 嵌套状态 TypedDict
├── harness/                # 治理层：安检责任链
│   ├── handlers/           # 输入安全、事实核查、幻觉检测等
│   └── orchestrator/       # 主编排器
├── models/                 # LLM 客户端 + Prompt 管理 + 语义缓存
│   ├── llm_providers/      # DeepSeek / Qwen Client
│   ├── prompts/            # Jinja2 Prompt 模板
│   └── router.py           # 模型路由策略
├── retrieval/              # RAG 检索层
│   ├── chunkers/           # 段落感知切分
│   ├── embedders/          # BGE 嵌入模型
│   ├── retrievers/         # HybridRetriever + CrossEncoder Reranker
│   └── pipelines/          # 索引构建流水线
├── infrastructure/         # DB / Cache / Queue / Observability
│   ├── database/           # PostgreSQL + Checkpointer
│   ├── cache/              # Redis 连接池
│   ├── memory/             # 短期记忆 (ZSET)
│   └── observability/      # 结构化日志 + Prometheus 指标
├── api/                    # FastAPI 路由 + 中间件
│   └── routers/            # chat / session / admin / task / health
├── mcp_tools/              # MCP 工具服务
│   └── mcp_servers/        # search_server / chart_server
├── frontend/               # Next.js 14 前端
│   ├── app/                # 页面路由
│   ├── components/         # React 组件
│   ├── stores/             # Zustand 状态管理
│   └── lib/                # API 客户端
├── tests/                  # 全量测试（unit / integration / e2e）
├── scripts/                # 启动/索引/基准测试脚本
├── config/                 # YAML 配置 + 工作流模板
└── docker/                 # Docker Compose (PG + Qdrant + Grafana)
```

## License

MIT
