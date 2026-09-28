---
title: 'Epic 3 候审发现修复'
type: 'bugfix'
created: '2026-09-28'
status: 'review'
route: 'dispatch'
baseline_commit: '4a8111bebfc2dbde659127e48992db07f1a3b8c2'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-3-context.md'
  - '_bmad-output/planning-artifacts/development-validation-policy.md'
---

<frozen-after-approval reason="用户批准的修复意图；变更须重新确认">

## Intent

**Problem:** 已提交的 Epic 3 候审实现存在迁移头不一致、附件任务积压失效、授权/过期竞态、Pack 索引与治理显示漂移、Claim 判定及引用追溯失效等可复现缺陷；验证源码无法覆盖关键失效路径。

**Approach:** 逐项核验三类审查发现，修复真实问题并补足对应确定性测试源码，误报须说明证据；保留 3.1–3.5 的 `review` 状态，不将运行验收视为完成。

## Boundaries & Constraints

**Always:** 保持 Pack 旧快照与实时授权视图分离；企业来源仅以新鲜外部签名证明+本地当前策略共同放行，撤权或冲突降级而不伪称支持。长任务须 fence/续租，附件过期委托不应使仍受权任务永久阻塞；历史 Claim/citation 可追溯但不能成为现时授权。保持用户已删除文件及四个工作树不变。需改 DB 时只新增前进迁移，不运行迁移。

**Never:** 不用历史令牌、宽松权限或测试替身规避撤权；不运行测试套件、服务、数据库、迁移、浏览器、真实模型或现场部署。源码编译与静态检查仅说明可构建，不能证明质量通过。

**批准决策：** OCR 权重采用构建时可选注入与缺失自检；未提供可信 det/rec 权重时明确 `OCR_UNAVAILABLE`，不宣称真实 OCR 已修复。附件隔离区使用独立 SeaweedFS 桶及清理身份最小权限。用户选择保留完整 Epic 3 发现修复规格，即使超过建议 token 范围。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 预期结果 | 异常 |
|---|---|---|---|
| 延迟附件解析 | 委托时效过后，操作者当前仍有权 | 当前策略重核并正常领用 | 真撤权仍 BLOCKED |
| Pack/搜索回读 | 早序片段撤权、治理更新、单个推荐失败 | 精确 ordinal、实时治理及继续轮询 | 旧摘录清空、Pack 原始散列不冒充展示散列 |
| Claim/引用 | 多链接、冲突、引用后新版本 | 不因背景链接抹掉支持，冲突待复核，当前版本可追溯 | 失权、过期或换版不暴露来源 |

</frozen-after-approval>

## Code Map

- `deployment/{compose.yaml,python.Dockerfile,seaweedfs/s3.json}`、`edw-api/src/edw_api/config.py`：迁移头、OCR 资产、S3 身份与桶配置。
- `migrations/versions/0016_safe_attachments.py`、`edw-worker/src/edw_worker/attachments.py`：委托过期当前策略、worker 领用/完成；用新迁移覆盖函数。
- `edw-api/src/edw_api/knowledge/{governance,routes,gateway,evidence,evidence_routes}.py`：适用范围/到期、外部最终证明、Pack 可见项和续租。
- `edw-api/src/edw_api/documents/{claim_routes,claims,editor_repository}.py`、`edw-web/src/features/knowledge/{EvidencePanel,claim-api,evidence-api}.tsx`：多链接与新版本引用追溯、稳定 ordinal 与独立 job 请求。
- `tests/{security,contract,worker}/`、`edw-web/src/features/knowledge/*.test.ts`：可执行边界用例源码；既有静态字符串断言不能替代路径验证。

## Tasks & Acceptance

**Execution:**
- [x] `deployment/compose.yaml`、`edw-api/src/edw_api/config.py` 与新迁移：统一需要的 schema head，恢复积压任务授权；按 OCR/桶选择调整部署源码。
- [x] `knowledge/{governance,routes,evidence,evidence_routes}.py`：来源实时性、fence/lease、视图治理/序号/散列。
- [x] `documents/claim_routes.py`、`features/knowledge/{EvidencePanel,ClaimPanel}.tsx`：多链接保守判定、冲突引用门禁、引用后可追溯与可恢复 job。
- [x] `tests/contract/`、`tests/security/`、Web 测试源码：授权拒绝、错序、过期、冲突、换版、部分失败的确定性断言；仅静态检查，未执行用例。

**Acceptance Criteria:**
- Given Epic 3 所需最新迁移，when 检查配置，then API/Worker/deploy 一致；附件延迟不因旧委托时效永久 BLOCKED，真正撤权仍拒绝。
- Given 撤权、过期、治理变化或外部延时，when 搜索/Pack/Claim 回读，then 不泄露旧片段、不错绑证据且可辨历史散列与当前视图。
- Given 引用已写入新版本，when 选择当前 Claim/引用追溯，then 当前权限允许时显示精确来源，否则清空并标待复核；相似文档失败不丢失 Pack 任务。

## Implementation Notes

- 新增前进迁移 `0021_epic3_remediation`，API/Worker/deploy 统一指向该头。旧委托到期不再独自阻止解析；显式 `g.active=false` 撤销仍阻断。新附件写隔离桶，已有附件保留原桶标记并用现有只读 worker 身份访问；仅新隔离桶可被最小权限清理身份删除。
- OCR 资产由可信离线 det/rec 目录按需注入；无权重时显式 `OCR_UNAVAILABLE`，不下载或冒充识别成功。模型真实性、完整性和实际识别效果尚未验证。
- Pack 的不可变 `snapshot_hash` 与实时 `view_hash` 分开，显示来源重核授权、适用治理、稳定 ordinal；任务使用续租与 fence，`/similar` 局部失败不抹去 Pack job。
- Claim 列表中历史 supported/partially_supported/conflicting 均显示 `unknown`/待复核；追溯在当前策略下重验，历史 citation 与当前 Claim 仅在所选 statement/value/conditions 匹配时关联，历史链接只可追溯而不能重复引用。引用所选手工 Claim 随版本推进以 unknown 保留。

## Spec Change Log

- 2026-09-28：按已批准范围完成候审修复并编写可执行回归用例源码；静态检查后本规格状态设为 `review`，并非运行验收。
- 提交前用户明确选择将 `sprint-status.yaml` 中 Epic 3 及 3.1–3.5 标为 `done`；这仅记录状态选择，不改变测试/迁移/现场验收 `not-run` 的事实，Story 规格仍为 `review`。

## Review Triage Log

| 审查发现 | 处置 | 尚待验证 |
|---|---|---|
| 迁移头 0019/0020 不一致、延迟附件误 BLOCKED、隔离桶及 OCR 可用性 | 0021 统一头/当前策略重核；显式撤销仍阻断；隔离桶与旧桶只读兼容；缺权重返回 `OCR_UNAVAILABLE` | 迁移/存储权限与真 OCR 均未运行 |
| Pack 租约竞争、过滤后错绑 ordinal、旧快照泄露/治理或散列冒充 | 续租与 fence；按原 ordinal 精确绑定；按当前授权/适用治理重绘，原始与展示散列分离 | 数据库并发与撤权时序未运行 |
| 企业授权/过期竞态、其他范围断言误抑制来源 | 提交响应前重核本地策略/外部证明及有效期；治理仅同范围断言可压制；新增签名网关拒绝路径用例 | 外部 ACL 与本地提交间竞态不能事务化，需现场验证 |
| 多链接判定、冲突降级、引用推进版本后不可追溯 | 保守状态、冲突门禁、当前策略追溯；所选手工 Claim 跨引用版本保留且历史链接不可重复引用 | 真实编辑器/数据库路径未运行 |
| `/similar` 失败丢失 Pack job、轮询断线 | 请求隔离与会话恢复；补充失败/重试源码 | 浏览器交互未运行 |
| 部分旧测试仅断言字符串，缺治理视图和网关拒绝路径 | 增加 `visible()`、错范围治理、签名 `retrieve()` 拒绝、Claim 追溯及 OCR 缺权重源码 | 所有测试仍按约定 `not-run`，新增用例执行结果未知 |

无审查发现判为误报。独立 P-08/P-09 页面仍缺失，保留单独待办 #7；本规格仅修复现有知识侧栏的 Claim/追溯路径。旧桶在切换前可能留下历史孤儿对象，新清理身份不可删除旧桶对象，需在受控环境单独盘点与处置，不能临时扩大清理权限。

## Verification

- 已独立执行并通过：Python `compileall`（API、Worker、迁移、脚本及测试源码）、Ruff、四个 JSON 解析、Web `tsc -b` 与 `vite build`、`git diff --check`。首次独立 TypeScript 检查发现 `EvidencePanel.tsx` 的 UUID 推断类型错误，明确标注 `requestKey: string` 后重检通过。Web 构建有动态/静态混合导入及 500 kB chunk 告警，未导致失败。
- `not-run`：测试套件、Alembic 迁移、数据库/服务、SeaweedFS 桶与 IAM、浏览器、真实 OCR/企业网关及现场验收。静态通过不等于运行验收；Story 规格仍为 `review`，sprint 状态按用户提交前选择为 `done`，不能解读为验收通过。
