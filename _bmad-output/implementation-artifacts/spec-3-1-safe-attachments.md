---
title: 'Story 3.1 安全上传并检查解析后的附件'
type: 'feature'
created: '2026-09-27'
status: 'in-review'
route: 'dispatch'
baseline_commit: '12afe76c6c46d858100d95534229c3d20ac0ed96'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-3-context.md'
  - '_bmad-output/planning-artifacts/epic-3-trustworthy-evidence.md'
---

<frozen-after-approval reason="用户批准的实施意图；变更须重新确认">

## Intent

**Problem:** 工作区目前只有正文图片上传与模板候选校验，没有可作为证据的附件上传、隔离解析、逐页状态与当前授权查看。声明了 `parse_ocr` 队列却没有附件任务处理，不能把图片或未解析文件误认为可信知识。

**Approach:** 增加受控附件隔离区、幂等解析任务和按页/章节/chunk 保存的来源定位及状态；对 PDF/DOCX/XLSX/图片调用隔离解析与 OCR，并在上传、处理提交、查看各阶段重验权限。工作区附件入口呈现进度、部分成功、失败和安全的来源详情，供下一 Story 的检索索引复用。

## Boundaries & Constraints

**Always:** 强制类型/签名/大小/散列/配额检查及 workspace、owner、密级、保留策略归属；不信客户端 MIME、文件名或对象 key。原件先隔离，只有受控解析结果可发布。解析子进程非 root、无网络/数据库/MQ 凭据、只读根、seccomp、受限 CPU/内存/时间/临时空间并清理。规范记录按文件散列和解析版本幂等；部分完成与页错误可见而不能冒充全量成功。任务的授权委派最小化，失权时拒绝完成后的内容暴露，保留策略不能删除正式受保护内容。

**Never:** 不重用正文图片作为文档附件；不运行测试套件、迁移、服务、容器、数据库、浏览器或实物/现场验证；这些运行验收记为 `not-run`。仅实现本 Story 附件管线，不预先声称企业扫描、知识检索或真实 OCR 效果验收通过。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 预期行为 | 错误处理 |
|---|---|---|---|
| 合法附件 | 当前授权的 PDF/DOCX/XLSX/图片 | 私有对象与散列、受限任务、页/章节/chunk/定位；逐页解析/OCR/失败状态 | 单页失败保留可核查的部分结果 |
| 恶意或超限 | MIME 不符、炸弹、穿越、宏/外链、大小或资源超额 | 拒绝或隔离，不发布下载、文本或外连 | 安全错误不泄漏对象键或片段 |
| 重试与撤权 | 同一任务重复投递、解析期间或查看前撤权 | 规范结果不重复；当前权限决定提交与读取 | 无权响应不泄漏元数据；隔离遗留按保留策略清理 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/access/{repository,policy}.py`：当前 workspace/资源权限与密级检查，上传和来源读取必须重验。
- `edw-api/src/edw_api/documents/{editor_routes,media,editor_repository}.py`：仅复用私有对象写入、散列、二次授权和拒绝模式；不能把图片路由扩充为泛附件绕开隔离。
- `edw-api/src/edw_api/task_contract.py`、`tasks/repository.py`：当前仅库存任务；扩展解析任务契约、状态与交接。
- `migrations/versions/0012_domain_editor.py`、`0015_outline_confirmation.py`：参照私有对象与不可变版本模式，新增前向附件/解析迁移，不更改既有迁移。
- `edw-worker/src/edw_worker/{app,inventory,template_validation,template_validator_process}.py`：队列已声明；复用 fencing/重试和 sandbox 模式，不复用模板解析逻辑。
- `deployment/compose.yaml`：Worker 当前未订阅 `parse_ocr`；静态声明队列/最小权限及隔离配置。
- `edw-web/src/features/templates/ProjectContext.tsx`、`src/features/tasks/TaskCenter.tsx`：X-15 上传/来源/页状态和任务状态入口；保持现有视觉布局。

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0016_safe_attachments.py`、`contracts/`：受控附件、页/chunk、任务结果与幂等键，外键、唯一键和元数据约束。
- [x] `edw-api/src/edw_api/attachments/`、`main.py`、`task_contract.py`：上传预检/隔离存储、当前授权来源读取、解析任务交接、撤权与清理策略。
- [x] `edw-worker/src/edw_worker/`、`pyproject.toml`、`deployment/compose.yaml`：受限 PDF/DOCX/XLSX/图片 OCR 解析、页级部分失败、无外联沙箱、规范结果原子写入和重试。
- [x] `edw-web/src/features/templates/ProjectContext.tsx`、`src/features/tasks/TaskCenter.tsx`、相关 API/types：真实上传、逐页状态及安全来源查看；保持既有 UI 基线。
- [x] `tests/security/`、`tests/worker/`、Web 测试源码：正反例覆盖类型/资源/重试/撤权/部分结果；只编写与静态检查，不执行套件。

**Acceptance Criteria:**
- Given 当前授权及四类合法附件，when 上传与解析，then 保存受控对象、可定位片段和逐页真实状态，重复任务不产生重复规范解析记录。
- Given 类型不符、危险负载或配额/时间超限，when 校验或解析，then 拒绝/隔离且无公开对象、外联及凭据访问。
- Given 解析提交前或来源读取前撤权，when 继续任务或查看，then 当前策略拒绝暴露结果并按保留策略处理隔离遗留。

## Implementation Notes

- 实施受控上传、私有 S3 隔离、散列和类型校验、按当前授权的页面/片段读取；解析 Worker 通过限权委派、fencing 与无网络的 bwrap/seccomp 子进程处理 PDF/DOCX/XLSX/图片，保存逐页部分状态。
- 附件解析记录独立持久于通用库存 `durable_task`；任务中心只显示本人最近 200 条候选中的前 25 条已授权记录，完整逐页信息需回到 X-15。该列表并非全量检索；本轮不以其证明原 1-6 通用任务观察链已复用。
- 24 小时清理只针对数据库没有任何附件行的隔离对象；正式/有行内容不删。调度器需独立 S3 cleaner 凭据，旧环境未应用配置；OCR 权重需离线提供到 `/opt/eid-ocr`，未提供时明确记 `OCR_UNAVAILABLE`，不宣称真实 OCR 效果。
- 已知缺口：新附件任务没有纳入通用 `durable_task` 事件/通知/取消/重试 UI；任务中心仅显示受权摘要，无法从该列表跳入逐页结果。独立质量门禁与真实集成暂不执行，此处 `in-review` 仅指候审代码，不代表各 AC 已经运行验证。

## Spec Change Log

## Review Triage Log

## Verification

**实际软件检查：** Python `compileall`、Web `npm run typecheck`、S3 JSON 语法解析及限定路径 `git diff --check` 均退出 0；早期子代理另报告离线构建/锁文件检查通过，本轮未独立复核该报告。`opencode models opencode-go --verbose` 核实 `opencode-go/muse-spark-1.3-contributor` 显示名后已调用只读辅助审查；其中一次返回可定位的清理/列表建议并已据此修订，最后一次调用未取得完整结论，不称质量门禁通过。

**待执行：** 所有测试套件、迁移、数据库/S3/MQ/服务、浏览器、实际 OCR 与现场运行验收均为 `not-run`。用户要求暂不进行质量门禁检查；静态编译不替代功能验收。
