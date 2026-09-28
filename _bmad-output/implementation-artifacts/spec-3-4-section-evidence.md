---
title: 'Story 3.4 章节 Evidence Pack'
type: 'feature'
created: '2026-09-28'
status: 'in-review'
route: 'dispatch'
baseline_commit: '12afe76c6c46d858100d95534229c3d20ac0ed96'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-3-context.md'
  - '_bmad-output/implementation-artifacts/spec-3-3-source-governance.md'
  - '_bmad-output/implementation-artifacts/spec-2-6-outline-confirmation.md'
  - '_bmad-output/planning-artifacts/epic-3-trustworthy-evidence.md'
---

<frozen-after-approval reason="用户批准的实施意图；变更须重新确认">

## Intent

**Problem:** 编辑器可以搜索来源，但没有基于已确认大纲精确章节的固定证据组合，也没有查询/预算/失权/不足的持久记录。单次搜索分数或 `complete=false` 不能证明关键事实已获支撑。

**Approach:** 为当前确认章节规划 3–10 条有界子查询，复用双链受权搜索及权威冲突治理，去重并持久保存不可变 Evidence Pack 与任务阶段。提交前对来源、章节、上下文和文档版本再次授权；P-05/X-15 显示来源定位、相似正式文档与明确缺口，不在证据不足或撤权时宣称支持充分。

## Boundaries & Constraints

**Always:** 请求固定 outline 的精确确认版本、稳定 section ID、文档 head、context 版本和当前 actor/workspace；没有 `OUTLINE_READY` 则拒绝。短事务外检索和重排，提交短事务再次核对版本、当前来源授权/有效期/权威/冲突；Pack 保存 query、source/version/page/chunk/原文/得分、字典/embedding/reranker 版本、策略散列、冲突/缺口/预算和不可变内容散列。超限、单链不可用、无当前支持或撤权须降低/移除结果并记录可解释不足，不把部分结果称为完整或已核证事实。任务状态持久、幂等、重试有界，受权查看实时过滤，切换选中章节清除旧片段；相似文档须真实、受权、同项目且可定位。

**Never:** 不把检索命中、置信度或旧快照当发布批准；不在本 Story 生成正文、Claim 或引用。不运行测试套件、迁移、服务、DB/MQ/S3、模型/浏览器/性能及现场实测，结果 `not-run`；前序候审接口并非已验收。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 结果 | 异常 |
|---|---|---|---|
| 已确认章节 | 3–10 子查询与授权来源 | 不可变 Pack、来源定位/版本/查询/分数和阶段 | 重复来源去重但保留版本冲突 |
| 缺少支持 | 预算耗尽、单链不可用、关键事实无来源 | 缺口明确、`insufficient`、不宣称完整 | 保留可审查的部分来源及缺失原因 |
| 提交竞态 | 检索后撤权、outline/context/document head 变更 | 不提交敏感片段或错误 READY | 返回安全阻塞/重选，原版本不改 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/documents/{outline_repository,outline_routes}.py`：确认版本、稳定章 ID 与 `OUTLINE_READY`；必须在请求和提交时核验。
- `edw-api/src/edw_api/knowledge/{routes,gateway,governance}.py`：双链检索、当前授权/版本、权威/冲突；`complete=false` 不是 Pack 支持证明。
- `migrations/versions/0018_source_governance.py`：`knowledge_dependency(kind='pack')` 可登记冲突依赖；新增 Pack 迁移不改历史。
- `edw-api/src/edw_api/tasks/{repository,routes}.py`、`task_contract.py`、`edw-worker/src/edw_worker/inventory.py`：库存专用持久任务与 fencing 模式；不能伪装已有 `parse_ocr` 或库存结果。
- `edw-web/src/features/templates/DomainEditor.tsx`、`features/knowledge/KnowledgePanel.tsx`：P-05 选章和来源栏；X-15 已有上下文/大纲，需新增真实 Pack 状态。

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0019_section_evidence.py`、`contracts/evidence-pack-v1.schema.json`：不可变 Pack/query/item/缺口、状态/任务幂等/冲突依赖与最小权限。
- [x] `edw-api/src/edw_api/knowledge/`、`task_contract.py`：确认章节与权限门禁、预算查询规划、短事务外检索、提交复核、受权 Pack/相似文档读取。
- [x] `edw-worker/src/edw_worker/`、`app.py`：有界持久任务领用、阶段/重试/失败与提交 fencing；敏感正文不进 MQ/普通日志。
- [x] `edw-web/src/features/knowledge/`、`features/templates/`：选章 Pack 请求、阶段、缺口、真实来源/相似文档及撤权清除。
- [x] `tests/security/`、`tests/contract/`、Web 测试源码：版本变动、预算、去重、撤权/权限拒绝和部分链路正反例；只编写/静态检查不执行。

**Acceptance Criteria:**
- Given 确认章节与当前受权来源，when 构建 Pack，then 持久 3–10 个子查询及有界来源/版本/locator/原文/分数/策略溯源，明确冲突和任务阶段。
- Given 缺口、超预算或检索至提交间撤权/改版，when 最终核验，then 不暴露失权片段，不把关键事实误称已支撑，长检索不占事务。

## Implementation Notes

- 固定 OUTLINE_READY 的章 ID/outline/context/document/revision/actor/policy epoch；规划确定性 3–10 查询，限定索引候选与 30 项 Pack。短事务外调用向量、企业 Gateway 与 reranker；最终短事务按来源当前授权和 fence 写不可变 Pack、查询、片段、冲突依赖。任何候选均保守标注 `insufficient`，关键事实留待后续 Claim 核证。
- Worker 只转发不含正文的任务标识，经独立 HMAC 密钥唤醒 API；API 承担受权任务领用、检索与提交。密钥缺失时只有受权轮询触发的回退执行；部署须配置唯一 32+ 字符密钥。相似文档只列可定位、同项目、当前有权、具有章关键词重合的索引记录，截断统一显式披露而不泄露未授权数量。
- 风险：企业 Gateway 当前有效性的提交竞态只能依赖短事务外新鲜签名证明；外部 ACL 变化不受本地锁保护。真实检索质量、集成、端到端任务恢复及性能均未实测。实现子代理以 WebSocket 1012 中断但已留下源码与检查记录；主代理独立复核 Python 编译、合同 JSON、Web TypeScript 与限定差异检查均退出 0。此 `in-review` 只表示候审实现，不宣称运行验收通过。

## Spec Change Log

## Review Triage Log

## Verification

源码 Python 编译/Ruff、合同 JSON 解析、Web TypeScript 类型检查与离线 Vite 构建、限定路径差异检查退出 0；Vite 仍报告既有的混合引入及大 bundle 警告。核实并使用 Muse Spark 1.3 Contributor 只读审查 API；首轮超时，第二轮指出 lease 时钟与空时间比较问题，已改为 DB clock/fence 条件并复查源码。测试套件、迁移、服务、DB/MQ/S3、模型链路/浏览器/性能与现场运行验收均 `not-run`；不作为独立验收通过。
