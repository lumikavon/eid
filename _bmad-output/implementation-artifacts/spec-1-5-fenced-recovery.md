---
title: 'Story 1.5：失租恢复与取消时拒绝旧结果'
type: 'feature'
created: '2026-09-23'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_key: '1-5-fenced-recovery'
epic_id: 'epic-1'
baseline_commit: 'f60aaccd663f794adeb7d2838e867fd82d7e8ad2'
context:
  - '_bmad-output/implementation-artifacts/epic-1-context.md'
  - '_bmad-output/planning-artifacts/development-validation-policy.md'
---

## 当前执行边界

用户已明确要求跳过测试、迁移、数据库、Broker 等运行时验证，推进 Story 1.5 到 `done`；这是仅适用于本 Story 的**软件开发关闭**例外，详见 `development-validation-policy.md`。本轮只允许源码与差异审查、静态检查和编译；测试源码可以编写、审查、编译，不运行 pytest、服务、数据库、Broker、迁移、fixture、故障注入或现场功能验证。五项运行 AC 全部保持 `not-run`，不表示通过或全量交付。代码修改后的 `opencode` 指定 Muse 模型调用已完成，结果仅作辅助源码意见。

## Intent

**Problem：** 1.4 已持久化 Task/Attempt/Outbox/Inbox，`eid_task_claim` 以 owner token 与 30 秒租约重领，`eid_task_finish_inventory` 只检查当前 owner、租约和 RUNNING。缺少独立单调 fence、按 attempt 隔离的 staging、唯一持久重试时间、取消请求与完成提交的明确排序，以及防止双 Beat 同时调度的协调契约。

**Approach：** 在现有任务协议上增量加入单调 fence、失租恢复、DB 计划重试、单活协调和取消提交检查。Worker 的慢工作位于短事务外；每个 attempt 只写自己的不可变 staging。只有当前 fence 的完成事务能发布 accepted result、终态、Inbox processed、事件与后继可执行性。先以现有只读 inventory handler 验证该通路；真实外部 connector 留给后续 Story。

## Boundaries & Constraints

**Always：** 失租后在 DB 锁下提升 fence 并创建新 Attempt；旧 Attempt 无论迟到、重复消息还是 ACK 丢失均不能接受结果。领取、续租、恢复、完成和取消均使用 DB 时间及当前行锁/CAS；完成短事务重验 fence、lease、base/content hash、当前授权与 policy epoch、cancel_requested。结果、Task 终态、Attempt、Inbox processed、TaskEvent 及适用的后继 Outbox 在同一提交边界内一致；完成提交后才 ACK。`next_retry_at` 是唯一 DB 重试计划，受 attempt 上限、指数退避上限和 jitter 边界约束；调度器只能依据持久状态生成下一 attempt 的投递，不能与 Celery retry 各自安排重试。Beat 通过 DB advisory lease/fence 保持单活，双实例竞争不产生双重有效领取。确定性权限/密级/缺项错误不自动重试；格式修复最多一次；耗尽或毒消息保留安全诊断和可检查失败/死信状态。取消先记录请求，完成与取消由 DB 提交顺序决定。已发送外部效果只能保留 `receipt_pending`/`unknown` 并等待核对；仅声明且获准的业务补偿可执行。

**Never：** 不把 Celery revoke、ACK、result backend 或 Broker 投递次数当业务真相；不让 DB 事务跨慢外部调用；不由旧 attempt 覆盖新 staging；不从旧结果推断当前授权。不能修改已提交的 `0008_durable_submission`，不能删除或重建既有任务、回执或历史。不得实现通用执行器、真实 connector、远程 shell 或 Story 1.6 的 SSE/UI；`0009` 仅扩展现有持久协议和必要 grants。

## I/O & Edge-Case Matrix

| 场景 | 输入 / 状态 | 可观察结果 | 错误与恢复 |
|---|---|---|---|
| 失租与迟到完成 | RUNNING attempt 租约过期，扫描器重领；旧 Worker 随后完成 | 新 attempt 的 fence 严格增大且 staging 独立；仅新 fence 可被接受 | 旧 Worker 得到 lost/stale，不改 result、终态、事件、后继或 Inbox processed；ACK 丢失重投按已提交状态去重 |
| 重试分类 | 瞬时 429/5xx/网络、格式、权限/密级/缺项、预算耗尽 | 同一 `next_retry_at` 决定可领取时刻；永久错误不排队 | 有界退避及 jitter；格式最多修复一次；耗尽为可检查 FAILED/DEAD_LETTER，不热循环 |
| 双调度器 | 两个 Beat 同时扫描到期计划和失租任务 | 每个到期意图只有一个有效 fence/attempt/投递意图 | 失去 advisory lease 的 Beat 停止写入；故障后持久计划可由新 owner 接续 |
| 完成先于取消 | 完成事务先提交 | Task 保持 SUCCEEDED，取消返回 too_late | 不将终态退回 CANCELLED，不额外接受结果 |
| 取消先于完成 | cancel_requested 先提交 | 后续完成不能接受；Task 在安全停止后为 CANCELLED | 未决外部效果标 `receipt_pending`/`unknown` 待核对，不能宣称已撤销；仅安全声明的补偿可继续 |

## Code Map

- `migrations/versions/0008_durable_submission.py`：当前 schema 与 `eid_task_claim`、`eid_task_finish_inventory`、relay 函数及 Worker grants；保持已提交文件不变。新增 `migrations/versions/0009_fenced_recovery.py`，以 `0008_durable_submission` 为 down revision，前向扩展状态/约束/索引/函数及最小权限，保留历史行与现有查询语义。
- `edw-worker/src/edw_worker/inventory.py`、`task_store.py`：现有唯一业务 handler、短连接调用和 ACK 边界；接入 fence、staging、heartbeat/retry/cancel 后仍保持只读 inventory，不接真实 connector。
- `edw-worker/src/edw_worker/relay.py`、`app.py`：现有持久 Outbox relay 与六类队列；在其上安排单活 DB 调度，明确 relay 与 Beat 的责任边界。
- `edw-api/src/edw_api/task_contract.py` 及任务路由：当前快照只含 QUEUED/RUNNING/SUCCEEDED/BLOCKED；按新增状态扩展严格 schema、受权取消及状态查询，保留现有请求幂等语义。
- `tests/contract/`、`tests/worker/`、`tests/ops/`、`tests/security/`：添加可执行的 fence、退避、双 Beat、取消双顺序和未知效果测试源码；本轮只静态检查/编译，不执行。

## Tasks & Acceptance

**Execution：**
- [x] 先核对当前源码、grants、状态约束和脏改动归属；确定 `0009` 的前向数据兼容、旧行默认值及受权 API/Worker 边界，不改 `0008`（源码方案已形成，迁移尚未执行）。
- [x] 增加单调 fence、按 attempt 的不可变 staging、租约续期/到期重领和带完整提交 guard 的完成函数；旧 owner/fence 不能执行任何接受写入（实现源码已写，运行行为未验）。
- [x] 增加有界分类重试、唯一 `next_retry_at`、FAILED/DEAD_LETTER 可检查诊断及 DB 单活调度；扫描与发布只创建持久意图，不执行慢任务（实现源码已写，运行行为未验）。
- [x] 增加取消请求/完成排序、受权查询与安全停止；对已发送外部效果定义 `receipt_pending`/`unknown` 契约，不在本 Story 接入真实 connector 或假装可撤销（实现源码已写，运行行为未验）。
- [x] 编写 crash/ACK-loss/lease-expiry、双 Beat、取消两种胜序、重试分类/上限及事务边界测试源码；完成允许的静态检查、编译、独立审查与指定 Muse 辅助审查，并真实记录未运行 AC。现有双调度/取消用例为顺序源码，Broker ACK 为 mock 标记，不宣称并发或真实 ACK 通过。

**Acceptance Criteria：**
1. **Given** RUNNING Worker 被杀或失租，**when** 扫描器重领并有旧 Worker 迟到完成，**then** 新 Attempt 的 fence 严格升高、staging 独立，旧完成不改变 accepted result/Task 终态/后继/事件/Inbox processed。**主验证：** PostgreSQL 租约到期与迟到完成运行试验，检查行版本及事件；当前 `not-run`。
2. **Given** 当前 Attempt 完成，**when** 短事务提交，**then** 只有 fence、lease、base/content hash、policy epoch、当前授权及未取消均有效时，结果/终态/Inbox processed/事件/后继一同提交。**主验证：** 逐项 guard 失效与事务故障点的 DB 运行试验；当前 `not-run`。
3. **Given** 瞬时、确定永久、格式及耗尽错误，且两个 Beat 同时扫描，**when** 到期计划被处理，**then** 仅 DB `next_retry_at` 产生一个有效的有界新 Attempt；永久错误不重试，格式至多修复一次，耗尽结果可检查。**主验证：** 带时钟与双 Beat 竞争的持久调度运行试验；当前 `not-run`。
4. **Given** 完成与取消并发，**when** 两种提交顺序分别获胜，**then** 完成先赢保持 SUCCEEDED 并返回 too_late，取消先赢拒绝后续接受并安全转 CANCELLED。**主验证：** 两种行锁提交顺序的并发运行试验；当前 `not-run`。
5. **Given** 取消前已发送外部效果但回执未知，**when** 取消被提交，**then** 效果保持 `receipt_pending`/`unknown` 供核对，不能记录为已撤销或无条件补偿。**主验证：** 声明式效果替身的持久状态/回执运行试验；当前 `not-run`，真实 connector 语义由后续 Story 验收。

## Verification & Open Decisions

`0009`、API、Worker、Web、健康契约、部署清单及测试源码已形成软件交付；见 `story-1-5-software-evidence-2026-09-23.md`。Ruff、Python 编译、Web 类型检查与构建、API/Worker 离线构建、Compose/JSON 静态解析及差异检查已通过。独立源码审查发现的问题已修复并复核；指定 `Muse Spark 1.3 Contributor` 的 `opencode` 调用已完成，输出只作辅助意见。依据用户对本 Story 的明确例外，`done` 只代表软件开发关闭；全部五项 AC 的主运行验证仍为 `not-run`，不构成运行验收通过。原 Epic 的 L 工作存储/Worker 终止、R 外部效果取消及 P 多节点恢复仍待后续授权与环境。

- **实现取值：** Task/Inbox 租约与续期为 30 秒、调度租约为 15 秒；最多 3 次 Attempt、格式修复最多 1 次，退避基数为指数 2 秒并设 60 秒上限及小于 1 秒的确定性 jitter。以上仅从源码核对，DB 时间与竞争行为 `not-run`。
- **接口同步：** 0009 已扩展重试 Outbox/任务快照状态，API、Worker、Web 与契约源码已同步；迁移兼容和旧客户端实际行为 `not-run`。
- **外部效果边界：** 本 Story 只保存可核对的效果状态/声明契约；具体 connector 的幂等、回执及补偿授权仍属于后续集成 Story，不能用 inventory 的无外部效果替代其运行验收。
