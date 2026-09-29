---
title: 'Story 5.4 有来源的技术方案编制'
type: 'feature'
created: '2026-09-29'
status: 'in-review'
route: 'dispatch'
baseline_commit: '1f276ac75c3cc891d0368781172819caeecc755e'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-5-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 技术方案虽能走通通用文档编辑、证据和审校路径，但尚无文种约束保障必备章节、架构论证、项目参数和适用标准的可核查性；空泛或无依据的数字可能被误认成当前项目事实。

**Approach:** 在现有模板→上下文→确认大纲→证据 Pack→章节提案→人工接受→八类 Review 链路上加入技术方案专属的确定性结构、来源与跨章节参数检查；未证实的数值与标准保留待确认问题，不由模型补造。保留来源及模板版本出处。

## Boundaries & Constraints

**Always:** 使用固定模板的必需章节策略及已确认项目事实，章节正文和架构/性能 Claim 必须有当前授权的精确证据；参数跨章冲突定位到区块并列出依据。标准编号只有当前适用来源才能标记已核验；缺少权威资料时输出未确认。保持通用编辑和 Patch 路径及来源权限复验，真实模型/企业效果与本地规则分开记录。

**Never:** 不生成虚构指标、标准号、企业批准模板或来源；不因本地规则通过称作正式技术评审通过。不运行测试套件、迁移、服务、浏览器或外部模型；本轮只到 `review`，不做独立质量门禁。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 预期 | 错误处理 |
|---|---|---|---|
| 完整方案 | 版本模板、确认上下文、授权来源 | 各必需章节与架构/参数 Claim 可定位复核 | 待确认信息不伪造 |
| 章节缺失 | 必需模板章节/结构被省略 | 高级别定位问题 | 不声称完整 |
| 参数/标准无依据 | 性能数字或标准仅在正文出现 | 标记待确认或严重缺口并定位 | 不把通用案例当项目事实 |
| 来源过期 | Pack/引用不再有效或撤权 | Review 不认证当前版本 | 保护历史引文 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/documents/{domain,outline_repository,editor_domain}.py` — 文种、固定模板必需章节、大纲与 AST；复用现有确认与 CAS。
- `edw-api/src/edw_api/model_gateway/{sections,patch_routes}.py` — 来源精确复述与受控 Patch；不修改为直接生成可信项目数值。
- `edw-api/src/edw_api/review/{rules,routes}.py` — 八类版本规则、当前引用/上下文复核与问题定位；在此增加文种规则和固定输入。
- `edw-web/src/features/templates/{TemplateWorkspace,DomainEditor,ReviewStatus}.tsx` — 共通创建、编辑、确认及审校入口；提供类型提示与真实待确认项。
- `tests/contract/`、`tests/security/` — 结构、数值、标准、来源及不越权的源码契约。

## Tasks & Acceptance

**Execution:**
- [x] `edw-api/src/edw_api/review/rules.py` — 为 `technical_solution` 增加必需章节、架构/参数/标准有来源的文种规则、跨章节冲突与稳定定位；严格区分模式提示与真实标准核验。
- [x] `edw-api/src/edw_api/review/routes.py` — 把模板政策、确认项目上下文与当前引用绑定到审校固定输入；来源失效维持不认证。
- [x] `edw-web/src/features/templates/` — 在通用工作台明确技术方案流程和未证实参数/来源的审校位置与待确认状态。
- [x] `tests/contract/`、`tests/security/` — 添加矩阵正反源码契约；仅编译。

**Acceptance Criteria:**
- Given 版本模板、确认事实和适用来源，when 作者经大纲、证据、生成、接受及审校完成技术方案，then 必需章节存在、架构与参数 Claim 可追溯，跨章检查有稳定问题定位。
- Given 缺章、旧来源、未经支持的性能数值或未知标准，when Review 运行，then 严重/待确认项继续展示，不能凭模型或历史范例填充当前项目数字。

## Implementation Notes

- 固定模板政策沿用版本化大纲策略；正文检查仅对 `technical_solution` 增强，规则版本为 `local-review-3`。来源精确复述以当前授权的附件引文为界，不以标准编号正则推断适用性。
- 架构与参数发现是有界本地规则；非结构化表格、自然语言同义参数和标准版本权威性仍需人工核查。

## Spec Change Log

## Review Triage Log

## Verification

静态检查通过；契约文件已编译，测试套件未运行。

**Commands:**
- `python -m compileall -q edw-api/src edw-worker/src migrations/versions tests/contract tests/security` — 编译成功。
- `npm --prefix edw-web run typecheck` — 类型检查成功。
- `git diff --check` — 格式无误。

测试、迁移、服务、浏览器、真实模型与企业标准核验记 `not-run`。
