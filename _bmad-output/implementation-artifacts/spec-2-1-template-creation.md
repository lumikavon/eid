---
title: 'Story 2.1 选择模板并创建目标文档'
type: 'feature'
created: '2026-09-24'
status: 'done'
route: 'dispatch'
baseline_commit: 'ad2e2070f370ece80e105d2d0590e028b7511c95'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-2-context.md'
  - '_bmad-output/planning-artifacts/epic-2-controlled-authoring.md'
---

<frozen-after-approval reason="用户已授权 PROMPT.md 串行开发；本段记录 Story 业务意图">

## Intent

**Problem:** 工作台的五个创建入口和模板中心仍是禁用或示例展示，无法依据当前权限选用模板并取得自己的文档。Discovery 元数据投影不能承载正文或模板版本。

**Approach:** 建立受当前授权约束的模板目录与版本固定创建命令，保存独立 Document/初始领域 AST/发现投影；连接既有首页、模板中心和创建弹窗，使所选版本、文种及知识范围进入同一创建事务。

## Boundaries & Constraints

**Always:** 五种模板范围及搜索/分类/文种筛选取交集；模板详情和预览来自选中版本自己的结构。创建返回 201、新文档 ID 与初始 AST；名称修剪后非空，模板版本、文种、知识范围和当前 workspace 授权在提交时核对。模板开发样例明确标记，完整 11 文种仅提供目录和初始结构，不声称后续专属流程可用。重试前重新鉴权，幂等键绑定规范化请求散列。API 与 Worker 的数据库权限保持最小化。

**Never:** 不信任客户端的角色、分类或范围声明；不把 Discovery 投影当正文；不修改原型源文件、旧迁移或既有 Story fixture；不把开发样例显示为正式模板；不运行测试套件、迁移、数据库、服务、浏览器或现场功能验证；不触碰预存远端脚本及无关改动。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 模板浏览 | 当前主体、workspace、五范围与查询/分类/文种组合 | 仅返回显式授予当前 workspace 且符合所有筛选的版本；详情、预览与卡片同版本 | 不可见模板不泄漏详情或计数 |
| 创建 | 有权作者、可用模板版本、合法名称/文种/知识范围 | 单事务写新 Document、DocumentVersion 初始 AST、head、当前可发现记录、审计和回执；返回 201 并打开新 ID | 提交未知结果用原键安全查询，禁止重复文档 |
| 拒绝 | 模板过期/并发废弃、无权模板或范围、非法名称、同键异请求 | 不写文档；保留弹窗输入 | `409 TEMPLATE_DEPRECATED` 或 `IDEMPOTENCY_KEY_REUSED`；安全 403/404；422 字段错误 |
| 取消 | 弹窗取消或点击背景 | 不创建；背景不关闭 | 无写请求 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/access/policy.py:60`、`access/repository.py:33`：当前授权与同 workspace 互斥锁；创建还需核对模板适用关系，不可只凭 `document:create`。
- `edw-api/src/edw_api/discovery/repository.py:276`：当前授权下的审计/幂等事务样式；`discovery_record` 只是元数据投影，`FUTURE_PANELS` 创建提示须随能力更新。
- `edw-api/src/edw_api/main.py:28`：路由组合根；新增模板/文档路由按已有 Bearer 与统一错误注册。
- `migrations/versions/0010_task_observation.py:5`：当前迁移 head；新增 `0011`，不改历史迁移。`0003_current_access.py:32` 的 `access_resource` 与 `0007_workspace_discovery.py:12` 的投影须在新事务中对应，API 新增最小 INSERT 授权。
- `edw-web/src/app/App.tsx:29`：现有路由白名单与当前身份/缓存失效边界；模板和新文档路由按稳定 ID 扩展。
- `edw-web/src/features/workspace/DiscoveryPanel.tsx:17`：五个禁用创建入口和目录；启用入口并传递实际意图。
- `edw-web/src/app/prototype.css:53`：模板中心、卡片、详情和创建弹窗既有样式；保持原型布局及 `≤1180px` 横向滚动。
- `contracts/`：新增模板/文档创建 wire schema 与文种目录，不扩写 Discovery 的粗粒度 `document_type` 枚举来冒充文种。

## Tasks & Acceptance

**Execution:**
- [x] `contracts/` 与 `edw-api/src/edw_api/documents/`、`templates/`：固定文种、知识范围、模板筛选/详情、初始 AST 和创建请求/响应契约；创建业务规则置于可复用的领域/application 层，API 仅做身份与 wire 边界。
- [x] `migrations/versions/0011_template_creation.py`：新增最小 Template/TemplateVersion、workspace 可用关系、Document/DocumentVersion、创建回执与索引/约束/最小 DB grants；模板版本不可变且有明确开发样例资格；不得运行迁移。
- [x] `edw-api/src/edw_api/main.py` 与新路由/仓储：实现当前 ACL + 模板版本锁 + 幂等/审计/初始 AST/发现投影原子创建；403/404/409/422 拒绝不留部分记录。模板 fixture 使用独立、隔离、受控来源，静态契约可检查；不覆盖已有 fixture。
- [x] `edw-web/src/app/App.tsx`、`features/workspace/DiscoveryPanel.tsx` 及新模板/创建/文档视图和 API client：启用五入口与模板中心；AND 筛选、选中详情/预览、真实创建、错误保留输入、取消不写、成功打开新文档 ID/AST，未实现专属流程清晰提示。
- [x] `tests/`、`edw-api/tests/`、`edw-web/tests/`：编写创建、交集筛选、ACL/废弃并发、幂等、初始 AST 和 UI 错误状态正反例；仅审查/编译测试源码，本轮不执行测试。

**Acceptance Criteria:**
- Given 显式可用的五范围开发模板及当前权限，when 用户组合筛选、查看详情/预览并创建，then 列表为交集，201 返回其新文档 ID、自有初始 AST 和固定模板版本，页面展示该 ID 的内容。
- Given 废弃/无权模板、无权知识范围、无效名称或提交时并发废弃，when 创建或重试，then API 安全拒绝且无部分写入；表单保留输入，取消无副作用，同一幂等意图不产生第二文档。

## Implementation Notes

已新增 `contracts/template-creation.schema.json`、`migrations/versions/0011_template_creation.py`、`edw-api/src/edw_api/documents/`、`edw-web/src/features/templates/` 和对应安全、迁移、前端测试源码；已接入 API 路由、前端入口与数据库 schema head。受控开发模板、文档类型目录、按当前授权筛选、固定版本创建、初始 AST、审计、发现投影和幂等回执均已写入源码。数据库角色及双连接竞态的隔离测试源码已补齐，但未执行。

本 Story 修改的既有文件还包括 `deployment/compose.yaml`、`edw-api/src/edw_api/{config.py,main.py}`、`edw-worker/src/edw_worker/app.py`、`edw-web/src/app/App.tsx`、`edw-web/src/features/workspace/DiscoveryPanel.tsx`、两个 fixture seed 脚本、五个 `tests/ops/` 文件和 `sprint-status.yaml` 的 Epic 2 状态块。工作区中 Story 开始前已有的其他改动不属于本 Story，提交时须逐块隔离。

用户确认新契约优先：已修订 `docs/03-数据模型与API接口规范.md` 8.1 节，明确必填 `Idempotency-Key`、`201` 的 `data` 包裹、显式 `template_version_id` 固定所选版本、旧 `template_id` 家族 ID 兼容形状和重放废弃语义；旧示例原样发送不再有效。保留受控开发样例标识。

## Spec Change Log

## Review Triage Log

- 独立安全/后端审查发现并推动修复 canonical 路由、schema head、筛选位置、幂等重放鉴权、初始版本散列/基线及最小数据库权限；复审已对这些实现给出静态 `approved`。
- 独立前端审查发现并推动修复拒绝后弹窗输入丢失和原型标题变动；复审通过。Muse Spark 1.3 Contributor 辅助静态审查提出响应校验与名称长度问题，已修复；该审查不作为运行证明。
- 既有创建示例兼容决策已由用户确认并写入规范。独立只读 API 复审未发现高/中缺陷；前端复审两项报告经主控核对：403/404 正常账户刷新不会卸载视图，失权导致卸载属于安全清理；快速创建只能从工作台进入，组件在离开模板路由后卸载，重入重置标记，故两项不成立。迁移/权限独立审查发现运行就绪探针仅检查列级 INSERT 正权限，未排除过宽表级 INSERT；已在 `edw-api/src/edw_api/main.py` 加两项负断言、`tests/ops/test_live_migration.py` 加角色断言。Muse Spark 1.3 Contributor 按实际显示名称核实模型后对该修复及规范进行了只读复审，无未解决的实质缺陷。独立审查只代表静态评估，不代表数据库测试。测试源码中的数据库竞态、回滚及 UI 用例均为 `not-run`。

## Design Notes

跨 workspace 的企业/部门/产品线模板须有明确的 workspace 可用关系，作为版本选择的授权依据；五范围标签本身不授予权限。Story 2.1 只消费受控开发目录，不实现 Story 2.4 的上传、校验、发布或废弃管理。初始 AST 供只读查看；完整双向编辑器在 Story 2.2、CAS/合并在 2.3。

## Verification

**Commands:**
- `uv run --offline ruff check`（Story 涉及的 API、Worker、迁移、fixture 与测试源码）— exit 0。
- `python -m compileall -q`（同一范围）— exit 0。
- `pnpm --filter edw-web lint`、`pnpm --filter edw-web build` — exit 0；构建处理 103 个模块。当前 Node 为 `v24.12.0`，仓库声明为 `24.20.0`，记录工具链偏差。
- `git diff --check` — exit 0；在最终暂存后还须检查 `git diff --cached --check`。
- 本次 `uv run --offline ruff check`（documents、API 组合根、0011 与安全测试源码）、`python -m compileall -q` — exit 0；`pnpm --filter edw-web lint && pnpm --filter edw-web build` — exit 0（103 模块）。
- `opencode run -m opencode-go/muse-spark-1.3-contributor --agent plan` — 已核实显示名称为 Muse Spark 1.3 Contributor 并完成辅助静态审查；独立代码审查由不同代理完成。
- 测试套件、迁移、数据库、服务、浏览器、现场及真实环境验收：均 `not-run`，不得计为通过。此处 `done` 只表示软件开发、静态检查、编译与独立审查闭环，不表示运行验收通过。
