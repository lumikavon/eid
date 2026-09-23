# Story 1.4 持久任务软件质量门禁

状态：2026-09-23 按用户最新指令生效。适用对象：`1-4-durable-submission`。本文件只规定当前允许的软件交付检查；保留原 AC1–AC3 的功能要求和运行验证禁令。原 PostgreSQL/RabbitMQ 故障、重复投递与 ACK 的运行时质量门禁已剔除，不再阻止本 Story 的软件完成和串行推进。有限例外见[开发与验证规则](../planning-artifacts/development-validation-policy.md)。

## 判定规则

门禁分别记录 `pass / fail / not-run / blocked`、候选 commit、检查命令或观察步骤、适用时的退出码、机器检查原始输出或人工复核的文件行号与记录路径，以及复核人。逐项记录见[软件门禁取证](story-1-4-quality-gate-evidence-2026-09-23.md)；其中 `.local/story-1-4-quality-gate-20260923/` 均从仓库根目录起算。软件检查的 `pass` 只证明其各自的源码、静态或构建范围。确定的软件缺陷记 `fail` 并修复；当前禁止执行的运行项目如实记 `not-run`，既不冒充通过，也不再是本 Story 的完成门禁。

### S：当前必须通过的软件门禁

| ID | 必须核对的源码与产物 | 通过条件 | 当前记录 |
|---|---|---|---|
| S0 归属 | `HEAD`、开工前工作区快照、Story 文件清单与差异 | 每个修改有 Story 归属；预存不相关修改未被覆盖、暂存或纳入 Story 提交 | 精确暂存与提交归属按本 Story 文件清单核验；预存规划修改不纳入提交 |
| S1 PostgreSQL 事务 | API `submit`、迁移 0008 的约束、grants 与 definer 函数 | `202` 在数据库事务提交之后；Task/初始事件/Outbox/审计/幂等回执同事务；同键先重验当前授权、异载荷精确 409；Worker 不获得 ACL/head/审批/发布或业务表广泛权限；无长外部调用占用事务 | 静态审查通过；SQL 实际执行 `not-run` |
| S2 RabbitMQ 传输 | Worker 队列/交换机配置、relay 领取和确认路径、Compose 入口 | durable quorum、具名已授权 exchange、publisher confirm、owner token 与租约一致；确认不明不标已投递；已确认但未完成记录仍可由持久状态恢复；relay 退出导致就绪失败 | 静态审查通过；实际投递 `not-run` |
| S3 重复与 ACK | Inbox/Attempt/结果事务、版本/绑定隔离、Worker 消费异常分支 | `received` 不等于 `processed`；旧 owner 不能完成；结果/终态/事件/processed 原子提交后才正常 ACK；不兼容版本、异载荷、存储损坏与终态不一致均可检查；暂时性租约失败保留恢复路径 | 坏信封隔离、数据库绑定、hash/租约围栏及就绪探针的确定缺陷已按审查意见修复；最终全量源码复核 `approved`；真实 ACK `not-run` |
| S4 契约与构建 | task schema、迁移 head/fixture guard 源码、Ruff、Python 编译、离线 API/Worker wheel | schema 与模型导出一致；head/fixture 的源码引用一致；检查/编译/构建退出 0，新模块进入 wheel；不得因检查失败弱化断言、权限或忽略规则 | 机器检查退出 0，原始日志和 wheel 散列见取证记录；head/fixture 只完成源码核对 |
| S5 独立复核 | 新上下文 `eid_reviewer` 与实际指定 `Muse Spark 1.3 Contributor` 辅助静态审查 | Reviewer 明确返回 `approved`；所有确定的高/中风险源码问题修复并复核；Muse 建议只作辅助 | 局部与最终全量源码复核均明确 `approved`；修复后 Muse 再调用退出 0 |

S1–S3 的“源码审查通过”只说明未发现确定的源码阻断问题。`tests/contract/test_tasks.py`、`tests/worker/test_durable_submission.py`、`tests/worker/test_durable_supervision.py` 和 `tests/ops/test_live_durable_recovery.py` 的源码用于审查覆盖面；本轮没有执行这些测试。现有 Worker 单元用例使用替身；SQL recovery 用例没有真实 Broker 或进程崩溃观察。

## 非门禁的未验证行为

本 Story 的原运行门禁清单已从完成判断中移除。真实 PostgreSQL 原子提交及并发幂等、RabbitMQ 故障与 publisher confirm 恢复、重复投递与 Broker ACK、有效权限及连接池边界均未运行，统一记为 `not-run`。这些行为仍是产品需求，不能由源码检查、替身测试源码或 wheel 构建证明；本轮既不执行，也不将它们转为 Story 1.5 或 Epic 13 的隐含门禁。若以后另有运行验收指令，必须重新核对隔离环境、候选代码与授权，且不得追认本轮为通过。

完整差异独立审查发现的条件性 P2 是持久 Outbox 坏信封缺隔离。后续修复和审查又发现数据库事件/任务绑定、仅修复 hash 时的隔离竞态，以及 Worker readiness 探针旧函数签名；这些已逐项修改，并补写对应测试源码。已认证 `eid_worker` 本身仍可通过既有 `eid_task_claim` 权限伪造异常使任务隔离，这是既有可信服务身份边界；不将其记为普通 API 用户可利用的新增路径，后续权限模型审查应单独处理。

## 当前判定与串行推进

- **S 层：软件检查与最终源码复核已通过。** 修复后 Ruff、编译、离线构建、局部与最终全量独立复核已完成，见[软件门禁取证](story-1-4-quality-gate-evidence-2026-09-23.md)和[软件审查记录](story-1-4-software-review-2026-09-23.md)。精确暂存与提交归属另须按 S0 核对。
- **运行行为：`not-run`、非本 Story 完成门禁。** 原 AC1–AC3 的运行结果不得写为通过。
- S5 已取得明确 `approved`；状态同步、精确暂存并提交成功后，按 `PROMPT.md` 串行规则推进 Story 1.5；不得在此之前开发下一 Story。
