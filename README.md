# EID 三工程开发工作区

本仓库包含 `edw-web`、`edw-api`、`edw-worker` 三个工程，依赖 PostgreSQL、Keycloak、RabbitMQ、Redis、SeaweedFS S3 和 NGINX。统一入口为 <http://localhost:18080>。各 Story 的完成状态与独立验收证据见 `_bmad-output/implementation-artifacts/`。

## 当前开发环境

当前服务运行于 `seadee-develop:/opt/eid`，以 [seadee-develop.yaml](deployment/environments/seadee-develop.yaml) 为唯一开发环境选择器。浏览器入口仍为 `http://localhost:18080`，通过已授权的 SSH 隧道连接；本机 PostgreSQL 转发端口为 **15432**，远端仍为 loopback 55432。操作步骤、归属守卫与恢复边界见 [远端开发说明](docs/remote-development.md)。

以下本机 bootstrap、55432 地址和 `.local/runtime-images.json` 说明保留为 Story 1.1 历史实现参考，**当前环境不执行本机 bootstrap、不启动本机开发容器、不使用旧本机运行清单**。当前有效运行清单位于 `.local/remote/seadee-develop/runtime-images.json`，绑定远端九服务、schema 3 来源和候选指纹；新候选必须重新完成其验证，不能修改旧清单冒充已部署。

## 工作区发现（Story 1.3，软件交付）

本次交付仅包括软件实现、独立静态审查和编译。用户已取消实际环境验证，运行行为保持未验证；以下运行命令仅为历史操作参考，当前不执行测试、启动、迁移、fixture 或部署。

实现提供当前授权下的首页汇总、记录列表、搜索、私人收藏和回收站元数据。各列表的标签与类型、生命周期、集合筛选取交集；数量及字节统计使用相同授权集合。搜索词仅进入 POST 正文，最多128个 Unicode 码点；中文组合输入在提交后应用上限。账户及项目选择位于右上“账户与会话”，成员管理保留在账户页。

| 接口（前缀 `/api/v1/workspaces/{workspace_id}`） | 用途 |
|---|---|
| `GET /discovery`、`GET /discovery/summary` | 有界游标列表、当前授权汇总 |
| `GET /discovery/{resource_id}` | 当前授权详情及可用操作 |
| `POST /search` | 元数据搜索，与其他筛选取交集 |
| `PUT /favorites/{resource_id}` | 当前主体的收藏目标状态及 expected revision |
| `POST /recycle/{resource_id}:restore` | 依明确政策恢复列表可见性 |

收藏和恢复命令必须携带幂等键；未知结果只能核对原操作，不能假报成功。恢复不改变 ARCHIVED 状态、正文/head 或历史，缺少有效政策时拒绝；隔离开发政策只作用于有明确 owner/version 的专用验收记录。质量、生成量、审校与推荐等后续能力没有来源时保持未评估/未开放；元数据字节不代表附件、磁盘占用或配额。

`0007_workspace_discovery` 仅扩展发现表和 API 所需窄授权，Worker 不获得新表权限；禁止 downgrade 或清理旧数据。新 fixture 按 run 追加专有项目/记录，复用已收据化身份而不重置其密码或原项目策略。浏览器验收在当前候选、真实环境和初始状态复核后消耗一次性 run；失败及未知结果均保留，不复用。

当前软件审查与编译结果见 [Story 1.3 软件交付记录](_bmad-output/implementation-artifacts/story-1-3-software-review-2026-09-21.md)，历史验证保留在 [验证记录](_bmad-output/implementation-artifacts/story-1-3-validation.md)。本节不是运行验收通过的声明。

## 启动前提

- Windows PowerShell 7；当前 context 必须是本机 `desktop-linux`，实际引擎必须为 `linux/amd64`。脚本记录 Docker Server/API、Compose 与 buildx 版本，并核验 Compose `--wait`/`--wait-timeout` 及 BuildKit/buildx 能力。本地已验证组合为 Docker Server `29.1.3`、API `1.52`、Compose `5.0.1`、buildx `v0.30.1-desktop.1`；这些是兼容证据，不是唯一允许版本。
- Node.js `24.20.0`、pnpm `10.17.1`、Python `3.12.14`、uv `0.11.23`。脚本会优先使用未纳入版本控制的 `.local/tools/node-v24.20.0-win-x64`（若存在），并在启动前精确核验版本。
- 本机端口 `18080`、`55432`、`58080`、`55672`、`55673`、`56379`、`58333` 可用。
- 首次启动时不得存在由其他项目创建的同名 `eid-local` 容器或 `eid-local-*` 数据卷。脚本只创建和验证本仓库的 `.local/ownership.json`，不会接管、清理或重置既有资源。

## 启动与核验

在仓库根目录运行：

```powershell
./scripts/bootstrap.ps1
```

bootstrap 先核验工具链、冻结锁文件、镜像锁清单和 Docker 本机归属，再启动基础设施。Keycloak 必须在限定时间内通过真实 readiness，且数据库 marker、S3 bucket、RabbitMQ vhost/权限、Keycloak realm/client/PKCE 配置全部通过后，才会执行 Alembic 迁移和启动三工程。最终启动使用 Compose `--wait`，API、Web 和 Worker 都必须通过各自健康检查。全部应用容器健康后，脚本才在未纳入版本控制的 `.local/runtime-images.json` 中记录源文件指纹、构建镜像 ID 和实际运行容器 ID；记录内容不包含环境变量或凭据。任一检查失败均以非零退出停止，不会删除数据库或清理数据。

bootstrap 在构建前捕获各工程源指纹，并通过 build argument 写入实际镜像的 `io.eid.source-fingerprint` 标签。记录前必须同时匹配构建前指纹、镜像标签和当前源码；构建期间或构建后源码变化会拒绝生成通过记录。日志扫描结束时还会重新核验九个容器及镜像/源码绑定，发现替换或变化即失败。

运行清单使用 schema 2：三个应用记录源指纹、镜像和容器 ID，六个基础设施服务按锁定摘要解析实际镜像 ID 并绑定运行容器。每次容器检查均核对归属 nonce，采集结束再次检查九个服务的实例、运行/健康状态、镜像及归属记录，保存前再探测公开 readiness。旧版三服务清单必须通过 bootstrap 重新生成。初始化在每个 broker、Keycloak 或 bucket 初始化步骤前复查专属 nonce 和服务实例，变化即停止；这些检查不承诺 Docker、HTTP 与数据库间的原子快照或未来状态不变。

前向迁移 `0002_worker_metadata_only` 收回 Worker 对身份、工作区和成员映射表的 SELECT，仅保留就绪检查所需的迁移元数据读取；既有业务行不变。数据库身份守卫和迁移连接都配置 3 秒连接、5 秒语句及 2 秒锁等待上限，超时则失败。

`.local/runtime-images.json` 只证明生成时的源文件和运行容器。修改 API、Worker、Web、锁文件或对应 Docker 构建输入后，必须重新运行 bootstrap；旧清单会因源指纹或镜像/容器 ID 不匹配而验证失败。可在已启动环境中只读复核：

```powershell
$env:EID_MIGRATION_DATABASE_URL = 'postgresql+psycopg://eid_migrator:local-migrate-only@localhost:55432/eid_local_dev'
./scripts/verify-local-environment.ps1 --verify-runtime-images
```

RabbitMQ 的 `eid_broker_admin` 仅供主机侧 bootstrap/guard 使用，不会传入 API 或 Worker 容器。bootstrap 在全部既有资源只读守卫通过后，仅当 `eid_api` 与 `eid_worker` 同时缺失时创建两个无管理标签的运行身份；任一身份已存在但 fixture 密码、标签或精确权限不符，或只有一个身份存在，脚本都会拒绝覆盖。SeaweedFS 同样分离主机侧 bootstrap、API 与 Worker 三个身份；业务容器只持有各自的 `Read:eid-local-artifacts`，用于 Story 1.1 的 `HeadBucket` 就绪探测，不具备 Admin、Write、List、ReadAcp 或 Tagging。guard 会核验精确静态授权，并以目标 bucket 的 `HeadBucket` 正例，以及对象清单、bucket ACL 和跨 bucket `HeadBucket` 的只读拒绝负例核验实际授权。已启动环境可执行实际正反探针；它会完成 `dependency_readiness` 请求/回复，再以 passive declare 验证修复版 RabbitMQ 拒绝 API 读取业务队列元数据，不会创建、删除或消费队列：

Keycloak readiness 使用独立的 `eid-readiness-monitor` confidential client。bootstrap 只在全部既有资源守卫通过后创建该命名 client 或补齐缺失的只读根角色 `view-clients`、`view-realm`。Keycloak 26.3.3 会把 composite `view-clients` 展开为令牌中的有效角色 `query-clients`，因此守卫精确接受这三个只读有效角色；既有配置、fixture secret 或任何额外角色均拒绝覆盖。API 在统一 4.5 秒 Keycloak 探测预算内读取实际 realm、`eid-web` client 与 audience mapper；任一持久化配置漂移都会使公开 readiness 返回 503。

```powershell
uv run --frozen python -m scripts.verify_rabbitmq_api_access
```

由旧版 Story 1.1 fixture 创建、且 `eid_worker` 仍是 RabbitMQ 管理员的专属环境，必须先运行一次性迁移。第一条命令只读核验 ownership nonce、容器/端口、vhost、用户清单、legacy Worker 管理标签、API/Worker fixture 凭据和精确授权；第二条命令显式创建 bootstrap 管理员，再收紧 Worker 权限并移除其管理标签。任一事实不匹配即停止，脚本不删除用户、vhost、队列或数据：

```powershell
uv run --frozen python -m scripts.migrate_rabbitmq_bootstrap_admin
uv run --frozen python -m scripts.migrate_rabbitmq_bootstrap_admin --apply
```

只读复核已运行环境：

```powershell
$env:EID_MIGRATION_DATABASE_URL = 'postgresql+psycopg://eid_migrator:local-migrate-only@localhost:55432/eid_local_dev'
./scripts/verify-local-environment.ps1 --check-only
```

## 本地测试凭据

这些凭据只用于本仓库的隔离 fixture，不得用于共享、企业或生产环境。

| 用途 | 用户/访问键 | 密码/秘密 | 目标 |
|---|---|---|---|
| 浏览器登录 | `local-member` | `eid-local-member` | `eid-local` realm / `eid-web` public client |
| Keycloak 本地管理核验 | `eid-local-admin` | `local-keycloak-admin-only` | `http://localhost:58080` |
| Keycloak readiness monitor | `eid-readiness-monitor` | `local-keycloak-readiness-monitor-only` | 仅 API client credentials；直接分配 `realm-management` 的 `view-clients`、`view-realm`，令牌另含其 composite 有效角色 `query-clients` |
| PostgreSQL 本地管理核验 | `postgres` | `local-postgres-admin-only` | `localhost:55432/eid_local_dev` |
| PostgreSQL 迁移 | `eid_migrator` | `local-migrate-only` | `localhost:55432/eid_local_dev` |
| PostgreSQL API | `eid_api` | `local-api-only` | `localhost:55432/eid_local_dev` |
| PostgreSQL Worker | `eid_worker` | `local-worker-only` | `localhost:55432/eid_local_dev` |
| RabbitMQ bootstrap 管理核验 | `eid_broker_admin` | `local-rabbitmq-bootstrap-admin-only` | 仅主机侧 `localhost:55673/eid-local`；不注入业务容器 |
| RabbitMQ API | `eid_api` | `local-api-broker-only` | `localhost:55672/eid-local`；仅 Celery control 请求/临时回复实体 |
| RabbitMQ Worker | `eid_worker` | `local-worker-only` | `localhost:55672/eid-local`；仅声明的任务队列、事件与 control 实体，无管理标签 |
| S3 bootstrap 管理 | `eid-s3-bootstrap` | `local-s3-bootstrap-admin-only` | 仅主机侧 `http://localhost:58333`；不注入业务容器 |
| S3 API | `eid-s3-api` | `local-s3-api-read-only` | `eid-local-artifacts`；仅 bucket 范围 Read |
| S3 Worker | `eid-s3-worker` | `local-s3-worker-read-only` | `eid-local-artifacts`；仅 bucket 范围 Read |

## 测试

依赖与许可证清单由本地冻结环境生成，记录锁文件摘要、相对仓库的安装路径（仓库外安装标为 `external-installation`，不记录主机绝对路径）、生产/开发分类和未知许可证字段；容器镜像只记录摘要边界，镜像内 OS 组件保持明确未知。该清单是审计输入，不构成法律结论：

```powershell
uv run --frozen python scripts/generate_dependency_licenses.py
uv run --frozen python scripts/generate_dependency_licenses.py --check
```

```powershell
uv run --frozen pytest tests -q
uv run --frozen ruff check edw-api edw-worker scripts tests migrations
pnpm --filter edw-web lint
pnpm --filter edw-web typecheck
pnpm --filter edw-web test
uv run --frozen python -m scripts.seed_access_fixtures > .local/access-fixtures.json
if ($LASTEXITCODE -ne 0) { throw '权限验收夹具初始化失败' }
pnpm exec playwright test tests/ux
```

真实依赖测试默认跳过。其中依赖故障恢复用例会短暂停止专用 PostgreSQL/Worker 容器，账户查询和空 schema 迁移回归只在单个回滚事务中写入；只能在无人使用本地环境时显式运行完整 live 套件：

```powershell
$env:EID_RUN_LIVE_TESTS = '1'
uv run --frozen pytest tests/ops/test_live_dependencies.py tests/ops/test_live_current_account.py tests/ops/test_live_migration.py tests/ops/test_live_access.py -q
```

当前证据边界只覆盖本地隔离环境。企业身份联邦、企业系统联调、真实模型效果，以及生产安全、容量、高可用不在 Story 1.1 的本地通过范围内；完整 Story 结论还需浏览器 UX 验证和独立代码审查。

## 当前项目权限（Story 1.2）

`0003_current_access` 增加最小项目/成员/资源策略、policy epoch、审计、失效记录及受限 delegation。`0004_access_correlation` 补充审计与 delegation 的 request/trace 关联；历史缺失关联保留为空，不伪造追踪值。Worker 仍不能直接读取身份或策略表，只能执行 `eid_worker_access(uuid)` 读取已经由 API 创建、绑定原发起人、操作、资源、用途、服务与五分钟期限的授权记录，并在每次阶段/输出检查时重新决策。数据库直接拒绝 Worker 对 ACL/head/approval/publication 的更改。

所有角色都必须满足 RBAC 操作 **且** ABAC 项目/客户/产品/部门/所有者/审批状态/有效期 **且** 密级上限。系统管理员也不绕过范围或密级。有效期使用数据库时间；无 allow 缓存，历史 epoch 不能授权。权限变更锁定项目并核验 expected epoch，策略、epoch、审计及失效记录同事务提交，审计失败整笔回滚。Web 在下一次拒绝响应后清除受控状态，项目切换先清除旧内容；未发生请求时通过15秒账户刷新发现变化。这不承诺召回已见字节或生产撤权 SLA。

`0005_delegation_epoch` 通过向前迁移增加 Worker 委托版本检查。权限变化后旧委托即失效，即使成员随后恢复访问也不能复活旧委托，必须重新签发；共享授权策略同时检查这一条件。

`0006_api_write_only` 移除 API 对审计、失效及委托表的不必要读取权限，保留实际所需的写入权限。成员审计记录变更前后的完整行、活动状态及实际新版本；运行就绪探针复用当前账户发现查询检查所需结构。

| 接口 | 用途 |
|---|---|
| `GET /api/v1/access/workspaces` | 当前可访问项目 |
| `GET /api/v1/access/workspaces/{id}` | 重新解析项目权限/epoch |
| `GET/PUT /api/v1/access/workspaces/{id}/members[/{actor_id}]` | 获准管理员读取/修改已有成员策略 |
| `GET /api/v1/access/workspaces/{id}/resources/{resource_id}` | 当前授权后的最小资源元数据 |
| `POST /api/v1/access/workspaces/{id}/delegations` | 建立受限后台授权引用，不表示提交了任务 |

项目列表返回 `data.workspaces` 与 `data.next_cursor`，通过 `after` 继续读取，每页最多50项且受响应字节预算约束；选择器提供前后页，支持超过200个项目。每页重新检查当前权限，拒绝的项目不返回；当前项目独立重新授权，不因位于其他页而误判撤权。范围编辑器逐项保留字符串，逗号和换行不再作为权限范围分隔符。

项目选择器及项目卡支持切换；`/workspaces/{id}/home`、`/workspaces/{id}/resources/{id}` 和 `/admin/members` 深链在登录后重新授权。新增 X-18 账户/项目和 X-20 成员表单遵循既有视觉体系；原型源文件不改。当前资源只是权限验证所需的元数据，不代表文档编辑、审批或发布已实现。Task engine、提交、恢复和 SSE 分属后续 Stories。

资源操作必须绑定具体资源；项目返回的操作列表仅供界面导航，不替代资源授权。资源拒绝保留已获准项目的返回入口，并重新核验成员关系；重新授权拒绝当前项目时立即清除旧内容。并发保存遇到409会关闭旧编辑器、读取新策略后再确认。成员列表按不可变成员ID游标分页（`after`/`next_cursor`），每页最多50项并按响应大小收缩；单项较大策略仍受256 KiB客户端响应上限约束。保存中禁用项目选择器，页面历史导航不会取消已经提交的权限变更；审计记录仍对应原项目。

权限验收夹具脚本创建两个明确标识的本地项目和七个 Keycloak 用户：`eid-access-author`、`eid-access-expert`、`eid-access-quality`、`eid-access-template-admin`、`eid-access-knowledge-admin`、`eid-access-approver`、`eid-access-system-admin`。它们仅使用本地测试密码 `eid-local-access`，角色分别对应作者、专家、质量、模板管理员、知识管理员、审批人、系统管理员；不映射企业人员或数据。

脚本先执行完整本地隔离核验；身份归属属性只允许 Keycloak 管理员读写，成功创建回执留在 `.local/access-fixture-receipts.json`。不匹配的已有用户或数据库映射会停止；脚本不覆盖既有成员政策、不删除用户、数据或数据库。恢复仅作用于有本工具创建回执的缺失归属/资料，更新保留完整用户表示。七角色与双项目的本机 ID 输出到 `.local/access-fixtures.json`，只供真实浏览器验收使用。测试会通过授权 API 暂时撤销并恢复作者的项目成员关系，并保留真实审计。

fixture创建由本地进程锁串行执行，回执采用原子替换；已有fixture密码通过新的本地PKCE登录验证，发现漂移即停止。九服务日志扫描保留从容器日志起点到共同 `log_cutoff_utc` 的完整范围，扫描前后再次核验所有权、容器、镜像和源绑定。
