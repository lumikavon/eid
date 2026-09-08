# 企业智能文档编写工作台 Tech Spec 交付包

版本：V1.1  
日期：2026-09-08

## 1. 交付目标

本交付包将“企业智能文档编写工作台”的产品方案、总体技术架构、LLM/RAG 文档生成机制、Evidence 证据体系、文档审校体系、权限审计、数据模型、接口规范、测试验收与实施路线，整理为可用于立项、架构评审、研发拆分和测试验收的软件技术规格文档。

## 2. 文档清单

| 文件 | 用途 |
|---|---|
| `01-软件技术规格说明书.md` | 主规格：目标、范围、架构、功能、模块、关键流程、技术选型、交付基线 |
| `02-系统架构与模块设计.md` | 详细模块职责、调用关系、运行时架构、状态机、错误与降级策略 |
| `03-数据模型与API接口规范.md` | 领域模型、核心表、Document AST、Evidence/Claim、REST API、事件契约 |
| `04-LLM-RAG与文档生成编排规范.md` | Query Planning、Hybrid Search、Rerank、Evidence Pack、章节生成、审校和模型路由 |
| `05-安全权限审计与NFR规范.md` | RBAC/ABAC、知识权限继承、数据分级、外部模型脱敏、审计、性能、可用性与运维 |
| `06-测试验收与实施计划.md` | 测试策略、AI/RAG 评测、验收指标、POC/一期/二期/三期实施路线 |
| `07-技术栈基线与工程规范.md` | 已确认技术栈、运行时边界、双检索链、异步编排、工程与替换规则 |
| `assets/总体技术架构图.png` | 前期设计的总体技术架构图 |
| `prototype/index.html` | 前期设计的可交互 Web 原型 |

## 3. 推荐使用方式

- **立项/管理评审**：优先阅读 `01`、`05`、`06`。
- **架构/研发评审**：重点阅读 `01`、`02`、`03`、`04`、`07`。
- **AI/RAG 团队**：重点阅读 `04`，同时遵循 `03` 的 Evidence/Claim 数据契约。
- **测试团队**：以 `06` 为验收基线，并将其中指标转为自动化测试项。
- **前端团队**：结合 `prototype/index.html` 与 `01/02/07` 中的交互状态和 React 技术基线完成实现。

## 4. 核心设计结论

系统采用：

> **模板驱动 + Evidence 驱动 RAG + 分章节生成 + Claim 级事实核验 + 多级 Reviewer + 人工签发**

核心边界：

- 企业知识库负责“公司知道什么”；
- LLM 负责“理解、规划、推理和表达”；
- Document Engine 负责“文档如何构建、修改、版本化和导出”；
- Reviewer 负责“文档是否完整、可信、一致、合规”；
- 人负责最终业务、技术和质量决策。

正式文档发布前，必须能够回答：

1. 关键事实从哪里来；
2. 关键需求是否全部覆盖；
3. 关键参数是否前后一致；
4. 哪些内容由 AI 生成、修改或审校；
5. 哪些待确认项尚未闭环；
6. 当前文档使用了哪个模板、哪个版本和哪些知识依据。
## 5. V1.1 技术栈变更摘要

V1.1 将技术选型从建议状态收敛为已确认基线：

- ReactJS + TypeScript + Vite + Ant Design；
- Tiptap 开源核心 + 自建 Document AST Adapter；
- Python 3.12 + FastAPI/Uvicorn/Pydantic 2；
- SQLAlchemy 2 + psycopg 3 + Alembic；
- PostgreSQL + JSONB，Redis 仅承担缓存/限流；
- Celery + RabbitMQ quorum queue，PostgreSQL 状态机 + Outbox + Celery Beat；
- REST `/api/v1` + OpenAPI + SSE；
- Keycloak + OIDC、NGINX；
- S3 API，SeaweedFS 为自建缺省实现；
- Knowledge Gateway 保留现有知识库权威源；工作台附件使用 pgvector + PostgreSQL FTS + jieba；
- BGE-M3 + bge-reranker-v2-m3 / FlagEmbedding；
- Python LLM Gateway + vLLM，Qwen3-32B 为正文/规划评测候选；
- PaddleOCR、LibreOffice、Mermaid CLI 等采用隔离 Worker；
- Docker/Compose，生产 Kubernetes + Helm；
- CloudNativePG + Barman Cloud；
- OTel + Prometheus/Grafana/Loki/Tempo/Alertmanager；
- pytest/Vitest/RTL/Playwright/k6 + Ruff/mypy/ESLint/TypeScript，uv + pnpm 锁依赖。

