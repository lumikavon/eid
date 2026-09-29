---
title: 'Story 5.2 审校问题、追溯与历史检查'
type: 'feature'
created: '2026-09-29'
status: 'in-review'
route: 'dispatch'
baseline_commit: 'cddcad2c04c32a9897dc425425f24383f835758f'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 现有工作台只显示最新审校运行的八类状态，无法检查真实问题、来源追溯、版本变化和历史；用户无法据此准确处理具体 Issue。

**Approach:** 基于已持久化且绑定文档版本的审校结果构建问题列表、组合筛选、选中详情、追溯、版本比较和历史视图；统计仅使用有定义的实际分子/分母，资格和来源均按当前权限复核。

## Boundaries & Constraints

**Always:** 严重级别、章节、状态与关键词筛选按 AND 组合；切换运行、过滤条件或 Tab 后清除不再匹配的选中问题；列表、详情与计数指向同一个版本运行。历史只在当前授权下显示；来源撤权时不得泄露旧引文。未知评分与零分母标记未评估。保留四个 Tab 的信息架构。

**Never:** 不用原型中的 92/86/78 示例指标代替统计，不把审校完成或分数解释为批准/发布；不运行测试套件、迁移、服务、浏览器或外部模型。本轮只推进到 review，不做独立质量门禁。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 预期行为 | 异常处理 |
|---|---|---|---|
| 多次审校 | 同文档不同版本及多个运行 | 选择运行后问题、类别状态、追溯与版本比较一致 | 切换清除旧 Issue 详情 |
| 组合过滤 | 级别、章节、状态、关键词 | AND 筛选并显示相同集合的计数与详情 | 空集合显示明确空状态 |
| 来源/权限变化 | 旧引用撤权或当前文档改变 | 不展示受保护摘录、标记历史/失效 | 不以旧结果证明当前可审 |
| 指标缺失 | 未定义评分或分母为零 | 显示未评估与有定义的计数 | 不伪造百分比 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/review/routes.py` — 已有 history/detail、current_eligible、source_safe；扩展受控问题状态与追溯/统计时复用当前 ACL。
- `edw-api/src/edw_api/review/rules.py`、`migrations/versions/0027_review_runs.py` — Issue 类别、定位及运行版本；新增状态时保持迁移前向追加。
- `edw-api/src/edw_api/documents/editor_repository.py` — 版本历史读取约定；避免绕过当前授权。
- `edw-web/src/features/templates/ReviewStatus.tsx`、`TemplateWorkspace.tsx` — 现有运行入口及挂载；用真实运行数据扩展检查界面。
- `edw-web/src/features/knowledge/ClaimPanel.tsx` — 已有当前来源追溯入口可复用，不以历史摘录直接授权。
- `_bmad-output/planning-artifacts/epic-5-review-core-types.md` — Story 5.2 原始 AC、四 Tab 与安全边界。

## Tasks & Acceptance

**Execution:**
- [x] `edw-api/src/edw_api/review/routes.py` — 为指定运行提供有界、权限复验的 Issue 列表/详情、定位、状态、追溯、统计与版本信息；避免无权限的历史摘录。
- [x] `edw-web/src/features/templates/ReviewStatus.tsx` — 接入四 Tab、组合过滤、选中详情和真实计数/未评估状态；切换运行或过滤清除旧详情。
- [x] `tests/contract/`、`tests/security/` — 加入过滤、分母、失效/撤权及版本隔离的正反源码契约；按约定仅编译。

**Acceptance Criteria:**
- Given 多个版本固定审校运行与真实问题，when 组合过滤、切换问题或 Tab，then ID/级别/位置/引文/影响/建议/来源及当前结果计数一致，历史选中项不会串入新运行。
- Given 空结果、无可计算指标、失效运行或来源撤权，when 查看审校，then 明确空/未评估/失效/拒绝状态，不出现样例指标或受保护摘录。

## Implementation Notes

审校 Issue 均为 `OPEN`（处理决策属于 Story 5.3）；列表每页最多 100 条并提供分页。历史运行只读当前文档权限，旧版来源摘录不重放。评分和覆盖率无定义分母，显式标为未评估。

## Spec Change Log

## Review Triage Log

## Verification

源码契约仅编译；矩阵的运行行为尚未执行验证，按本轮边界留待后续验收。

**Commands:**
- `python -m compileall -q edw-api/src edw-worker/src migrations/versions tests/contract tests/security` — 语法编译成功。
- `npm --prefix edw-web run typecheck` — Web 类型检查成功。
- `git diff --check` — 补丁格式无错误。

测试套件、迁移、服务、浏览器、真实模型均记 not-run。
