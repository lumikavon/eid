---
title: 'Story 1.2：强制执行当前项目成员关系与密级'
type: 'feature'
created: '2026-09-11'
status: 'done'
baseline_commit: '8fd8398b1500f78fea5f8f5dc804db14f7b647b5'
route: 'dispatch'
review_loop_iteration: 10
context:
  - '_bmad-output/implementation-artifacts/epic-1-context.md'
  - '_bmad-output/planning-artifacts/epic-1-secure-workspace.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem：** 现有账户查询只检查活动成员关系并选择首个项目；角色、属性范围、密级、有效期和撤权不能共同约束下一次使用。

**Approach：** 以 PostgreSQL 当前策略生成服务端授权上下文；实现真实项目选择和成员管理，API/Worker 复用同一授权决策，权限变更、epoch、失效记录与审计原子提交。

## Boundaries & Constraints

**Always：** 每次使用满足 RBAC 操作 AND ABAC 项目/客户/产品/部门/owner/审批状态/有效期 AND L0–L3 密级。JWT 只证明主体，URL、请求体、历史上下文不能扩大权限。服务身份与原主体受限 delegation 共同约束后台检查。项目/主体/资源有持久 epoch；无授权缓存优于无法证明新鲜的缓存，Web 在撤权响应与切换项目时清除全部受控状态并阻止旧响应回填。权限变化与审计失败共同回滚；Worker 不能写 ACL/head/approval/publication。只增量引入本 Story 实际使用的策略与受控资源元数据，不建立完整文档领域。

原型不改，P-00 项目卡/账户位置与六导航保持既有布局；X-18 项目/账户补充和 X-20 权限表单按 UX 合约，持久呈现 loading/empty/forbidden/error/success。密钥不进入 URL、持久浏览器状态、普通日志。迁移/测试前验证本地项目隔离，继承已有数据库授权。

**Never：** 不实现任务引擎、任务 SSE 或后续文档业务；提供并实际测试可供后续阶段/流使用的当前授权入口与受限后台上下文，但不冒充完整任务/流传输验收。不用系统管理员角色绕过 ABAC/密级，不用模拟数据库替代权限/撤权/事务验收；不连接企业/生产、不删除已有数据。企业映射/撤权语义与生产安全留待 Epic13。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 结果 | 错误处理 |
|---|---|---|---|
| 项目选择/深链 | 真实账户及项目成员策略 | 只列/打开当前获准项目与资源；响应来自实际 ID | 未知与越权资源统一拒绝，不泄露存在性 |
| 联合矩阵 | 七类角色、不同客户/产品/部门/owner/状态/期限/L0–L3 | 三类条件全部满足才允许明确操作 | 未配置/过期/停用/非法上下文安全拒绝 |
| 撤权后再用 | UI/后台上下文加载后策略 epoch 改变 | 下一次 API/后台阶段/输出检查重读并拒绝，Web 清受控数据 | 不凭历史 epoch 放行，不回填旧响应 |
| 权限写入 | 当前有管理权限且 expected epoch 匹配 | 策略+epoch+审计+失效记录原子提交 | 冲突409；审计失败整笔回滚 |
| Worker 直接写 | 独立 eid_worker 连接 | 仅授权读取/受限上下文查询；敏感写由 PG 拒绝 | 真实 negative grants 测试 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/auth.py`：保留 OIDC 验签与 subject，扩展上下文不能信任 token role。
- `edw-api/src/edw_api/db.py`：独立 eid_api 连接、当前账户 SQL；新增策略读取与短事务接缝。
- `edw-api/src/edw_api/main.py`：现有 `/me`、结构化错误、readiness；新增授权 router，保留健康检查。
- `migrations/versions/0001_identity_workspace.py`、`0002_worker_metadata_only.py`：历史不可改；新迁移补最小策略模型和精确 grants。
- `edw-worker/src/edw_worker/app.py`：现只有 readiness，新增受限授权入口，不引入任务调度。
- `edw-web/src/app/App.tsx`、`api.ts`：复用内存 token、generation fence、401/403清理及 bounded JSON。
- `tests/ops/test_live_migration.py`：真实空 schema 事务回滚模式；保留隔离检查。

## Tasks & Acceptance

**Execution：**
- [x] `migrations/versions/0003_current_access.py`、配置/schema readiness：增量策略、epoch、审计/失效与最小数据库授权。
- [x] `edw-api/src/edw_api/access/`：纯决策、当前策略仓储、原子管理与契约路由；后台只用受限 delegation。
- [x] `edw-worker/src/edw_worker/access.py`、`contracts/`：共享当前授权契约及阶段/输出重验，不序列化用户 token。
- [x] `edw-web/src/app/`：项目选择、账户权限/成员管理、受保护深链和统一撤权清理，保持壳层。
- [x] `tests/security/`、`tests/contract/`、`tests/ops/`、`tests/ux/`：正反矩阵、真实 PG 变更/撤权/审计回滚/grants、浏览器切换及失序状态。
- [x] `README.md`、验证/截图与 Story 记录：保留真实证据、失败记录和 R/P 边界，独立审查通过。

**Acceptance Criteria：**
- Given 作者、专家、质量、模板管理员、知识管理员、审批人、系统管理员及不同属性 fixtures，When 调用允许/拒绝操作与深链，Then 当前 RBAC AND ABAC AND clearance 决定，客户端 actor/scope 不扩大权限。
- Given UI 加载或后台上下文创建后成员撤权，When 下一次 API、后台阶段或输出授权入口使用，Then 当前 epoch/策略拒绝旧权限且受控 UI 数据清空；后续任务/流复用此入口。
- Given Worker 数据库身份，When 直接更改 ACL/head/approval/publication，Then PG 拒绝；关键权限变更与审计同成同败。
- Given 原型壳层与新补充页面，When 切换/深链/失败/撤权，Then 保留视觉基线并呈现真实持久状态，经独立截图审查。

## Design Notes

不缓存授权 allow；每次从数据库读取持久 epoch 和当前事实，避免 TTL 冒充实时撤权。角色仅映射操作能力，管理员也必须满足项目范围和密级。资源策略关系由数据库解析；请求中的 ID 只用于定位。最小资源策略元数据是本 Story 属性鉴权对象，不认证未来编辑/审批/发布业务。后台 delegation 以数据库受限记录绑定原 actor、resource、operation、purpose 与到期时间，Worker 身份不得自行创建或扩权。

## Implementation Notes

2026-09-11：Story1.1 已提交并验证151文件及无 tracked 遗留；本 Story 基线为 frontmatter SHA。两项独立代码探索完成；主代理负责实现/方案与最终验证。依据 PROMPT 的全自主串行授权继续准备与开发，无需重复普通确认。

2026-09-11 实施进展（未完成）：新增0003策略/资源/epoch/审计/失效/delegation与Worker受限函数，纯授权决策、API项目/成员/资源/委托路由，Web项目选择和成员表单。当前默认Python396 passed/17显式live skipped，Web72 passed，typecheck与范围Ruff通过。真实唯一schema迁移1 passed；真实策略事务6 passed（38.36s），覆盖角色/撤权/审计失败回滚/epoch冲突/Worker写拒绝/资源范围。首次完整bootstrap正在执行，尚无Story1.2独立审查或浏览器验收。

失败与修复：新live夹具遗漏connect_timeout导致建立连接等待，诊断栈确认尚未进入SQL，已加入3秒连接/5秒statement/2秒lock上限。随后6项因eid_migrator不能SET ROLE失败；未扩大迁移账号权限，改用隔离校验后的本地测试管理员在独立回滚schema中SET LOCAL ROLE，后续仍须实际Worker凭据证明。再有3项因应用/数据库时钟差异触发新建策略有效期拒绝，改为从数据库读取evaluated_at并使用同一数据库时间判有效期，6项随后全部通过。Web新增不可达error分支导致一次typecheck失败，删除重复分支后通过。早期账户查询单测仍绑定旧SQL，现改为验证当前授权投影与无可访问项目拒绝；真实账户回滚测试同步新策略fixture。

当时尚需（后续实现与复验见下文及验证记录）：C-1请求/trace上下文与schema工件、真实Keycloak多角色/多项目fixture及Worker阶段重验、浏览器切换/深链/撤权/失序/成员保存与截图、当前readiness/日志绑定、独立完整审查和修复。不得提前标记done或启动Story1.3。

## Spec Change Log

2026-09-11 恢复验证：已完成0004关联请求/trace迁移、七类真实Keycloak身份、项目/资源深链、Worker受限delegation检查及浏览器成员撤权。单独权限浏览器11/11通过；首次合并30项为27通过、3失败（Worker探针25秒超时、403账户请求计数2而非1、日志扫描60秒超时）。原样重跑三项后前两项通过，日志仍超时，未把复跑当成全部通过。

诊断发现账户轮询可在前一次请求未完成时重叠，现以当前generation的in-flight标记阻止定时重入，手动刷新/路由切换仍创建新generation；403用例加入250毫秒响应延迟稳定覆盖100毫秒加速轮询。日志扫描耗时主要为两轮独立所有权、容器和镜像校验；现仅并行独立镜像校验与所有权/容器校验，完整保留扫描前后绑定与所有拒绝检查，不扩大超时门槛。诊断期间修改Web源码导致一次源绑定校验正确拒绝，随后已重新构建Web并通过完整本地隔离/readiness/运行镜像记录校验。默认Python404 passed、17显式live skipped；日志门禁16单测通过，Web lint通过。完整30浏览器正在重验，尚未独立审查。

## Review Triage Log

第十一轮最终批准（2026-09-14）：盲审、边界、验证缺口均完整完成且无发现；初次验收代理超时中断、不计通过，随后分别完成AC/源码、24原图、运行证据三项独立验收并全部PASS。73路径候选清单/哈希一致，既有有效问题全部解决。主控最终安全/契约/Worker/守卫/日志关键复验446 passed（10.75秒），当前九服务运行校验通过。Story状态done，仅代表本地当前权限闭环；企业/生产验收仍属Epic13。按已授权串行流程执行本Story范围本地提交，不推送。

第十轮四层完整完成：盲审完整5564行/73路径无发现，边界无发现，验收批准24图及当前九服务绑定和新鲜健康检查；验证层下列1项有效缺口已修复，进入第十一轮完整审查。

| ID | 判定/路由 | 证据与处理 |
|---|---|---|
| R10-V1 | medium / patch | 权限数据库故障缺少服务端503契约证明；新增连接建立与查询阶段两类OperationalError用例，断言完整POLICY_UNAVAILABLE结构、retryable=true、请求/追踪字段及无原始诊断泄露。8项路由契约通过，完整Python487通过/23显式live跳过，Ruff通过。产品代码和运行未变。 |

第九轮四层完整完成：盲审完整5503行/73路径无发现，边界无发现，验收批准24图及当前运行绑定；验证层仅下列1项有效缺口，修复后重新完整审查。

| ID | 判定/路由 | 证据与处理 |
|---|---|---|
| R9-V1 | medium / patch | 角色、owner、审批状态、期限控件无真实UI持久化证明；新增一次表单保存，连同四类范围和生效时间逐项编辑，核对实际策略与PG审计完整字段/请求归属，afterEach恢复原策略。 |

第八轮边界层无发现；验收图像/运行证据有效但新增禁用状态缺陷，验证层2项，盲审收束为1项（其余覆盖标partial）。当前整体changes-required，修复后仍需新的完整四层审查。

| ID | 判定/路由 | 证据与处理 |
|---|---|---|
| R8-V1 | medium / patch | 宿主机100容器批次边界无覆盖；扩展101容器，将缺失/错ID/外部卷挂载置于第二批，断言两批均读取并拒绝。 |
| R8-V2 | medium / patch | 两轮运行镜像读取只覆盖应用中途变化；加入Postgres第二次读取才替换/停止/变镜像，保留完整首轮屏障断言并要求目标第二次调用。 |
| R8-A1 | low / patch | DESIGN.md第339行要求禁用状态有可见原因；项目/成员分页补可见页码、首页/末页和忙碌原因，以aria-describedby关联，并增加明确禁用样式。浏览器检查两端状态及可访问说明，更新截图。 |
| R8-B1 | false | “成员与权限/关闭成员管理”是当前项目内临时展开控件；刷新按URL初始化是有意行为，无跨刷新保存展开状态的要求。已支持/admin/members深链与路径变化重建/清除编辑状态，单击展开不改变项目上下文；将所有展开折叠写入路由属于额外导航设计。 |

第七轮完整四层已完成，验收层批准73文件、24图与当前运行/保留真实证据。其他层逐项判定如下，整体changes-required。

| ID | 判定/路由 | 证据与处理 |
|---|---|---|
| R7-E1 | medium / patch | 无资源创建授权没有要求draft范围；共享API/Worker决策补显式草稿许可，仍不实现文档创建业务。 |
| R7-V1 | medium / patch | 服务端50条分页缺少小记录边界测试，客户端仍接受200条；客户端收紧50并补50/51服务端游标与客户端拒绝测试。 |
| R7-V2 | medium / patch | 资源响应未核对请求ID；客户端比对规范化ID，契约断言repository实收URL ID及返回ID，补错ID拒绝。 |
| R7-B1 | false | 已展示的项目选择列表是导航快照，手动“刷新可访问项目”会重新授权；当前项目15秒刷新与任何选中项目的实际访问都重新授权，旧B项不能授予访问。没有声明所有未选中项目在后台自动刷新或将导航缓存当成授权allow；增加全列表轮询属于刷新体验增强，非当前授权绕过。 |
| R7-B2 | medium / patch | 新回调失败可能保留旧token，而失败promise一直重用；失败清会话，真正再次进入callback URL重新验证，StrictMode共享已同步清URL后的同次promise。补已有会话失败后重新认证的单测与浏览器测试。 |
| R7-B3 | false | 本仓声明并支持单仓根pyproject/uv.lock统一依赖安装，Worker是该工作区工程；Docker明确复制两源码路径，共享纯策略由该受控组合加载。单独把空依赖子工程作为独立发行物安装不是现有交付入口；若将来独立发行必须重新声明完整运行依赖，不将此扩为本Story打包重构。 |

第六轮四层完成；验收图像与运行证据全部通过，发现逐项判定如下，整体changes-required。

| ID | 判定/路由 | 证据与处理 |
|---|---|---|
| R6-V1 | medium / patch | 原密级测试仅走拒绝分支；补API/Worker成功授权，两个方向L0/L3均输出L3及完整epoch。 |
| R6-E1 | medium / patch | 默认候选在两次读取间连续撤权时第二次403锁死；改为有界可重试503，显式深链不改变。 |
| R6-A1 | false | 70KB单项复现不能来自所称名称字段：0001的workspace.name为varchar(128)、slug为varchar(64)，identity显示名/部门各varchar(128)。workspace_payload只返回这些受限字段、UUID、数值及已验证角色/能力，不返回无界资源title或scope。现有写入口roles限制7项且唯一；在伪仓储中注入70KB名称绕开真实schema，未证实可达故障。 |
| R6-B1 | false | 0003明确为已有本地成员配置author、精确项目/客户/产品/部门、self/draft/L1，是版本迁移的显式默认策略；并非对缺失策略执行时默认allow。新成员缺少access_member仍无法发现，停用成员迁移后仍拒绝；0002升级实际测试覆盖。真实企业映射不在本Story。 |
| R6-B2 | false | AC要求当前权限写入与审计同事务及Worker数据库负授权，均有实际回滚/grants测试。假定后续另写任意SQL绕过现有API，不证明当前事务缺陷；未声明可信API数据库身份无法执行任意错误SQL。 |
| R6-B3 | false | Worker是受信授权边界，authorize需要当前角色、范围、owner、状态、期限和资源策略事实，不能仅凭已计算C-1上下文证明当前权限。受限函数按有效delegation绑定具体主体/项目/资源，只返回本Story元数据而非文档内容；表读取仍禁止。 |
| R6-B4 | false | 每次Worker检查重读当前资源policy_epoch及全部资源策略；资源撤权期间拒绝，恢复当前允许策略后并未凭历史allow扩权。工作区issued_epoch保守失效已有实现；本Story无资源变更入口，也无承诺所有外部资源恢复都永久销毁旧委托，后续资源写入须遵循当前授权/失效契约。 |
| R6-B5 | false | load_current读取的是本Story最小授权元数据，不是受保护文档或知识内容；必须取出目标属性才能做ABAC判断。实际资源响应在authorize后输出，未实施后续检索引擎，不能套用内容检索前后检查要求禁止读取策略事实。 |
| R6-B6 | false | evaluated_at定义本次短事务事实读取的数据库判定时刻；每次使用重新取得，不复用历史缓存。任意响应发出前到期的绝对零时间窗口不可由移动一次时钟读取实现；未证实在本次判定时刻已失效仍放行。 |
| R6-B7 | false | 与R6-A1同根，但其“workspace名称/slug是无界text”前提被0001真实varchar定义直接反证。 |
| R6-B8 | false | readiness核对迁移head、必要权限、当前发现查询及依赖健康，未承诺检测管理员保持head不变而任意删列的所有schema篡改。已应用迁移不可改、路由真实验收覆盖；不把readiness扩大为全schema完整性审计。 |
| R6-B9 | medium / patch | 保存403后成员表仍可见直至账户刷新结束；立即阻断成员观察并清理缓存，补持有后续/me的浏览器验证。 |
| R6-B10 | medium / patch | load失败仅隐藏旧audit回执；同步清空accessResult，补拒绝后再次导航恢复的无旧回填验证。 |

第五轮四层完成：acceptance批准73文件、24图与当前运行绑定；blind返回4项有据意见（未为10项数量门槛编造）；edges和verification各1项。逐项复核后整体changes-required：

| ID | 判定/路由 | 证据与处理 |
|---|---|---|
| R5-B1 | medium / patch | approval_states未限制数量和重复；限制四种唯一值，契约测试覆盖重复与五万项请求在写入前422。 |
| R5-B2 | false | 成员表是当前项目membership:manage授权的策略配置，不是资源内容；成员clearance描述该成员可被授予的上限，不是该配置行的密级。读取仍经调用者当前项目ABAC/密级判断。写入的grant ceiling防止扩权，不构成配置行的隐藏规则；现有AC/UX无按目标授权集合隐去管理配置的要求。 |
| R5-B3 | false | 当前管理者不能以active=false请求修改超出自身授权上限的策略，是现有管理边界，非授权提升缺陷。active=false不是绕过当前授权的独立紧急撤权能力；也不承诺低权限管理者能管理所有更高权限成员。允许该例外将扩大控制范围，保留失败关闭及上限内降权能力。 |
| R5-B4 | medium / patch | 默认入口从独立项目刷新收到403后被永久阻断，漏掉仍获准的B项目；清除旧受控状态后重读/me，保留显式深链403拒绝，并用真实撤权/恢复验证。 |
| R5-E1 | medium / patch | 根路径与/admin/members之间历史导航未重建成员状态；路由pathname加入面板key，初始管理状态从Router读取，浏览器覆盖前进/后退及旧编辑器清理。 |
| R5-V1 | medium / patch | 原迁移仅空库种子覆盖；保留原场景并新增0002多项目/多成员（含停用）升级，核对完整backfill和实际first_workspace发现，独立schema整体回滚。 |

第四轮四层完成：edges返回无发现，acceptance批准完整71文件及24图/运行绑定；其余12项逐项复核如下，整体changes-required。

| ID | 判定/路由 | 证据与处理 |
|---|---|---|
| R4-B1 | medium / patch | readiness仍EXPLAIN旧账户SQL，不能发现当前查询依赖列缺失；复用真实发现SQL作只读计划探针。 |
| R4-B2 | medium / patch | API仅写入audit/invalidation/delegation，无业务读取需求；以新迁移撤去三项SELECT并同步真实权限检查，不改已应用迁移。 |
| R4-B3 | medium / patch | after_policy仅请求字段，未含实际新member epoch与身份；记录写入后的完整行与active，补实际审计断言。 |
| R4-B4 | low / patch | expected_epoch与active发生类型强制转换；请求模型改为严格整数/布尔值并覆盖拒绝。 |
| R4-B5 | medium / patch | 422被显示为服务故障；提供明确输入校验提示，并约束可见范围长度。 |
| R4-B6 | false | 三次连续并发撤权后返回可重试503是有界、失败关闭的明确设计，单次调用不承诺在持续变动下遍历成功。去掉上限会恢复已修复的无限加载风险；下一次请求重新选择稳定可访问项目，不误报无权或扩大权限。 |
| R4-B7 | false | 实施范围要求写入前验证本机项目所有权；boundary逐次执行并在后续再验证。建议要求在具有Docker宿主机控制权的一方替换端点时仍保证瞬间原子HTTP绑定，超出本地开发流程及本Story威胁范围；不声称对宿主机接管提供原子隔离。 |
| R4-B8 | medium / patch | 收据直接覆盖可能因中断损坏或并发丢失；增加本地seed互斥与原子替换，不覆盖或接管既有身份。 |
| R4-B9 | low / patch | 顺序扫描没有共同时间上限；九服务使用同一显式cutoff，报告只声明到该时刻，保留前后身份/镜像校验。 |
| R4-B10 | low / patch | 服务端生成游标正常，但客户端成员分页缺少格式/单调检查；补齐并覆盖重复游标拒绝。 |
| R4-V1 | medium / patch | 实际Worker写拒绝需覆盖INSERT/DELETE而非仅UPDATE；扩展逐表真实负向权限验证。 |
| R4-V2 | medium / patch | 保存中历史导航的原目标审计与新页面无回填尚未行为验证；增加持有PUT、切换项目、释放写入并检查实际审计的浏览器用例。 |

第三轮四层均已完成：acceptance批准全部24图及71文件绑定；其他层仍有有效问题，整体changes-required。

| ID | 判定/路由 | 证据与处理 |
|---|---|---|
| R3-B1 | false | 与第一轮E5相同；明确撤权可包括本人，无最后管理员保留约束，不引入撤权否决。 |
| R3-B2 | medium / patch | `/me`只需首个当前可访问项目却读取并逐个锁定全部成员项目；改为数据库筛选候选并在锁内重新授权首项。 |
| R3-B3 | medium / patch | 已有fixture的profile一致不足以证明公布密码能登录；以隔离本地OIDC登录验证并拒绝漂移，不重置已有密码。 |
| R3-B4 | medium / patch | StrictMode第二次effect因history已变成根路径而跳过同一个callback Promise；以Router回调路由等待共享交换结果并验证深链。 |
| R3-E1 | medium / patch | 与R3-B2同一账户全量扫描问题，合并修复，保留此项。 |
| R3-E2 | medium / patch | getWorkspaces逐页无限汇集，UI直到结束才可用；改为服务端页及前后入口，并单独重验当前项目，不能用单页缺席推断撤权。 |
| R3-E3 | medium / patch | 未知approval_state与未知成员授权值相同会放行；纯策略拒绝未知审批状态词汇。 |
| R3-E4 | medium / patch | scope NUL通过请求校验后不能存入PG；在写入前返回422。 |
| R3-E5 | medium / patch | purpose NUL同上，单独覆盖委托路由。 |
| R3-E6 | false | 客户端拒绝非安全整数是必要的fail-closed。现有epoch只能从1开始由服务每次加1，客户端expected_epoch不写入epoch；触发需超过9千万亿次变更或不受支持的直接改库。未证明本Story支持路径回归，不扩大表示/迁移范围。 |
| R3-V1 | medium / patch | 补齐readiness新SELECT依赖的断言及真实REVOKE负向验证。 |
| R3-V2 | medium / patch | 参数化验证管理者所有属性与有效期上限，拒绝前无写入。 |
| R3-V3 | medium / patch | 实际事务审计除数量还需完整前后策略、actor/target/workspace/action和request/trace内容。 |

第一轮完整独立审查：blind、edges、verification-gap、acceptance四层均返回；22张图全部检查，原型壳层通过，整体changes-required。逐项复核如下，全部有效问题均进入修复，不因严重度低而跳过。

| ID | 判定/路由 | 证据与处理 |
|---|---|---|
| B1 / E1 | high / patch | resource_id=None可跳过资源属性与epoch；共享策略明确资源必需操作，API和Worker共同拒绝。 |
| B2 | medium / patch | resource 403走全局onReject使有效工作区锁死；局部提示并重验当前工作区，提供返回入口。 |
| B3 | medium / patch | 新DML缺失时SELECT检查仍绿；就绪校验加入实际UPDATE/INSERT权限。 |
| B4 | medium / patch | Worker只查版本不探测实际函数；新增空UUID只读函数探针，缺函数/EXECUTE即失败。 |
| A1 | high / patch | fresh列表不含当前workspace仍展示旧current；收到列表立即隐藏并走统一撤权清理。 |
| A2 | low / patch | 空成员响应只有表头；添加持久empty提示及浏览器状态覆盖。 |
| E2 | low / patch | 请求始终绑定提交时workspace，故不存在写入新项目，但切换会丢失反馈；保存中禁用项目选择器。浏览器历史导航仍以既定请求目标提交，mounted fence阻止回填，不声称可取消已提交写入。 |
| E3 / V3 | medium / patch | 409后旧editor和epoch可重复提交；关闭旧editor、重读成员及epoch，再允许重新编辑。 |
| E4 | medium / patch | LIMIT200没有继续入口；增加受当前授权约束的游标分页，UI前后页及边界测试。 |
| E5 | false | 当前意图允许明确撤权包括本人，无必须永久保留管理员约束；引入last-admin veto会拒绝原本允许的安全撤权。操作原子审计且当前actor授权在提交前验证，未发现权限扩大或错误目标。本轮不凭建议新增业务禁令。 |
| E6 | medium / patch | 默认项目两次读取之间撤权而另有项目可用会锁住；默认路由仅一次重新解析当前账户/项目，显式项目深链仍拒绝，不循环重试。 |
| E7 | medium / patch | 非UUID地址返回422被当成服务故障；发送权限请求前校验ID并给持久无效地址提示。 |
| V1 | medium / patch | access请求deadline存在但无停滞headers/body测试；新增fake-timer abort及transient错误验证。 |
| V2 | medium / patch | Worker实际边界缺少非法request/trace记录测试；补纯边界和脱敏control拒绝测试。 |


## Verification

第二轮四层完整审查已返回；验收层核验全部24图及69文件哈希后批准，但其他层有有效问题，整体仍 changes-required。主代理逐项裁定：

| ID | 判定/路由 | 证据与处理 |
|---|---|---|
| R2-B1 | high / patch | issued_epoch 已持久化但 SQL 与纯策略均不比较；撤销后恢复可复活旧委托。以新0005迁移及共享策略拒绝旧版本，不修改已应用迁移。 |
| R2-B2 | medium / patch | UUID正则允许大写，App比较小写响应时隐藏账户；路由ID规范化。 |
| R2-B3 | false | “保存其他字段会分裂逗号范围”不成立：state原数组保留，仅该范围input的onChange才split。另已确认编辑该范围本身会歧义拆分，作为补充medium问题修复为逐项编辑。 |
| R2-E1 | high / patch | 资源/成员403隐藏UI但仅调用onRefresh；当前工作区仍允许且epoch未变时旧查询数据留缓存。清除对应受控缓存及editor。 |
| R2-E2 | medium / patch | 服务端无限工作区数组与客户端200项/64KiB上限冲突；增加有界游标页并逐页汇集可选项目。 |
| R2-E3 | medium / patch | 路由仅解析前缀，合法UUID后的未知段可进入已有界面；整条受支持路径验证，禁止发送权限请求。此处未证明API越权。 |
| R2-E4 | medium / patch | 非空Keycloak profile漂移只检查owner/enabled，seed仍报告预定义身份；检测声明字段不符并拒绝，不覆盖用户数据。 |
| R2-E5 | medium / patch | DB冲突行仅检查slug/subject，其他固定策略/资源字段漂移不报告；校验固定fixture声明，保留已有数据且不自动重置。 |
| R2-V1 | medium / patch | 增加成功Worker边界request/trace原值及C-1序列化契约验证。 |
| R2-V2 | medium / patch | 增加最大合法范围行的成员分页字节上限与游标续读验证。 |
| R2-V3 | high / patch | 增加低密级管理员不能授予更高密级及无写入证据。 |
| R2-V4 | medium / patch | 固定DB evaluated_at验证委托持久化及返回期限恰为5分钟。 |
| R2-V5 | medium / patch | 覆盖旧格式无returnTo的成功OIDC事务，返回根路径。 |

### Review Findings — Round 2

- [x] [Review][Patch] R2-B1 委托版本栅栏。
- [x] [Review][Patch] R2-B2/E3 UUID规范化及完整路由校验。
- [x] [Review][Patch] 补充范围字段逐项无歧义编辑。
- [x] [Review][Patch] R2-E1 局部拒绝清理受控缓存。
- [x] [Review][Patch] R2-E2 工作区分页。
- [x] [Review][Patch] R2-E4/E5 声明fixture漂移拒绝。
- [x] [Review][Patch] R2-V1/V2/V3/V4/V5 关键验证缺口。

Rejected: R2-B3 false，其他字段保存不调用范围onChange，原数组不变；实际范围编辑歧义已单列修复，不混淆两项结论。

- `uv run --frozen pytest`：联合授权单元/契约及现有回归通过；live 单独显式运行。
- 固定 Node24.20.0/pnpm：Web lint/typecheck/unit 和浏览器项目切换/撤权/深链。
- `scripts/bootstrap.ps1`：隔离守卫、新迁移、真实服务构建/readiness。
- 显式 live 测试：实际 PG 权限/审计回滚/撤权、实际 Worker 受限入口与浏览器链；记录延迟、不声称生产 SLA。
- 完整独立审查→有效问题修复→关键复验→Story/sprint done→仅本 Story 提交。

## File List

- `README.md`
- `_bmad-output/implementation-artifacts/spec-1-2-current-access.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/access-editor.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/access-forbidden.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/access-members-empty.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/access-members.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/access-revoked.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/access-workspace-b.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/actual-shell-1024x768.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/actual-shell-1180x800.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/actual-shell-1181x800.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/actual-shell-1440x900.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/actual-shell-1920x1080.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/actual-shell-768x1024.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/reference-shell-1024x768.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/reference-shell-1180x800.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/reference-shell-1181x800.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/reference-shell-1440x900.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/reference-shell-1920x1080.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/reference-shell-768x1024.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/reference-toast-shown.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/runtime-log-scan.json`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/visual-manifest.json`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/workspace-account-loading.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/workspace-authenticated.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/workspace-readiness-error.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/workspace-toast-hidden.png`
- `_bmad-output/implementation-artifacts/story-1-2-evidence/workspace-toast-shown.png`
- `_bmad-output/implementation-artifacts/story-1-2-validation.md`
- `contracts/access-context.schema.json`
- `deployment/compose.yaml`
- `edw-api/src/edw_api/access/__init__.py`
- `edw-api/src/edw_api/access/policy.py`
- `edw-api/src/edw_api/access/repository.py`
- `edw-api/src/edw_api/access/routes.py`
- `edw-api/src/edw_api/config.py`
- `edw-api/src/edw_api/db.py`
- `edw-api/src/edw_api/main.py`
- `edw-web/src/app/AccessPanel.tsx`
- `edw-web/src/app/App.tsx`
- `edw-web/src/app/api.ts`
- `edw-web/src/app/access-api.test.ts`
- `edw-web/src/app/access-api.ts`
- `edw-web/src/app/workspace.css`
- `edw-web/src/auth/oidc.test.ts`
- `edw-web/src/auth/oidc.ts`
- `edw-web/src/main.tsx`
- `edw-worker/src/edw_worker/access.py`
- `edw-worker/src/edw_worker/app.py`
- `migrations/versions/0003_current_access.py`
- `migrations/versions/0004_access_correlation.py`
- `migrations/versions/0005_delegation_epoch.py`
- `migrations/versions/0006_api_write_only.py`
- `scripts/seed_access_fixtures.py`
- `scripts/verify_access_delegation.py`
- `scripts/verify_local_environment.py`
- `scripts/verify_runtime_logs.py`
- `tests/contract/test_access_routes.py`
- `tests/contract/test_health.py`
- `tests/ops/test_access_fixture_safety.py`
- `tests/ops/test_guard.py`
- `tests/ops/test_live_access.py`
- `tests/ops/test_live_current_account.py`
- `tests/ops/test_live_dependencies.py`
- `tests/ops/test_live_migration.py`
- `tests/ops/test_runtime_logs.py`
- `tests/security/test_current_access.py`
- `tests/security/test_access_repository.py`
- `tests/ux/access.spec.ts`
- `tests/ux/shell.spec.ts`
- `tests/worker/test_current_access_boundary.py`
- `tests/worker/test_worker_health.py`

第二轮入口：Python431、Web80、真实环境19、浏览器37通过；24张最新截图与故障后九服务零匹配日志绑定一致。第一轮有效问题及补充渲染/epoch/完整表单问题均已修复，进入全量独立复审；尚未done。

第三轮入口：第二轮所有有效问题已修复；Python445通过/21显式live跳过（57.85秒），另行真实环境21通过（166.51秒），Web83通过，41浏览器同轮通过（3.8分钟、日志26.6秒）。编辑器定向完整重拍1通过（10.9秒），24张图及故障后九服务零匹配日志的运行绑定一致。关键新增安全/分页/兼容路径、并行读取的完整首轮及替换检测均已验证。71文件完整变更待新四层独立复审，不代表done。

第四轮入口（2026-09-14）：第三轮全部有效问题已修复；当前Python464通过/21显式live跳过（17.00秒），Web84通过（2.74秒），真实环境21通过（101.62秒），43浏览器同轮通过（1.8分钟，含受控StrictMode开发服务器测试及完整编辑器截图）。九服务已在保留数据下完整bootstrap恢复并绑定新应用源指纹；故障后日志九服务全部零匹配且与24张当前截图绑定一致。七fixture真实密码登录通过且ID不变，未覆盖已有密码。TypeScript/ESLint/Ruff及diff检查通过。进入新四层完整审查，尚未done，未开始Story1.3。

第五轮入口（2026-09-14）：第四轮有效问题均已修复；0006及当前九服务完整bootstrap通过。Python468通过/22显式live跳过，Web88通过，真实环境22通过（109.75秒），45浏览器同轮通过（1.8分钟）；24图已按当前运行重新捕获并核对。日志在共同UTC cutoff之前九服务零匹配，运行绑定与截图一致。fixture新互斥路径七角色实际登录通过且ID不变；TypeScript/ESLint/Ruff/diff通过。73文件完整变更进入第五轮独立审查，尚未done或提交。
