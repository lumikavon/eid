---
title: 'Story 1.4：通过持久化传输保留已提交操作'
type: 'feature'
created: '2026-09-22'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_key: '1-4-durable-submission'
epic_id: 'epic-1'
baseline_commit: 'f43ab41efdd4ebbe201ee0758b5b8bd36e372ac3'
context:
  - '_bmad-output/implementation-artifacts/epic-1-context.md'
  - '_bmad-output/planning-artifacts/development-validation-policy.md'
---

## 当前执行边界

用户当前只授权软件开发、源码检查、静态分析和编译。可以编写测试，但不得运行测试、服务、数据库迁移、fixture、浏览器或实际环境功能验证。2026-09-23 用户进一步明确剔除本 Story 的 PostgreSQL/RabbitMQ 故障、重复投递和 ACK **运行时质量门禁**；实际运行结果仍为 `not-run`，静态和编译结果不得冒充运行通过。软件完成以[有限例外](../planning-artifacts/development-validation-policy.md)和[软件质量门禁](story-1-4-quality-gates-2026-09-23.md)判定。代码修改后调用 `opencode`，先核实 `Muse Spark 1.3 Contributor` 的模型标识，并记录真实返回。

<frozen-after-approval reason="PROMPT.md Epic 1 串行开发授权与当前规划约束">

## Intent

**Problem：** 当前 API 和 Worker 只有身份、工作区及发现能力，接受异步请求后还没有持久任务和消息投递链。代理、Broker 或 Worker 故障时无法证明请求仍被保留。

**Approach：** 增量引入 C-3 Task/Attempt、最小 DAG 依赖、TaskEvent、Outbox/Inbox 和只读项目 inventory 任务。API 在短事务中保存当前授权请求、幂等回执与审计并返回 `202 task_id`；独立 relay 在提交后用租约与 publisher confirm 投递；Worker 按持久 Inbox 和受保护完成事务处理重复消息。

## Boundaries & Constraints

**Always：** 同键同载荷必须先重验当前授权并返回原任务身份，异载荷返回 `409 IDEMPOTENCY_KEY_REUSED`。Task/事件/回执/审计/Outbox 原子提交；relay 的 claim 与确认更新使用租约及 owner token，确认不明时保留待投递。Inbox `received` 不等于 `processed`；结果、终态、processed、事件与存在的后继 Outbox 同事务提交，之后才 ACK。消息校验 schema、来源和数据库绑定，未知不兼容版本保留可检查诊断且不得执行。Worker 不获得 ACL、head、审批、发布或发现元数据的广泛读写权；inventory 从当前授权、受限的项目投影产生有界结果，查询结果仍须当前授权。六类队列声明保留，业务 handler 只实现 inventory。原三项 AC 的功能行为保留；其运行时故障、重复投递和 ACK 观察不再作为本 Story 软件完成门禁，未执行不视为通过。

**Never：** 不在 API 请求事务内访问 Broker；不依赖 Celery ACK/Redis 作业务真相；不把用户 token 写入消息；不扩充通用远程执行器、模型或企业接口；不实现 1.5 的完整 fence/heartbeat/退避/cancel 或 1.6 的 SSE。不得改变既有迁移、删除数据或降低现有数据库 grants。

## I/O & Edge-Case Matrix

| 场景 | 输入 / 状态 | 可观察结果 | 错误与恢复 |
|---|---|---|---|
| 提交与重放 | 有权 inventory 请求和 Idempotency-Key | 首次 `202` 及稳定 task_id；同载荷重放同一任务，无第二条 Outbox/审计 | 撤权后拒绝；异载荷 `409 IDEMPOTENCY_KEY_REUSED`；审计/DB 失败全回滚 |
| Broker 故障 | DB 提交成功、Broker 不可用或确认不明 | Task 与 Outbox 保留 queued；恢复后以同 event_id 至少一次投递 | claim 失效后可重领；旧 owner 不得覆盖新确认 |
| 消费崩溃与重复 | Inbox 已 received、未完成；重复 event_id | 可恢复领取并只提交一个业务结果；完成后重复消息不重复执行 | 同 ID 异内容或未知主版本隔离并可检查；完成事务失败不 ACK 成功 |
| Inventory | 当前项目与用户授权、随后授权变化 | 只读、有界、可追溯的当前项目摘要；任务状态与结果标识可查询 | 过期/撤权 delegation 阻断，不重新签发或绕过；旧结果不得泄漏 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/access/repository.py`、`policy.py`：当前授权锁及 `inventory:read`；delegation 只有五分钟，不能直接假定长期有效。
- `edw-api/src/edw_api/discovery/repository.py:280`、`routes.py:60`：同事务审计/幂等及路由模式；发现回执的错误码与任务协议不同。
- `edw-api/src/edw_api/db.py`、`main.py`：数据库连接、Bearer 与路由装配；Broker 故障不能阻止已授权 DB 提交。
- `edw-worker/src/edw_worker/app.py`：六类 quorum 队列及 publisher confirm 已配置，目前没有业务任务。
- `migrations/versions/0007_workspace_discovery.py`：当前 head，新增迁移只能 expand，并配置 API/Worker 最小 grants。
- `tests/contract/test_discovery.py`、`tests/security/test_discovery.py`、`tests/ops/test_live_discovery_upgrade.py`：契约、事务回滚、迁移/grants 测试写法；本轮只编写不执行。

## Tasks & Acceptance

**Execution：**
- [x] 定义版本化 task envelope、提交/状态/结果 schema 和静态契约向量；六类路由保持声明，inventory 是唯一执行 handler。
- [x] 新增 0008 expand 迁移与最小 API/Worker grants；Task、Attempt、依赖、Event、Outbox、Inbox、隔离记录和幂等约束均有明确 owner、索引及大小上限。
- [x] 实现 API 受权提交、重放、状态/结果查询；当前授权和审计与 Task/Outbox 同事务，失败回滚。
- [x] 实现独立 Outbox relay 及 Worker inventory handler、Inbox 领取/完成与 ACK 语义；不在慢调用期间持有数据库事务。
- [x] 编写契约、安全、迁移和故障点测试源码；更新必要配置/静态检查入口，不启动实际运行环境。
- [x] 做源码检查、编译、独立审查、问题修复、指定 Muse 辅助审查；记录未执行的原运行验收及完整文件归属。

**Acceptance Criteria：**
1. **Given** 有权请求及 Idempotency-Key，**when** API 接受或重放，**then** Task/state/audit/Outbox 原子持久化并返回同一 `202 task_id`；不同载荷 `409 IDEMPOTENCY_KEY_REUSED`，relay 只投已提交工作。
2. **Given** 提交前、提交后投递前或确认后更新前故障，**when** 恢复扫描，**then** 未提交请求没有任务，已提交请求保留并至少一次投递；Broker 不可用时 queued 仍真实可见。
3. **Given** 重复 `(consumer,event_id)` 或 received 后崩溃，**when** Worker 重领并完成，**then** received 不冒充 processed，结果/终态/processed/事件/后继 Outbox 原子成功后才 ACK；未知版本可检查且不执行。

## Implementation Notes

2026-09-23：源码、测试源码、配置及 0008 迁移已写入；修复后受影响 Python Ruff、编译、差异检查及 API/Worker 离线 wheel 构建均退出 0。独立 `eid_reviewer` 先后发现持久坏信封、数据库绑定、hash 修复竞态与 readiness 探针缺陷，已按意见修复并补测试源码；readiness 局部及最终全量源码复核均明确 `approved`。指定 `Muse Spark 1.3 Contributor` 的标识核实和修复后留存原始输出的禁用工具审查见[软件门禁取证](story-1-4-quality-gate-evidence-2026-09-23.md)，其错误行号与输入截断提示不当作独立证据。完整文件归属和保留问题见[软件审查记录](story-1-4-software-review-2026-09-23.md)。

已勾选项仅表示对应的软件实现与允许的检查已完成。AC1–AC3 的 PostgreSQL/RabbitMQ/Worker 运行验证均为 `not-run`，但依用户最新指令已从本 Story 的完成门禁剔除。最终全量源码审查已 `approved`；本 Story 的 `done` 只表示软件开发完成，不表示上述运行行为验收通过。须完成精确暂存及 Story 专属提交后才可开始 1.5。

## Spec Change Log

- 2026-09-23：依据用户最新指令，仅调整 Story 1.4 的完成证据语义；从软件质量门禁中移除 PostgreSQL/RabbitMQ 故障、重复投递和 ACK 运行观察。保留原 AC 功能行为与 `not-run` 事实。上文冻结段只改动与本指令冲突的最后一句，不改变数据完整性、权限或消息处理约束。

## Review Triage Log

- 2026-09-23 完整差异独立审查：持久 Outbox 中的未来版本/损坏信封在 relay 解析失败后无持久隔离，租约到期可能反复领取；按条件性 P2 修复。测试源码另缺 claim 事务提交先于 publish 的假连接顺序断言。软件门禁在修复及复核前保持未通过。
- 后续独立复核：格式合法但与 Outbox 行不符的事件/任务 ID 可错误发布；只修复 hash 时旧 relay 可隔离已修复任务；readiness 仍查旧 `eid_task_relay_confirm` 签名。这些确定缺陷已修复并补测试源码，readiness 局部及最终全量源码复核均明确批准。
- 最终文档/暂存审查发现暂存区仍是旧代码和旧散列；提交前重新精确暂存并检查 index，避免遗漏修复或纳入预存规划修改。
- 已认证 `eid_worker` 能通过既有 `eid_task_claim` 权限伪造异常隔离任务，是现有可信服务身份边界；不将其记为普通用户可触发的本 Story 新漏洞，后续权限审查单独处理。

## Verification

本轮已运行影响范围的 Ruff、Python 编译、JSON/契约静态检查和两个 Python 工程离线构建；退出码均为 0。未执行 pytest/Vitest/Playwright、迁移、服务或 Broker。原 PG/RabbitMQ failpoint、重复投递和 ACK 观察均为 `not-run`，不再是本 Story 软件完成门禁，详见本 Story 审查记录。

2026-09-23 更新[持久任务软件质量门禁](story-1-4-quality-gates-2026-09-23.md)：S0–S5 是当前可判定的软件检查；原运行门禁清单已移除，未验证行为另在[取证记录](story-1-4-quality-gate-evidence-2026-09-23.md)记为 `not-run`，不冒充通过。
