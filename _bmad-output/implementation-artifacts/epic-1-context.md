# Epic 1 Context: 进入安全工作区并可靠保留请求

## 当前开发与验证边界（2026-09-21）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件的执行安排统一受[开发与验证规则](../planning-artifacts/development-validation-policy.md)约束。下文涉及启动、部署、迁移、fixture、功能测试、浏览器实测、联调、性能和故障演练的条款保留为待执行验收要求，当前暂停执行并记录 `not-run`；其中静态检查与编译可按规则单独执行。历史证据按原日期保留，不代表本轮通过或继续运行的授权。


<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Epic 1 建立后续文档工作的可信入口：用户通过真实本地 OIDC 身份进入项目隔离的工作区，在当前权限下发现实际记录，并使已接受的后台请求即使遇到代理、消息队列或 Worker 故障也能恢复。Epic 的本地完成只证明隔离环境中的真实三工程与真实本地基础设施链路；企业身份联邦、真实企业系统语义以及生产安全、容量和高可用证据仍由 Epic 13 独立验收。

## Stories

- Story 1.1: 打开隔离的三工程工作区
- Story 1.2: 强制执行当前项目成员关系与密级
- Story 1.3: 查找实际工作区记录与保留集合
- Story 1.4: 通过持久化传输保留已提交操作
- Story 1.5: 在不接受陈旧结果的前提下恢复或取消执行
- Story 1.6: 重连后继续跟踪真实任务与通知

## Requirements & Constraints

- 2026-09-17：依据后续已批准的 `docs/remote-deployment-path-authorization.md`，EID 服务已切换到 root 控制的 `seadee-develop:/opt/eid`；旧 `/opt/docker/eid` 保留。下文 2026-09-15 路径为历史记录，当前配置和后续实施均使用新路径，仍逐次验证同一项目归属。

- 2026-09-15 用户授权开发服务改用 `seadee-develop:/opt/docker/eid`，后续读取 `deployment/environments/seadee-develop.yaml`。文中“本地”交付指隔离开发验收级别，不再表示服务必须运行本机；本机仅运行开发工具、测试客户端及 SSH 转发。迁移前仍须证明远端 EID 专用资源归属，企业/生产验收边界不变。
- 2026-09-15 已重新核对最新 PRD、架构、UX 与 Epic 分片。每条本地 AC 对应可观察结果和具名验证；按变更影响选择回归与一次独立风险审查，有安全/数据完整性问题则专项复审。失败仍须修复、复验，不减少安全门禁。
- 本地测试可声明隔离的合成政策并验证同一生产判定路径的成功与拒绝；不把没有实现的功能记成环境缺口。真实模式缺政策仍拒绝，企业/模型/生产验收留在 Epic13。

- 仓库只包含 `edw-web`、`edw-api`、`edw-worker` 三个业务工程；共享 Python 领域、应用、持久化、Knowledge Gateway 和 LLM Gateway 是内部库，不能成为第四个监听服务。`contracts`、`migrations`、`deployment`、`tests`、`evaluation`、`scripts` 是交付目录。
- Web 只通过 REST、带 Bearer 的 fetch-streaming SSE 和 OIDC 访问系统，不直连数据库、消息队列、模型或企业接口。API 是权限、工作区和敏感业务变更的权威入口；Worker 只执行获准任务类别并受独立身份、数据库授权和资源边界约束。
- 当前仅进行软件开发、代码检查和编译验证，不启动或使用 Web/API/Worker 及基础设施进行功能实测。原真实链路和替身边界保留为后续验收要求，当前运行验证为 not-run；静态检查或编译通过不能证明真实模型效果、企业联调或生产 NFR。
- SPA 使用 OIDC Authorization Code + PKCE S256，令牌只保存在内存；API 校验签名、issuer、audience、exp/nbf 和 JWKS 轮换。无效身份、依赖故障或未配置策略必须安全拒绝，不能回退到样例用户、共享凭据或特权工作区。
- PostgreSQL 保存业务、权限、任务、Outbox/Inbox 和审计真相；Redis 仅可重建。RabbitMQ 使用持久化消息、publisher confirm 和至少一次传输。任务、消息和 SSE 必须保持明确身份、顺序、幂等、重放与失败状态。
- 依赖、容器镜像和契约必须锁定；禁止 `latest`。Node 受支持 LTS、pnpm、Python 3.12、uv/Python 依赖和镜像组合在首次工程启动时核验并记录 lock、许可证/清单和兼容证据。
- 仅可对新建且能证明属于 `eid` 的隔离本地开发/测试数据库执行迁移和测试数据写入。执行前核对主机、库名、Compose project、数据库 marker、bucket、broker vhost 与 Keycloak realm/client；不能证明隔离时停止，禁止删除数据库、清理既有数据或接触生产/企业库。
- `/health/live` 只表示进程存活；`/health/ready` 必须反映数据库、schema 和必需配置的实际状态。依赖不可用时保留准确降级原因，不得以静态 200 或样例数据冒充就绪。
- API 使用 `/api/v1`、snake_case、UTC RFC3339、不可猜测 ID、统一结构化错误、`X-Request-ID`/`traceparent`，并由服务端推导 actor、workspace、scope 和 classification。秘密、令牌、敏感正文与 Prompt 不得进入 URL、浏览器持久存储或普通日志。
- 每个 Story 保留中等质量的检查→优化→验证闭环；当前执行契约/迁移源码检查、独立代码审查和编译验证。关键正反测试仅保留用例及待执行清单，不运行功能测试。软件缺陷仍须修复，未执行运行验收独立记录。

## Technical Decisions

- 采用模块化单体与六边形架构。领域层不依赖 FastAPI、Celery 或具体 UI/模型 SDK；API router、Worker handler 和共享 application/domain/ports 之间保持单向依赖，通过组合根注入适配器。
- 使用单一 SQLAlchemy metadata 和 Alembic 迁移链，API、Worker 与 migration 采用不同数据库身份及连接池。表和迁移随首个实际用途增量引入，避免先建完整领域模型。
- `edw-web` 为 React/TypeScript/Vite SPA，使用 Ant Design、React Router、TanStack Query 和有限 Zustand；`edw-api` 为 FastAPI/Pydantic 2/SQLAlchemy 2/psycopg 3；`edw-worker` 为 Celery，并保留六类队列及单活动 Beat。
- 当前执行顺序为：阅读变更及契约 → 软件开发 → 代码检查与审查 → 编译验证 → 修复并复查 → 记录未执行运行验收。原环境启动、迁移与真实跨工程端到端检查暂停，不作为当前操作步骤。
- 身份与请求上下文契约至少携带 request/trace、actor/service、workspace、policy epoch、classification、purpose 和受限 delegation 引用；用户长期令牌不进入消息，后台执行不得扩大原用户权限。

## UX & Interaction Patterns

- 功能 Story 验证改动控件与具名状态；完整 viewport/zoom/原型全控件基线由 7-5 负责。1.3 保留首页四 KPI、四卡片、最近记录四标签和右侧栏；质量/生成等未来数据保持未评估，无样例分数。列表、搜索、计数、存储均来自同一当前授权集合，收藏/可恢复可见性写入必须持久化并审计。

- 保留原型 P-00/P-12 的布局与交互基线：64px 顶栏、266px 侧栏、12px shell 间距/内边距、原六个导航入口、通知与账户位置、toast 和窄屏提示。原始 `docs/prototype/index.html` 不修改。
- 现有页面按匹配 viewport、字体、缩放和状态进行严格 1:1 比对；真实身份、路由、项目和依赖状态替换演示数据。新增账户/搜索/项目详情遵循 UX 契约，不声称拥有不存在的原型像素基线。
- 宽度不超过 1180px 时保持最小 1180px 桌面布局、横向滚动和原提示；1181px 不显示提示。不得自行加入移动堆叠、折叠侧栏或暗色主题。
- 认证、加载、空、失败、禁止、会话过期、离线和依赖降级必须具有持久、可读状态；1800ms toast 只做瞬时反馈，不能承载唯一错误或成功事实。键盘焦点、对话框 Escape/取消、重新认证和安全退出遵循统一交互契约。

## Cross-Story Dependencies

- 1.1 无前置依赖，建立可运行工程、基础身份、最小工作区数据和真实就绪语义。
- 1.2 依赖 1.1，并将当前成员关系、RBAC、ABAC、密级、policy epoch、服务身份和数据库授权应用到每次使用。
- 1.3 依赖 1.2，所有列表、搜索、计数与集合使用同一当前授权数据集。
- 1.4 依赖 1.2，引入 PostgreSQL Task/Attempt/Outbox/Inbox 和 RabbitMQ 持久传输。
- 1.5 依赖 1.4，引入 lease/fence、恢复、重试与取消竞态保护。
- 1.6 依赖 1.3 与 1.5，通过持久 TaskEvent、REST snapshot 和可重放 SSE 提供最终任务观察链。
