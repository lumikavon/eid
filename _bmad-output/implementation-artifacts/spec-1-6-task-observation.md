---
title: 'Story 1.6：重连后跟踪真实任务与通知'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
review_loop_iteration: 5
story_key: '1-6-task-observation'
epic_id: 'epic-1'
baseline_commit: 'cacd87eb7ff17922c649254e11ecd0e133c3ced3'
context:
  - '_bmad-output/planning-artifacts/development-validation-policy.md'
  - '_bmad-output/planning-artifacts/epic-1-secure-workspace.md'
---

<frozen-after-approval reason="Story 1.6 intent and constraints authorized by Epic 1 planning">

## Intent

**Problem：** 当前任务仅能按 ID 查询 inventory；通知铃铛仍提示未开放。关闭页面或漏收事件后，用户无法从持久任务列表和通知恢复进度，也无法安全判断失败、取消和最终结果。

**Approach：** 在已提交的任务状态与 TaskEvent 上建立当前授权列表、REST 快照、可重放 Bearer SSE 和持久通知；Web 从快照恢复并按序应用事件。六类任务按真实记录呈现；只有已注册且声明安全能力的业务操作可提交、取消或重试。

## Boundaries & Constraints

**Always：** PostgreSQL Task/Attempt/Event 是真相；每任务提交序号递增，终态与事件同一短事务。每次列表、详情、结果、通知打开与动作重新核对当前身份、工作区、资源权限和策略 epoch；SSE 每次发事件及空闲心跳前重新核对，撤权/过期断流，Web 清受保护快照、订阅和详情。非法或未来 `Last-Event-ID` 拒绝；低于保留窗口时返回受权 `reset_required/current_seq`，客户端重新取快照后续接，忽略重复或旧序号。进度未知为 `null`；事件仅含安全 ID/状态摘要，正文、Evidence、Prompt、凭据和可直接使用的下载地址只经重新鉴权 REST 获取。通知已读状态独立于任务状态；结果与产物身份不因重连改变。

**Never：** 不把队列声明当六类业务 handler 已实现；现阶段仅 inventory 有真实 handler，其余类别无任务时显示真实空态，缺能力时禁用操作并给原因。不得伪造进度、结果、通知或样例成功，不从客户端 category/owner 判权；不将 token 放 URL、持久浏览器存储或原生 EventSource。未知外部效果不得盲重试；终态重跑创建有父关联的新 Task，保留旧历史。不改 0008/0009 历史迁移、原型 HTML、既有数据；不执行迁移或清理历史事件。

## I/O & Edge-Case Matrix

| 场景 | 输入 / 状态 | 可观察结果 | 错误与恢复 |
|---|---|---|---|
| 重连与缺口 | 同一任务断线，重复 cursor 或事件保留缺口 | 按 `seq` 去重重放；缺口以授权快照重建并保留 `result_ref` | 非法/未来 cursor 拒绝；不能补齐时明确 reset，不猜测状态 |
| 撤权 | 列表、通知、流中或打开目标时授权变化 | 服务端拒绝或断流；Web 清受保护内容并提示重认证 | 不发送旧缓存、旧结果或资源存在性 |
| 操作与通知 | 可取消/安全重试任务、失败/死信及已读通知 | 取消请求中与终态分开；安全重试产生新 Task；已读仅改通知 | 不支持或 unknown 效果持久显示原因；失败不以 toast 充成功 |

</frozen-after-approval>

## Code Map

- `migrations/versions/0008_durable_submission.py:44`、`0009_fenced_recovery.py:70`：已有 `(task_id,seq)` TaskEvent 与扩展状态；新增前向 0010、最小授权 grants/通知存储，不改历史迁移。
- `edw-api/src/edw_api/tasks/repository.py:13`、`:90`：snapshot/`_owned` 当前仅 inventory owner 读取；列表、事件、通知、动作需复用当前事实授权并避免跨 scope 泄漏。
- `edw-api/src/edw_api/tasks/routes.py:17`、`task_contract.py:12`：当前仅按 ID 读/结果/取消，C-3 只允许 integration/inventory；扩展 wire schema 与路由，未注册操作拒绝。
- `edw-api/src/edw_api/access/policy.py:60`、`access/repository.py:58`：`authorize`/`checked` 是当前 RBAC+ABAC+密级入口；缺专门动作授权时 fail closed。
- `edw-worker/src/edw_worker/inventory.py:129`、`app.py:23`：唯一注册 handler 是 inventory；六队列已声明，不能据此生成六类假任务。
- `edw-web/src/app/App.tsx:24`、`:45`、`:176`：补 X-16 路由、scope 清理与原位 `.bell`；fetch streaming Bearer、快照 reducer、真实通知详情。`deployment/nginx/default.conf:13` 为 SSE 配非缓冲、禁缓存与超时；保留普通 API 行为。

## Tasks & Acceptance

**Execution：**
- [x] `0010`、C-3 契约、API：前向扩展真实六类状态投影与通知，提供受权分页列表/详情/快照、持久事件与 reset；序号分配和 retention floor 持久一致，默认不删历史。
- [x] API/NGINX：提供 `GET /api/v1/workspaces/{wid}/tasks/{id}/events` 标准 SSE；短轮询各自事务，心跳无业务序号，校验 cursor、输出上限、当前权限及断流；代理关闭缓冲和缓存。
- [x] API/Web：通知列/读/开与安全任务取消、手动重试能力；重试仅已注册且可安全重放的操作，终态用 child Task；Web 展示六类真实状态、attempt/错误/结果、断线重建、撤权清理与不支持原因。
- [x] 编写 cursor/缺口/重复、撤权、动作竞态、通知独立性与六类空态测试源码；只做源码审查、静态检查和编译，独立强档审查并修复；代码修改后核实并调用指定 Muse 模型作辅助静态意见。

**Acceptance Criteria：**
1. 给定六类中有真实持久任务，打开通知并断线重连后，受权用户从快照和 TaskEvent 恢复有序状态、去重且保留最终产物身份；未知进度为 `null`。主验证：API→Worker→PG→NGINX→浏览器重连及保留缺口试验；当前 `not-run`。
2. 给定非法/未来 cursor 或流中撤权，下一次发送前拒绝或关闭连接，Web 清受保护内容；URL 无 token，事件无正文/Evidence/秘密。主验证：cursor 与实时撤权安全试验及事件体检查；当前 `not-run`。
3. 给定失败/死信、未知效果或不支持操作，界面持久显示原因；允许的取消/重试重新授权并返回真实新状态，通知已读不改变任务。主验证：任务动作与通知持久状态试验；当前 `not-run`。

## Implementation Notes

- 0010 为终态事件建立持久通知，并加入仅由服务端绑定的本地资源观察关系；读取任务、事件、通知和结果时复核当前身份、工作区、权限与策略 epoch。无绑定或无法核对的非 inventory 任务不可见；外部 ACL 尚无可信路径。仅现有 integration/inventory handler 可以提交、取消、重试或读取库存结果；其他类别只展示真实持久任务及不可用原因，绝不制造任务或结果。
- REST 提供受权任务/通知分页、事件页与未读存在性查询；SSE 使用 Bearer 请求头、有限流时长及每轮重新鉴权。Web 恢复最新保留事件、显示历史裁剪、重连去重、撤权清理，并在结果未知时保持 `null`。未读查询最多核对 512 条不可见候选，超限返回 503 而不误报无未读；0010 的部分索引覆盖未读筛选。
- 测试源码覆盖契约、授权、cursor、撤权、通知独立性及 Web wire 边界；按当前政策只编译和审查，未执行测试套件、迁移或实际运行。三项 AC 的运行主验证均保持 `not-run`，此处 `done` 仅表示软件实现及静态门禁关闭。
- SSE 每个轮询使用独立的已授权事务；事务结束到实际发送之间存在极短竞态窗口，独立后端审查将其列为未证实的时序风险。真实撤权时序尚未运行验证。

**本 Story 文件清单：** `contracts/task.schema.json`、`deployment/compose.yaml`、`deployment/nginx/default.conf`、`edw-api/src/edw_api/{config.py,main.py,task_contract.py,tasks/repository.py,tasks/routes.py}`、`edw-web/src/app/{App.tsx,prototype.css,task-api.ts,task-api.test.ts}`、`edw-web/src/auth/oidc.ts`、`edw-web/src/features/tasks/{TaskCenter.tsx,TaskCenter.action.test.ts,task-action.ts,tasks.css}`、`edw-worker/src/edw_worker/app.py`、`migrations/versions/0010_task_observation.py`、`scripts/seed_access_fixtures.py`、`tests/{contract/test_task_observation.py,security/test_task_observation.py,ops/test_live_dependencies.py,ops/test_live_migration.py,worker/test_worker_health.py}`、本记录与 `sprint-status.yaml` 的 Epic 1/Story 1.6 状态块。

## Spec Change Log

## Review Triage Log

- 第一轮（2026-09-24，独立审查）：high，`tasks/repository.py` 与 `0010_task_observation.py` 的六类观察范围不一致，真实非 inventory 任务会在受权查询中消失；需按类别建立服务端观察授权，动作仍只允许现有 handler。
- 第一轮：medium，`TaskCenter.tsx` 的任务 API 401 未被 `App.tsx` 的认证错误判别识别，失效令牌未清除；需统一 401 边界。
- 第一轮：medium，`TaskCenter.tsx` 提交中的刷新改变 request key，可能丢弃真实响应并永久停在 pending；需保留操作身份与恢复路径。
- 第一轮：medium，`task-api.ts` 在拆帧前限制 SSE 总缓冲，批量合法帧可能被拒；需只限制未完成单帧。
- 第一轮：low，`App.tsx` 的铃铛红点无条件显示，与真实未读状态不符；需绑定持久未读数。
- 第二轮：medium，铃铛最多扫描 100 页，可能漏报更早未读；新增服务端受权未读查询并让未知状态不显示红点。low，`reset_required` 后旧事件未清；改为清空并重建。
- 第三轮：medium，未读查询缺匹配索引；0010 加部分索引。medium，历史从保留起点最多取 256 条且初始 reset 不重建；改从最新 64 条恢复并重试变化的窗口。low，轮询时红点短暂消失；同授权范围内保留已确认状态。
- 第四轮：medium，实时第 65 条事件裁剪历史却未提示；增加 `eventCount` 与同步的历史不完整提示。
- 第五轮：独立 `eid_reviewer` 对最终事件计数修复给出限定范围 `approved`；后端部分索引复审 `approved`。指定 Muse Spark 1.3 Contributor 的辅助静态审查已实际调用，未发现该最终切片的阻断问题；其意见不替代独立审查或运行证明。

## Verification

`development-validation-policy.md` 2026-09-23 全 Epic 规则优先：只运行源码/差异、契约/配置静态检查和编译或离线构建；测试源码可写、可审、可编译，测试套件、服务、数据库、迁移、SSH/Docker、浏览器及真实环境均不运行。软件关闭仍需全部功能与安全实现、独立审查和缺陷修复。上述三个 AC 与原 L/R/P 运行验收逐项记 `not-run`，静态/编译通过不计为运行通过；未实现 handler 是功能缺口，不得归类为环境缺口。

最终静态门禁：`npm run build`、`npm run lint`、`python -m compileall`、`ruff check`、`git diff --check` 均退出 0。测试套件、迁移、数据库、服务、浏览器及现场验证均 `not-run`。
