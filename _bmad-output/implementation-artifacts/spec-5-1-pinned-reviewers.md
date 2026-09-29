---
title: 'Story 5.1 八类版本固定审校'
type: 'feature'
created: '2026-09-29'
status: 'review'
baseline_commit: 'bcf3eb2d1ab9bbf68583b2287c1b42901510053f'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前文档工作台没有真实的八类 Reviewer 执行、持久化结果与版本固定的审校状态；旧结果或缺失结果不能证明当前正文可审。

**Approach:** 将审校绑定不可变文档版本、模板和规则/模型版本，复用持久化任务及 Worker 隔离执行路径；记录每一类结果和可定位 Issue，让重新审校创建新任务，当前权限/版本变化或必需审校失败时明确失效。

## Boundaries & Constraints

**Always:** 八类为结构、事实、需求、技术、质量、一致性、风格、安全；API 持有状态和权限判定，Worker 仅写受限候审结果；每条问题保留文档/章节/块/Claim/来源、引文、影响、建议、规则和模型出处；确定性规则和标记为 double 的模型检查分别记录，不把局部规则的成功当真实模型质量。

**Never:** 不把 Task 完成等同审校完成或正式发布；不因失败、撤权、正文更新而复用旧认证；不运行测试套件、真实服务/数据库、浏览器或外部模型；本轮到 `review` 即止，不执行独立质量门禁。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 预期行为 | 异常处理 |
|---|---|---|---|
| 初次审校及重跑 | 当前文档版本、八类规则固定集 | 返回新的 202 任务；分别保存八类结果与有出处的定位问题，只有必需项成功才完成 | 重复请求遵循幂等键，同版本重跑保留历史 |
| 注入可定位缺陷 | 数字矛盾、残留名称、旧引用、缺章/缺需求、模糊阈值、术语差异、无依据关键事实、错误标准号 | 相应确定性检查产出明确位置；没有可靠判断的模型项标注未评估 | 不虚报 FP/FN 或真实模型召回率 |
| 异步变更 | 运行中修改文档、撤销授权、来源失效、规则失败 | 结果留作历史但不认证当前版本 | 暴露 stale/failed/denied；草稿编辑仍可用 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/main.py` — 路由注册、错误包装；注册 Review 路由，不修改通用请求上下文。
- `edw-api/src/edw_api/documents/{domain,repository,editor_domain}.py` — 文档/模板版本与领域 AST；复用稳定定位和版本 CAS，不以浏览器 DOM 为输入。
- `edw-api/src/edw_api/model_gateway/{sections,copilot,patches}.py` — 已有任务、提案和来源再验证约定；审校不得直接应用 Patch。
- `edw-api/src/edw_api/tasks/{routes,repository}.py` — 202 任务与状态观察，沿用持久化和幂等约定。
- `edw-worker/src/edw_worker/{app,model_wake,task_store}.py` — review 专用队列及 worker 领取/受限提交模式；不能提升 worker 为文档写者。
- `migrations/versions/` — 增量 schema 与 DB 函数/最小权限；新持久化对象不可覆盖旧迁移。
- `edw-web/src/features/templates/TemplateWorkspace.tsx` — 文档入口，后续 5.2 完善详情界面；此 Story 展示真实启动和八类状态。

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/` — 新增审校运行、分类结果、定位问题的版本固定输入/审计存储及受限 Worker 函数；确保 API 是决议所有者。
- [x] `edw-api/src/edw_api/review/` — 定义严格输入/结果契约、审校发起/重跑、读取与当前版本资格判断，按当前授权和幂等键拒绝错误目标。
- [x] `edw-worker/src/edw_worker/` — 接入 review 队列与八类规则，产出定位结果并显式记录未评估/失败；完成提交复验版本、权限及任务 fence。
- [x] `edw-web/src/features/templates/` — 提供当前文档的 Review 启动/重跑入口和独立八类状态，失效/不可用明确呈现。
- [x] `tests/contract/`、`tests/security/` — 增加八类及缺陷定位、旧版本/撤权/失败等正反契约源码，当前仅作静态/编译验证。

**Acceptance Criteria:**
- Given 文档版本和固定规则集，when 首次或重新审校，then 返回 202，分别记录八类检查状态/版本和定位结果，必需项完成前不标识完整。
- Given 编辑、撤权或必需检查失败，when Worker 提交及资格读取，then 拒绝把旧审校标为当前认证，历史可在当前权限下查看且草稿仍可编辑。

## Implementation Notes

- 已加入 Review 数据表、版本固定 API、review 队列通知、工作台状态入口和源码级契约样例；Worker 仅通知 API 受权执行，不具有 Review 表写权限。
- 八类固定 `local-review-2` 有界确定性检查分别记录 `execution_kind=deterministic`、`model_version=none`；涵盖缺章/需求、模糊阈值、数字冲突、名称残留、术语差异、无支持关键 Claim、来源需复核与标准编号提示等定位问题。真实模型召回率和错误标准号真实性均未由本地模式规则证明。
- Review 固定正文、模板、规则及输入摘要；API 在提交前按 fence、当前权限、正文、模板、Claim/上下文/引用和来源重新核验。来源需复核时事实类标记 `UNEVALUATED`，运行失败且不取得当前资格。Worker 仅发送标识通知，无 Review 表读写权限。
- Python compileall、Web typecheck 与 `git diff --check` 已通过；测试套件、迁移、服务、浏览器及真实模型验收 `not-run`。质量门禁未执行。

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `python -m compileall -q edw-api/src edw-worker/src migrations/versions tests/contract tests/security` — 仅语法编译通过。
- `npm --prefix edw-web run typecheck` — 类型检查通过。
- `git diff --check` — 补丁格式无错误。

测试套件、迁移和运行验收记为 `not-run`；不进行独立质量门禁。
