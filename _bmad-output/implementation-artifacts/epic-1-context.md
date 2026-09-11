# Epic 1 Context: 进入安全工作区并可靠保留请求

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

- 仓库只包含 `edw-web`、`edw-api`、`edw-worker` 三个业务工程；共享 Python 领域、应用、持久化、Knowledge Gateway 和 LLM Gateway 是内部库，不能成为第四个监听服务。`contracts`、`migrations`、`deployment`、`tests`、`evaluation`、`scripts` 是交付目录。
- Web 只通过 REST、带 Bearer 的 fetch-streaming SSE 和 OIDC 访问系统，不直连数据库、消息队列、模型或企业接口。API 是权限、工作区和敏感业务变更的权威入口；Worker 只执行获准任务类别并受独立身份、数据库授权和资源边界约束。
- 本地验收必须运行真实 Web/API/Worker、Keycloak、PostgreSQL、RabbitMQ、Redis、S3 兼容对象存储和 NGINX。只有模型及企业系统端口可以使用明确标注的确定性替身；替身结果不能宣称真实模型效果、企业联调或生产 NFR 已通过。
- SPA 使用 OIDC Authorization Code + PKCE S256，令牌只保存在内存；API 校验签名、issuer、audience、exp/nbf 和 JWKS 轮换。无效身份、依赖故障或未配置策略必须安全拒绝，不能回退到样例用户、共享凭据或特权工作区。
- PostgreSQL 保存业务、权限、任务、Outbox/Inbox 和审计真相；Redis 仅可重建。RabbitMQ 使用持久化消息、publisher confirm 和至少一次传输。任务、消息和 SSE 必须保持明确身份、顺序、幂等、重放与失败状态。
- 依赖、容器镜像和契约必须锁定；禁止 `latest`。Node 受支持 LTS、pnpm、Python 3.12、uv/Python 依赖和镜像组合在首次工程启动时核验并记录 lock、许可证/清单和兼容证据。
- 仅可对新建且能证明属于 `eid` 的隔离本地开发/测试数据库执行迁移和测试数据写入。执行前核对主机、库名、Compose project、数据库 marker、bucket、broker vhost 与 Keycloak realm/client；不能证明隔离时停止，禁止删除数据库、清理既有数据或接触生产/企业库。
- `/health/live` 只表示进程存活；`/health/ready` 必须反映数据库、schema 和必需配置的实际状态。依赖不可用时保留准确降级原因，不得以静态 200 或样例数据冒充就绪。
- API 使用 `/api/v1`、snake_case、UTC RFC3339、不可猜测 ID、统一结构化错误、`X-Request-ID`/`traceparent`，并由服务端推导 actor、workspace、scope 和 classification。秘密、令牌、敏感正文与 Prompt 不得进入 URL、浏览器持久存储或普通日志。
- 每个 Story 均执行中等质量门禁：锁定契约与迁移、关键正反测试、独立代码审查以及检查→优化→验证。失败或缺失的本地功能不能转记为环境缺口。

## Technical Decisions

- 采用模块化单体与六边形架构。领域层不依赖 FastAPI、Celery 或具体 UI/模型 SDK；API router、Worker handler 和共享 application/domain/ports 之间保持单向依赖，通过组合根注入适配器。
- 使用单一 SQLAlchemy metadata 和 Alembic 迁移链，API、Worker 与 migration 采用不同数据库身份及连接池。表和迁移随首个实际用途增量引入，避免先建完整领域模型。
- `edw-web` 为 React/TypeScript/Vite SPA，使用 Ant Design、React Router、TanStack Query 和有限 Zustand；`edw-api` 为 FastAPI/Pydantic 2/SQLAlchemy 2/psycopg 3；`edw-worker` 为 Celery，并保留六类队列及单活动 Beat。
- 本地启动顺序为：验证环境 manifest 与隔离性，安装冻结依赖并检查契约，启动基础设施，执行隔离守卫后迁移，再构建并启动 API/各 Worker/NGINX，最后运行真实跨工程契约与端到端检查。
- 身份与请求上下文契约至少携带 request/trace、actor/service、workspace、policy epoch、classification、purpose 和受限 delegation 引用；用户长期令牌不进入消息，后台执行不得扩大原用户权限。

## UX & Interaction Patterns

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
