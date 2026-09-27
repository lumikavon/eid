---
title: '修复远端开发环境接入审查缺陷'
type: 'bugfix'
created: '2026-09-15'
status: 'done'
completion_scope: 'local-code-repair-only; remote-runtime-acceptance-blocked'
route: 'dispatch'
baseline_commit: '2680247ab3a45bef9246d23328ce18ffe597bdb8'
review_loop_iteration: 3
context:
  - '{project-root}/docs/remote-development.md'
  - '{project-root}/_bmad-output/implementation-artifacts/remote-environment-2026-09-15.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

## 当前开发与验证边界（2026-09-21）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件的执行安排统一受[开发与验证规则](../planning-artifacts/development-validation-policy.md)约束。下文涉及启动、部署、迁移、fixture、功能测试、浏览器实测、联调、性能和故障演练的条款保留为待执行验收要求，当前暂停执行并记录 `not-run`；其中静态检查与编译可按规则单独执行。历史证据按原日期保留，不代表本轮通过或继续运行的授权。


<frozen-after-approval reason="沿用用户 execute PROMPT.md 与交接记录第55行的明确修复授权">

## Intent

远端接入有六项已裁决缺陷，阻止 Epic 1 串行验收。修复归属、候选绑定、转发检查和远端验收入口，先完成可审查的本地实现与测试，再请求仍缺少的主机策略授权。

## Boundaries & Constraints

保留预存修改、既有远端数据及全部失败门禁。只读核验远端允许；本轮不修改 sshd、不启动转发、不执行远端写入、重建或故障注入，不启动本机服务。Story 1.3 和 Sprint 状态保持原样。测试替身只证明控制逻辑，真实持久性、日志及运行验收保持未通过。不提交混杂或未验收 Story，不 Push。

## I/O & Edge-Case Matrix

| 场景 | 期望 |
|---|---|
| RabbitMQ 已有节点数据 | 只读核实节点与目录，渲染固定匹配身份；拒绝猜测或自动切换到空数据 |
| 迁移前旧或停机应用 | 保留归属校验，允许先迁移；最终运行仍强制当前源码、镜像和健康状态 |
| SSH 额外 LocalForward、RemoteForward、动态转发或目标进程额外监听 | 操作前拒绝，包括非预期端口的通配监听 |
| 两次运行快照稳定 | 返回绑定同一容器、隧道、owner 与源码的清单 |
| 容器、隧道、owner 或源码变化 | 失败且不覆盖旧清单 |
| 远端日志或依赖停启 | 仅以经过归属校验的远端容器 ID 操作；禁止本机 Docker 副作用；保留候选绑定与秘密扫描 |

</frozen-after-approval>

## Code Map

- `scripts/remote_environment.py`: render_compose、verify_ssh_config、tunnel_inventory、validate_tunnels、validate_guard_state、guarded_inventory、runtime_images。
- `scripts/verify_local_environment.py`: ownership、service_container、record_runtime_images；复用远端选择器和原子写入边界。
- `scripts/verify_runtime_logs.py`: 日志收集当前仍直接调用本机 Docker。
- `tests/ops/test_live_dependencies.py`: 数据库与 Worker 故障用例仍硬编码本机容器。
- `tests/ops/test_remote_environment.py`、`test_remote_guard.py`、`test_runtime_logs.py`: 既有回归入口。

## Tasks & Acceptance

- [x] `remote_environment.py`、远端 YAML 和相关测试：修复 R1/R2/R3；只读节点证据保存在专属 `.local/remote/` 目录。
- [x] 独立新增运行快照测试：执行真实 runtime_images/record_runtime_images 函数路径，覆盖 R4 成功、漂移和失败保留旧文件。
- [x] `verify_runtime_logs.py`、`test_live_dependencies.py` 与必要专用 helper/测试：修复 R5/R6/R7，约束远端命令、归属和恢复目标。
- [x] 运行聚焦测试、Ruff 和后端回归，独立强模型审查并修复有效发现。
- [x] 更新远端运行指引和交接记录，明确剩余现场验收及 SSH 策略授权。

Given 既有 EID 资源与预存工作区，when 修复与测试完成，then 不修改其他项目、不丢失预存内容、不将模拟或未执行验收记为通过。
Given 安全边界异常，when 调用修复后的入口，then 在任何副作用前拒绝。

## Implementation Notes

初始化快照：`.local/remote/recovery-20260915/baseline.json`、`status.txt`、`tracked.diff`；502 个既有文件记录。无 merge/rebase/cherry-pick，main HEAD 如上。图索引排除了 scripts，相关符号采用文件检索回退。

2026-09-16：三位独立执行代理完成本地修复，主代理组合验证 195 passed / 9 skipped，Ruff 通过。现场 RabbitMQ 当前节点为空队列，卷有两个节点目录，未合并/删除或重建；只读证据 `r1-rabbitmq-readonly-current.json`。新 remote 测试受用户全局 ignore 影响，必须显式保留归属清单。真实现场验收未执行。

## Spec Change Log

## Review Triage Log

2026-09-16 第一轮四层审查均返回终态；主代理按具体代码复核，以下全部裁决为 patch，测试缺口依据独立内存变异证据接受。

| ID / 来源 | 裁决 | 证据与修复 |
|---|---|---|
| A1 acceptance | medium | record_runtime_images 最后 readiness 后直接写文件；写前再次核对候选并保留旧证据 |
| V1 verification | medium | 将 guarded_inventory 的 require_running 传参改为 False 后195项仍通过；补实际链路旧候选拒绝 |
| V2 verification | medium | 根目录 UID 条件放宽后195项仍通过；补 collect_remote_state 实际文件系统边界测试 |
| V3 verification | medium | 去掉远端 stderr 扫描后195项仍通过；补 stderr-only 秘密检测 |
| E1 edge | high | 并发停两个依赖时恢复互相要求其他运行，均失败；与 B4 同根因保留两种触发验证 |
| E2 edge | medium | SOURCE_TREES 扩展名限制遗漏静态资源；打包集合必须与镜像指纹输入一致 |
| E3 edge | medium | 基础服务 health=None 被一概允许；按渲染候选实际声明的 healthcheck 强制健康，未声明探针的服务允许 None，不新增无关探针 |
| B1 blind | high | 外来 bind Source 与 EID 卷实际路径重叠不被归属检查发现；采集卷 Mountpoint 并检查路径重叠 |
| B2 blind | medium | 运行环境/命令未纳入 candidate；比较实际容器运行配置与渲染候选，清单绑定配置摘要 |
| B3 blind | medium | stop 结果返回前 KeyboardInterrupt 跳过恢复；未知结果仍尝试原目标安全恢复 |
| B4 blind | high | 其他服务退出阻止已停目标恢复；恢复与最终健康验收分离，仍拒绝任何身份/归属漂移 |

原远端部署、迁移、RabbitMQ 持久性和浏览器验收均未执行。第一轮后端回归 663 passed / 23 skipped，不能抵消上述有效发现。

第二轮修复：三个新执行上下文完成上述项目。核心174项、操作76项、最终readiness相关324项测试各通过；V1/V2/B1/B2/stderr 内存变异均被新增测试检出。运行清单每服务新增 runtime_config_sha256，provenance 增加 compose_sha256；按实际声明健康检查判断。等待完整组合与独立复审。

测试事件：修复前 selector 漂移用例触发旧入口回退，覆盖 `.local/runtime-images.json`；有限备份检索无可信原件，该本机旧清单作废，未伪造恢复。副本和说明保存在 `.local/remote/recovery-20260915/quarantine/runtime-images-invalid-test-write-20260916.{json,md}`，SHA256 `151F2D50FC66DB298091CFBD650AB9605080B99D17B3D41A0F12F4A8FCBFBF3E`。测试后来将所有证据路径重定向临时目录，并阻止真实 subprocess。最初一次旧snapshot测试触发本机 ssh -G 和监听只读枚举，无远端连接或服务操作。

第二轮四层审查全部终态；734 passed / 23 skipped 不关闭以下新发现。每条来源保留，归并为四项修复：

| ID / 来源 | 裁决 | 原文证据与修复 |
|---|---|---|
| C1 主线程 / blind / edge / verification / acceptance | high | producer provenance 新增 compose_sha256，但 RemoteRuntime 仍按旧字典精确比较，真实清单必被拒绝；统一生产消费契约并补真实生成到消费路径测试，不删除配置绑定 |
| C2 blind / edge | high | collector 未采实际 Privileged/PidMode，特权或宿主 PID 容器仍通过；实际隔离配置必须检查并绑定 |
| C3 blind / edge | medium | 只读健康状态未读实际 Healthcheck，CMD true 仍可通过；核验候选健康检查定义及预算，不能把状态替代检查定义 |
| C4 blind | medium | 停机后转发进程退出，恢复因 verify_tunnels 失败而不发管理 SSH；恢复可通过固定管理 SSH 重核验原容器身份归属，保持正常运行和日志的隧道门禁 |

第三轮修复候选：统一完整 runtime_manifest 契约；绑定实际隔离参数与健康探针定义；start 恢复独立于数据隧道。新增13项真实生产消费路径测试；六份聚焦测试317 passed（156.42s）、Ruff和diff检查通过，等待独立复审。测试使用原始I/O替身，未访问真实服务或本机运行清单。

第三轮复审：blind 无发现，acceptance approved（仅代码），verification 与 edge 共提出四项有效发现；主代理判为 patch，805 passed / 23 skipped 不抵消：

| ID / 来源 | 裁决 | 证据与修复 |
|---|---|---|
| D1 verification | medium | stage_remote_release.sh 实际归档校验消费者无测试；补正确包及内容/清单哈希不一致的拒绝，保证不进入解包 |
| D2 verification | medium | seed 远端锁/收据路径只有旧本地场景测试；启用真实远端选择器验证远端锁、恢复收据以及本地文件字节不变 |
| D3 edge | high | Python 镜像 USER eid，而 collector 未采 Config.User；Worker 实际User=0仍通过，必须按镜像默认及Compose合并后比对并绑定 |
| D4 edge | medium | 所有容器 bind Source 均 strict resolve，无关已停容器的消失路径导致采集失败；解析现存祖先仍检查父子重叠，不能阻断不相关恢复 |

第四轮修复候选：D3/D4 仅修改核心helper及两份相关测试，363 passed；D1 新增归档消费者测试5 passed；D2 新增真实远端selector/seed锁及收据测试12 passed，两处目录回退的内存变异均失败。主代理统一Ruff通过，整套后端回归及第四轮独立复审进行中。

2026-09-16 收尾：第四轮 blind、edge、verification、acceptance 四个新上下文全部终态，无剩余有效代码发现，acceptance approved。主代理完整后端 `uv run --offline --frozen pytest tests -q` 为877 passed / 23 skipped / 2既有弃用警告，261.26秒，exit0；统一Ruff与git diff检查exit0。done 只表示本规格的本地代码修复、隔离测试、独立审查及交接完成，不表示远端接入、任何Story或Epic完成。现场义务及唯一授权请求见 `remote-environment-2026-09-16.md` 和 `../../docs/remote-forwarding-authorization.md`。

## Verification

- `uv run --frozen pytest tests/ops/test_remote_environment.py tests/ops/test_remote_guard.py -q`
- `uv run --frozen pytest tests -q`（禁止设置 live 标志）
- `uv run --frozen ruff check`（变更文件）及 `git diff --check`
- 独立审查覆盖完整接入差异及本轮修复，不宣称远端验收完成。
