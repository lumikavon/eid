---
title: 'Story 3.3 来源权威、时效与冲突治理'
type: 'feature'
created: '2026-09-28'
status: 'in-review'
route: 'dispatch'
baseline_commit: '12afe76c6c46d858100d95534229c3d20ac0ed96'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-3-context.md'
  - '_bmad-output/implementation-artifacts/spec-3-2-authorized-retrieval.md'
  - '_bmad-output/planning-artifacts/epic-3-trustworthy-evidence.md'
---

<frozen-after-approval reason="用户批准的实施意图；变更须重新确认">

## Intent

**Problem:** 当前检索按文本/语义分数排序，缺少九档权威、适用版本与有效期，也无法保留两条相矛盾的可核查原文。安全密级不能替代来源权威，失效或无权来源不应在治理页再次暴露。

**Approach:** 为当前授权的企业和附件来源增加独立的权威/适用性/时效元数据、可定位断言和双侧 `KnowledgeConflict` 记录；检索优先适用且有效的高权威来源，但冲突双方保留版本。知识管理员可在当前授权下提交带原因的裁定；X-10/X-11 呈现来源历史、冲突和禁止访问态，并使依赖结果待复核。

## Boundaries & Constraints

**Always:** 九档权威按法律、公司、项目、产品、批准历史、部门、内部、允许外部、LLM 一般知识分别表达，不由 L0–L3 密级推断；LLM 一般知识不形成正式 Evidence。有效期、适用项目/产品/客户、具体版本与当前授权都参与排序/查看/裁定；分数只表示相关性，不证明真伪。冲突记双方断言、单位/条件、来源版本/locator，且不能因排名较低隐藏；无权侧只能展示安全的禁止访问状态，不返回摘录、标题或可推断计数。裁定只允许知识管理员或明确授权角色，记录理由、操作者/时间与 CAS，后续依赖的 Pack/Claim/Review 待复核，历史快照不提供再次授权。

**Never:** 不把人工裁定当自动真相或改写原始断言；不在本 Story 实现章节 Pack、Claim、引用或发布。不启动服务、迁移、数据库、模型、测试套件或现场运行，原运行验收 `not-run`；保留前序候审接口的风险。

## I/O & Edge-Case Matrix

| 情形 | 输入/状态 | 可观察结果 | 错误处理 |
|---|---|---|---|
| 权威冲突 | 九档来源、同主题不同值或版本 | 优先适用高权威并保留可定位的两侧断言和历史 | 无证据的 LLM 常识不可引用 |
| 失效/撤权 | 过期来源或无权对手方 | 仅安全状态，不暴露保护内容；下游待复核 | 裁定重验双方、CAS 冲突拒绝 |
| 授权裁定 | 当前知识管理员与理由 | 不可变裁定事件、当前状态与失效标记 | 无权/空理由/过期版本拒绝 |

</frozen-after-approval>

## Code Map

- `migrations/versions/0016_safe_attachments.py`、`0017_authorized_retrieval.py`：附件定位与检索索引版本；新增治理迁移不修改旧数据。
- `edw-api/src/edw_api/access/{policy,repository}.py`：`knowledge:manage` 与资源当前授权；密级与权威维度不可混用。
- `edw-api/src/edw_api/knowledge/{routes,gateway}.py`：检索前后 ACL、签名企业证明、来源查看；扩展治理字段时保留 fail-closed 协议。
- `edw-worker/src/edw_worker/knowledge.py`：只生成受控索引，不由模型猜测来源权威。
- `edw-web/src/features/knowledge/{knowledge-api.ts,KnowledgePanel.tsx}`、`edw-web/src/app/App.tsx`：X-10 真实结果与清除逻辑；添加 X-11 状态/冲突页，不虚构原型像素。

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0018_source_governance.py`、`contracts/`：权威/适用版本、双侧断言及冲突、不可变裁定历史与待复核标志、唯一键和最小权限。
- [x] `edw-api/src/edw_api/knowledge/`、`task_contract.py`：受权来源登记/冲突识别/排序、失效判定、双侧查看与原因裁定 CAS；企业来源证明失败时不输出保护文本。
- [x] `edw-web/src/features/knowledge/`、`App.tsx`：X-10 权威/时效提示、X-11 两侧来源与历史/禁止访问/裁定状态，撤权清除片段。
- [x] `tests/security/`、`tests/contract/`、Web 测试源码：九档/密级分离、冲突版本、无权侧、失效和裁定权限/并发正反例；只编写和静态检查。

**Acceptance Criteria:**
- Given 九档有效且相互冲突的来源，when 作者检索或管理员查看，then 优先适用高权威来源，但双方断言和精确版本仍可在各自授权下检查；LLM 一般知识不成为正式证据。
- Given 过期来源或无权对手方，when 查看或裁定，then 无受保护摘录/标题泄漏，只有有权且带理由的版本化裁定可持久提交，依赖发现维持待复核。

## Implementation Notes

- 新增不可变来源断言、双侧冲突、CAS 裁定事件和未来 Pack/Claim/Review 的待复核依赖表；级别 9 仅为说明，不能登记正式断言。管理员明示登记来自重新核验的原文，不由 Worker/模型推断权威；同主题版本/值差异进入冲突。X-10 只对当前有效、适用且有权的来源附加权威；X-11 双侧当前核验，失效/无权侧仅返回禁止访问状态。
- 双侧当前授权之外的 POST 裁定统一返回不可区分的 404；单侧仍有权的 GET 仅返回安全冲突壳、`revision=0`、无历史和无权侧 `forbidden`。后续 Pack/Claim/Review 写入者需在绑定依赖时登记 `knowledge_dependency` 并消费 `needs_review`；本 Story 不虚构下游实体或发布流程。企业检索 `verify` 需签名 `current=true`；X-11 需网关新增签名 `inspect` 回应（ACL、当前版本、定位、内容散列、密级及有效期证明）；未提供能力时拒绝输出/查看/裁定。先前检索链和部署未实测。

## Spec Change Log

## Review Triage Log

## Verification

Python 编译、合同 JSON 解析、Web 类型检查/离线构建及限定路径 `git diff --check` 已退出 0；Web 保留混合引入/大 bundle 警告。先前子代理的只读审查超时且其记录的 DeepSeek 显示名不符合指定模型；主代理已通过 `opencode models opencode-go --verbose` 核实 `opencode-go/muse-spark-1.3-contributor` 的显示名为 Muse Spark 1.3 Contributor，并使用它只读审查撤权/历史泄漏，修复 404/409 可区分及 revision 暴露后复核无该项明确缺陷。测试套件、迁移、数据库、服务、真实企业网关/ACL/模型/性能及现场验收均 `not-run`；不作为已通过的独立质量门禁。
