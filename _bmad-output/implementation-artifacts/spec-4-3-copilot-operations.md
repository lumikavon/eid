---
title: 'Story 4.3 Copilot 操作目录与目标契约'
type: 'feature'
created: '2026-09-28'
status: 'review'
route: 'dispatch'
baseline_commit: '6b9b20cc84220d4be3e6c5bd4cad10bbf0c4e7c3'
context:
  - '_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="来源 Epic 4 与用户批准的顺序实施范围">

## Intent

**Problem:** 缺少将 Copilot 全部操作映射至明确章节/选区的受控接口；原型按钮无法保证只读查询和写入提案的边界。

**Approach:** 建立共享目标解析与操作目录，按只读回答、Patch 提案、定位发现、结构化图形四个家族返回可审阅结果；权限、输入、来源和模型输出均失败关闭。

## Boundaries & Constraints

**Always:** 操作必须声明目标、所需输入、权限和效果；无目标、无权、失效版本或不安全模型输出明确拒绝。只读不得改变 AST；写入操作只能产生提案。保留六个原型标签，扩展项放入“更多”。

**Never:** 不让 Worker 修改文档，不让模型授予权限，不把纯模型文字当已验证事实；本轮不执行测试套件或真实运行，推进到 review 即止。

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/model_gateway/sections.py`：当前授权证据和只读提案；复用固定模型策略。
- `edw-api/src/edw_api/documents/editor_domain.py`：稳定节/块标识与 AST 校验。
- `edw-web/src/features/templates/SectionGeneration.tsx`：当前章节生成入口；继续保留原有编辑交互。
- `edw-web/src/features/templates/DomainEditor.tsx`：目标选区/章节状态。

## Tasks & Acceptance

**Execution:**
- [x] `edw-api/src/edw_api/model_gateway/copilot.py`：操作目录、目标 hash、只读/文本 Patch/发现提案；结构化图形按后续 4.5 显式阻断。
- [x] `edw-api/src/edw_api/model_gateway/copilot_routes.py`、`routes.py`、`main.py`：文档作用域持久模型运行，运行前后和最终事务重新鉴权与验证来源/输出。
- [x] `edw-web/src/features/templates/`：六按钮、“更多”及只读提案预览，正文不自动更改。
- [x] `tests/contract/test_copilot_catalog.py`：家族正反契约源码，不执行。

**Acceptance Criteria:**
- Given 当前授权目标，when 只读操作执行，then 原 AST hash 不变。
- Given 写入操作，when 执行，then 只返回 Patch/定位项/结构化提案，不更新正文。
- Given 无目标、无效输入、撤权或不安全输出，when 调用，then 命名失败且没有副作用。

## Implementation Notes

- 模型生成文字只作 `REVIEW_REQUIRED` 候审内容，引用的 `quote` 必须与当前授权 Pack 摘录逐字相符；不宣称提案中的新陈述已获事实验证。只读回答不写 AST；发现/待确认仅是定位候审项。章节和续写生成 append/insert 块 Patch，替换保留目标块 ID 与需求结构字段；只允许后续人工选择应用（4.4）。结构化图表操作在 4.3 明确阻断并返回原因，由 4.5 完成安全图形管线。
- 模型请求前后复核当前证据；最终模型结果持久化事务重查文档、目标 hash、策略、授权、Pack 完整性/版本，以及本地附件的实时来源。企业来源在外部实时复核后进入短事务，并在观察时再次实时复核，不能声称跨系统原子授权。`view_hash` 与模型输出结构、来源和目标均核对；未运行的运行时撤权/竞态案例保持 `not-run`。

## Verification

离线检查：`python -m compileall -q edw-api/src/edw_api/model_gateway tests/contract/test_copilot_catalog.py migrations/versions/0024_copilot_run.py`、`npm --prefix edw-web run typecheck`、`git diff --check` 均退出 0。测试套件、迁移、服务、浏览器、实际 Gateway 与撤权竞态运行验收保持 `not-run`。仅推进到 `review`，未进行质量门禁或独立验收。
