---
title: 'Story 3.5 可核查 Claim 与精准引用'
type: 'feature'
created: '2026-09-28'
status: 'in-review'
route: 'dispatch'
baseline_commit: '12afe76c6c46d858100d95534229c3d20ac0ed96'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-3-context.md'
  - '_bmad-output/implementation-artifacts/spec-3-4-section-evidence.md'
  - '_bmad-output/implementation-artifacts/spec-2-3-version-conflicts.md'
  - '_bmad-output/planning-artifacts/epic-3-trustworthy-evidence.md'
---

<frozen-after-approval reason="用户批准的实施意图；变更须重新确认">

## Intent

**Problem:** Pack 只有候选来源，AST 的 Claim/citation 数组缺少支持语义和当前授权约束；编辑器没有固定真实选区，无法保证引用落在所选陈述而非首段或过期位置。

**Approach:** 为可核查 Claim 建立类型/条件/数值/单位/稳定块与选区位置，绑定零个或多个精确来源及 supports/conflicts/contextual 关系，标出未支撑、冲突与待确认；提供受控引用命令，按当前版本、书签、原文和来源授权校验后在选区准确位置原子生成新文档版本。P-05/P-08/P-09 来源追溯随当前 Claim 或问题切换，失权立即清空受控摘录。

## Boundaries & Constraints

**Always:** 类型覆盖数字、百分比、性能、容量、时间、日期、型号、标准、法规、能力、验收阈值、客户/项目名称、版本及声明的未知类型；保存条件、值/单位、版本、位置，状态为 supported/partially_supported/conflicting/unsupported/unknown，链接关系为 supports/conflicts/contextual。关键 Claim 缺有效依据必须定位并待确认/待复核；置信度与链接数量不证明事实。来源绑定到当前授权的 Pack 精确版本/chunk/引用原文，历史快照不能授权。插入引用先捕获真实 AST 块 ID、选区偏移/文本与基础文档版本，确认时重验编辑权限、source、选区、base revision 和支持原文；任何失效都保留正文且要求重选，绝不追加首段。变更后标记相关 Claim/Review 待复核，旧 outline/Pack 资格按正文新版本失效但保留溯源。

**Never:** 不把确定性抽取或本地支持分类称为真实模型精度，不自动批准发布；不借客户端引用数组绕过服务端受控命令。不启动测试套件、迁移、数据库、服务、浏览器、真实模型或现场运行，均 `not-run`。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 结果 | 异常 |
|---|---|---|---|
| Claim 绑定 | 有类型、条件和零/多精确证据 | 关系、位置、五态与关键缺口持久 | 未知类型保留原值；冲突不伪报支持 |
| 精准引用 | 当前选区/基础版本/受权来源 | 在选区写入引用并产生新文档版本 | 选区/原文/权限过期则拒绝且正文不变 |
| 追溯切换 | Claim/问题 A 后选择 B 或撤权 | 只展示 B 当前授权的精确原文/版本 | 旧缓存/快照不可重新授权 |

</frozen-after-approval>

## Code Map

- `migrations/versions/0019_section_evidence.py`、`edw-api/src/edw_api/knowledge/evidence.py`：Pack 候选、版本与受权读取；`insufficient` 不证明 Claim 支持。
- `edw-api/src/edw_api/knowledge/governance.py`、`migrations/versions/0018_source_governance.py`：当前来源重验及 `knowledge_dependency(kind='claim')`。
- `edw-api/src/edw_api/documents/{editor_routes,editor_repository,editor_domain,schemas}.py`：AST 与 base/revision CAS；现有 citations/claims 只验证 ID，需专用命令。
- `edw-web/src/features/templates/DomainEditor.tsx`、`domain-adapter.ts`、`domain-merge.ts`：Tiptap 选区、块 ID 与合并；引用不能继续视为尾部独立块。
- `edw-web/src/features/knowledge/EvidencePanel.tsx`、`KnowledgePanel.tsx`：当前按章节展示，需 Claim/问题切换与来源清除。

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0020_claim_citation.py`、`contracts/claim-citation-v1.schema.json`：版本化 Claim/关系/引用/待复核记录与最小权限。
- [x] `edw-api/src/edw_api/knowledge/`、`documents/`：确定性 Claim 抽取与五态支持判定、受权 Pack 绑定、引用位置与原文/版本/当前权限/CAS 原子操作。
- [x] `edw-web/src/features/templates/`、`features/knowledge/`：固定真实选区、引用确认/冲突重选、Claim 跟随追溯及撤权清空。
- [x] `tests/security/`、`tests/contract/`、Web 测试源码：类型/关系/往返、陈旧书签、选区文本变化、撤权、精确位置、跨 Claim 切换正反例；仅编写/静态检查。

**Acceptance Criteria:**
- Given 各类可核查 Claim，when 提取/绑定，then 持久其条件/值/单位/版本/位置、零或多关系与五态；关键不支持或冲突有可定位待确认项，未知类型不丢失。
- Given 当前编辑选区与有权精确来源，when 插入引用，then 准确落在该选区并生成正确文档版本；陈旧书签/base、撤权或引用原文改变时不改正文，要求重新选择。
- Given 先选 A 再选 B 或来源撤权，when 打开追溯，then 只显示 B 当前授权的原文/版本；旧快照和置信度不授予支持。

## Implementation Notes

- `0020_claim_citation` 持久化版本化 Claim、关系、精确选区引用；服务端保持当前 head/revision CAS、Pack 精确项/原文、短事务外企业来源证明及提交时本地授权复核。受控引用保存为 AST 选区尾部内联标记与新文档版本；旧版 Claim/引用保留溯源并标待复核，新版候选重新提取。列举 Claim 不把历史正向状态呈现为当前支持；选中追溯须再核当前来源。确定性匹配仍非事实审定。
- Web 捕获真实 Tiptap 同块选区和服务端版本，变更、切章、保存、冲突与撤权清空旧书签/摘录。P-08/P-09 尚无独立页面可接线：当前仅在知识侧栏提供 Claim/问题选择和追溯，独立视图保留后续 UX 工作，不宣称其已交付。
- 企业 Gateway 从外部获取证明到数据库提交之间的 ACL 竞态无法通过本地锁完全消除；真实质量/人审精度、浏览器交互、迁移与现场恢复未验证。

## Spec Change Log

## Review Triage Log

## Verification

Python 编译、Ruff、合同 JSON 解析、Web TypeScript/离线构建与限定路径差异检查均退出 0；主代理修复了历史正向状态直接显示及引用对逐字匹配的过度限制后，再次通过源码编译、Ruff、合同 JSON、Web TypeScript 与限定差异检查。Muse Spark 1.3 Contributor 已辅助只读审查，发现问题已由实现子代理处理。测试套件、迁移、数据库/服务、浏览器和真实模型/用户验收均 `not-run`，不做独立质量门禁。
