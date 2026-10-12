# 灵山胜境 AI 数字人导游系统

一套面向文旅导览场景的**多模态 Agentic RAG** 应用：支持语音 / 文字 / 图片 / 视频四类输入，贯穿「理解 → 检索 → 生成 → 语音合成」全链路，并提供 3D 数字人交互与管理后台。

核心不是"套壳大模型"，而是一套从 **Agent 编排 → 检索增强 → 长期记忆 → 多模态 → 可观测与可靠性 → 生产化** 的完整工程落地。

---

## 核心亮点

| 能力 | 实现 |
|------|------|
| **智能体编排** | 基于 Function Calling 实现 ReAct 自主决策；采用 Agent-as-Tool 模式搭建 Orchestrator + 领域子 Agent 两级编排，检索策略由 LLM 动态路由（寒暄直答 / 知识检索 / 工具调用自动分流） |
| **检索增强（RAG）** | 向量 + BM25 混合检索 + RRF 融合 + bge-reranker 精排 组成的多级召回链路，叠加知识图谱 GraphRAG（离线 LLM 三元组抽取 + 在线实体链接与邻域扩展） |
| **长期记忆** | memoryAgent：SQLite + Chroma 双存储、读写分离异步、30 天时间衰减召回、语义冲突合并，并提供用户查看 / 删除的合规接口 |
| **多模态** | 语音（faster-whisper ASR）/ 文字 / 图片视觉理解 / 视频「关键帧 + 视觉 + ASR + LLM 融合归一化」降级闭环 |
| **可靠性** | LLM 层指数退避重试、超时熔断、并发限流、token 预算告警 |
| **可观测性** | Langfuse v4 全链路 trace（贯通工具调用层级）+ 结构化日志 + Sentry 错误追踪 |
| **工程化** | 持久化任务队列（建图 / 记忆压缩异步化，失败退避重试 + 崩溃恢复）、统一鉴权、生产 WSGI（waitress）+ SQLite WAL |
| **评测** | RAG / Agent / 直答 三级评测集与自动化脚本 |

---

## 技术栈

| 层 | 技术 |
|------|------|
| 后端 | Flask + flask-sock(WebSocket) + SQLAlchemy / SQLite + ChromaDB |
| 大模型 | 通义千问 Qwen3.5-Omni-Flash（DashScope，兼容 OpenAI 协议） |
| 检索 | sentence-transformers（text2vec-base-chinese）+ rank-bm25 + bge-reranker-base |
| 语音 | faster-whisper（ASR）+ Edge-TTS（合成） |
| 可观测 | Langfuse v4 + Sentry + 结构化日志 |
| 部署 | waitress + SQLite WAL |
| 前端 H5 | Vue3 + Vite + Pinia + Vue Router + Vant |
| 管理后台 | Vue3 + Vite + Pinia + Vue Router + Element Plus |

---

## 架构

```
用户（语音/文字/图片/视频）
        │
        ▼
   WebSocket 网关（身份校验）
        │
        ▼
 ┌──────────────┐   动态路由    ┌────────────────────┐
 │  预判 Router  │ ───────────► │ Orchestrator (ReAct) │
 └──────────────┘              └─────────┬──────────┘
        │                                │ Agent-as-Tool 编排
        ▼                                ▼
   寒暄直答                   ┌──────────────────────┐
                             │  RAG Agent / 行程 Agent │
                             └──────────┬───────────┘
                 ┌──────────────────────┼──────────────────────┐
                 ▼                      ▼                       ▼
          混合检索 + 精排          GraphRAG 图谱扩展         工具调用
         (向量+BM25+RRF)        (实体链接+邻域扩展)      (路线/景点信息)
                 └──────────────────────┴──────────────────────┘
                                        │
                           长期记忆 memoryAgent（双存储）
                                        │
                                        ▼
                               LLM 生成 → TTS 合成 → 数字人输出
```

---

## 目录结构

```
backend/
├── app.py                 # 应用入口（waitress 生产服务）
├── config.py              # 配置（从环境变量读取，密钥不落源码）
├── log_config.py          # 结构化日志（request_id + 轮转文件）
├── models.py              # 数据库模型（含 Job 任务表 / KnowledgeTriple 三元组表）
├── requirements.txt
├── agents/                # 多 Agent 编排（Orchestrator / 子 Agent）
├── services/              # RAG / GraphRAG / 记忆 / LLM / ASR / TTS / 可观测 / 任务队列
├── routes/                # REST API 路由（统一鉴权）
├── websocket/             # WebSocket 通信
├── evaluation/            # 三级评测集与脚本
└── scripts/               # 建图 / 路线图片等命令行工具
h5/                        # H5 游客端（Vue3 + Vant）
admin/                     # 管理后台（Vue3 + Element Plus）
knowledge/                 # 知识库源文档
```

---

## 快速开始

### 环境要求

| 依赖 | 版本 |
|------|------|
| Python | 3.10+ |
| Node.js | 18+ |
| ffmpeg | 可选（视频 / 语音降级链路） |

### 1. 配置密钥

在 `backend/` 下创建 `.env`，参考 `backend/.env.example` 填入所需密钥（模型 / 地图 / 可观测等均为**可选**，未配置时对应能力自动降级或关闭）。本地真实密钥建议放 `backend/.env.local`（已被 `.gitignore` 排除）。

### 2. 安装与启动

```bash
# 后端
python -m venv .venv
# Windows: .venv\Scripts\activate   macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
python backend/app.py

# H5 游客端
cd h5 && npm install && npm run dev

# 管理后台
cd admin && npm install && npm run dev
```

### 3. 访问

| 服务 | 地址 |
|------|------|
| 后端 API | http://localhost:5001 |
| H5 游客端 | http://localhost:3000 |
| 管理后台 | http://localhost:3001 |

---

## 说明

- 知识库向量需通过管理后台手动同步；知识图谱通过后台「建图」接口或 `scripts` 命令行工具异步构建。
- 所有外部依赖（LLM / ASR / 嵌入 / 精排 / 可观测）均做了**失败降级**，缺失配置不影响系统启动与核心问答可用性。