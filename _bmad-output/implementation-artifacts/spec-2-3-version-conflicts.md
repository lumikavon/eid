---
title: 'Story 2.3 无损保存和处理并发版本'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
baseline_commit: 'eecf92df2a44df75c21b4215654307e604fafc4d'
review_loop_iteration: 2
context:
  - '_bmad-output/implementation-artifacts/epic-2-context.md'
  - '_bmad-output/planning-artifacts/epic-2-controlled-authoring.md'
---

<frozen-after-approval reason="用户已授权 PROMPT.md 串行开发；业务意图源自 Epic 2、架构和 UX">

## Intent

**Problem:** Story 2.2 只提供手动 CAS 保存；并发冲突后既无授权历史，也无明确的 base/local/latest 对比和人工合并，离线或请求结果不明可能使作者误以为保存成功。

**Approach:** 在现有不可变版本链上增加当前权限下的版本列表/详情，客户端保留内存草稿，1000ms 空闲自动保存与显式保存共用 CAS；冲突时以稳定节点 ID 三路比较，逐块选择本地/最新/人工修改，基于最新 head 再提交经检验的新版本。

## Boundaries & Constraints

**Always:** 列表与历史详情每次依当前 `resource:read`、文档归属及完整性散列核验；保存/合并使用当前 `document:edit`、未发布状态和 base/revision CAS。只在服务端确认本次草稿版本时显示“已保存”与时间；冲突保留 base/local/latest 与所有尚未确认选择，另一轮竞态不静默覆盖。无法无损自动合并的章节顺序、标题、引用绑定与未知节点必须显式提示或阻断；不能以按位置拼接吞掉新块。离线、撤权、Published 与未知请求结果明确区分；不持久化敏感正文或令牌。计时事件分隔 debounce、客户端请求与服务端处理字段，不把 1000ms 计入服务端 P95。

**Never:** 不改写或删除已有 DocumentVersion；不在 409 响应里泄露未经再次授权的正文；不向未授权重试返回历史成功正文；不盲目重试可能已提交的写入；不做 2.4 模板治理或 Epic 13 的多用户/负载运行验收。不执行测试、迁移、数据库、服务、浏览器或现场功能实测。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 单人编辑 | 1000ms 空闲或 Ctrl/Cmd+S、当前 base | 一次 CAS 新版本、明确状态与分层时间 | 后续输入仍 dirty，不显示旧草稿已保存 |
| 并发编辑 | 两个作者同 base 修改相同或不同块 | 一方成功；另一方保留本地，取授权 base/latest，逐 ID 显示差异并显式合并 | 缺失决策、结构不兼容或再次竞态不能写入 |
| 网络/权限变化 | 离线、超时、未知结果、撤权、Published | 离线内存待保存；未知结果先核对 head 与内容散列；历史重新授权 | 不复用旧成功正文，不虚报保存时间 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/documents/editor_repository.py`：复用已锁定的 `save_document` CAS；新增当前 ACL 历史列表/详情，核对版本与文档归属、散列。
- `edw-api/src/edw_api/documents/editor_routes.py`、`schemas.py`：扩展版本路由与 `Server-Timing` 服务端处理毫秒；保持 PUT 现有协议与 409 安全错误。
- `migrations/versions/0011_template_creation.py`：已有 revision/base/hash/AST/actor/time 和不可变触发器，保持只读；无新迁移需求。
- `edw-web/src/features/templates/DomainEditor.tsx`：现有 draft/base/dirty/CAS 只支持手动保存；新增自动保存、快捷键、历史与冲突视图，未确认期间不销毁本地草稿。
- `edw-web/src/features/templates/template-api.ts`、`TemplateWorkspace.tsx`：新增安全历史读取与请求计时；后者现有查询/返回入口须保留 dirty 状态并提供离开确认。
- `edw-web/src/features/templates/domain-adapter.ts`：稳定节点 ID 和未来只读保留；新增独立纯三路合并工具，不把 Tiptap JSON 当权威。
- `tests/security/test_domain_editor.py`、`edw-web/src/features/templates/*.test.*`、`contracts/`：写并发、授权、三路选择、状态/计时契约的源码；本轮只 lint/编译。

## Tasks & Acceptance

**Execution:**
- [x] `edw-api/src/edw_api/documents/{editor_repository,editor_routes,schemas}.py`：授权版本列表/详情及服务端计时字段；重用版本完整性检查，禁止跨文档与撤权读取。
- [x] `edw-web/src/features/templates/{domain-merge.ts,template-api.ts,DomainEditor.tsx,TemplateWorkspace.tsx}`：实现只在无损时自动合并、每个重叠节点显式选择、历史/比较界面、1000ms debounce/Ctrl+S、离线/未知结果协调与离开确认。
- [x] `tests/security/`、`edw-web/src/features/templates/`、`contracts/`：补正反测试源码、版本与计时事件契约；只运行静态检查/类型检查/编译与离线构建，不执行测试。

**Acceptance Criteria:**
- Given 同一 base 的两次写入，when 竞态与逐块合并发生，then 仅一方 CAS 成功，另一方保留所有草稿与决策；再次提交基于最新版本且生成新的不可变版本，新的竞态返回 409。
- Given 离线、未知提交结果、撤权或 Published，when 自动保存/重试/历史读取发生，then UI 不宣称成功，受保护版本重新授权，未获授权不泄露旧成功内容。
- Given 1000ms 无输入，when 保存计时事件记录，then `debounce_ms`、`client_request_ms`、`server_processing_ms` 独立；运行 P95 不在本轮宣称通过。

## Implementation Notes

- 历史列表每页至多 50 条并读取至多 51 份 AST 校验 SHA-256；历史详情同样按当前 ACL 和文档归属核验。无新迁移。
- 合并保留本地新增块的相对锚点；不同 head 到来时旧选择失效但人工文本草稿保留。服务端确认或不确定结果核对后的权威 AST 更新会重建编辑画布，防止旧画布覆写远端块。
- 站内导航、文档返回和浏览器历史导航进入离开确认；浏览器历史阻断采用捕获阶段撤销地址变化，不写入草稿。其浏览器实际行为尚未运行验收。

## Spec Change Log

## Review Triage Log

- 独立只读审查第一轮报告 6 项（旧画布覆写、再次竞态沿用选择、浏览器返回丢草稿、新增块位置、历史列表散列、撤权正文残留），逐项修复；第二轮指出核对原提交撤权路径仍留历史弹窗，已在受保护错误路径立即关闭。
- 核实显示名称 **Muse Spark 1.3 Contributor** 对应 `opencode-go/muse-spark-1.3-contributor` 后调用 `opencode` 独立只读审查；其明确指出已知 503 误归入未知、Ctrl+S 可绕历史弹窗保存、版本对比选取响应竞态，均修复。最终定向复审认为这三类及撤权历史可见性问题在所读源码范围内无剩余阻塞。
- 以上均为源码审查，未以模型建议替代软件静态/编译检查，也未执行测试或真实环境验收。

## Design Notes

- 2.2 已有 PUT 保持唯一写入口。合并结果使用服务器当前最新版本的 `base_version_id/revision` 走同一 CAS，客户端三路构造按 ID 检出未知/顺序/删除冲突；服务端已有 AST/媒体校验与 Published 拒绝。不引入新的可绕过 CAS 的“强制覆盖”。

## Verification

**Commands:**
- `uv run --offline ruff check edw-api/src/edw_api/documents tests/security/` 与 `python -m compileall -q ...`：仅源码/语法检查。
- `pnpm --filter edw-web lint`、`pnpm --filter edw-web build`：先核对脚本，只做静态和离线构建。
- `uv run --offline ruff check edw-api/src/edw_api/documents tests/security/test_domain_editor.py`、`python -m compileall -q edw-api/src/edw_api/documents tests/security/test_domain_editor.py`、`pnpm --filter edw-web lint`、`pnpm --filter edw-web build`、`contracts/document-versions.schema.json` JSON 语法及 `git diff --check`：通过；Node 版本与项目指定版本不一致的引擎警告、Vite >500 kB 分包建议仍在。
- 自动/手工测试、迁移、DB、S3、服务、浏览器、性能 P95 和现场运行验收：**not-run**。`git diff --cached --check` 及精确暂存须在提交前单独核对。
