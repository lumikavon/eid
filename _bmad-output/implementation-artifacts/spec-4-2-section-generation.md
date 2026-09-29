---
title: 'Story 4.2 受控章节生成提案'
type: 'feature'
created: '2026-09-28'
status: 'review'
route: 'dispatch'
baseline_commit: '6b9b20cc84220d4be3e6c5bd4cad10bbf0c4e7c3'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-4-context.md'
  - '_bmad-output/planning-artifacts/development-validation-policy.md'
---

<frozen-after-approval reason="用户拥有实施意图；批准后仅由用户修改">

## Intent

**Problem:** 现有模型运行接受任意文本并返回通用响应，不能按已确认的大纲、项目上下文和当前授权的章节证据生成可审阅的章节提案。

**Approach:** 为章节建立持久阶段与固定输入，分阶段验证当前上下文、确认大纲、Evidence Pack、模型策略和权限，生成结构化提案并进行跨章节一致性检查；Worker 只唤醒 API，不修改文档 head。

## Boundaries & Constraints

**Always:** 章节 ID 来自当前确认大纲；Pack 必须与章节、上下文、正文基版一致，且逐项按当前权限复核。无足够证据时明确 `BLOCKED_BY_MISSING_INFO` 并列出缺失项，不凭模型补造事实。提案保留 AST、Claim、引用、假设、缺失项和模型/来源溯源；阶段、失败、取消与冲突可查询。外部调用前后及提交时重验权限、策略、基版、租约与取消状态。整稿按章节提案组装并检查相互冲突，不绕过人工接受。

**Never:** 不让 Worker 写文档版本/head；不将模型输出直接保存为正文；不把本地替身视为真实质量证据；不运行测试套件、迁移、服务或浏览器。本轮只推进 `review`，运行验收 `not-run`。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 结果 | 失败 |
|---|---|---|---|
| 合规 | 当前大纲/上下文/章节 Pack/策略 | 202、持久阶段、受限章节提案 | schema 不合法终态失败 |
| 缺证 | Pack 无当前可验证支持 | 无虚构正文，缺失信息可定位 | BLOCKED_BY_MISSING_INFO |
| 失效 | 取消、撤权、正文或 Pack 改变 | 保留任务及原因，提案不生效 | cancelled/conflict/blocked |
| 组装 | 多章节提案 | 按大纲顺序合并并检查交叉矛盾 | 不作整稿自由生成 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/model_gateway/routes.py`、`repository.py`：复用受控模型调用及持久栅栏；通用文本入口不能证明来源。
- `edw-api/src/edw_api/knowledge/evidence.py`、`evidence_routes.py`：复用 Pack 可见性和逐项来源复核；不要将旧摘录视为授权。
- `edw-api/src/edw_api/documents/outline_repository.py`、`context_repository.py`：读取当前确认版本与章节 ID；不要相信调用方传入的标题。
- `edw-api/src/edw_api/documents/editor_domain.py`、`claims.py`：结构化 AST/Claim 契约；提案不能提交文档版本。
- `edw-worker/src/edw_worker/model_wake.py`、`relay.py`：最小权限唤醒与持久重试模式。
- `edw-web/src/features/templates/TemplateWorkspace.tsx`、`edw-web/src/features/tasks/TaskCenter.tsx`：章节入口及持久任务观察；保留既有编辑路径。
- `migrations/versions/0022_model_governance.py`：新增迁移应在其后，不改历史迁移。

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0023_section_generation.py`：持久章节任务、阶段、取消、提案及受限授权；不授 Worker 正文权限。
- [x] `edw-api/src/edw_api/model_gateway/`：检查当前输入/Pack、顺序阶段、生成有界 schema、失败与取消栅栏、组装一致性检查。
- [x] `edw-api/src/edw_api/main.py`、`edw-worker/src/edw_worker/model_wake.py`、`relay.py`：路由及仅唤醒的任务链。
- [x] `edw-web/src/features/templates/`：当前章节生成、持续状态与只读提案，缺证及失败可见。
- [x] `tests/contract/`、`tests/security/`、Web 测试源码：正反契约与拒绝路径；仅编写不运行。

**Acceptance Criteria:**
- Given 当前上下文、确认大纲与当前章节 Pack，when 提交生成，then 返回 202/task_id，记录各阶段并输出结构化提案和溯源，而正文版本不变。
- Given 无确认大纲、缺证、撤权、基版变化、模型故障或取消，when 阶段执行或提交，then 返回准确阻断/失败/冲突/取消状态，手工编辑仍可用。
- Given 多章节已完成提案，when 组装，then 按确认大纲核验章节和跨章节一致性，不通过单次自由文本生成。

## Implementation Notes

- 采用仅内网模型和严格逐字证据匹配；无法从普通自由文本可信地推断 Claim 支持时，显式 `BLOCKED_BY_MISSING_INFO`。未运行模型或数据库验收。
- API 限定同一提交人的当前 Pack，Worker 仅发送标识唤醒；生成前后重验 Pack 可见性、outline/context/正文和策略，用户取消清除提案。额度用保守预留且与 4.1 共用日预算。
- 离线编译/类型检查通过，测试源码未执行；数据库迁移、真实来源、模型与浏览器状态均 `not-run`。
- 复核发现通用字符串输出不满足结构化章节契约；需补齐后才可转 review。
- 结构化 `blocks/source_ref/assumptions/missing` 在保存前按 Pydantic 契约验证，输出必须逐项与当前 Pack 摘录匹配；未验证的改写阻断，避免假引用。
- 候审代码仅支持严格证据复述的章节块；这不是自由生成质量结论。所有运行案例仍 `not-run`。

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `python -m compileall -q edw-api/src edw-worker/src migrations/versions/0023_section_generation.py` — 仅静态编译。
- `npm --prefix edw-web run typecheck` — 仅类型编译。
- `git diff --check` — 无空白错误。

静态检查：上述三条命令退出码 0；测试套件、迁移、真实服务及浏览器 `not-run`。实现状态仍待核对持久任务/来源门禁，不据静态结果声称验收通过。

2026-09-29 Epic 4 跨 Story 源码核查了章节任务栅栏、当前 Pack 与只读提案路径；返修后 Python `compileall`、Web `typecheck`、`git diff --check` 退出码均为 0。未执行来源/并发运行验收，仍为 `not-run`。
