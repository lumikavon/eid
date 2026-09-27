# 远端开发环境修复与授权交接 — 2026-09-16

状态：**本地代码修复与独立审查通过；远端运行验收未完成；等待限定 SSH 本地转发授权。Epic 1 未完成。**

## 当前 Story 与 Git

| Story | 本次开始 / 结束状态 | 已有提交 |
|---|---|---|
| 1.1 runnable-workspace | done / done，跳过 | `8fd8398b1500f78fea5f8f5dc804db14f7b647b5` |
| 1.2 current-access | done / done，跳过 | `2680247ab3a45bef9246d23328ce18ffe597bdb8` |
| 1.3 workspace-discovery | ready-for-dev / ready-for-dev | 无 |
| 1.4 durable-submission | backlog / backlog | 无 |
| 1.5 fenced-recovery | backlog / backlog | 无 |
| 1.6 task-observation | backlog / backlog | 无 |

分支 `main`，HEAD 保持 `2680247ab3a45bef9246d23328ce18ffe597bdb8`。本次没有提交、暂存或 Push；Epic 集成与复盘未执行。保留预存 BMAD、规格、配置及其他用户工作；环境修复不替代 Story 生命周期。

## 修复与独立审查

继续9月15日交接的六项修复（R5/R7同根因），并处理审查中确认的有效问题：

- RabbitMQ 根据现场只读取证固定当前 hostname、nodename 和数据目录；迁移前归属检查与最终候选检查分开。
- 拒绝额外有效 SSH 转发及目标进程额外监听；固定目的主机、账号、端口和跳板。
- 校验真实目录权限、资源归属、专属卷 Mountpoint 与外来 bind 父子路径重叠；无关已停止容器的缺失挂载叶节点不阻断恢复。
- 绑定源码、Compose、镜像、容器、命令、入口、环境、执行用户、隔离配置和实际健康检查定义；清单生成与操作消费共用完整契约，Python 服务拒绝 root。
- 双快照和最后 readiness 后复核，环境选择或候选漂移时保留旧证据；使用独立临时文件原子写入。
- 远端日志扫描覆盖 stdout/stderr 并保留脱敏结果。故障恢复固定原容器身份，允许其他服务退出或数据隧道丢失；身份、归属漂移仍拒绝。
- 测试直接执行真实清单生产/验证/操作消费链、归档嵌入校验消费者，以及远端 fixture 选择器/锁/创建恢复收据路径。

| 审查轮次 | 结果 |
|---|---|
| 第1轮，四个新强模型上下文 | changes-required；最终readiness、并发/中断恢复、路径重叠、打包、配置与测试缺口已修复 |
| 第2轮，四个新强模型上下文 | changes-required；生产消费契约、隔离配置、探针定义、断隧道恢复已修复 |
| 第3轮，四个新强模型上下文 | changes-required；执行用户、缺失路径、归档与fixture消费者测试已修复 |
| 第4轮，四个新强模型上下文 | blind / edge / verification 无剩余有效发现，acceptance approved，仅限代码 |

逐项裁决在 `spec-remote-environment-repair.md`。最终审查包含19个文件；主代理抽查接口和关键保护并实际运行整套后端测试。审查结论没有被当成真实远端运行证据。

## 最终验证

```text
uv run --offline --frozen pytest tests -q
877 passed, 23 skipped, 2 warnings in 261.26s；exit 0
```

23个 skip 是未启用的真实环境测试，不是通过。两个警告为既有 httpx/Starlette 与 AnyIO 弃用警告。全部相关 Python 代码和测试 Ruff 通过，`git diff --check` exit0。未修改前端，因此没有复用旧浏览器结果充当本次验收。

最终候选文件哈希及验证摘要保存在 `.local/remote/recovery-20260915/final-review-candidate.json`。初始502项预存文件快照位于同目录 `baseline.json`、`status.txt`、`tracked.diff`。

## 现场只读证据与未完成事项

RabbitMQ 当前节点 `rabbit@5e8cac11b089`，活动目录 `/var/lib/rabbitmq/mnesia/rabbit@5e8cac11b089`；当前队列为空，仅有初始管理员。卷还保留旧 `rabbit@06043a6c248a` 目录，未删除、合并或恢复。证据 `r1-rabbitmq-readonly-current.json`。固定当前身份不证明历史数据恢复，也不证明重建后持久性。

主代理只读复核有效 sshd 配置，退出0：

```text
gatewayports no
allowtcpforwarding no
disableforwarding no
permitopen any
permitlisten any
```

以上为授权前阶段记录：当时没有修改 sshd、建立隧道、部署修复候选、重建容器、操作数据库或执行远端故障。九月十五日只启动五个基础服务的历史状态不能视为当前候选通过；完整九服务、初始化/迁移/fixture、RabbitMQ同卷重建与用户/队列/持久消息保留、日志和浏览器仍需实际验收。

2026-09-16 用户随后明确批准 `docs/remote-forwarding-authorization.md` 中的限定 SSH 本地转发。只针对 `seadee`，来源 `172.16.10.3`，目标主机 `172.27.0.38:22`，目的地仅 `127.0.0.1` 的 18080、55432、58080、55672、55673、56379、58333 七端口。该授权已解除原策略阻塞，其他账号/来源/远端转发策略保持。

## 测试误写事件

修复前的 selector 漂移回归用例触发旧实现回退，覆盖了旧本机 `.local/runtime-images.json`。该文件现已作废；有界检索未找到可信原件，没有从其他日志拼装或伪造恢复。误写字节和说明已保存在 `quarantine/runtime-images-invalid-test-write-20260916.{json,md}`，SHA256 `151F2D50FC66DB298091CFBD650AB9605080B99D17B3D41A0F12F4A8FCBFBF3E`。

首次适配旧snapshot测试还触发过本机 ssh -G 和监听只读枚举，没有远端连接。测试后来将本机及远端证据路径都封闭到临时目录，并阻断未替身的进程/网络/数据库访问。后续未再次修改误写文件；此次事件没有执行业务数据写入或服务操作。该本机清单不得作为任何验收证据；新的远端清单只能在真实验收后生成。

## 未提交文件归属与恢复顺序

远端接入候选包括：`scripts/remote_environment.py`、`remote_service_operations.py`、`verify_local_environment.py`、`verify_runtime_logs.py`、`initialize_local_storage.py`、`seed_access_fixtures.py`、`stage_remote_release.sh`、远端 YAML，以及相应运行指引、规格和交接记录。保留了开始前已有接入代码，未将其错误归为新 Story 完成。

测试包括 `test_remote_environment.py`、`test_remote_guard.py`、`test_remote_runtime_snapshot.py`、`test_remote_final_readiness.py`、`test_remote_service_operations.py`、`test_remote_manifest_integration.py`、`test_remote_staging_consumer.py`、`test_remote_seed_paths.py`、`test_runtime_logs.py`、`test_live_dependencies.py`。若干 remote 文件及 staging 脚本被用户全局 ignore 命中；后续提交必须按此清单明确归属和必要的单文件 force-add，不能 broad-stage。

获得明确策略授权后，先按方案备份、检查并限定修改 sshd，验证允许与拒绝路径；再验证 EID 独占资源并部署固定身份候选。完成现场门禁后，继续1.3及后续串行 Story；不把授权本身当作测试通过，不自动 Push。

## 授权后接续：限定转发与 cgroup 修复

最小 Match 块已写入 `/etc/ssh/sshd_config` 并通过语法检查和服务重载。执行代理与独立审查分别核验54组完整有效配置，仅授权连接条件的两个转发字段变化。六个已监听端口的 SSH 通道正常，18080 的策略允许但应用尚未监听；三个非白名单目的地及远端转发被服务器拒绝。正式项目隧道 PID43096 的完整 argv、进程及七个 IPv4 loopback 监听经守卫验证，Redis 返回 PONG，Keycloak 返回 HTTP302。

首轮审查发现 `/opt/docker` 非 root 所有导致原回滚材料有祖先目录替换风险；已从本地校验过的原始字节在 `/etc/ssh/eid-forwarding-backup-20260916` 保存可信备份和恢复脚本，全部祖先由 root 控制。新的独立审查通过，实际回滚未执行；详细证据与恢复命令在 `.local/remote/forwarding-20260916/EXECUTION.md`。临时管理 SSH 会话已在完成验证后关闭，正式隧道保留。

远端归属守卫随后拒绝旧容器的 `CgroupnsMode=host`。只读诊断确认远端 Docker25/cgroup v1 默认 host，而渲染器未显式设置 private；现有守卫要求 private 是正确的。已为全部九个远端服务显式渲染 `cgroup: private`，保留原拒绝规则；296项相关测试、Ruff及独立配置增量审查通过。候选打包在 `.local/remote/acceptance-20260916/candidate-source-001.tar.gz`，SHA256 `1874cbff7a0aa83f54cf106e6644e6a12bcaf34f3f86e91fe92d72837ca4569d`，尚未证明远端重建与运行通过。不得通过修改采集快照、弱化守卫或复用旧清单跳过该边界。

主代理补跑六组运行清单、最终就绪、恢复、部署包消费及 fixture 路径测试：111 passed，107.82秒，退出0；这是本地控制逻辑证据。只读远端镜像检查确认 API/Worker/Web 的导入镜像标签与当前源码指纹一致，记录在 `forwarding-20260916/imported-app-images.json`。旧作废清单 SHA256 未变，暂存区仍为空。工具预检有一次未设置远端 selector，触发了本机 Docker 只读版本/能力查询；没有启动本机服务或写业务数据，其输出不作为远端证据。后续验收命令必须明确设置远端 selector，并选择已安装的 Node24.20.0。

五服务纠正草稿独立审查为 changes-required：非 root 所有的共享父目录存在替换竞态，锁和前后 inode 检查不能固定 Compose/Docker 真正读取的路径；另有挂载顺序比较误报、临时目录字符规则及缺失执行入口。草稿只读预检失败，未执行部署或服务重建，禁止直接运行。独立架构复核不建议以自绑定挂载作为目录锁；建议在 root 控制的 `/opt/eid` 建立 EID 专用部署路径，保留全部旧目录和数据卷。主代理只读确认新路径不存在；该目录超出既有授权，需用户批准 `docs/remote-deployment-path-authorization.md` 后实施。SSH 授权事项已完成，这一新边界仍阻止环境验收及 Story1.3 启动。
