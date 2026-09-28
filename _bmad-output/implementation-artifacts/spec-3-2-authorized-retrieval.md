---
title: 'Story 3.2 授权双链检索'
type: 'feature'
created: '2026-09-27'
status: 'in-review'
route: 'dispatch'
baseline_commit: '12afe76c6c46d858100d95534229c3d20ac0ed96'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-3-context.md'
  - '_bmad-output/implementation-artifacts/spec-3-1-safe-attachments.md'
  - '_bmad-output/planning-artifacts/epic-3-trustworthy-evidence.md'
---

<frozen-after-approval reason="用户批准的实施意图；变更须重新确认">

## Intent

**Problem:** 现有发现页只按标题检索记录元数据，附件虽有页级片段却无索引和可授权召回。P-10 为占位，无法安全地将企业知识与附件作为有版本的可核查来源提供给作者。

**Approach:** 实现声明能力的企业 Knowledge Gateway 适配器，以及独立的本地附件 FTS/jieba+pgvector/BGE-M3、reranker 版本化索引与检索；组合限定范围、精确标识符和语义查询，但每条返回结果均经过当前权限/版本/适用性前后过滤。P-10/X-10 提供真实受权来源、片段定位及链路不可用状态，不把未配置/失效链路伪报为全量检索。

## Boundaries & Constraints

**Always:** 企业适配器先声明可证明的 ACL 预过滤、精确来源定位、版本及失效时刻；无法证明或故障时企业链不可用，不重建企业向量。附件索引只由受控解析结果建立，保留工作区/文档/分类/版本与 chunk 哈希；索引不扩大原件权限。查询范围、密级、context、版本与有效性需在召回前后及模型使用前重验；撤权与外部 ACL 不可证时拒绝而不泄露标题、摘录、数量或敏感日志。精确型号/标准/项目编号等走关键词路径，即使向量不可用也要明示该链缺失。搜索/索引操作有边界、版本溯源和最小委派，长网络调用不在 DB 事务中。

**Never:** 不使用发现页的标题示例当 Evidence；不将 LLM 常识当正式来源；不把替身通过等同企业联调或 BGE/reranker 效果验收。不运行测试套件、迁移、服务、数据库、浏览器或真实环境，运行验收均 `not-run`。不提前实现 Story 3.3 冲突裁定或 Story 3.4 Pack。

## I/O & Edge-Case Matrix

| 情形 | 输入/状态 | 预期 | 异常 |
|---|---|---|---|
| 双链结果 | 授权附件、声明能力的企业源、范围/版本过滤 | 真实片段、定位、版本、链路、策略与检索版本 | 精确标识符关键词命中不依赖向量 |
| 撤权/过期 | 失效成员或来源、跨域或更高密级 | 前后过滤均不输出受保护内容与计数 | 失败关闭且清空旧受控片段 |
| 适配器或模型缺失 | ACL 证明缺失、网关故障、模型未配置 | 明确链路不可用、结果不称完整 | 不把旧索引快照当当前授权 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/access/{policy,repository}.py`：`checked`、`authorize` 和 `create_delegation` 的当前权限/作用域/密级；不能只依据上传时的许可。
- `edw-api/src/edw_api/discovery/{routes,repository}.py`：仅标题/元数据发现，不作为证据检索实现。
- `migrations/versions/0016_safe_attachments.py`、`edw-api/src/edw_api/attachments/routes.py`：受控解析片段、页/定位、来源读授权；新索引需按附件解析版本与 chunk hash 绑定。`eid_attachment_allowed_v1` 只针对原上传者及五分钟解析委派，检索不可复用它授权普通读者。
- `edw-worker/src/edw_worker/{app,access,attachments}.py`：检索队列已声明，无检索处理；解析写入与隔离权限模式可复用，不复用通用库存任务。
- `edw-web/src/app/App.tsx`、`features/templates/DomainEditor.tsx`、`docs/prototype/index.html`：P-10 占位、P-05 示例证据；仅在原样视觉外壳添加 UX 契约定义的真实搜索/查看器。

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0017_authorized_retrieval.py`、`contracts/knowledge-search-v1.schema.json`：本地附件来源索引、FTS/向量版本和最小数据库权限；保留旧迁移。
- [x] `edw-api/src/edw_api/knowledge/`、`main.py`、`task_contract.py`：有界参数、两链结果状态、当前 ACL 与来源版本的前后重验，明确不可用/不完整状态。
- [x] `edw-worker/src/edw_worker/knowledge/`、`app.py`、配置与依赖：授权附件索引/召回、精确关键词及可用的语义/rerank 链；能力可证企业网关适配，故障失败关闭。
- [x] `edw-web/src/features/knowledge/`、P-10/P-05 接入：范围/版本/分类过滤、企业/附件/Golden 类别、片段与版本定位、链路不可用和撤权清除。
- [x] `tests/security/`、`tests/contract/`、`tests/worker/`、Web 测试源码：许可与拒绝、精确召回、版本变动、缺失能力与超时正反例；只编写/静态检查不运行。

**Acceptance Criteria:**
- Given 授权与拒绝来源及精确标识符，when 组合查询，then 预/后过滤均受当前 ACL、密级、适用性和来源版本约束，关键词可补充向量链且可查真实片段。
- Given 撤权、成员或版本变动、企业适配器失败或模型未配置，when 查询或重试，then 不向模型/结果/日志暴露失权内容，链路显示不可用，不宣称全量搜索。

## Implementation Notes

- 本轮增加 0017 前向索引（解析版本/附件散列/chunk 散列、FTS/jieba 词项、可选 pgvector）、受限 Worker 定期索引、当前权限范围内 API 关键词/精确子串与可选向量/重排、签名能力声明和二次校验的企业 Gateway 适配器。缺少模型、企业网关或可证 ACL 时明确标不可用，`complete=false`，不把发现页标题当来源。
- P-10 使用原壳内的新知识检索正文，P-05 编辑器侧栏可按当前文档检索；更改筛选、选章、离开、拒绝或定时核验均清除旧片段。查看片段需重新请求及按当前版本匹配。
- 用户确认仅修改部署源码：compose 与镜像锁改为按 digest 固定的 `pgvector/pgvector:0.8.6-pg17`，新库 init SQL 预建扩展，0017 断言 `extversion=0.8.6`；旧数据卷不会自动执行 init，迁移前的扩展准备、镜像切换与真实兼容性均待单独授权和验证。未提供真实 Gateway 端点、模型端点/权重时相应链明确不可用；Golden 只通过可证明的企业声明返回，不虚构本地数据。请求限制为同项目最多 100 个候选文档，不声称全量搜索。长网络调用不在 DB 事务中，撤权与远端 ACL 同步时序仍需真实集成验证。

## Spec Change Log

## Review Triage Log

## Verification

Python `compileall`、合同 JSON 解析、`uv lock --check --offline`、Web `npm run typecheck` / 离线 `npm run build` 和限定路径 `git diff --check` 已执行并退出 0；Web 构建仅提示原有大 bundle / 混合动态引入告警。`opencode models opencode-go --verbose` 已核实显示名并调用 `opencode-go/muse-spark-1.3-contributor` 只读辅助审查；已修正其指出的 Worker `call` 参数缺失、查看器版本绑定、模型响应、检索限定等问题；第二次只读审查尝试在 120 秒超时，未取得最终结论；其后补充针对 pgvector 镜像/初始化/版本断言的只读辅助审查，静态一致且未运行数据库。以上不是独立质量门禁。

所有测试套件、数据库/迁移、服务、浏览器、真实企业 Gateway/BGE/reranker、权限撤权和检索效果/性能验收均为 `not-run`。
