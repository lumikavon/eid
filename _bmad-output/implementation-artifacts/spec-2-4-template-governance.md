---
title: 'Story 2.4 可复用模板版本治理'
type: 'feature'
created: '2026-09-25'
status: 'done'
route: 'dispatch'
baseline_commit: '2999633ef19d3ec190feaf0c578b3bbd8d81ebc5'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-2-context.md'
  - '_bmad-output/planning-artifacts/epic-2-controlled-authoring.md'
---

<frozen-after-approval reason="PROMPT.md 串行开发已获授权；验收来自 Epic 2 与 UX X-14">

## Intent

**Problem:** Story 2.1 模板目录仅包含不可管理的开发样例；管理员无法提交结构与规则、核验资产、预览固定版本、治理状态或查看被文档固定引用的影响。

**Approach:** 增加经当前模板管理权限校验的受限资产/规则提交、确定性安全验证、不可变版本与独立的可废弃状态；预览仅来自精确版本，发布/废弃记录审计和固定引用影响；缺少正式字体、主题或审批/规则所有者时只可标识开发样例，禁止宣称正式可用。

## Boundaries & Constraints

**Always:** 仅允许声明式章结构/检索/Prompt/Reviewer/渲染/审批引用，不执行任意脚本、HTML 或宏；压缩包/图像/文档资产严格限制大小、展开比、文件数、类型与路径，未知格式拒绝。模板家族/版本/状态/归属在同一事务与当前 ACL 下核验；既有 Document 的 `template_version_id` 不变化。管理员列表和影响计数按当前权限，不泄露未授权文档。受保护写入必须记录同事务审计；请求结果未知时不盲目重试。

**Never:** 不将 Story 2.1 fixture 擅自标为企业正式标准；不以模拟/静态检查宣称官方字体/规则、真实 Worker/数据库/浏览器或现场验收完成；不迁移或清理已有数据、不删除引用版本；不启动服务、数据库、迁移、测试套件、浏览器或实际运行环境。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 管理员导入并验证 | 声明式清单和受限资产 | 校验结构/文件/规则和预览；生成不可变版本及审计 | archive bomb、穿越、活跃内容、未知规则明确拒绝且不写正式状态 |
| 发布/废弃 | 经校验版本及当前管理授权 | 受控状态变更、新版本保留、精确版本预览及固定引用影响 | 并发状态冲突/审计不可用失败关闭；现有文档不改写 |
| 官方前置缺失 | 未配置正式字体/主题/批准的政策引用 | 标记 development-only，正式使用受限 | 不能以开发样例冒充正式模板 |

</frozen-after-approval>

## Code Map

- `migrations/versions/0011_template_creation.py`：既有只读历史；新迁移放宽仅 fixture 约束、增加受控规则/资产/审计状态，不改旧迁移。
- `edw-api/src/edw_api/documents/{repository,routes,schemas}.py`：保留创建时固定版本与现有目录；新增治理路由和授权、状态、影响数服务，审查与验证必须区分。
- `edw-api/src/edw_api/access/policy.py`：已有 `template:publish` 为资源绑定操作；新建时需要安全的、当前服务端事实派生的授权对象或已持久化的家族资源，禁止把客户端字段当授权事实。
- `edw-worker/`：确定性的隔离资产验证边界及明确状态，不在 API 请求中执行不受信任模板。
- `edw-web/src/features/templates/`：保留 P-07 视觉基准，补 X-14 管理页及真实状态/影响记录。
- `contracts/`、`tests/security/` 与前端测试源码：声明式契约、恶意压缩包/错误规则/撤权/并发/固定版本的正反例；只做源码、lint、类型与编译验证。

## Tasks & Acceptance

- [x] 设计安全声明式模板包、受限资产验证、缺失前置的开发样例/正式拒绝语义及版本状态机；固定跨工程契约。
- [x] 添加最小新迁移和 API/Worker 实现；静态核对权限、审计、不可变版本与精确版本预览，不修改既有版本或文档引用；实际迁移/运行验证 `not-run`。
- [x] 开发 X-14 与 P-07 上传管理入口；状态不靠演示 toast，错误可定位且不泄露资源。
- [x] 补测试源码；静态/编译检查与独立 `Muse Spark 1.3 Contributor` 源码审查及修复；精确暂存单独提交。运行验收 `not-run`。

## Implementation Notes

- `domain.outline` 只接受 `structure.sections[{title}]`；发布时应从已验证 manifest 的 `{id,title,mandatory}` 投影为精确版本结构，同时在不可变策略快照保留 ID/必选规则，不能直接把扩展字段塞入旧结构。已增加初版受限 ZIP manifest + PNG/JPEG/WebP 资产的 Worker 侧纯解析器 `edw-worker/src/edw_worker/template_assets.py`、JSON Schema 与负面测试源码。压缩/展开/数量/路径/链接/图像像素有界且不落盘；重编码预览图去除 EXIF/ICC。DOCX、宏、SVG、HTML 和脚本格式直接拒绝。规则 UUID 只是语法校验，**尚未**接入 API、持久化、Worker 消费、状态机或正式审批；本 Story 不得标为完成。
- 已起草 `0013_template_governance.py` 前向迁移：保留 0011 样例，允许仅开发样例的受治理不可变版本，增加家族资源/策略快照、提交时延迟触发器与受限废弃状态函数；尚未执行迁移、核实实际 DB 约束名或接入 API，不能据此宣称可用。迁移引用的 `(id,workspace_id)` 唯一索引已在 0010 定义；0011 版本行的 UPDATE/DELETE 由既有不变触发器拒绝。`template:publish` 是资源绑定授权；后续还须在提交时重新校验当前 ACL，不能放开旧目录后直接发布。未具备官方字体/政策证据，正式发布必须失败关闭。

- 后续闭环顺序：补隔离候选包/校验收据和幂等回执 → API 当前 `template:publish` 家族资源授权、受限上传/状态读取 → Worker 从不可变私有对象取包、校验摘要并回写有界报告（不得授予目录表直接 SELECT） → 短事务重新锁工作区和家族、核验报告摘要与规则/字体前置、写入不可变版本/状态/工作区/审计/回执 → 受控废弃及历史引用影响 → X-14 UI 和测试源码。现有解析器/迁移并未完成这些步骤。

## Review Triage Log

- 高风险只读设计核验列出 fixture-only 约束、资源绑定授权、归属/锁顺序、Worker 隔离、缺正式前置及目录/AST 联动风险，已作为后续实现约束；未据此宣称代码审查通过。
- 按已核实的 `opencode-go/muse-spark-1.3-contributor` 调用 `opencode` 审查初版解析器两次，均以 `unknown certificate verification error` 退出；未禁用证书校验。后续同模型对未执行的 0013 迁移和解析器完成只读审查：指出资源权限函数缺少自身 ACL、策略归属/状态约束、索引、manifest 摘要、动画/内存上界等；已补家族/版本联合 FK、家族不变触发器、延迟策略存在性检查、索引、时间顺序、规范化 manifest 摘要、拒绝动画与更严内存上界。最终局部复审还发现 Worker 专用拒绝码被 `ValueError` 捕获改写，已将 `PackageRejected` 原样传播并补 APNG 拒绝码测试源码（未运行）；其主张 0011 fixture 可以 UPDATE 为治理行与既有 `template_version_immutable` 更新/删除触发器冲突，该项不成立。后续测试源码审查建议单列 `INVALID_IMAGE` 和 manifest 资产清单不一致案例，已补源文件断言，仍未运行。跨工作区访问仍须后续 API 当前资源授权，规则引用/报告真实性须由 Worker 与提交门禁闭环。审查称 0011 外键目标直到 0013 才存在，经查 0010 已有 `access_resource_observation_workspace_key` 唯一索引，此项为误报并撤销重复索引。两次独立 Pi 解析器审查超时；**Story 2.4 审查门禁仍未通过**，不得提交或进入 2.5。

## Verification

- Worker 解析器、测试源码及新迁移的 Ruff、Python `compileall`，模板包 JSON 语法和 `git diff --check`：通过；迁移只做源码检查，未执行。
- 自动/手工测试、迁移、数据库、服务、Worker、浏览器及现场全部 `not-run`；解析器运行行为未经验证，模板治理实现未完成。

## 本轮后端接续（2026-09-26；未完成）

- 新增 `governance_repository.py`、`governance_routes.py`、`governance_schemas.py`：受限流式 ZIP 上传、候选状态与规范化图读取、显式开发版本发布、受控废弃、固定引用的权限过滤分页。创建/发布要求 `Idempotency-Key`，201/data；重放仍重查当前资源授权。API 入口已注册，但未启动或调用。
- 0013 新增不可变候选包、租约校验状态、上传/动作幂等收据、家族/候选/版本联合外键。Worker 通过受限 SECURITY DEFINER 领取与完成函数重查当前上传者授权，未取得模板表直接读取权限；废弃函数另行核验 eid_api 身份、当前 actor 家族权限，按工作区→模板根顺序加锁。迁移未执行。
- 新增 `template_validation.py` / `template_validator_process.py` 并接入 Worker supervisor 的独立进程与健康信号；原包 SHA-256、manifest canonical SHA-256、规范化资产 SHA-256 与收据绑定。API 发布短事务重查家族、base version、版本标签和摘要后写入版本/策略/状态/审计/回执，不改文档固定引用。
- 目录已新增治理资源及策略快照投影，并按当前 resource:read 验证；开发标记保持为 true。API/Worker 默认 revision 与 Compose 更新为 0013。只修改配置源码，未部署、未迁移，也未检查远端实际状态。
- 修正分页先扫描再过滤可能暴露未授权 ID 的问题：候选和影响页均在 SQL LIMIT 前按当前资源权限过滤。冻结家族范围以避免首个版本发布前切换 personal/non-personal 造成归属漂移；创建版本时间使用 clock_timestamp，避免等待锁期间事务起始时间倒序。
- 未接入批准的规则注册表，因此任何非空外部规则 UUID 均拒绝为 RULE_REGISTRY_UNAVAILABLE；不能把合法 UUID 当作已批准规则。正式发布继续失败关闭，开发模式只允许空规则引用；今后接入正式规则必须另行建立权威所有者/版本核验。
- 新增 `tests/security/test_template_governance.py` 测试源码，涵盖明确布尔确认、摘要错配、未验证状态、资源绑定授权、幂等重放撤权、正式模式拒绝与权限过滤分页；解析器补五类非空规则 UUID 拒绝案例。全部测试未执行。
- 本轮最终 Ruff、Python compileall、模板包 JSON 语法、git diff --check 均通过；未运行任何测试、服务、Worker、数据库、迁移、浏览器或现场检查。
- 接续后前端 ESLint、TypeScript 与 Vite 离线构建通过（仅有既有大分块警告）；Python Ruff/compileall 与 JSON 语法通过。指定显示名已通过 `opencode models opencode-go --verbose` 核实为 `opencode-go/muse-spark-1.3-contributor`，本轮 `opencode run --pure -m ...` 成功只读审查，无高风险发现。审查建议静态核对 fixture_owner 约束：该约束来自 0011 中 `fixture_owner text NOT NULL CHECK` 自动命名，并非审查回复误称的 0012。所有运行用例与迁移仍为 `not-run`，不计为通过。

### 未闭环事项与审查阻塞

- 已通过 `opencode models opencode-go --verbose` 核实 `Muse Spark 1.3 Contributor` → `opencode-go/muse-spark-1.3-contributor`。首次本轮只读后端审查在 240 秒超时，仅取得读取记录；一次有界重试退出 1，`unknown certificate verification error`。未禁用证书校验、未替换模型，未取得最终审查结论。日志：`.local/story-2-4-opencode-backend-review.jsonl`、`.local/story-2-4-opencode-backend-bounded.jsonl`。
- 当前解析子进程只有去环境凭据、可信模块路径与 POSIX CPU/地址空间/输出文件限制；这不等于独立网络/文件系统安全沙箱。仍须源码审查其同 UID 文件访问及 stdout/stderr 捕获上界，不得宣称完整解析隔离已验收。
- 后续接续（2026-09-26）：已补 X-14 管理界面、P-07 上传入口、原幂等标识核对、前端治理 API 契约和测试源码；新增仅含 manifest.json 的受限 ZIP 章节编辑器，含章节顺序/必选状态。含图片的包仍需上传已有 ZIP，UI 只预览验证后的固定结构与资产元数据，不冒称正式渲染。未执行任何运行/测试套件验证。

### 独立复核待修（2026-09-26）

三个独立源码复核层指出以下问题；不能以先前一次 `opencode` 无高风险结论替代复核，也不能在未修复时进入 2.5。逐条初步裁决：

| 来源与定位 | 裁决和证据 | 状态 |
|---|---|---|
| blind `template_assets.py:168` ZIP 前后缀 | low：ZipFile 可接受附带非 ZIP 字节；已增加前缀/EOCD/尾部约束及测试源码。 | 源码修复；运行 not-run |
| blind `template_validator_process.py:10` 同 UID 文件/网络权限 | high：原实现无文件系统/网络边界；按用户选择新增 bubblewrap rootless 命名空间、只读 Python/解析器挂载、无网/临时目录，并在领取租约前做未来运行时预检，失败关闭；源码已补，容器/userns 可用性未运行核验。 | 源码修复待核 |
| blind `template_validation.py:29` 无界 capture_output | medium：父进程内存上界不受输出检查保护；已改输出到临时文件并设子进程文件大小限制，仍未运行验证。 | 源码修复待核 |
| blind `governance_repository.py:199` 列表读取完整报告 | medium：100 项可能导致大报告传输；列表 `_candidate(include_report=False)` 已不读取报告，仍未运行验证。 | 源码修复待核 |
| blind `0013_template_governance.py:113` 无持久化配额 | high：授权管理员可无界保留 ZIP/报告，资源耗尽风险；已在工作区排它锁下加入 128 候选上限与索引，未运行数据库验证。 | 源码修复待核 |
| blind `governance_repository.py:22` 旧 fixture 家族不可治理 | maybe-false：既有样例不允许冒充正式标准；若要求继承同家族而非新建，需明确转换规则和权限。 | 不擅自迁移 |
| blind `TemplateGovernance.tsx:22` 旧候选作为 base | medium：多个历史发布候选可被选择并导致可预见的 409；API 新增当前 head 回执并仅允许选择与 head 相同的候选，尚未运行核验。 | 源码修复待核 |
| blind `TemplateGovernance.tsx:24` 未知结果重载丢键 | high：按当前授权查 committed receipt、sessionStorage 仅保存键/非敏感元数据；unresolved 可重选同一 ZIP 或同命令用原 key 重试，服务端摘要绑定防重复。表单生成 ZIP 提交前要求下载同一包备份；若原包未保存且一直无回执，则保持失败关闭并需管理员介入，不换键重提。 | 源码修复；运行 not-run |
| blind `TemplateGovernance.tsx:24` 明确冲突后 pending 不解除 | medium：原流程不能再导航；明确错误时已清 pending，仍未运行验证。 | 源码修复待核 |
| blind `governance_repository.py:258` 必选章标志未进初始 AST | medium：不可变 manifest 保留 ID/mandatory，但目前新建只取标题；2.6 须消费该快照才能实现必选检查，不得先称 2.6 已满足。 | 2.6 依赖项 |
| blind `governance_repository.py:42` 审计无前后状态/引用影响 | medium：废弃操作已记 active→deprecated 与原因；影响列表按当前授权另行读取，不记录全局非授权计数。 | 源码修复待核 |
| blind `tests/security/test_template_governance.py` 队列/迁移/恢复覆盖 | medium：已补队列 claim/finish、沙箱预检、审计、回执授权及资源上限的测试源码；迁移实际执行与浏览器恢复未验证，不能计为通过。 | 源码修复待核 |
| edge `TemplateGovernance.tsx:29` fixture 触发治理 404 | medium：接口仅查询受治理版本；已恢复只对匹配受治理候选显示入口。 | 源码修复待核 |
| edge `governance_schemas.py:135` 无效 base64 抛未包装异常 | medium：可能变 500；已转 ValueError 并补 503 断言源码，未运行。 | 源码修复待核 |
| gap `documents/repository.py:32` 新治理可见性无正反例 | medium：fixture 测试未覆盖新分支；已补可读/撤权两侧测试源码，未运行。 | 源码修复待核 |
| gap `template_validation.py:52` 队列交接无验证 | medium：已补隔离软件层的 claim/finish 调用与租约身份测试源码，未运行。 | 源码修复待核 |
| gap `relay.py:225` 双健康信号无验证 | medium：已补独立 validator 健康信号测试源码，未运行。 | 源码修复待核 |

按用户选择已在源码加入 bubblewrap 失败关闭沙箱和启动前预检，Dockerfile 增加依赖；容器内 namespace 支持与实际校验仍 `not-run`。前端 ESLint/TypeScript/Vite 构建、Python Ruff/compileall、契约 JSON 语法及 diff 检查通过；未执行测试套件、服务、数据库、迁移、浏览器或现场验证。指定 opencode 模型最终增量只读复核未发现明显的原键重试/备份问题；早先的超时及误报已分开记录。独立复核的真实源码缺陷已修，旧 fixture 家族治理不在本次目标，mandatory 规则仍需 2.6 消费。Story 软件门禁可关闭，但真实行为/迁移与容器沙箱可用性均不计为通过。
