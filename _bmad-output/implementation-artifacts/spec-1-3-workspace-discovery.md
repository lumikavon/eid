---
title: 'Story 1.3：查找实际工作区记录与保留集合'
type: 'feature'
created: '2026-09-15'
status: 'done'
delivery_scope: 'software-static-only'
runtime_verification: 'cancelled-by-user-not-verified'
story_key: '1-3-workspace-discovery'
epic_id: 'epic-1'
baseline_commit: '2680247ab3a45bef9246d23328ce18ffe597bdb8'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-1-context.md'
  - 'deployment/environments/seadee-develop.yaml'
  - 'docs/remote-development.md'
---

## 当前开发与验证边界（2026-09-21）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件的执行安排统一受[开发与验证规则](../planning-artifacts/development-validation-policy.md)约束。下文涉及启动、部署、迁移、fixture、功能测试、浏览器实测、联调、性能和故障演练的条款保留为待执行验收要求，当前暂停执行并记录 `not-run`；其中静态检查与编译可按规则单独执行。历史证据按原日期保留，不代表本轮通过或继续运行的授权。


## 当前执行范围（2026-09-21）

最新用户指令“取消实际环境验证，继续”：本 Story 的实际环境验证从当前交付范围取消，不再作为本次软件交付收尾的等待项。原 D01–D12 的运行方法和历史结果保留用于追溯，取消项记 `cancelled-by-user / not-verified`，不得记为通过。继续完成源码实现、独立静态审查、必要修复及编译；仍不运行测试套件、服务、数据库、浏览器或部署。最终状态须明确区分软件交付与未经验证的运行行为。

依用户最新指令与根目录 `AGENTS.md`，本 Story 继续软件开发、静态代码检查与编译；不执行测试、浏览器探针、实物/硬件/现场验证，不启动或使用实际环境进行功能实测。下文涉及运行验收的历史计划保留，但当前不执行，也不视为已通过。代码修改后使用 `opencode-go/muse-spark-1.3-contributor`（显示名 `Muse Spark 1.3 Contributor`）作辅助静态审查，其建议同样受上述限制。

Story 的 `done` 仅表示用户收窄后的软件交付完成：实现、独立静态审查、问题修复和编译已完成。实际环境验证已取消，不作为等待项，也不算通过；原运行 AC 仍无当前运行证明。前置远端支持与 Story 的提交归属已按开工差异拆分，提交结果由主代理核验；本次不启动 1.4。具体记录见 `story-1-3-software-review-2026-09-21.md`。

<frozen-after-approval reason="user-owned intent from PROMPT.md autonomous Epic 1 authorization and current approved planning">

## Intent

**Problem：** 已有真实登录、项目选择和当前授权，但首页尚无实际记录发现能力；全局搜索、收藏、参考资料、回收站仍不能打开实际集合。

**Approach：** 为现有受控资源建立最小持久化发现投影，通过同一当前授权集合提供首页、文档列表、搜索、项目详情及保留集合。用户能够找到并打开正确记录，在允许时收藏、取消收藏或恢复列表可见性；初始化数据可以为空，但必须以真实 API/PostgreSQL fixture 完成正反验收。

依赖 `1-2-current-access`；工作工程为 W/A。追踪 FR-2、FR-3、FR-47，NFR-1、NFR-8、NFR-16、NFR-17，C-1，AD-7、AD-16。首页质量指标的完整行为归 9-1，企业项目映射、真实用户验收和生产负载分别归 13-2、13-3、13-4。

## Boundaries & Constraints

**Always：** 每次列表、详情、集合写入、计数和存储读取均重新核验数据库中的主体、成员、角色、项目/客户/产品/部门/owner/审批状态/有效期及密级。客户端 ID 只定位对象，参与关系、收藏或历史游标都不授予访问权。SQL 筛选与既有 `authorize` 的当前判定保持一致；同一响应的行、数量和字节取自同一授权/筛选口径。访问撤销后清除全部相关受控缓存、选中详情和待用操作，旧响应不能回填。

私人收藏归当前主体；恢复要求当前可见目标、当前操作权限及显式有效策略共同成立，缺任一项拒绝。可声明隔离开发 fixture 政策，沿同一生产判定函数验证允许与拒绝；真实模式缺政策仍拒绝。恢复仅改变发现可见性，保留归档状态、正文版本、head、审批、发布及历史。写入状态、幂等回执和审计在同一短事务提交；审计失败不得留下部分成功。

开发与运行验收显式设置 `EID_ENVIRONMENT_CONFIG=deployment/environments/seadee-develop.yaml`，服务位于已授权并完成切换的 `seadee-develop:/opt/eid`（依据 `docs/remote-deployment-path-authorization.md`）；原 `/opt/docker/eid` 保留。任何迁移或 fixture 写入前验证实际 SSH 目标、专用目录/owner、Compose 项目、网络/卷/容器、数据库 `eid_local_dev` 与 marker `eid-local-dev-v1`；名称相同本身不证明隔离。只使用主代理完成审查的远端环境接入；证据绑定当前远端容器和候选源码。

保留原型 P-01 四 KPI、四卡片、四最近标签和右栏，以及 P-00 搜索/集合/存储位置。布局、层级、尺寸、间距、字体、颜色、圆角、阴影、边框及原始 glyph 按 DESIGN/EXPERIENCE；六导航、64px 顶栏、266px 侧栏、1180/1181 桌面滚动边界不变。原型 SHA-256 保持 `C876D444167A999D820BFC27D99C59D091C7AC885E93BC89CDF3B65EA1B4198E`。仅验证本 Story 改动控件与具名状态；完整 viewport/zoom/control 基线由 7-5 负责，哈希不能替代视觉证据。

**Never：** 不实现正文 AST/编辑/创建、模板治理、Review、模型推荐、知识语义检索/Evidence、上传下载、任务传输/fence/SSE；不把元数据记录冒充这些功能完成。无公开分享、物理删除、清理既有数据或自定保留期限；不覆盖已有 fixture/身份/密码/策略以制造通过。不启动本机 Docker，不复用旧本机 runtime manifest，不绕过隔离守卫，不接触企业/生产数据、付费模型或执行 Push。初始质量、审校、生成指标缺来源时是未评估/未采集，不能填样例分数、零问题或假同比。

## I/O & Edge-Case Matrix

每行的测试 ID 对应下方具名验证；列中的允许/拒绝均需独立断言，不以一条笼统 PASS 代替。

| 场景 | 输入 / 状态 | 预期输出 / 行为 | 错误与恢复 | 验证 |
|---|---|---|---|---|
| 当前授权集合 | 两项目、多 owner/参与者/状态/密级，含失效、停用及不可见反例 | 列表、详情、计数、字节仅来自当前允许记录；无权记录标题/ID/数量不外泄 | 未知与不可见对象同一安全响应；系统管理员也受属性/密级限制 | D01 `authorized_projection_matrix`，真实 PG + API |
| 四标签与交集 | 最近、我创建的、我参与的、我的收藏，叠加当前项目/类型/状态 | 所有筛选 AND；创建者/参与者/收藏均取持久关系；分页及总数相符 | 无匹配保留筛选并允许重置，不显示其他集合填充 | D02 `tabs_filters_counts`，API + 浏览器 |
| 搜索与定位 | Enter 输入文档/知识/功能关键词，选择结果或项目/卡片行 | 返回真实类型、可见上下文及稳定 ID；打开自己的详情，返回保留允许筛选 | 空白不发搜索；无匹配独立空态；未知路由不能落到默认记录 | D03 `search_navigation_context`，真实 HTTP + 浏览器 |
| 有界游标 | 首/末页、相同更新时间、超过一页记录，非法/跨项目/跨筛选游标 | 稳定排序、有限页，数据未并发变化时续读不重复遗漏；每页重新授权，总数不是当前页长度 | 非法/错筛选游标 422；授权 epoch 变化使游标失效并从首页重读，旧游标不扩权 | D04 `cursor_boundaries`，契约 + PG |
| 失序与切换 | 搜索 A 慢于 B；切换项目、返回、退出或 epoch 更新时旧请求迟到 | 当前请求/主体/项目胜出；清旧详情、游标及可操作数据 | 已取消请求和迟到成功/失败均不能覆盖新上下文 | D05 `latest_request_wins`，受控延迟浏览器测试 |
| 页面读状态 | 冷加载、空库、空筛选、API 503/超时、离线、401、工作区撤权 | 持久且不同的 loading/empty/error/offline/reauth/forbidden；无示例行/KPI | 503 可重试，401 重认证，确认撤权立即清数据；局部目标无权不伪称整个项目无权 | D06 `discovery_read_states`，客户端单测 + 浏览器 |
| 收藏写入 | 当前可见记录，当前用户添加/取消自己的收藏，重复提交及刷新 | 显式目标状态持久化，其他用户收藏和记录内容不变；返回回执与实际状态 | 未确认成功前不乐观报成功；同键异载荷 409；失效权限不返回历史受控成功 | D07 `favorite_persistence_idempotency`，真实 PG/API + 刷新浏览器 |
| 恢复可见性 | 当前授权的 recycled 文档，已声明合成政策；归档记录可读 | 恢复仅令发现可见性变为 visible；ARCHIVED 生命周期/版本/引用/内容保持不变 | 无政策、真实模式缺政策、错类型/无权/陈旧 revision 拒绝；不存在永久删除入口 | D08 `restore_policy_visibility_only`，正反策略 + PG + 浏览器 |
| 原子性与竞态 | 收藏/恢复执行前撤权，重复键、并发目标状态、审计写失败 | 只有符合当前权限/期望 revision 的事务提交；状态/回执/审计一致 | 审计失败 503 并全回滚；冲突 409 后重新读取再确认，网络未知结果核对原请求 | D09 `collection_atomicity_and_races`，PG 事务/故障注入 |
| 首页数据与未来项 | 真实文档/项目，尚无 Review/模板/生成/质量/推荐数据 | 四区域完整；可用 More 去实际过滤列表；未来项显示持久原因和明确 owner | 不用随机建议/演示成功 toast；无分母、无指标来源不显示 0/100% 或同比 | D10 `home_truthful_panels`，API + 浏览器 |
| 存储口径 | 可见/不可见、visible/recycled 元数据及未知容量 | 以当前授权集合的实际可计量数据计算字节，标口径/时间；容量未知无假百分比 | 不把 metadata 计量说成全部 S3/物理磁盘占用；无计量来源显示未统计 | D11 `storage_scope_and_provenance`，真实 PG 期望值对照 |
| UI 与时间证据 | 固定浏览器/字体/viewport/fixture 和当前远端候选 | C01/C04–C07/C09 与 X-17/X-18 改动状态有 B/R/S 登记、截图/键盘证据；记录首页/列表基线耗时 | 差异逐项处置；不自造像素容差或把开发计时称生产 NFR 达标 | D12 `discovery_fidelity_and_baseline`，截图审阅 + 实际计时 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/access/repository.py:33` `load_current`、`:58` `checked`：复用工作区共享/独占锁与当前事实；`:113` `workspace_page` 已有有界授权项目分页。图索引行号已落后，以上位置已用当前文件核对；不能照旧 snippet 修改。
- `edw-api/src/edw_api/access/policy.py:60` `authorize`：当前纯 RBAC/ABAC/密级判定；`:15` 现有公共 `workspace:read/resource:read/inventory:read`。收藏是当前主体的私人关系，不能改资源 ACL；恢复的配置规则复用当前 `document:edit` 等明确操作，不新发明管理员通行权。
- `edw-api/src/edw_api/access/routes.py:93` 项目列表/详情，`:121` 受控资源详情：保留旧接口兼容；`db.py:11` 验证实际 API DB 身份；`main.py` 复用 Bearer、结构化错误及路由装配。
- `migrations/versions/0003_current_access.py:32` `access_resource` 是权限元数据，并非 DocumentVersion/知识引擎；`:43` `access_audit` 可追加审计。`0006_api_write_only.py:10` 已撤去 API 对审计/失效/delegation 的 SELECT；不重新授予这些无关读取权。
- `edw-web/src/app/App.tsx:18` 严格完整路由与 ID 校验，`:38` 身份 generation，`:89` 拒绝清理，`:137` 当前 readOnly 搜索与未开放集合；新增数据面必须进入同一清理边界。
- `edw-web/src/app/AccessPanel.tsx:14` 当前 actor/workspace/epoch Query key，`:38` 项目切换，`:58` 当前资源权限详情；保留成员管理/原资源深链并为发现详情复用其授权上下文。
- `edw-web/src/app/access-api.ts:15` 有界 JSON、超时、Bearer 与结构化拒绝；`api.ts`/`http/bounded-json.ts` 复用客户端传输约束，新增客户端不能接收无界数组/未知 schema。
- `edw-web/src/app/prototype.css` 是已提取视觉基础，`workspace.css` 为当前补充。原始 `docs/prototype/index.html` 只读；首页源锚点见 DESIGN 的 P-01、EXPERIENCE C01/C04–C09/X-17/X-18。
- `tests/ops/test_live_access.py:29`、`:34` 是隔离校验后唯一 schema、真实角色和事务回滚模式；`tests/ux/access.spec.ts:35` 为真实 PKCE fixture 登录；`tests/security/test_current_access.py`/`tests/contract/test_access_routes.py` 保留当前授权回归。
- `scripts/seed_access_fixtures.py` 与 `scripts/verify_local_environment.py` 正由远端适配工作更新；`environment_state_directory` 用于当前环境收据。实现前吸收主代理交付，不覆盖在途修改或把 `.local/access-fixtures.json` 认作远端身份依据。

## Tasks & Acceptance

当前软件交付清单：

- [x] 契约、授权投影、迁移源码及原子集合命令实现与静态审查。
- [x] Web 发现页面、登录返回路径、筛选冲突拒绝及旧数据清理实现与静态审查。
- [x] 契约、安全、fixture、并发、交互和 UX 回归用例源码检查；本轮未执行测试。
- [x] TypeScript、ESLint、Vite、Ruff 和 Python 编译检查；指定 Muse 辅助审查实际返回。
- [x] 修改备份、归属清单、独立复审及取消运行验证的记录。

下列原清单保留完整运行验收定义；未勾选表示运行行为未验证，不表示当前软件任务未完成。取消范围不伪装成运行通过。

**Execution：** 依赖顺序执行；安全、数据库授权、迁移和事务修改交 `eid_high_risk`，独立审查由主代理派新 `eid_reviewer`。下列框表示完整任务验收，未勾选不表示源文件尚未实现；运行相关步骤受顶部最新执行范围限制。

- [ ] `contracts/discovery.schema.json`、`edw-api/src/edw_api/discovery/schemas.py`：冻结列表/详情/summary/search/集合命令的 schema、错误、分页及严格输入，加入 `tests/contract/test_discovery.py` 校验共同向量，先定义 D01–D11 的契约。
- [ ] `migrations/versions/0007_workspace_discovery.py`：在当前 0006 head 上只新增实际使用的发现元数据、参与关系、主体收藏状态、恢复策略及窄命令回执；稳定外键/唯一约束/有限字段/游标索引。API 仅取得所需读取、个人状态及可见性更新、回执/审计追加权限；Worker 无新表直接读写权，正文/head/ACL/审批/发布 grants 不变。
- [ ] `edw-api/src/edw_api/discovery/repository.py`、`policy.py`：实现复用当前事实的授权投影、集合命令与审计事务；D01/D02/D04/D07–D09/D11 覆盖查询语义、策略缺失拒绝、角色上限、并发和回滚。
- [ ] `edw-api/src/edw_api/discovery/routes.py`、`main.py`：装配最小 REST 查询/详情/search/收藏/restore 入口，统一拒绝、不泄露 SQL/秘密；保留 `/api/v1/access/*`。`config.py`、`scripts/verify_readiness.py` 及实际 schema 检查入口同步新 head/必要 grants，不降低原守卫。
- [ ] `edw-web/src/app/discovery-api.ts`、`discovery-api.test.ts`：实现严格有界响应、当前上下文核对、取消/失序、安全错误及集合命令相关 ID；D04–D09 的客户端负例不依赖真实网络时序。
- [ ] `edw-web/src/features/workspace/DiscoveryPanel.tsx`、`discovery.css`、`edw-web/src/app/App.tsx`、`AccessPanel.tsx`：接入首页四 KPI/四卡/四标签/右栏、项目文档/项目详情、搜索和 X-17；所有详情真实 ID 定位，路由/项目/epoch/会话变化清控。保留账户/成员管理入口、壳层及已有资源深链。
- [ ] `scripts/seed_discovery_fixtures.py`、`tests/ops/test_discovery_fixture_safety.py`：读取远端 selector/当前环境身份收据；仅追加本 Story 专有且有 owner/version 的合成记录/政策；重复运行校验漂移并拒绝覆盖。`scripts/seed_access_fixtures.py` 若需 schema head 兼容，仅在远端适配交付后最小更新，不修改其身份归属语义。
- [ ] `tests/security/test_discovery.py`、`tests/ops/test_live_discovery.py`：落实 D01/D02/D04/D07–D09/D11；真实隔离 PG 验证迁移、API 角色、Worker 拒绝、状态/审计/回执同事务及当前权限，不能只靠 mock 查询返回值。
- [ ] `tests/ux/discovery.spec.ts`：以远端真实 Keycloak/API/PG 走 D02/D03/D07/D08/D10，另用明确响应延迟/拒绝注入覆盖 D05/D06；测试反向导航、键盘标签/行操作、刷新持久性、跨项目与会话清理。
- [ ] `_bmad-output/implementation-artifacts/story-1-3-validation.md`、`story-1-3-evidence/`、`README.md`：逐行记录 D01–D12 实际结果、fixture/策略口径、迁移与回退、B/R/S 差异、远端候选绑定和计时；填完整 File List。由主代理完成独立审查、必要修复/复验、Story/sprint 同步与单 Story 提交后才能进入 1.4。

**Acceptance Criteria：** 保留来源 Story 三项 AC 的全部子句，拆为最多五个可观察结果。

1. **Given** 实际可见与不可见记录及不同 owner/参与/状态/收藏，**when** 使用首页、四标签、搜索、项目和卡片 More，**then** AND 筛选、游标、数量、存储口径及打开的 ID/上下文一致，当前权限以外数据不泄漏。**验证：D01–D04、D10–D11 的实际 PG/API 与导航断言。**
2. **Given** 搜索/详情请求乱序或切换项目、返回、退出、撤权，**when** 旧请求完成，**then** 只显示当前请求上下文，旧数据与操作不会复活。**验证：D05 浏览器延迟响应与 D01 当前权限反例。**
3. **Given** 空记录、失败、离线、过期会话或失去成员关系，**when** 页面/集合加载，**then** 持久区分各状态，提供适用恢复，绝不填入样例或泄露不存在/无权对象的区别。**验证：D06 具名状态矩阵及浏览器截图。**
4. **Given** 收藏及 retained/recycled 记录，**when** 当前授权下设置收藏或依明确策略恢复可见性，**then** 只有目标关系/可见性和相应审计/回执原子持久化；历史/归档/正文不变，拒绝和未知结果不假报成功。**验证：D07–D09 真实 PG/API/刷新及故障/竞态正反测试。**
5. **Given** 固定 UI 环境与当前远端候选，**when** 复核 Story 改动面及首页/列表操作，**then** P-00/P-01/X-17/X-18 按批准视觉与交互契约登记差异并记录实际基线时延，未来质量/推荐能力保持准确未评估/未开放。**验证：D10/D12；不认证 7-5 全量视觉或 13-4 生产数值。**

## Design Notes

### 最小数据与投影语义

- 发现记录必须 FK 到 `access_resource`，保留其 ID、workspace 和全部授权属性为真相。增量元数据仅含实际检索所需的类型、创建者/时间、更新时间、文档类型、记录生命周期、可选有来源的版本标识、可见性及 revision；参与关系和私人收藏独立保存。未注册的 `kind=policy` 权限验收资源不伪装文档。没有正文的记录明确是元数据详情，不能展示旧原型正文；正文/版本编辑留待 2-1–2-3。
- `recent` 按实际 `updated_at DESC, resource_id DESC`，`created` 另限定 `created_by=current actor`，`participating` 另限定实际参与关系，`favorites` 另限定当前 actor 的收藏关系；权限过滤始终在这些关系之外共同约束。普通文档视图排除 recycled，回收视图仅含 recycled；ARCHIVED 为只读生命周期，不等于 recycled。参考资料为已注册 knowledge/reference 元数据，不实施来源正文检索或 Evidence。所有查询按当前 workspace 限定；全局搜索覆盖当前已选项目中的文档、知识元数据及允许功能，并明显显示项目范围。
- 首页“本周新建文档”按 UTC 周一 00:00 起的实际创建时间计算并展示时间窗/定义；其余审校、AI 字数、质量均分无权威来源则数值 `null` 和持久原因。待办文档使用当前可见尚待作者处理的持久 DRAFT 元数据，不创建 Task；最近项目来自当前获准项目及实际活动时间，无活动则说明。审校提醒/模板快捷区无对应业务数据时保留区域和原因，More 不制造目标或成功。快速新建保留五入口/完整类型说明，创建归各 owner；推荐换一批/使用/创建未具备依赖时明确不可用（2-1/3-4），不做随机模拟。
- 存储先提供确有来源的计量：初始可对当前授权记录的持久元数据字段用 PostgreSQL 实际字节计量，显示“可见记录元数据占用”、计量时间与定义；不表示 S3 附件或物理数据库总量。计量不重复参与/收藏 join，同一 record 仅一次，recycled 是否计入在视图筛选中显式标示。附件/总体配额尚无来源为 `null`，无比例进度；3-1 引入文件后再扩展口径。D11 直接从同批 PG 字段计算期望值，不能靠客户端估算标题字符数或 fixture 手填容量。

### 查询与写入契约

- 建议最小族：`/api/v1/workspaces/{wid}/discovery`（列表/summary）、`/discovery/{resource_id}`（元数据详情）、`/search`（只读 POST，关键词在 body）、`/favorites/{resource_id}`（显式设置 favorite 的 PUT）、`/recycle/{resource_id}:restore`（POST）。项目选择继续使用现有 access 接口，新增项目详情从当前 DB workspace 属性及发现摘要组成。函数搜索是白名单内部路由目录，按当前 workspace 能力过滤；无外部 URL、无 arbitrary redirect。
- schema 先冻结列表核心 envelope：`{data:{items,total_count,next_cursor,context}}`；summary/详情定义独立严格字段，`context` 保留当前 actor/workspace/policy epoch，ID/UTC 时间严格校验。页大小默认 20、上限 50，单页编码与客户端限制同时测试；关键词 trim 后 1–128 字符、禁止 NUL，枚举/UUID/日期/游标严格验证，额外 actor/scope 字段拒绝。游标绑定规范化筛选、主体/项目/epoch 和稳定排序位置，有长度/结构上限；它只续页，不是授权凭证。每页重新授权，跨页记录变化时允许刷新重读，不承诺跨请求历史快照。SQL 参数化，并以有限查询/statement timeout 保证失败可恢复。
- 搜索词只留当前会话内存，避免进入 URL/普通日志/浏览器持久存储；Back 保留内存中仍允许的筛选/选择，重新登录后重新取数。Query key 至少包含 actor/workspace/epoch/视图/筛选/游标，请求取消与 generation 双重约束迟到结果。详情返回的资源和上下文必须与请求一致。
- 收藏属于当前 actor，`resource:read` 合格后只可修改自己的状态。恢复仅对配置政策声明支持的记录类型，额外要求该类型的已有当前操作许可；本地合成例采用当前 `document:edit` + 自有 document + 明示 `restore_visibility` 政策。政策绑定 workspace、版本、环境级别与 fixture 归属；不能因环境变量“测试模式”就放行。真实模式未配置/无效政策、非 fixture 套用测试政策、错类型均拒绝。
- 所有变更带 `Idempotency-Key` 和期望状态 revision；恢复另核对当前政策版本。独立窄回执绑定 actor/workspace/操作/目标/规范化载荷散列；同键同载荷先重验当前权限再返回同一操作身份，同键异载荷 409。已发生后续变化时界面重新读取当前状态，不用旧回执覆盖它。重放不重复变更/审计。服务端锁内核验权限、revision 和政策，与状态/回执/审计一次提交；不为本 Story 引入 Task/Outbox 调度器。
- 审计沿用 `access_audit` 的 append-only 路径，记录 actor/target/workspace/action、实际前后收藏或可见性、revision、政策版本、request/trace、时间及成功结果。授权拒绝保留安全关联诊断；不写敏感搜索词或原文。回执读取不要求恢复 API 的历史审计 SELECT 权限。

### 数据保护与回退

新迁移仅 expand，不重写 0001–0006 或清库；真实验收包含前一 head → 新 head 保留数据，以及唯一隔离 schema 的空 → head 并事务回滚。回退为保持新表/数据并使用经验证兼容的前一应用候选或 forward fix，禁止自动 downgrade/drop/reset。fixture 使用独立 owner/version 标记和新记录，已有不匹配项 fail closed；测试仅回滚当次独立事务，不能清理既有企业/项目记录。

本文件基于当前完整 PRD/架构/UX/Epic 和上个 done Story 阅读生成。未发现需重新定义产品/安全政策的意图缺口；缺真实企业政策已有显式拒绝边界。远端环境接入、部署和最新 candidate 验证是主代理并行前置工作，尚未由本准备任务执行或认证。按 PROMPT 的无人值守 Story 准备授权保持一个完整 Story，完整 AC/边界矩阵优先于技能参考篇幅；不省略审查或恢复门禁。

## Verification

**当前仅执行静态检查和编译。** 下列包含运行测试、迁移或现场访问的原计划暂不执行；历史执行证据按原日期保留，不补称本轮通过。最新修复的检查、编译及辅助审查分别登记。

### 当前执行清单

只执行源码/契约审查、Ruff、前端 lint/typecheck/build 及 Python 编译检查，并记录命令、退出码和范围。执行前检查脚本及构建钩子，不能隐式启动服务、迁移、fixture 或测试。代码修改后的 opencode 辅助审查遵循统一规则，未执行的测试建议不计为通过。

### 暂停的原运行验收计划

以下原清单整体不再作为当前执行步骤；其中静态检查和编译仅按上面的独立清单执行。下列命令/路径均为后续计划，不是已执行证明。使用仓库固定 Python 3.12.14、Node 24.20.0、pnpm 10.17.1 和现有 lock，不因本 Story 更新依赖。

1. 先设置 `$env:EID_ENVIRONMENT_CONFIG='deployment/environments/seadee-develop.yaml'`；主代理提供经审查的远端 selector 接入及当前归属/隧道/服务就绪证据。`.venv/Scripts/python.exe scripts/remote_environment.py check` 只证明其报告的检查范围，不等于部署/迁移/运行通过。迁移仍走既有 `alembic.ini` 和完整远端目标守卫；严禁用离线 SQL 绕过。
2. `.venv/Scripts/python.exe -m pytest tests/contract/test_discovery.py tests/security/test_discovery.py tests/ops/test_discovery_fixture_safety.py -q`：D01–D11 的契约/纯判定/守卫分支均通过；按改动范围运行现有 access 与迁移负例，不以 skip 当通过。
3. `.venv/Scripts/python.exe -m ruff check edw-api/src/edw_api/discovery migrations/versions/0007_workspace_discovery.py scripts/seed_discovery_fixtures.py tests/contract/test_discovery.py tests/security/test_discovery.py tests/ops/test_live_discovery.py tests/ops/test_discovery_fixture_safety.py`，另覆盖实际变动的接入文件；分别执行 `pnpm --filter edw-web lint`、`pnpm --filter edw-web typecheck`、`pnpm --filter edw-web test`、`pnpm --filter edw-web build`，退出码均为 0。
4. 明确 `$env:EID_RUN_LIVE_TESTS='1'` 后运行 `.venv/Scripts/python.exe -m pytest tests/ops/test_live_discovery.py tests/ops/test_live_migration.py tests/ops/test_live_access.py -q`：在已验证远端专库的独立测试 schema/实际 API 角色下执行，记录实际 schema/角色/迁移/审计/回滚及零泄漏反例；必要 Worker grant 验证保持真实凭据。
5. 在当前远端 Web/API 候选及真实 Keycloak fixture 上 `pnpm exec playwright test tests/ux/discovery.spec.ts`；回归 `tests/ux/access.spec.ts` 中项目切换/完整深链/401/撤权/晚响应路径。新测试从当前环境收据定位身份，不能读取旧本机收据假称远端证明；真实成功链不得全拦截成 network mocks。
6. D12 固定现有 1920×1080/Chrome/实际字体为首页与集合的主对比环境；仅对改变响应式规则时补对应 1180/1181 边界检查。保存首页、筛选集合、详情、持久错误/拒绝、收藏/恢复结果的必要截图及 B/R/S 控件记录。原型源只读；需要匹配行长的对照数据只在明确测试渲染中使用，不进业务成功证据。
7. 首页/list API 与浏览器 tab/navigation 分别记录固定数据/身份/远端容器/网络/样本数、开始结束时间和原始毫秒值，给出样本 P50/P95 及错误数；仅开发基线，不宣称 NFR-8 的生产负载 `<1s` 达标。性能异常说明真实原因和影响，不能移除失败样本。
8. `git diff --check`；主代理核对 Story 基线起全部归属修改、未跟踪文件、原型哈希、完整 D01–D12 证据与独立 `eid_reviewer` 结论。安全/数据完整性问题修复后专项复审；只在实现、必要测试和审查真实完成后推进 review/done。

证据清单至少有：完整 HEAD 与 candidate source fingerprint、YAML 哈希、远端 SSH 目标/目录/owner/Compose project、服务容器 ID/镜像 ID、真实 DB/schema/角色、fixture/政策版本、各 case ID 的命令/退出码/结果、时间窗、截图/输出哈希及独立审查结论。远端 prereq 尚未通过时记 blocked/not-run，不能拿 Story 1.2 的本机旧 PASS 填充。

## Implementation Notes

- 2026-09-21 接续：修复仅功能命中的搜索结果被误标为空的问题，补充两条回归用例源码；TypeScript、ESLint、Vite 编译均退出 0，独立切片静态审查未发现确定缺陷。指定 Muse 模型已核实并实际调用，但 50 秒超时未取得结论；测试和运行验收未执行，完整 Story 审查未完成，保持 `in-progress`。备份、差异与调用证据见 `.local/story-1-3-baseline/search-empty-static-20260921/`，详细记录见 `story-1-3-static-review-2026-09-21.md`。

- 2026-09-18：远端前置完整UX验收52项通过，无跳过、失败或遗留恢复标记；新本机15432映射已审查。按PROMPT启动本Story实现并同步sprint，保留原baseline_commit及全部预存修改。开工文件哈希、Git状态与tracked diff在 `.local/story-1-3-baseline/`；本条不代表下列业务任务或D01–D12已经通过。

- 2026-09-18：只读架构取证补充实施定位，未启动业务实现。新schema head除API config外还须同步 `deployment/compose.yaml`、`edw-worker/src/edw_worker/app.py`、`scripts/seed_access_fixtures.py`、`tests/ops/test_live_migration.py`、`tests/ops/test_live_dependencies.py`；旧候选精确head检查意味着expand迁移本身不能证明回退兼容。发现详情的三元epoch含资源epoch，不能直接等同列表的工作区epoch。
- D09真实并发测试不能直接复用当前 `test_live_access.database()` 的未提交schema：第二连接不可见。实施时须明确本项目专有双连接测试schema的创建归属和保留方案，不擅自提交旧测试fixture或新增DROP清理。SQL授权投影以现有 `authorize` 为正反判定参照；幂等键应按主体/项目/键唯一，规范化载荷包含操作和目标，先重验当前权限再识别回执。

- 2026-09-15：仅完成规格准备，主代理已同步 sprint 为 `ready-for-dev`，业务实现未启动。远端五个基础服务已启动；当前 `seadee` 的生效 SSH 策略为 `AllowTcpForwarding no`，客户端连接被拒绝。远端接入独立审查尚有未解决项；先处理 [远端环境阻塞记录](remote-environment-2026-09-15.md)，不执行迁移/fixture，不进入 1.4，不用旧本机证据代替远端验收。

## Spec Change Log

- 2026-09-21：按用户明确的新开发约束暂停全部运行验证，只继续代码、静态检查和编译；保留原业务安全要求与未完成验收项，不以辅助模型意见或编译成功替代运行通过。

- 2026-09-17：按已授权部署路径方案和实际完成证据，将运行目录同步为 root 控制的 `/opt/eid`；保留旧目录，不改变产品、安全策略或 Story 状态。九服务、迁移与专用 fixture 已完成，完整浏览器前置验收仍在修复验证中，详见 `remote-environment-2026-09-17.md`。

## Review Triage Log

| 本轮发现 | 判定 | 处置与源码证据 |
|---|---|---|
| 新发现详情深链登录后丢目标 | medium | `oidc.ts` 返回白名单原仅支持 home/resources；已补齐 App 当前发现页及 records UUID，保留严格 pathname、禁止 query/hash/外部返回。独立复审未发现确定缺陷。 |
| 固定视图覆盖显式筛选 | medium | `DiscoveryPanel.tsx` 原覆盖 kind/collection/tab；现在 home/documents、references、favorites 冲突明确拒绝，禁用查询并隐藏缓存/操作，保留兼容 AND。主线程补齐 home 和 records/from 分支及重置；独立复审未发现确定缺陷。 |

后端与测试源码覆盖审查未报告确定缺陷；Muse 辅助审查本次调用退出 0，未发现指定修复的阻塞问题。模型建议仅记录，不运行测试或环境。详情与局限见 `story-1-3-software-review-2026-09-21.md`。

- 2026-09-18 后端实施前置独立审查：`changes_required`。349项本地回归、Ruff及diff检查通过；发现待办计数没有同口径列表筛选、参考资料缺少knowledge/reference联合筛选两项P2。已安排限定后端修复，为现有Filters增加 `collection=all|todo|references` 并贯穿同一SQL集合、分页/字节/计数及游标绑定；保持四个最近标签和当前授权边界。真实PG/迁移仍未执行，本次审查不替代最终完整审查。

## File List

- 本轮新增变更归属：`edw-web/src/auth/oidc.ts`、`edw-web/src/auth/oidc.test.ts`、`edw-web/src/features/workspace/DiscoveryPanel.tsx`、`edw-web/src/features/workspace/DiscoveryPanel.test.tsx`；均有修改前备份及独立复审。
- `story-1-3-software-review-2026-09-21.md`：当前软件审查收尾、编译证据及取消验证说明。

- `_bmad-output/implementation-artifacts/spec-1-3-workspace-discovery.md`（规格、实施状态与验证边界）
- `_bmad-output/implementation-artifacts/story-1-3-validation.md`（历史证据与当前缺口）
- `_bmad-output/implementation-artifacts/story-1-3-static-review-2026-09-21.md`（本轮修复、静态审查、编译与辅助模型意见）
- 实现文件包括 `contracts/discovery.schema.json`、`migrations/versions/0007_workspace_discovery.py`、`edw-api/src/edw_api/discovery/`、`edw-web/src/app/discovery-api.ts`、`edw-web/src/features/workspace/` 及相应契约、安全、运维和 UX 测试源码。完整逐文件归属清单仍须在最终 Story 审查和提交前核定；不得将预存远端接入修改一并提交。
