# seadee-develop 远程开发环境

环境配置保存在 `deployment/environments/seadee-develop.yaml`。服务运行在 SSH 别名
`seadee-develop` 指向的 `seadee@172.27.0.38`，经 `jump-local` 连接；工作站仅使用 SSH
端口转发。专用目录已切换为 `/opt/eid`，五个基础服务纠正门禁已通过，旧 `/opt/docker/eid` 保留。Compose project 为 `eid-remote-dev`，不得使用
宿主机已有的 5432 数据库或其他 `/opt/docker` 项目。

## 交付范围与当前边界

`scripts/remote_environment.py` 提供配置校验、只读远程检查、九服务 Compose 渲染、源码打包、
SSH 隧道命令及现有初始化/迁移入口的远端守卫适配。它不自动执行部署或数据库写入。
首次授权的实际部署由主代理完成，必须在远程写入之前再次核验目标和资源归属。

已有 `scripts/verify_local_environment.py`、`scripts/initialize_local_storage.py`、
`scripts/seed_access_fixtures.py` 和 `migrations/env.py` 通过显式设置
`EID_ENVIRONMENT_CONFIG=deployment/environments/seadee-develop.yaml` 接入远端；也支持固定选择器
`seadee-develop`。不存在、空白或不受支持的选择器直接失败，不回退本机。未设置时旧本机守卫
保留原行为，仅供旧入口测试；当前项目开发必须设置远端选择器，不运行旧本机 bootstrap。
远端分支通过 SSH 查询固定的远端 Docker socket，本机 Docker 调用被拒绝；不会改写本机
`PROJECT` 或 `.local/ownership.json`，也不使用离线迁移绕过守卫。

检查到的远程工具为 Docker 25.0.3、Compose 2.32.4 和 Python 3；当时没有 buildx 或 uv。
这是前置环境记录，实际能力以每次 `check --require-build` 为准。缺少 buildx 时不能宣称远程
源码构建已通过；可另行安装项目需要的构建能力，或者先验收固定源码构建的镜像再传输。

## 隔离设计

- 所有发布端口绑定远程 `127.0.0.1`，API、Worker、Web 没有直接发布端口。
- `eid-remote-dev-postgres`、`eid-remote-dev-keycloak`、`eid-remote-dev-seaweedfs`、
  `eid-remote-dev-rabbitmq`、`eid-remote-dev-redis` 是独立 volume；显式覆盖镜像声明的数据
  路径以避免匿名 volume。网络为 `eid-remote-dev_default`。容器、volume、网络都有同一随机 owner nonce。
- `/opt/eid` 必须由 root 所有、权限 0700，其归属收据 `.eid-remote-owner.json` 必须
  为 root 所有的普通文件、权限 0600。已有目录没有相同收据时拒绝接管。
- 新根目录的祖先固定于 YAML：`/` 为 UID/GID `0:0`、0555；`/opt` 为 `0:0`、0755。
  两者必须为真实目录、无符号链接且非组/其他用户可写，归属或模式漂移即拒绝。
  共享 `/opt/docker` 的权限不变，新发布输入不再从其下消费；旧 EID 目录及卷仍受外来挂载检查保护。
  已有外部容器占用端口、接入专属网络或挂载专属 volume 时检查失败，检查不会清理资源。
- 数据库仍为 `eid_local_dev`，标记仍为 `eid-local-dev-v1`，以兼容现有 schema 和权限契约。
  这些名称本身不证明隔离，必须同时核验 SSH 目标、专属容器、volume、owner 和真实连接身份。
- 使用现有开发 fixture 凭据以保持当前契约；凭据是仓库内公开的测试值。它们仅适用于这个
  受 SSH 控制的开发环境，不是企业凭据。远程主机上有本机访问权限的其他用户可以访问
  loopback 服务，因此这不是对不可信宿主机用户的安全边界。随机化凭据须同时更新初始化、
  readiness、迁移及验收契约，不应仅替换 Compose 中的密码。

## 本机准备与检查

在仓库根目录使用现有 Python 环境。下列命令不会启动本机服务：

```powershell
.venv/Scripts/python.exe scripts/remote_environment.py check
.venv/Scripts/python.exe scripts/remote_environment.py check --require-build
.venv/Scripts/python.exe scripts/remote_environment.py tunnel-command
```

`check` 验证 SSH 实际 hostname、user、ProxyJump，强制已知主机密钥检查、禁止 agent
转发，并核对 SSH 连接服务端地址。远程只运行 `sudo -n python3`、Docker 查询及 `ss`。
有条件满足的空目录目标会报告 `isolation_verified: true`；这不是创建或部署成功。
`runtime_verified` 始终为 false，因为本工具不验证数据库 schema、依赖权限或业务可用性。

全新安装首次打包前生成一次 owner，保存到 `.local/remote/seadee-develop/ownership.json`，后续发布
保持该值。记录必须是 `owner_receipt(config, owner)` 的精确 JSON，不能从已有远端资源猜测
或补建；首次安装流程同时保存本机记录和远端 root 收据。当前环境已有旧 root 收据，必须沿已授权的一次性过渡保留 nonce、旧收据和变更来源；不能重新生成 owner 或提前改写收据来通过守卫。

```powershell
$eidRemoteOwner = .venv/Scripts/python.exe -c "import secrets; print(secrets.token_hex(16))"
.venv/Scripts/python.exe scripts/remote_environment.py render --owner $eidRemoteOwner --output .local/remote/render-001
.venv/Scripts/python.exe scripts/remote_environment.py package --owner $eidRemoteOwner --output .local/remote/eid-001.tar.gz
```

输出位置必须尚不存在；重复执行使用新文件名。`render` 只写生成配置，不复制源码；
`package` 包含构建、迁移及运维需要的允许列表文件、生成的 `deployment/remote.compose.yaml`、
环境 YAML、归属收据和源码文件哈希。包不包含 `.env*`、`.local`、`.git`、私钥文件、
secrets 目录、BMAD 材料、node_modules 或本机运行时清单。符号链接、junction 和硬链接
不会被打包。包内含已公开的开发 fixture 值，仍应仅传给授权的开发主机。

应用镜像使用 `eid-remote-dev-<service>:<源指纹前 16 位>` 标签；完整 source-fingerprint
算法与现有本机镜像契约一致。传输已有镜像时必须比对完整指纹，并在远程使用对应标签；
源码包总哈希单独记录，不能替代镜像指纹或镜像 ID。

## 实际部署衔接

1. 主代理检查包清单、哈希、生成 Compose 和资源归属，并处理构建能力缺口。
2. 首次安装时，在通过空目标检查后，独占创建 `/opt/eid`（0700）并写入同一 owner
   收据（0600）。禁止向未经证明归属的已有目录解包。
3. 将包解压到专属目录中新建的 release 子目录，保留以前的 release；拒绝绝对路径、`..`、
   链接、设备文件和未经审核的包成员。相对 Compose 路径要求包目录布局保持完整。
4. 在 release 根目录，显式使用远程本机 Docker socket 和 project 验证渲染结果：

   ```sh
   sudo -n docker --host unix:///var/run/docker.sock compose -p eid-remote-dev -f deployment/remote.compose.yaml config --quiet
   ```

5. 先启动 `postgres keycloak rabbitmq redis seaweedfs`；完成经审查的远程初始化和迁移接入、
   真实数据库隔离验证后，才能执行初始化、迁移并启动 `api worker web nginx`。
6. 完整服务启动后使用 `inspect --owner <同一 nonce>` 检查资源；另行执行真实 readiness、
   身份权限、OIDC、Worker 委派及浏览器验收，将证据写入专属远程证据目录。

辅助脚本没有自动 stage/deploy 命令：安装路径写入、已有数据迁移和服务更新必须由已审查的
部署入口负责。前置只读检查存在检查与操作之间的时间间隔，不能单独充当写入事务的锁。
实际入口应在远程持有项目锁后重核验归属，并在失败时保留现场，不自动清理。

2026-09-17 的旧路径过渡依照已获授权的 `docs/remote-deployment-path-authorization.md` 完成五服务纠正，保留原网络、卷及旧目录。原失败、恢复和最终完成证据分别位于 `.local/remote/acceptance-20260916/`、`resume-20260917/`、`complete-20260917/`；最终 `execute-003.json` 退出0。本机 owner 收据已沿创建来源与实时普通守卫切换至新 root，旧字节备份保留。禁止重放一次性入口，旧 `correction_runner.py` 草稿仍禁止执行。完成限于基础服务隔离与限定持久性验证。

## 初始化、迁移和运行验收

2026-09-15 首次远端启动时，RabbitMQ 的三个实际 CLI 检查耗时 8.153 秒，超过原本机
5 秒健康检查预算。远端 YAML 将单次预算明确设置为 20 秒；原检查命令、认证管理接口、
重试和通过条件全部保留，不把正在启动或超时当成健康。

安装收据、五个基础服务及 SSH 隧道已就绪后，在仓库根目录运行：

```powershell
$env:EID_ENVIRONMENT_CONFIG = 'deployment/environments/seadee-develop.yaml'
$env:EID_MIGRATION_DATABASE_URL = 'postgresql+psycopg://eid_migrator:local-migrate-only@localhost:15432/eid_local_dev'
uv run python -m scripts.initialize_local_storage
uv run alembic upgrade head
```

随后由部署入口启动 API、Worker、Web 和 NGINX，再运行：

```powershell
uv run python -m scripts.seed_access_fixtures
$env:EID_RUN_LIVE_TESTS = '1'
uv run pytest tests/ops/test_live_access.py -q
```

适配器在任何实际数据库连接前检查 SSH 主机、远端 root 收据、容器/卷/网络 owner、精确
端口、持久卷挂载目的地、基础镜像锁定引用及镜像 ID。已启动的应用还要匹配当前源码指纹。
挂载配置必须为 EID 目录内的 root 保护普通文件、只读挂载，且内容哈希与当前仓库相同。
初始化阶段允许仅五个基础服务；迁移归属检查允许旧版或已停止的 API/Worker/Web/NGINX，仍验证这些资源的 owner、网络及挂载。最终运行证据要求九个服务、当前候选镜像和健康检查通过。
数据库名称、迁移身份和 marker 仍由真实连接查询；Alembic 保留连接内的第二次身份核验。
S3、RabbitMQ、Keycloak 的既有身份及最小权限检查保持执行。

隧道检查读取 Windows 实际监听 socket 及其进程，要求七个配置端口仅由同一个 OpenSSH
进程绑定 `127.0.0.1`，进程可执行文件及完整 argv 必须匹配 `tunnel-command`。
argv 显式固定 Hostname/User/ProxyJump，防止仅凭之后修改的 SSH alias 配置认定旧隧道目标。
检查拒绝 SSH 有效配置中额外 LocalForward/RemoteForward/DynamicForward，拒绝歧义重复关键字段，并枚举目标 PID 的全部 TCP 监听。额外端口、IPv6/通配监听、外国进程、缺失隧道或转发目标变化都会阻止操作；隧道 argv 同时固定 Port=22。
当前进程级验证仅支持本 Windows 工作站；其他平台明确失败，不跳过该检查。

远端 fixture 锁、创建收据和运行镜像清单均位于 `.local/remote/seadee-develop/`。
记录运行镜像前应保留构建前的 `EID_API_SOURCE_FINGERPRINT`、
`EID_WORKER_SOURCE_FINGERPRINT`、`EID_WEB_SOURCE_FINGERPRINT`，再执行现有
`verify_local_environment.py --record-runtime-images` 入口。该入口先后检查 readiness，
两次读取远端容器以检测替换，并记录 schema 3 清单，包含远端主机、路径、Compose project、
owner、Docker Server、镜像 ID、容器 ID 和源码指纹。旧本机 schema 2 清单不能作为远端证据。
清单同时绑定渲染 Compose 摘要及每服务命令、入口、环境配置摘要；最后一次 readiness 后再次核验完整候选和隧道，失败保留旧清单。原子写入使用独立临时文件。
缺少 buildx 时使用已构建且指纹匹配的导入镜像，结果不声称进行了远端源码构建。

## 访问及回退

Web/OIDC 始终使用 `http://localhost:18080`。保持此 origin 可沿用现有 Authorization Code
+ PKCE S256 和浏览器 localhost Secure cookie 行为。不要把浏览器地址替换为远程 IP。

| 服务 | 本机隧道端口 | 远程 loopback 端口 |
| --- | ---: | ---: |
| NGINX / Web / OIDC | 18080 | 18080 |
| PostgreSQL | 15432 | 55432 |
| Keycloak 管理检查 | 58080 | 58080 |
| RabbitMQ AMQP / 管理 | 55672 / 55673 | 55672 / 55673 |
| Redis | 16379 | 56379 |
| S3 | 58333 | 58333 |

`tunnel-command` 返回 argv，显式绑定本机 `127.0.0.1` 并要求转发建立失败即退出。
执行该命令前仍应检查 SSH 目标和本机端口占用。隧道断开只影响本机访问；不会停止远程服务。
不要为复用旧脚本在本机启动数据库或替换旧的 runtime manifest。

回退保留专属 volume 和数据库；只在验收过的 schema 兼容条件下选择上一 release 与镜像。
本工具不提供 `down -v`、删除目录、数据库降级、重置或清理命令。更新失败和部分初始化状态
应保留以便诊断，不能作为自动接管或重建数据的依据。

## 2026-09-16 修复候选与未完成验收

RabbitMQ 配置根据只读取证固定 hostname `5e8cac11b089`、节点 `rabbit@5e8cac11b089` 和数据目录 `/var/lib/rabbitmq/mnesia/rabbit@5e8cac11b089`，2026-09-17已实际部署并验证节点身份、原卷和专有持久消息保留。旧 `rabbit@06043a6c248a` 目录仍保留；固定当前身份不证明旧节点历史数据已恢复。

`scripts/remote_service_operations.py` 为日志和依赖故障验收提供受限远端入口。现场每次操作绑定 owner、原完整容器 ID、镜像、网络和挂载，恢复允许预期的运行状态变化，但拒绝容器替换或归属漂移；失败可能保留停机现场。远端模式不调用本机 Docker。

归属采集检查外来容器 bind Source 与 EID 根目录、专属卷真实 Mountpoint 的父子路径重叠。恢复原目标不以其他服务运行作为前提，最终健康验收仍独立要求完整候选；stop 结果未知或中断时也尝试对同一原容器安全恢复。

本地控制逻辑测试不能代替以下现场验收：SSH 转发可用性、同一卷重建后的用户/队列/持久消息保留、迁移及 fixture、九服务候选运行、日志和浏览器验收。2026-09-16 用户已明确授权并执行最小 SSH 转发方案，见 `docs/remote-forwarding-authorization.md`；正式隧道进程/监听守卫已通过。后续环境检查发现五个旧容器使用 host cgroup namespace，未通过 private 隔离要求；须保留该守卫并完成配置纠正、资源归属核验及现场验证后再继续迁移。

## 2026-09-17 当前现场证据

已按获批方案完成 `/opt/eid/release-20260917-002` 路径过渡及五服务隔离纠正，保留原卷/网络。初始化、0006迁移和七角色fixture已完成；API、Worker、Web、NGINX启动后九服务就绪。当前schema3清单是 `.local/remote/seadee-develop/runtime-images.json`，绑定当前九个完整容器ID及候选；旧 `.local/runtime-images.json` 仍为作废证据，不得复用。

本轮真实PostgreSQL权限11项、迁移2项和依赖9项（含三种故障恢复）全部通过。九服务日志截至UTC `2026-09-17T09:53:41.861786+00:00` 未检出登记的令牌/认证参数/开发凭据模式；浏览器作者登录、项目切换、资源允许与拒绝冒烟通过。完整权限浏览器回归及Worker委派正反验收仍在推进，不能宣称Story完成。

七角色fixture成功输出已保存为环境专属 `access-fixtures.json`，并校验各身份创建收据与当前nonce；不通过重跑seed取得输出。只读 `scripts.verify_access_fixtures` 预检已实际通过。UX套件恢复工具的竞态修复正在审查，审查通过前不执行其成员策略变更用例。详细失败、修复、审查和实际退出码见 `_bmad-output/implementation-artifacts/remote-environment-2026-09-17.md` 及 `.local/remote/app-start-20260917/`。

## 2026-09-18 当前验收状态

上述历史阻塞已修复并独立审查。Windows保留端口覆盖55432后，本机PostgreSQL转发调整为15432，远端55432及sshd的七端口授权不变；新隧道通过进程、参数及全部监听校验。真实当前账户测试1项通过，完整远端UX套件52项通过（无跳过或失败），覆盖Worker委派、撤权恢复和最终九服务日志门禁；结束后无待恢复fixture标记。

证据在 `.local/remote/acceptance-20260918/ux-full-001.json`、`ux-full-summary.json` 和 `_bmad-output/implementation-artifacts/remote-environment-2026-09-18.md`。这些结果解除开发前置阻塞，后续Story仍须对自己的候选重新完成实现、审查和验收。
