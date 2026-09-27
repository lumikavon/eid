---
title: 'Story 2.5 组装并确认项目上下文'
type: 'feature'
created: '2026-09-26'
status: 'in-progress'
route: 'dispatch'
baseline_commit: 'e3dceac68bb7dedcb479d00f1107b1411a1548ac'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-2-context.md'
  - '_bmad-output/planning-artifacts/epic-2-controlled-authoring.md'
---

<frozen-after-approval reason="Story 2.5 用户意图">

## Intent

**Problem:** 文档已有模板与领域 AST，但项目事实、术语、约束及缺项尚无独立、可确认的版本化上下文。

**Approach:** 提供 X-15 手工编辑/检查器、不可变上下文版本、冲突/缺项定位及人工确认；仅持久化前置条件满足时进入 `CONTEXT_READY`。

## Boundaries & Constraints

**Always:** 服务端按当前 actor/workspace/document 授权、密级、草稿状态与 base/revision CAS 检查；事实保留值、单位、来源定位、负责人及确认状态。确认固定精确版本/操作者/时间，同事务审计；撤权、冲突或未知结果不返回旧成功正文，UI 保留未提交输入。外部引用必须有当前读取权。用户决定允许零事实：必须显式确认“无项目事实”、记录确认人与时间，并解决全部必需缺项，不能静默将空上下文判为 ready。

**Never:** 不改历史 AST/DocumentVersion；不把无权、空来源或虚构事实当作已确认；不假装企业知识、附件 OCR、检索或模型已接入。不运行测试套件、服务、数据库、迁移、浏览器或现场环境；运行验收 `not-run`。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 保存与确认 | 当前授权草稿、有来源的事实，或显式声明零事实 | 新增不可变版本，显式确认后评估 ready | 必需缺项定位，不伪造 ready |
| 冲突/失权/过期 | 矛盾事实、无权来源、旧 base | 拒绝写入或确认，旧版本不变 | 结构化冲突/缺项/403 或隐藏 404；保留输入 |
| 前置失效 | 新编辑、权限或文档状态变化 | ready 按精确版本与当前授权重算 | 不由弹窗/任务/模型隐式确认 |

</frozen-after-approval>

## Code Map

- `migrations/versions/0011_template_creation.py`、`0012_domain_editor.py`、`0013_template_governance.py`：从 0013 新增前向 0014，不改旧迁移。
- `edw-api/src/edw_api/documents/editor_repository.py:16-27,82-143`：复用草稿授权/head 锁/CAS；`editor_domain.py:101-146` 不允许靠旧 AST metadata 承载上下文。
- `edw-api/src/edw_api/documents/editor_routes.py`、`main.py`：独立 context 读/保存/确认/资格路由。
- `edw-web/src/features/templates/DomainEditor.tsx`、`TemplateWorkspace.tsx`：沿既有 P-03 增加 X-15 检查器；不改既有页面视觉基准。

## Tasks & Acceptance

**Execution:**
- [ ] `migrations/versions/0014_project_context.py`、`contracts/`：上下文快照/head/确认/审计契约。
- [ ] `edw-api/src/edw_api/documents/`：授权、CAS、来源及冲突校验、确认/ready 原因、失败关闭。
- [ ] `edw-web/src/features/templates/`：事实/术语/约束/缺项编辑与显式确认；失权/未知结果安全恢复。
- [ ] `tests/security/` 与前端测试源码：覆盖正反例；仅静态/编译检查及指定 opencode 模型审查。

**Acceptance Criteria:**
- Given 当前授权草稿和合格事实，when 保存并确认精确版本，then 返回不可变版本、确认人/时间及持久化 ready 判断。
- Given 越权引用、矛盾、过期 base 或撤权，when 保存/确认，then 原版本不变、错误可定位，UI 输入不丢。

## Implementation Notes

- 新增前向 0014（上下文快照/head/不可变确认）与独立 API：当前授权/密级与来源重核、正文及上下文双 CAS、按精确版本手工确认、已记录必需缺项不得静默删除、确认审计同事务；历史上下文按当前读取权重新核验，过期版本不返回 READY。
- X-15 手工检查器记录意图、事实/单位/来源/负责人、术语、约束、缺项及显式零事实；失权/未知保存不自动重试，草稿输入留在内存。未接入企业来源或模型。
- 保留兼容的 0013 迁移；API、Worker 和部署配置的预期版本更新至 0014。无数据库迁移或运行验收执行。
- 独立源码复核发现异步历史响应可能跨授权范围回显、冲突后重新读取可能隐式采用新 base；已补 scope 代际拦截与显式采用门禁，并将 408/5xx 写响应列为未知结果。ESLint/Vite 复查通过，指定 opencode 模型只读增量审查未发现新缺陷；未做运行验证。

## Spec Change Log

## Review Triage Log

## Verification

**Commands:** Ruff/compileall、ESLint/TypeScript/Vite、JSON 语法、`git diff --check`、独立源码审查；测试套件及运行验收一律 `not-run`。

- 已执行：`python -m compileall -q`（API/Worker/0014/新增测试源码）、`python -m ruff check`（修改的 Python 源码）、`npm run lint`、`npx tsc --noEmit`、`npm run build`、JSON 解析、`git diff --check`（退出 0；Vite 报已有 bundle >500 kB 提示）。
- 已核实 opencode 模型目录：`opencode-go/muse-spark-1.3-contributor` 的显示名称为 **Muse Spark 1.3 Contributor**；已调用该模型完成源码审查，发现 JSON 语法、权限/输入恢复等问题并修复。仅源码审查，未运行测试或现场。
- 单元/契约/安全测试及真实 DB、迁移、浏览器、环境验收：`not-run`。PostgreSQL 实际锁/授予语义与 UI 交互仍需后续允许的软件验证边界下核查；不得据此声称运行通过。
- **2026-09-27 规则更新：** 测试套件仍为 `not-run`；其未执行不再阻止本 Story 的软件开发关闭。可根据源码实现、静态/编译证据与独立审查继续 step-04/05。本 Story 尚无同一断言或 Bug 经 3 次修改验证仍失败的记录，因此不触发 `FORCED_PASSED`；状态须由后续真实审查结果决定。
