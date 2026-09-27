---
title: 'Story 2.6 生成前确认完整大纲'
type: 'feature'
created: '2026-09-27'
status: 'done'
route: 'dispatch'
baseline_commit: '6b62b18d87161c1b09f4d31236c2b6c2b0cee983'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-2-context.md'
  - '_bmad-output/planning-artifacts/epic-2-controlled-authoring.md'
---

<frozen-after-approval reason="用户要求按 Sprint 顺序继续下一 develop Story；依据 Epic 2 Story 2.6">

## Intent

**Problem:** 作者尚不能保存并人工确认生成前的必需大纲；模板必选章只在模板策略快照中，现有正文 AST 的随机章节 ID 不能证明大纲完整。

**Approach:** 以固定模板版本建立可手工编辑和键盘重排的大纲，保存不可变版本，由作者明确确认精确版本；API 按当前授权、上下文、正文与模板前置实时计算 `OUTLINE_READY` 和结构化缺项。

## Boundaries & Constraints

**Always:** 服务端依据固定模板版本的不可变 manifest 识别必选章 ID/标题，不信客户端必选标记或同名替身。大纲章节有稳定 ID；手工新增章没有模板章 ID。保存和确认检查当前 actor/workspace/document 授权、草稿、正文 head/revision、`CONTEXT_READY` 的精确 context 版本及大纲 CAS，同事务写审计。人工确认固定版本、操作者和时间；新大纲、正文或上下文版本使旧确认的资格失效。保存失败、失权和未知结果时 UI 保留未提交输入。

**Never:** 不把任务完成、模板选择或 AI 提案当作人工确认；不依靠章节标题或现有 AST 随机 ID 猜测必选身份，不修改历史 AST/DocumentVersion。无模板 policy 的开发 fixture 显式把固定 `structure.sections` 全部视为必选并生成确定性模板章 ID，仍标 development-only；已固定到旧文档的废弃模板版本可继续用于该文档，模板版本不匹配仍拒绝。不运行测试套件、服务、迁移、数据库、浏览器或现场环境；运行验收记录 `not-run`。

## I/O & Edge-Case Matrix

| 场景 | 输入 / 状态 | 可观察结果 | 错误处理 |
|---|---|---|---|
| 保存与确认 | 当前授权草稿、`CONTEXT_READY`、必选章完整 | 新增不可变大纲版本；明确确认后返回精确版本、操作者、时间与 `OUTLINE_READY` | 新增章节与重排保留稳定 ID |
| 必选章缺失 | 删除、替换 ID 或改写必选标题 | 旧版本不变，资格列出缺失章及路径 | 保存/确认拒绝且 UI 保留输入 |
| 前置变化 | 撤权、旧大纲 base、正文/context head 变化 | 旧确认不再产生 `OUTLINE_READY` | 403/隐藏 404、409 或结构化 pending；不回显旧成功正文 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/documents/governance_repository.py:286-305`：受治理模板的 `rule_refs.sections` 保留 `{id,title,mandatory}`；`structure` 只有标题，不能当必选权威。
- `edw-api/src/edw_api/documents/domain.py:58-92`：fixture `structure` 与初始 AST；AST 随机 ID 不作模板章 ID。
- `edw-api/src/edw_api/documents/context_repository.py:96-171,217-314`：当前 context 资格、授权/文档锁、双 CAS、确认与审计模式。
- `edw-api/src/edw_api/documents/editor_repository.py:15-144`：草稿权限、document head/revision CAS；正文变更应使旧 outline 资格失效。
- `migrations/versions/0014_project_context.py`：新增前向 0015，沿用不可变 version/head/confirmation 约束；不改旧迁移。
- `edw-web/src/features/templates/DomainEditor.tsx` 与 `ProjectContext.tsx`：P-03 正文树及 X-15 上下文检查器；大纲独立展示，不冒充正文已重排。

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0015_outline_confirmation.py`、`contracts/`：不可变 outline version、head、confirmation，固定前置引用、摘要、审计与有界 wire 契约。
- [x] `edw-api/src/edw_api/documents/outline_*.py`、`main.py` 与版本配置：固定模板必选章、当前权限、CAS、保存/确认/历史/资格接口；`OUTLINE_READY` 实时派生。
- [x] `edw-web/src/features/templates/`：X-15 手工大纲树、键盘重排、必选章保护、缺项与确认历史；失权/冲突/未知结果保留输入。
- [x] `tests/security/` 与前端测试源码：正反例覆盖矩阵；只审查、静态检查和编译，不运行测试套件；代码修改后调用核实 ID 的 `Muse Spark 1.3 Contributor` 辅助审查。

**Acceptance Criteria:**
- Given 当前授权草稿、确认的 context 与固定模板必选章，when 作者保存并明确确认精确大纲版本，then 返回不可变版本、确认人/时间及可追溯的 `OUTLINE_READY`。
- Given 必选章缺失、旧正文/context/template、大纲冲突或失权，when 保存、确认或读取生成资格，then 原有效版本不被改写，返回可定位原因且不产生新的 READY。

## Implementation Notes

- 2026-09-27 规划：开发 fixture 的全部固定模板章节作为必选；废弃但已固定的模板版本保留已有文档的大纲确认资格。大纲独立于正文 AST；未来 AI 只可提交未确认提案，复用同一人工确认 API。
- 0015 增加不可变大纲版本、head 与人工确认；API 提供 `/outline` 当前读取/保存、`/confirm`、`/eligibility`、`/versions` 及精确历史读取。必选章来自固定策略的 manifest ID；fixture 从模板版本与序号派生稳定 ID。当前上下文、正文、模板或大纲 head 变化会使旧确认资格失效。
- X-15 大纲控件与正文 AST 树分离；保存/确认按精确前置版本发送。上下文重新读取/保存/确认时撤销旧 READY 并重核；未知 PUT 的等价版本仅供人工采用基线，不证明原请求成功。

## Spec Change Log

## Review Triage Log

- 独立跨层审查发现标题 trim 后 dirty 无法清除、同页 context 更新后旧 READY 仍显示、未知 PUT 等价版本误归因三项中风险；已在 Web 侧修复，独立复核 `approved`。
- Muse 后端审查提出并发确认唯一键、模板策略重复 ID、模板标题、共享契约和字节长度五项；独立复核：并发确认受 document 行锁串行化、标题异常不形成所称 pending；重复 ID 仅异常持久数据可达，已补失败关闭校验；契约明确标注 API 额外校验；字节低估未找到可复现输入，保留静态局限。最终局部 Muse 复审未发现新增高/中缺陷。
- 旧版 `ProjectContext.tsx` 与正文编辑器的未知保存等价版本归因仍可能误称原请求成功；独立审查确认是 Story 2.6 前已有缺陷，另行跟踪，不据此声称两处已修复。

## Verification

**Commands:** Python Ruff/compileall，前端 lint/TypeScript/Vite，JSON/配置静态解析，`git diff --check`，独立源码审查。测试套件与实际运行验收 `not-run`。

- 已执行：Story 2.6 Python 源码 Ruff、compileall、JSON 合同解析、Web lint/typecheck/Vite build、差异检查，均退出 0；指定 `opencode-go/muse-spark-1.3-contributor` 已核实显示名并多次完成只读辅助审查。独立源码审查及问题复核通过；无同一问题三次修改验证仍失败的事实，不触发 `FORCED_PASSED`。
- 测试源码已编写并静态检查；测试套件、迁移、数据库、服务、浏览器和现场运行验收均 `not-run`。本文 `done` 仅为软件开发关闭，不是功能运行或 Epic 13 验收通过。
