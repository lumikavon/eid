---
title: 'Story 4.4 逐项审阅并接受当前 AI Patch'
type: 'feature'
created: '2026-09-29'
status: 'review'
route: 'dispatch'
baseline_commit: '039cf97e17cc70d2638c0483bf7be7b5d40e357a'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="用户指定 4.4 → 4.5 顺序推进到 review">

## Intent

**Problem:** 当前 Copilot 仅能展示候审提案，作者无法选择其中的精确变更并在并发编辑、来源撤权时安全地生成新的文档版本。

**Approach:** 提供绑定持久运行、基础版本、目标散列和来源的 Diff 及接受/拒绝操作；仅由 API 在当前授权、来源与基线复核后，对选中且兼容的 Patch 一次性创建不可变文档版本。4.3 中尚无多项模型输出时，可将一份完整生成的提案作为单项选择；支持多份兼容提案组合接受。

## Boundaries & Constraints

**Always:** 用户明确选择；服务端从持久运行重新推导 Patch，绝不信任前端提交的 `after`/JSON pointer。拒绝不写 AST；重复接受先重鉴权且只回放已记录的精确结果；冲突保留提案供版本对比。记录模型运行、Pack、Prompt/策略、用量、目标哈希、选中项目及新版本的溯源。

**Never:** Worker 或模型不更新 document head；不能修改文档 metadata/ACL/审阅状态或未选中块。当前仅开发、代码检查和离线编译；测试、迁移、服务和运行验收 `not-run`，最多到 `review`。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 逐项接受 | 当前基线 + 至少一个候审 Patch + 精确选中 ID | 单事务创建一个新版本，仅目标块或指定插入位置改变，保存 provenance | 不可兼容目标/重复块 ID 拒绝 |
| 拒绝 | 精确当前提案 | 留存决定与审计，不创建新版本 | 重复决定返回精确已提交结果 |
| 过期与撤权 | 版本/目标 hash/Pack/授权已变化 | 原提案保留并返回冲突线索 | 409/404；无正文副作用 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/model_gateway/copilot.py`、`copilot_routes.py`：目录、目标 hash、模型结果、当前证据和运行溯源；在 API 内重新推导与重新鉴权。
- `edw-api/src/edw_api/documents/editor_repository.py`、`editor_routes.py`、`schemas.py`：复用 `save_document` 的 CAS、AST 校验和不可变版本写入，不绕过资源校验。
- `edw-api/src/edw_api/model_gateway/sections.py`、`section_routes.py`：章节任务与 Pack 提案边界；新接受入口不直接写入章节任务的内容。
- `edw-web/src/features/templates/CopilotPanel.tsx`、`VersionHistory.tsx`：显示逐项 before/after/来源与冲突交接，保留编辑器既有版本对比。
- `migrations/versions/0024_copilot_run.py`：当前 schema head；新迁移需前向版本和最小 API 权限。

## Tasks & Acceptance

**Execution:**
- [x] `edw-api/src/edw_api/model_gateway/patches.py`：封闭的 stable-ID Patch 选择/组合和 AST 目标 hash 验证。
- [x] `edw-api/src/edw_api/model_gateway/patch_routes.py`：持久提案读取、拒绝/接受的当前权限和证据复核、确定性幂等回放及冲突响应。
- [x] `migrations/versions/0025_reviewed_patches.py`：记录选中项、决议、审计、精确来源和输出版本；Worker 无写入权限。
- [x] `edw-web/src/features/templates/CopilotPanel.tsx`：真实 Diff、单项选择、拒绝与接受、失败时保留提案并提示对比最新版本。
- [x] `tests/contract/`、`tests/security/`：正反源码契约、并发/越权/恶意指针场景；不执行测试套件。

**Acceptance Criteria:**
- Given 当前授权文档及多份候审 Patch，when 作者选择兼容子集并接受，then 仅该子集经当前 ACL/来源/基础版本/目标 hash 校验后生成恰好一个新版本，并留存完整模型与 Evidence Pack 溯源。
- Given 作者拒绝或提交空选择，when 记录决定，then 正文与版本不变化且重复请求重鉴权后幂等返回。
- Given 过期/删除的目标、恶意任意指针、跨工作区、撤权或并发接受，when 请求接受，then 409/404 失败关闭，保留候审记录和冲突入口，不产生部分版本或双重应用。

## Implementation Notes

- 增设独立接受路由；仅服务端根据已保存的 Copilot run 重建 Patch，接受通过 `save_document` 的 CAS/AST/权限路径生成版本。对企业链缺少事务内即时证明的提案明确返回 `AI_PATCH_SOURCE_UNVERIFIED`，不赋予虚假支持。
- 现有 `recheck` 重用 4.3 的完整持久 Evidence Pack 与目标复核；目标稳定 ID 不允许任意 JSON pointer。迁移为 API-only INSERT 和不可变决议记录。
- 源码与测试用例已经编写，实际运行测试、迁移、服务、浏览器和截图均 `not-run`；候审不代表真实链路通过。

## Spec Change Log

## Review Triage Log

- 静态复核修复了同一运行并发接受的检查顺序、应用后 hash 与基础节的区分、恶意额外字段，以及企业来源缺少事务内证明时的失败关闭。独立运行审查与矩阵测试尚未执行，保留为后续验收。
- Epic 4 跨 Story 复核进一步修复了同节多个 append 的组合、幂等回放的当前 head/权限锁定、并发决议冲突、替换块的非 content 字段保护、Patch 来源 hash 溯源和接受/拒绝审计。补充对应离线契约源码；未执行测试。

## Verification

**Commands:**
- `python -m compileall -q edw-api/src migrations/versions tests/contract tests/security` — Python 离线语法编译。
- `npm --prefix edw-web run typecheck` — Web 类型检查。
- `git diff --check` — diff 空白校验。

运行测试、迁移、服务和浏览器均记 `not-run`。

2026-09-29：Python `compileall`、Web `typecheck`、`git diff --check` 通过；所有运行验证 `not-run`。

2026-09-29 返修后：上述三项离线命令重新执行，退出码均为 0（`git diff --check` 仅提示 LF/CRLF 转换）；迁移、测试、服务、浏览器与真实验收仍为 `not-run`。
