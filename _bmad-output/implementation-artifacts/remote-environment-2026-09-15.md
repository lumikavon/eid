# 远端开发环境接入记录 — 2026-09-15

状态：**部分部署；外部授权阻塞；独立审查 changes-required。不是运行验收通过。**

2026-09-16 更新：本文件保留9月15日历史现场；后续本地代码修复及四轮复审结果见 `remote-environment-2026-09-16.md`。SSH授权和远端运行验收仍阻塞，不应将历史“均未修复”作为当前代码状态。

## 用户范围与已完成操作

用户要求停用本机服务，改用 `seadee-develop:/opt/docker`，允许新建本项目服务，将配置保存为本机 YAML，并写入 AGENTS 后继续 Epic 1。

- 配置：`deployment/environments/seadee-develop.yaml`；指引：`docs/remote-development.md`。
- SSH 实际目标 `seadee@172.27.0.38:22`，通过 `jump-local`；服务端看到来源 `172.16.10.3`。
- 独占创建 `/opt/docker/eid`，root:0700；收据 `.eid-remote-owner.json` 为 root:0600。没有修改共享 `/opt/docker` 的既有 uid/gid/权限。
- Compose `eid-remote-dev`，专有网络和 PostgreSQL、Keycloak、RabbitMQ、Redis、SeaweedFS 五个命名卷；不接管其他项目。
- 当前配置 release `/opt/docker/eid/release-20260915-002`。初版 001 保留，数据卷未删除。
- 六个基础镜像按仓库锁定摘要拉取。现有 API/Worker/Web 镜像经过源码指纹比对、归档传输和远端导入；尚未启动这三个应用及 NGINX。
- 五个基础服务已通过 Compose `up --wait`（退出 0）；SeaweedFS 无自身 healthcheck，此结果仅为启动条件满足，S3 协议与权限仍待初始化验证。
- 原 RabbitMQ 单次检查 5 秒超时，三个 CLI 诊断实测 8.153 秒；YAML 改为 20 秒，全部原探针、认证检查、重试及成功条件保留，第二次启动通过。
- 本次此前启动的四个本机 EID 基础服务已停止；最终 `docker ps` 的 `eid-local` 项目无运行容器。数据卷保留。没有删除数据库或已有数据。

## 授权阻塞及实际证据

实际 PostgreSQL 客户端经 SSH 转发报服务端关闭连接，隧道 stderr 为：

```text
channel 7: open failed: administratively prohibited: open failed
```

服务器自身 `pg_isready` 与 `127.0.0.1:55432` TCP 检查均成功。只读核验：

```sh
sudo -n sshd -T -C user=seadee,addr=172.16.10.3,laddr=172.27.0.38,lport=22
```

输出 `allowtcpforwarding no`、`disableforwarding no`、`permitopen any`。这是生效的主机安全策略，不是客户端端口占用；七个本机监听/PID/argv 校验成功不能证明服务端允许转发。

未修改 sshd，未绕过禁止转发策略，未将服务改为对外暴露。已停止本次创建但不可用的 SSH 隧道进程，错误日志留在 `.local/remote/seadee-develop/tunnel-stderr.log`。

唯一待用户决定：是否授权仅对 `seadee` 账号、来自现有跳板的连接，开放到 YAML 指定七个远端 loopback 端口的 SSH **本地**转发。若授权，仍须限制目的端口、保留其他账号策略、检查配置语法并保留现有管理会话；先修复下列转发校验缺陷，再重建隧道。不得视为批准任意转发或全局放开 sshd。

未执行 Alembic 迁移、`initialize_local_storage` 或 `seed_access_fixtures`；首次空数据库/realm 初始化仅为所创建服务的官方启动流程。未执行真实业务、浏览器、日志或依赖故障验收。

## 独立审查与逐项裁决

使用 bmad-code-review 的四个新上下文强模型层；全部返回终态。7 条原始发现归并为 6 个修复项，没有拒绝、降级放行或已通过声明。以下均未修复，不属于可跳过的环境缺口。

| ID / 来源 | 裁决与证据 | 必要修复 |
| --- | --- | --- |
| R1 blind | high：`remote_environment.py` 新建 RabbitMQ 持久卷但渲染没有稳定 hostname/nodename；重建默认节点身份变化会选择另一份节点数据。当前已经发生两次新容器启动，不能直接重新初始化声称保留数据。 | 取证现有实际节点和数据，固定其身份；加入重建后用户/队列/消息保留验证，不删除旧数据。 |
| R2 blind | medium：`validate_guard_state` 即使初始化/迁移模式也检查所有现有应用必须运行且等于当前源码；源码更新后的旧应用或停止应用都会拒绝，阻断先迁移再部署。主代理复核调用链 `verify_migration_target → ownership → guarded_inventory`。 | 分离迁移目标归属门禁与最终候选镜像门禁；保留旧/停机应用的归属校验但不要求新候选已经部署。 |
| R3 edge | high：`verify_ssh_config` 未拒绝配置附带 LocalForward/RemoteForward；`tunnel_inventory` 只查 YAML 七端口。审查只读探针证明额外 wildcard 转发可逃过检查；当前服务器禁止转发，未声称实际已暴露。 | 排除/拒绝额外有效转发配置，并核验目标 SSH PID 的全部监听及转发，不只七个预期端口。 |
| R4 verification-gap | medium：`runtime_images` 双快照一致性断言无执行级回归保护。审查在独立测试进程移除此断言后仍有 243 项通过；未修改仓库源码。 | 添加稳定成功、容器/隧道/源码变化拒绝，以及失败保留旧 manifest 的实际函数路径测试。 |
| R5 verification other | medium：`verify_runtime_logs.py:44` 和 `:113` 仍直接调用本机 Docker，而前置 ownership/runtime_images 已支持远端；不能检查当前远端服务日志。主代理已核对函数及调用路径。 | 远端日志按当前归属容器取证，保留秘密扫描及 candidate 绑定；新增组合测试。 |
| R6 acceptance | high：`test_live_dependencies.py:89,97,136,144` 在远端 verify_database 后仍 stop/start `eid-local-*`；finally 会重启本机旧容器并测试错误环境。主代理已逐段核对。 | 用已验证远端 EID 容器实现故障/恢复并拒绝任何本机副作用；禁止运行当前未适配的完整 live suite。 |
| R7 acceptance | medium：与 R5 同根因，`tests/ux/shell.spec.ts:449` 的必需日志验收无法完成。 | 与 R5 归并修复，但保留本条来源。 |

恢复后无需用户再次决定这些明确修复项；它们仍在原授权范围内，应修复、测试、独立复审。主机 SSH 权限变更是另一个必须取得明确授权的事项。

## 检查与 Git / Story 状态

- 环境辅助/远端守卫/既有归属/fixture 安全/迁移连接聚焦测试：246 passed；增加远端 RabbitMQ 检查预算用例后，两份远端测试 90 passed，Ruff passed。
- 前端显式 Node 24.20.0 执行 Vitest：91 passed。此前使用系统 Node 的结果不代替锁定版本结果。
- 初始后端基线 487 passed、23 skipped；skipped 是未启用的真实环境测试，不是通过。
- 收尾重跑 `uv run --frozen pytest tests -q`：577 passed、23 skipped、2 个既有弃用警告，49.51 秒，退出 0；`git diff --check` 退出 0。单元/契约通过不消除上述审查项，也不替代远端真实验收。
- 原型未修改。预存 spec 1.1 SHA256 `BB5F001479D7C19426A4DC390145AE95D836AF1DFDC11486E40512D7B3BE5915`，spec 1.2 `9C6C0DC8403665E55A26753A25BB8007BA02A6E9D341D223636B5A3ABF0B68EC`，与开始基线相同。
- HEAD 保持 `2680247ab3a45bef9246d23328ce18ffe597bdb8`。1.1/1.2 已完成并跳过；本次没有 Story commit、Push 或 Epic 完成声明。
- Story 1.3 已准备规格并同步 `ready-for-dev`，业务未实现；1.4–1.6 仍 backlog。环境接入不是 Story done。
- 未提交范围：远端 YAML、helper、staging 脚本、原 guard/initializer/fixture 接入、两份远端测试、AGENTS、运行指引/本记录、Epic context、Story 1.3 规格及 sprint 同步。预存 1.1/1.2 修改及其他 untracked BMAD 文件不得混入提交。
- `tests/ops/test_remote_environment.py`、`tests/ops/test_remote_guard.py`、`scripts/stage_remote_release.sh` 被用户级 ignore 命中；后续通过门禁后需逐个明确归属，不得遗漏或 broad-stage。

本机 `.local/remote/seadee-develop/ownership.json` 保存独立远端 nonce；没有伪造本机 `.local/ownership.json` 或复用旧 runtime manifest。源码包 002 SHA256：`8e3e65abb3db3ae10f8dd42fa94353d84e3a87de0c65bd9fc620431941d068d3`。导入应用归档 SHA256：`2e73afb81e3207c6039733dcc83c0b95d67c57038d73d8cda5dc9b8ce945e1a8`。
