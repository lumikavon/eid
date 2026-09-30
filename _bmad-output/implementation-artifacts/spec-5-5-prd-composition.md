---
title: 'Story 5.5 结构完整的 PRD 编制'
type: 'feature'
created: '2026-09-29'
status: 'in-review'
route: 'dispatch'
baseline_commit: 'c58df95'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-5-context.md'
  - '_bmad-output/planning-artifacts/epic-5-review-core-types.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前通用 `requirement` 区块仅校验需求编号、陈述、验证方式和来源 ID，不能保证 PRD 的角色、场景、前置条件、正常/异常流程、业务规则、输入输出、权限、NFR 与验收条件以可定位字段保存。叙述性摘要不能替代结构化需求，重复编号或缺项也不能可靠地呈现在 Review 中。

**Approach:** 沿现有 PRD 固定模板→项目上下文→大纲确认→授权 Evidence Pack→章节提案→人工接受→版本审校路径，为 PRD 的 `requirement` 区块增加版本化结构化字段和保存校验、稳定 FR-ID/区块定位与来源关联，并在八类 Review 中定位重复编号、空缺字段及无效来源；Web 编辑器提供字段录入、缺项提示和问题定位。保留旧版本合法数据，未经授权的引用不被视作有效证据。

## Boundaries & Constraints

**Always:** PRD 需求字段包含 FR-ID、名称、角色、场景、前置条件、正常流程、异常流程、规则、输入、输出、权限、NFR、验收条件；持久化保留 section/block/source 定位。保存路径维持原有 AST/CAS、版本、权限和引用保护；Review 必须以当前固定版本及当前授权来源检查，不把正文段落冒充结构字段。对现存非 PRD 文种与历史合法区块保持兼容；缺项时保留已录入值并返回字段级、区块级问题，不用模板或模型臆补。

**Never:** 不由本地规则声明产品质量、批准或可发布；不以推测的来源或虚构 FR-ID 补全数据。不运行测试套件、迁移、服务、浏览器、外部模型或真实环境验收；只做源码/静态检查及离线编译，本轮推进到 `review`，不做独立质量门禁。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 预期 | 错误处理 |
|---|---|---|---|
| 完整需求 | PRD 版本模板、已确认上下文、当前授权引用及完整结构字段 | 需求和编号稳定持久化，字段与来源可按章节/区块复核 | 不等同于正式审批 |
| 字段缺失 | 异常流程、权限或验收条件为空，或仅写在普通正文 | 指出确切字段与需求区块；已有值原样保留 | 不用叙述性摘要抵消缺项 |
| 编号冲突 | 两个需求使用同一 FR-ID 或缺失编号 | 定位全部冲突区块及缺编号字段 | 不自动重编号导致引用漂移 |
| 来源变更 | 引用撤权、版本过期、来源与当前区块不匹配 | 当前审校不认证支持状态，保留历史记录 | 不泄露已撤权内容 |
| 旧文档 | 既有通用 requirement/其他文种 | 仍可读取和按既有规则编辑；PRD 缺字段明确提示 | 不破坏旧版本或静默丢字段 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/documents/editor_domain.py` — AST `requirement` 结构校验、版本与未知字段兼容。
- `edw-api/src/edw_api/documents/` — 需求投影/版本保存及模板文种路径；确认实际持久化和 source_refs 的语义后选定最小改动。
- `edw-api/src/edw_api/review/{rules,routes}.py` — 固定输入、PRD 字段/编号/来源检查和精确定位。
- `edw-web/src/features/templates/` — 需求字段编辑与 Review 导航，沿用现有编辑/生成/接受流程。
- `tests/contract/`、`tests/security/` — 正反例源码契约，仅编译不运行。

## Tasks & Acceptance

**Execution:**
- [x] 定义并校验 PRD requirement 字段，保持稳定标识、来源及现有版本化保存语义。
- [x] 接入当前模板/上下文/来源的 PRD 文种审校，报告缺失、重复与过期/无权来源。
- [x] 在现有编辑器暴露结构化录入、字段缺项和精确问题定位，不破坏既有界面主层级。
- [x] 编写契约与安全用例源码；仅运行允许的编译、typecheck、diff 检查。

**Acceptance Criteria:**
- Given PRD 模板、上下文和授权来源，when 作者创建、接受、保存并审校结构化需求，then 所有约定字段、稳定 FR-ID、章节/区块和来源引用被持久化且可复核。
- Given 重复/缺失编号、异常/权限/验收缺项或撤权来源，when 保存或 Review，then 精确报告缺陷、保留此前合法输入，普通段落不能抵充需求字段。

## Spec Change Log

- 初步实现结构化字段编辑、保存校验和审校定位；发现现有引用命令仅支持正文选区，`requirement.source_refs` 缺少受控的当前版本来源绑定路径。不能把该字段的手填 ID 或旧版本引用认作已授权证据。该项尚未满足验收。
- 后续补充了 `prd_requirement` Claim 的当前版本候选、受控引用命令及编辑器来源入口；API 在事务前后复核 Pack/项目权限/版本/冲突，原子写入文档版本及对应引用记录。普通编辑不能添加或替换引用 ID；陈述等正文修改继续沿用版本化保存，再次编辑产生新版本时旧引用不再认证，须通过受控命令重新绑定。历史合法需求编号与最长 2048 字陈述可在普通修改时保留，旧编号由 Review 报告，不使旧文档无法编辑。
- 此来源绑定只覆盖受控附件，且要求当前 Pack 的精确陈述。无可核验来源时仍保持高优先级待确认；不声称企业来源或历史来源已验证。

## Review Triage Log

- 静态核对：受控来源写入与 `save_document` 同事务，当前 Pack、附件原文、冲突、Claim/章节/区块、文档头及编辑权在提交前复核。普通保存拒绝伪造引用；旧版本引用经版本失效处理，不认证当前需求。
- 用户明确要求本轮推进至 `review`；按已批准的静态验证政策登记 `in-review`，不将未执行的矩阵测试视为通过，也不声明独立质量门禁或运行验收完成。

## Verification

`python -m compileall -q edw-api/src edw-worker/src migrations/versions tests/contract tests/security`、`npm --prefix edw-web run typecheck`、`git diff --check` 通过。矩阵测试源码尚未运行，因此不得按 workflow 的矩阵测试门禁宣称验收完成。测试、迁移、服务、浏览器、外部模型与运行验收均 `not-run`。
