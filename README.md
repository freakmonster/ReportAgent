# 智能研报生成系统

> 基于 LangGraph 的多 Agent 协作式智能研报自动生成平台，专业金融研报 × 现代 AI 产品的精品质感。

## 这是什么项目？

输入一个研究主题，系统自动完成 **意图识别 → 研究规划 → 数据采集（Tavily 搜索 + RAG 知识库）→ 数据处理 → 数据分析 → 报告撰写 → 编辑润色 → 质量审核 → 发布输出** 的全流程，最终生成结构化的 Markdown 研报。

**核心能力**：
- 支持 3 种报告类型：深度研报、快讯、财报分析
- 多 LLM 可选：DeepSeek Flash / Pro、Qwen 8B / 32B / Max
- RAG 知识库检索（Qdrant 向量库 + Hybrid 检索 + CrossEncoder 重排序）
- LLM 驱动的智能图表规划：自动分析文档选择 9 种图表类型（柱状图、折线图、饼图、面积图、散点图、雷达图、漏斗图、双轴图、直方图），随机选取最优呈现
- 图表数据持久化：图表随报告历史记录保存，刷新不丢失
- 短期记忆追踪：最近 3 轮主题去重注入搜索，提升相关性
- 语义缓存减少重复 LLM 调用成本
- SSE 实时推送节点进度，前端可视化展示执行过程
- 治理层责任链安检：输入安全、事实核查、幻觉检测
- 内容 hash 去重：向量库同步索引时自动去重，避免重复 chunk 膨胀
- 多会话管理：会话级历史隔离，空会话自动清理，支持删除确认
- 运营面板：Token 用量、请求量、成功率、模板分布等监控指标

<img width="760" height="360.5" alt="屏幕截图 2026-07-25 164325" src="https://github.com/user-attachments/assets/f447d459-4b34-477f-9b49-c6997a1c1307" />


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
# MCP search_server → http://localhost:8005
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
| **后端框架** | FastAPI 0.110+ + SSE (sse-starlette 2.0+) | REST + 流式事件推送 |
| **LLM** | DeepSeek v4、Qwen（通义千问） | 通过 `resolver.py` 按 task 动态路由 |
| **搜索引擎** | Tavily API | 实时网页搜索 |
| **向量检索** | Qdrant + BGE/Chroma | chunk → embed → RAG |
| **缓存** | Redis + 语义缓存 | 减少重复 LLM 调用 |
| **数据库** | PostgreSQL (SQLAlchemy Core + Alembic) | 工作流状态、会话、运营数据 |
| **前端** | Next.js 14 + TypeScript + Tailwind CSS 3.4 + Zustand 5 | Markdown 实时渲染、深蓝精品质感 UI |
| **可观测性** | structured logging + Prometheus + Docker Compose 集成 Grafana | 指标、追踪 |
| **测试** | pytest (unit / integration / e2e / contract / chaos) | 覆盖核心链路 |
| **代码质量** | ruff (linter + formatter) + pre-commit hooks | 提交前自动格式化与检查 |

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
│  data_collector       data_processor    │
│  (Tavily ∥ RAG)             ↓           │
│       ↓              data_analyst       │
│       ↓  (LLM 图表规划 + AntV 生成)     │
│       ↓──────────────────┘              │
│  writer  →  editor  →  reviewer         │
│                    →  publisher         │
└─────────────────────────────────────────┘
              │
              ▼
          SSE 实时推送 → 前端渲染
```

### 效果数据

| 工作流 | 输出字符数 | 章节数 | 节点通过率 | 平均耗时 (flash) |
|--------|---------|-------|-----------|-----------------|
| `flash_news` | ~1,000 | 1 | 6/6 | ~60s |
| `deep_report` | ~5,000–7,000 | 5 | 10/10 | ~125s |
| `earnings_analysis` | ~1,500 | 1 | 6/6 | ~60s |

> 耗时分布（deep_report / flash）：data_collector ≈ 42s（Tavily 搜索 + RAG 检索并行），writer ≈ 22s（5 章并行），data_analyst ≈ 28s（LLM 图表规划），其余节点 <1s。Pro 模型 writer 耗时增至 ~140s。

### 前端视觉设计

前端采用 **专业金融研报 × 现代 AI 产品** 的精品质感，以深蓝 + 金色点缀传递权威感，毛玻璃、渐变、微动效传递科技感。

| 区域 | 设计要点 |
|------|---------|
| **Header** | 深蓝渐变背景 + 微弱网格纹理，品牌 Logo 蓝→青渐变文字 + 金色描边「生成系统」，导航 tab 胶囊形状带蓝色发光描边 |
| **左侧栏** | 深色半透明毛玻璃（`backdrop-blur-xl`），会话列表卡片化（选中态金色左边框 + 微弱金色背景），模型选择器为彩色标签按钮 |
| **输入区** | `rounded-2xl` 大圆角输入框，聚焦时蓝色光晕扩散动画，发送按钮渐变色（蓝→青）悬停微放大 |
| **报告卡片** | 微妙投影替代传统边框（`shadow-blue-500/5`），顶部按报告类型显示彩色渐变条（深度研报=蓝，快讯=琥珀，财报=翠绿），展开时蓝光从上往下照亮动画，引用标注 hover 显示 URL |
| **空状态** | 品牌首屏：CSS 粒子漂浮背景 + Slogan 逐字淡入 + 三张功能卡片（hover 上浮）+ 底部引导提示 |
| **会话管理** | 多会话隔离，空会话自动清理，创建/删除/切换，打开页面自动创建新会话 |
| **运营面板** | Token 总量/请求数/成功率/平均耗时四卡片统计，最近工作流表格，模板分布进度条，7/30 天时间范围切换 |

### 前端架构

```
frontend/
├── app/                    # Next.js 14 App Router
│   ├── page.tsx            # 主页（工作台）
│   ├── layout.tsx          # 根布局（全局深蓝背景）
│   ├── globals.css         # 全局样式 + 动画关键帧
│   ├── history/page.tsx    # 历史报告列表
│   ├── dashboard/page.tsx  # 运营数据面板
│   ├── report/[id]/page.tsx # 报告详情页
│   └── api/chat/stream/    # SSE 流式代理
├── components/
│   ├── TaskForm.tsx        # 输入表单（模型选择 + 提示）
│   ├── SessionSelect.tsx   # 会话列表
│   ├── ReportBubble.tsx    # 精装报告卡片
│   ├── ReportContent.tsx   # Markdown 渲染 + 引用标注
│   ├── NodeProgress.tsx    # Agent 执行进度
│   ├── OutputToolbar.tsx   # 导出/复制工具栏
│   ├── DashboardCards.tsx  # 运营面板统计卡片
│   └── WorkflowTable.tsx   # 工作流记录表格
├── stores/                 # Zustand 状态管理
│   ├── workflowStore.ts    # 工作流实时状态（SSE）
│   ├── sessionStore.ts     # 会话列表 CRUD
│   ├── reportStore.ts      # 报告历史持久化
│   └── uiStore.ts          # 全局 UI 状态
└── lib/api.ts              # API 客户端
```

## 项目结构

```
ReportAgent/
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
│   ├── mcp_std_client.py   # 标准 MCP 客户端（AntV 图表等）
│   ├── registry.py         # 工具注册表
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
