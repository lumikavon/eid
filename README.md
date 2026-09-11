# EID 本地三工程工作区

本仓库提供 Story 1.1 的本地隔离开发环境：`edw-web`、`edw-api`、`edw-worker`，以及真实的 PostgreSQL、Keycloak、RabbitMQ、Redis、SeaweedFS S3 和 NGINX。统一入口为 <http://localhost:18080>。

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
pnpm exec playwright test tests/ux
```

真实依赖测试默认跳过。其中依赖故障恢复用例会短暂停止专用 PostgreSQL/Worker 容器，账户查询和空 schema 迁移回归只在单个回滚事务中写入；只能在无人使用本地环境时显式运行完整 live 套件：

```powershell
$env:EID_RUN_LIVE_TESTS = '1'
uv run --frozen pytest tests/ops/test_live_dependencies.py tests/ops/test_live_current_account.py tests/ops/test_live_migration.py -q
```

当前证据边界只覆盖本地隔离环境。企业身份联邦、企业系统联调、真实模型效果，以及生产安全、容量、高可用不在 Story 1.1 的本地通过范围内；完整 Story 结论还需浏览器 UX 验证和独立代码审查。
