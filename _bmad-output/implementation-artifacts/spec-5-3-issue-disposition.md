---
title: 'Story 5.3 审校问题的人工处置'
type: 'feature'
created: '2026-09-29'
status: 'in-review'
route: 'dispatch'
baseline_commit: 'a6c57fcc3294e4dfa3d6edfda84eb7a87a7cf69a'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前审校问题只能查看，缺少可审计的人工决议；将拒绝或标记已处理误当问题修复，会掩盖严重事实与安全缺陷。

**Approach:** 为固定审校运行的问题增加接受、拒绝、修改、已处理四种独立处置：接受仅关联经过现有 Patch 校验后产生的新版本，拒绝保留理由和未解决状态，修改定位到真实块，已处理要求当前版本的重新核验；决议与运行版本、操作者和审计关联。

## Boundaries & Constraints

**Always:** 决议操作复核 `document:review`、当前文档版本、问题归属、幂等请求与当前来源；正文改变后旧结果失效，必须重新审校。接受复用现有 `ai-patches/decisions` 的作者授权及证据/策略检查，不允许 Reviewer 直接改正文。严重未解决问题保持阻断；无配置的豁免权限默认拒绝，安全/发布硬门禁不可豁免。所有行动保留审计证据。

**Never:** 不把接受等同于自动应用任意模型建议；不把拒绝、定位修改或已处理等同修复；不添加未经配置的豁免角色或虚构批准状态。不执行测试套件、迁移、服务、浏览器和真实模型；本轮只到 `review`，不做独立质量门禁。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 期望 | 拒绝条件 |
|---|---|---|---|
| 接受 | 当前问题、所选合法 Patch | 复用现有决议并记录新版本，待重审 | Patch 不匹配、撤权、旧版本 |
| 拒绝 | 当前问题和非空理由 | 保留理由、问题仍待解决 | 无理由或把严重问题消隐 |
| 修改 | 当前块定位 | 打开精确块编辑，保存后要求重审 | 位置已失效或无编辑权 |
| 已处理 | 当前问题及独立重审结果 | 验证相应缺陷不再出现后记录关闭 | 未重审、同一缺陷仍存在 |
| 豁免 | 无配置或不可豁免问题 | 维持阻断并提示权限/规则 | 任何绕过安全或批准门禁的尝试 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/review/routes.py` — 运行、问题、当前资格和来源复核；增加幂等决议与受控状态投影。
- `edw-api/src/edw_api/model_gateway/patch_routes.py` — `Decision`、`selected`、`persist_decision` 现有 Patch 复核/应用；勿复制为 Reviewer 直写。
- `migrations/versions/0027_review_runs.py` — 问题及运行表；新增 0028 前向迁移保存不可变处置、修复证据与审计。
- `edw-web/src/features/templates/ReviewStatus.tsx`、`DomainEditor.tsx` — 四操作 UI、选中问题与真实块导航；草稿保存沿用 Editor。
- `tests/contract/`、`tests/security/` — 处置状态、幂等、严重阻断、撤权及旧版本契约源码。

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0028_review_dispositions.py` — 增加版本固定、不可变的审校问题处置/修复证据表及最小 API 权限。
- [x] `edw-api/src/edw_api/review/` — 实现四种不同决议、严格归属/权限/版本/幂等校验、重审确认和决议审计；把实际状态映射到检查 API。
- [x] `edw-web/src/features/templates/ReviewStatus.tsx`、`DomainEditor.tsx` — 四操作及理由输入、精确块定位、重新检查提示；旧选中状态清除。
- [x] `tests/contract/`、`tests/security/` — 编写矩阵正反契约源码；本轮仅编译。

**Acceptance Criteria:**
- Given 当前授权问题，when 分别接受、拒绝、修改或已处理，then 接受经过 Patch 检查、拒绝记录理由且不修改正文、修改指向确切块、已处理需要后续有效重审；每步可审计。
- Given 严重未支持事实、旧审校、撤权或未配置豁免，when 尝试关闭、豁免或错误接受，then 问题仍阻断并拒绝状态伪造；新正文需新审校。

## Implementation Notes

- `review_disposition` 仅插入，按问题最多一项初次决议与一项后续 `handled` 关闭；关闭必须以当前版本的独立完整重审证明相同定位/规则缺陷消失。拒绝及待重审仍计作阻断。
- 接受在提交事务中调用现有 `persist_decision`，以原 Patch 的作者权限、证据和策略复核生成新版本；UI 只提交选定 Patch 运行 ID。
- 修改仅持久化当前块定位并导航编辑器，正文由原有保存流程提交。
- 静态核对修复了新增迁移的 schema revision 配置，以及接受 Patch 后 `PENDING_RECHECK` 问题的“已处理”入口；缺少重审版本证据的状态仍保持阻断。

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `python -m compileall -q edw-api/src edw-worker/src migrations/versions tests/contract tests/security` — 语法编译成功。
- `npm --prefix edw-web run typecheck` — Web 类型检查成功。
- `git diff --check` — 补丁格式无误。

结果：上述三项命令成功；契约/安全用例仅完成源码编译，未运行。`git diff --check` 只有 Git 工作树 LF/CRLF 提示，没有格式错误。

测试、迁移、服务、浏览器和真实模型记 `not-run`。
