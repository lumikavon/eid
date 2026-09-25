---
title: 'Story 2.2 编辑与编辑器解耦的领域 AST'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
baseline_commit: '58dc2edae78b7e4d34084eee0c6a7c6d4f2a18fc'
review_loop_iteration: 1
context:
  - '_bmad-output/implementation-artifacts/epic-2-context.md'
  - '_bmad-output/planning-artifacts/epic-2-controlled-authoring.md'
---

<frozen-after-approval reason="用户已授权 PROMPT.md 串行开发；以下业务意图源自 Epic 2 与架构约束">

## Intent

**Problem:** Story 2.1 的文档只有只读的初始段落投影；编辑标题和结构化内容尚无双向转换、保存路径与授权图片引用，浏览器编辑可能丢失领域语义。

**Approach:** 用 Tiptap/ProseMirror 与领域 AST 之间的显式双向 Adapter 承载编辑；在当前权限下持久化新的不可变版本，保留旧版本和引用关系，提供最小安全图片资源路径。

## Boundaries & Constraints

**Always:** AST `1.0` 的 metadata/sections/claims/citations/review_state 为权威；Section/Block/Claim/Citation 使用稳定 ID。块类型为 paragraph、heading、table、figure、diagram、requirement、citation、warning、code、form；列表由 paragraph metadata 表达。requirement_id/statement/verification_method/source_refs、表格跨行、图片 alt/比例及未知扩展必须往返不丢失。未知未来节点只读提示，不允许保存时静默删除；不安全 URL、非法结构拒绝且不改变旧版本。写入在事务内按当前授权、对象范围与 Published 状态重核，并用预期 base/revision 保护 head；图片仅可引用当前有权的受控资源，校验 MIME、大小、散列、alt 和比例，不抓远程 URL。

**Never:** 不把 Tiptap JSON/DOM 作为公共持久协议；不直接 UPDATE/DELETE 已存 DocumentVersion；不允许读者编辑或直接改 Published；不在浏览器持久化敏感正文/令牌；不扩展 3.1 的 OCR/多格式解析、4.5 的生成图形、2.3 的人工合并/完整历史 UI；不运行测试套件、迁移、数据库、服务、浏览器或现场实测。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 有权编辑 | 现有版本、合法各类块和引用、图片资源 | 双向 Adapter 保留稳定 ID 与字段；标题、选区、撤销/重做、列表/对齐/链接/表格/图片操作后产生新不可变版本，树定位正确 | 只在服务端确认后提示已保存 |
| 未知或危险 | 未知节点、畸形 AST、危险 URL、外部图片 | 未知原始数据只读保留，危险结构/引用不能提交 | 422/403，不覆盖上一有效版本 |
| 权限与并发 | 读者、失权、Published、过期 base/revision | 不写入；并发不能后写覆盖先写 | 安全 403/404/409，草稿保留内存 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/documents/domain.py`：现有 `initial_ast`/`content_hash`；补严格领域验证，保持纯 Python。
- `edw-api/src/edw_api/documents/{schemas,routes,repository}.py`：复用 Bearer/current ACL、只读 head 和初始创建；新增编辑命令、受控资源与原子版本推进。
- `migrations/versions/0011_template_creation.py`：只读旧迁移；新建 0012 增量迁移提供最小 head 更新和受控图片资源/权限，不能改历史版本。
- `edw-web/src/features/templates/{TemplateWorkspace.tsx,template-api.ts}`：现有只读文档/授权错误流；与独立 AST Adapter/编辑器会话对接，不覆盖 dirty buffer。
- `edw-web/package.json`、`pnpm-lock.yaml`：已有 React/Vite，无 Tiptap；采用开源 Tiptap 3.x（当前可查 3.31.3），锁定一致版本，禁用云服务。
- `tests/security/`、`edw-web/src/features/templates/*.test.*`：增加正反 AST 往返、安全资源、授权和编辑行为测试源码，本轮只检查/编译。

## Tasks & Acceptance

**Execution:**
- [x] `contracts/document-ast-v1.schema.json`、`edw-api/src/edw_api/documents/editor_domain.py`：定义 AST 1.0/块与资源引用契约，拒绝坏结构/不安全链接，未知节点只读保留。
- [x] `edw-web/src/features/templates/`：实现 `domainToEditor`/`editorToDomain` 与 Tiptap 基础编辑会话，保留未知字段、稳定 ID、选区和 undo；树、标题、画布及工具栏复用 P-03 布局。
- [x] `migrations/versions/0012_domain_editor.py`、`edw-api/src/edw_api/documents/`：新增当前 ACL 下的图片上传/读取和受限版本保存，单事务核对 base/revision、Published，原版本不可变；未执行迁移。
- [x] `tests/`、`edw-web/`：编写矩阵正反例与 schema/往返/API/UI 源码；执行静态检查、类型检查、编译/离线构建；测试执行 not-run。

**Acceptance Criteria:**
- Given 每种合法块和 requirement/source 引用，when 用户编辑、撤销重做并保存，then ID/结构/引用经双向 Adapter 和新版本读取保持一致，图片只引用授权资源。
- Given 未知节点、坏 AST/危险链接、过期版本、无权/Published，when 加载或提交，then 只读保留或安全拒绝；旧版本/head 不被覆盖，界面不误报已保存。

## Implementation Notes

- 2026-09-24：使用锁定的开源 Tiptap 3.31.3；领域 AST 仍为版本权威，编辑器状态仅存内存。`PUT` 必须匹配当前 base/revision，提交生成新的 DocumentVersion；图片上传归一化为私有 PNG，读取复核权限和散列。旧迁移 0011 不变。
- 表格域模型只承载纯文本单段单元格；单元格多段/富文本在 Adapter 转换时显式阻断保存，避免无声丢失。未来节点不支持编辑且不可删移。Story 2.3 才增加冲突合并与自动保存。
- 软件完成不代表运行验收：测试套件、迁移、数据库、S3、服务、浏览器及现场全部 `not-run`，不能由静态/编译结果推断功能通过。

## Spec Change Log

- 为修复只读未来节点丢失、链接路径包含 `@`、表格单元格非无损转换、服务端重读后陈旧草稿等审查问题，添加 fail-closed Adapter/AST 检查与重读草稿保持；未改变业务意图。

## Review Triage Log

- 独立只读源码审查发现 P1 未来节点可删除、P2 安全链接 `@` 路径丢失、表格多段/格式丢失及重读陈旧会话。均已修复并补回归源码；未运行测试。
- 已核对 `opencode models opencode-go --verbose` 中显示名称 `Muse Spark 1.3 Contributor` 对应 `opencode-go/muse-spark-1.3-contributor`；最终只读复审两次返回“无”。此前一次宽范围审查超时，不记为通过。

## Design Notes

服务端版本保存即使 Story 2.3 尚未交付，也要有最小 CAS 防止本 Story 的编辑覆写他人：后续 2.3 负责三路比较/合并和自动保存体验，不得因此放松 2.2 的原子性。所有运行案例目前 `not-run`。

## Verification

**Commands:**
- `uv run --offline ruff check edw-api/src/edw_api/documents migrations/versions/0012_domain_editor.py tests/security/test_domain_editor.py`、`python -m compileall -q edw-api/src/edw_api/documents migrations/versions/0012_domain_editor.py tests/security/test_domain_editor.py`；只做源码检查。
- `pnpm --filter edw-web lint`、`pnpm --filter edw-web build`；运行前核对依赖脚本不启动服务或测试。
- `git diff --check`、`git diff --cached --check`；仅 Story 文件精确暂存。

**结果（2026-09-24）：** Ruff、Python compileall、Web ESLint、TypeScript/Vite 离线构建、JSON 语法检查和源代码差异空白检查通过。Vite 有大 chunk 非阻塞告警；Node 24.12.0 与项目声明 24.20.0 不一致的引擎告警。所有运行验证 `not-run`。
