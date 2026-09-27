## 开发与验证约束（2026-09-21 用户最新指令）

本节适用于后续开发及所有代理、工具的验证活动；与下文既有运行验收安排或模型路由约定冲突时，以本节为准。历史执行记录保留，不构成继续运行验证的授权。

1. 不进行任何实物、硬件或现场环境中的运行验证。
2. 仅执行软件层面的开发、代码检查和编译验证，不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测。
3. 完成代码修改后，调用 `opencode`，并指定模型为 `Muse Spark 1.3 Contributor`，用于代码审查、验证和测试建议。实际调用前核实该显示名称对应的可用模型标识；不得猜测标识、静默替换模型或伪称已调用。
4. `opencode` 的验证结果仅作为辅助参考；其审查、验证及建议的执行均须遵守“不进行实物运行验证、仅进行开发和编译”的限制。不得因工具建议启动实际环境或执行现场功能测试；未执行的运行验证如实记录为未执行，不计为通过。

- bmad-develop-epic resolved filesystem path: C:\Users\virtualink\.claude\skills\bmad-develop-epic
- bmad-develop-auto quality gate: 中：核心质量检查、关键测试、代码审查与验证；每个 Story 保留检查 → 优化 → 验证闭环，不绕过失败或阻塞门禁。
- bmad-develop-auto S4c confirmation: 用户明确确认当前 Epics 规划（13 Epic、73 Story；67 项本地实施 + 6 项真实环境验收），并明确要求“不要进入开发”。当前停在规划确认后；不得自动启动 S7、实现代码或修改开发状态。S5/S6 尚未执行，不得宣称通过；后续推进须遵守用户新指令。
- bmad-develop-auto confirmed scope: 全三期；单仓库；edw-web、edw-api、edw-worker 三个工程；Knowledge/LLM Gateway 为共享模块；Worker 保留分类队列及必要运行隔离；部署、迁移、共享契约、测试和评测作为仓库交付目录。
- bmad-develop-auto prototype decision: 允许沿用现有原型风格补齐缺失页面、必要控件与真实任务状态；已有页面保持视觉基准，示例数据随真实业务更新，演示按钮实现真实业务；补充项须在 UX 产物中逐项列明。
- bmad-develop-auto integration boundary: 企业知识库、身份、MES/项目系统先实现本地适配及契约测试，真实系统联调待接口接入；模型先实现适配器和确定性测试替身，真实生成、检索效果及容量验收待环境就绪。模拟测试不得作为真实集成或AI效果通过证据，未满足时不得宣称全量交付完成。
- bmad-develop-auto database authorization: 用户明确授权仅对本项目新建的、与现有业务数据隔离的本地开发/测试数据库执行迁移和测试数据读写；不涉及现有企业数据库或生产环境。执行前核对目标地址、数据库名称及项目专用性，无法证实隔离时暂停；本授权不包含删除数据库、清理既有数据或访问生产。

## 开发服务环境（2026-09-15 用户最新指令）

- 后续开发、迁移及运行验收统一读取 `deployment/environments/seadee-develop.yaml`；服务部署于 SSH 别名 `seadee-develop`。用户已批准将部署根目录从 `/opt/docker/eid` 切换至 root 控制的 `/opt/eid`，过渡已完成，旧目录和全部数据卷保留。不再启动本机 Docker 开发服务。具体步骤见 `docs/remote-development.md` 和 `docs/remote-deployment-path-authorization.md`。
- 用户已明确授权在该主机 `/opt/docker` 下新建本项目所需服务。仅操作 EID 专用目录、Compose 项目、网络、容器及数据卷；不得复用或修改其他项目服务、企业数据库或生产数据。此授权取代此前开发服务限于本机的约定，不扩大到生产发布或删除既有数据。
- SSH 配置负责主机、跳板及密钥解析；配置文件不得包含真实私钥、访问令牌或生产密码。本机可使用 SSH 端口转发连接远端服务，转发并不代表本机运行服务。
- 写入或迁移前验证远端主机、部署路径、资源归属及专用数据库标识；无法证明隔离时停止。远端验证必须记录远端容器及候选代码证据，不得沿用本机旧运行清单声称通过。
- 当前 `execute ./PROMPT.md` 与 Epic `1` 是用户在原规划暂停之后给出的继续开发指令；继续严格串行 Story 门禁，不因环境迁移自动标记 Story 完成，不自动 Push。
- 2026-09-15 环境接入尚未验收：仅五个基础服务已启动；当时 `seadee` 生效 `AllowTcpForwarding no`。2026-09-16 用户已明确授权 `docs/remote-forwarding-authorization.md` 的最小转发方案，已限定 `seadee`、跳板来源 `172.16.10.3`、本地地址 `172.27.0.38:22` 及七个远端 loopback 端口，不得扩大此范围。远端迁移/fixture、三工程运行及验收仍未完成。
- 2026-09-16 接续：远端接入代码缺陷曾通过第四轮四层独立审查，后端877 passed / 23 skipped（真实环境未执行）；详见 `_bmad-output/implementation-artifacts/remote-environment-2026-09-16.md`。最小 SSH 转发已应用，正式隧道进程/监听守卫通过；现场发现五个旧容器的 cgroup namespace 为 host，仍被 private 隔离守卫拒绝，须修复并验收后才能迁移或推进 Story。回滚材料和详细证据见 `.local/remote/forwarding-20260916/EXECUTION.md`。一次隔离测试误写使旧 `.local/runtime-images.json` 作废，副本已隔离且无可信原件，禁止将其当作验收证据。
- 2026-09-17 部署路径接续：用户已明确批准 `docs/remote-deployment-path-authorization.md`，授权创建 root 控制的 `/opt/eid` 并按方案纠正五个基础服务；无需再次请求相同授权。五服务已迁至 release-20260917-002 并通过 private cgroup、原卷/网络、专有持久消息及普通隔离守卫；完成证据 `.local/remote/complete-20260917/execute-003.json`。本机 owner 已沿精确来源收据同步新 root，旧收据已备份。保留旧目录、全部数据卷、nonce、网络和 Compose project，不修改共享 `/opt/docker` 权限。禁止重放过渡/恢复/完成入口或删除现场。初始化、迁移、九服务及应用验收另行推进；Story1.3 仍为 ready-for-dev。首次执行前完整 RabbitMQ definitions 缺失不能补称通过，恢复时完整快照及专有消息已实际验证保留，详见当日接续记录。

- 2026-09-17 应用接续：九服务已在原 release 启动，五个基础容器 ID 未变；初始化、0006迁移、七角色fixture完成，真实权限11项、迁移2项、依赖9项（含三种故障恢复）测试通过，浏览器登录及资源允许/拒绝冒烟通过。挂载顺序误报已修复并独立审查，远端schema3运行清单已正式生成；九服务现有日志扫描通过。UX工具的写入归属、未知结果、失锁及过期凭据恢复修复已通过第二轮审查，仍待HTTP503补充回归和完整现场UX/委派验收；Story1.3不得据此标记完成。当前证据 `.local/remote/app-start-20260917/`，完整记录 `_bmad-output/implementation-artifacts/remote-environment-2026-09-17.md`。

- 2026-09-18 接续：远端接入修复及本机PostgreSQL15432映射已经独立审查，新隧道通过完整进程/监听守卫；远端55432和其余六端口、sshd授权不变。真实当前账户测试1项、完整远端UX52项全部通过，包含Worker委派、撤权恢复及九服务日志门禁；结束后无待恢复fixture标记。证据 `.local/remote/acceptance-20260918/`，详见当日接续记录。Story1.3开始实现，尚未完成；不得重放过渡、seed或迁移，也不得将这些前置结果当作新Story验收。

<!-- eid-model-routing:begin -->
## Codex 项目模型路由

本节是用户于 2026-09-14 授权建立的项目级路由。只在本项目生效，不启动 BMAD 开发、不修改 Story 状态，不扩大既有操作授权。配置适用于本机已验证的 Codex CLI 0.154.0；升级或更换客户端后重新验证。

### 角色选择

| 任务 | agent_type / 文件名 | 模型 | 推理强度 |
| --- | --- | --- | --- |
| 搜索、符号定位、来源摘录、资料整理 | default | gpt-6-luna | low |
| 范围明确的常规编码 | eid_coder | gpt-6-sol | medium |
| 常规测试编写与运行 | eid_tester | gpt-6-sol | medium |
| 独立代码审查 | eid_reviewer | gpt-6-sol | xhigh |
| 复杂、跨模块、间歇性或反复失败的排障 | eid_debugger | gpt-6-sol | xhigh |
| 架构分析、共享契约、重大设计取舍的证据核验 | eid_architect | gpt-6-sol | xhigh |
| 安全、身份权限、迁移、数据完整性、破坏性操作等高风险修改 | eid_high_risk | gpt-6-sol | xhigh |

- 默认选择能胜任该任务的最低档；混合任务按最高风险分级，或先切出独立低风险探索。代码审查始终走强档。
- 主代理保持现有默认模型，负责授权判断、任务划分、方案取舍和最终验证。主代理亲自执行常规工作时可用 `codex -m gpt-6-sol -c 'model_reasoning_effort="medium"'`；复杂或高风险工作用 `codex -m gpt-6-sol -c 'model_reasoning_effort="xhigh"'`。既有会话需通过实际可用的模型选择器切换；提示词中的模型名不会切换模型。
- 子代理工具支持 `agent_type` 时显式选择上表角色，`fork_turns="none"`，任务自包含，写清文件范围、问题、修改权限及验收条件。不要传 `model`、`reasoning_effort` 或 `service_tier` 覆盖角色文件。
- 本节在模型路由范围内取代此前“只能用 default、禁止选择其他角色”约定；在明确授权并分配独立文件范围时，eid_coder、eid_tester、eid_high_risk 可进行对应修改，其他角色仍只探索、检索和核验。主代理保留最终决策和验证职责。
- 已知小文件与单一事实由主代理直接处理；架构、设计、交接等奠基性文档必须由主代理亲自完整阅读。即将修改的代码由实际执行修改的代理亲自阅读。
- 子代理只运行一轮，不复用、不用 followup_task、不再派生；最多 10 个并行子代理。不得让多个代理修改相同文件。结果提供状态、file:line、符号、关键原文、命令及退出码；主代理按证据抽查。
- 在当前工具/上层指令要求独立并行工作时，按其约束派发；已有等待、催收、终态收敛规则继续适用。不得将 MESSAGE 当成完成，不以子代理自报成功替代最终核验。

### 失败升级

1. Luna 出现证据不足、遗漏关键调用关系、相互矛盾的材料或范围超出整理时，返回 partial；主代理将压缩后的已知事实、检索范围和缺口交 Terra。涉及设计、安全或审查直接交强档。
2. Terra 经一次有依据的修正后同类失败再次出现，或无法解释失败、涉及跨模块根因时，升级 eid_debugger；发现架构或高风险边界立即升级对应强档，不等待第二次失败。
3. 升级使用新的角色实例，带上可复现步骤和失败证据；不要重复完整上下文或原样重试。模型不可用/权限错误与代码质量失败分别记录。
4. 强档仍不能解决时，缩小范围、核对证据并说明阻塞。不得跳过测试、弱化断言、安全策略或质量门禁，不得制造通过证据。

### 不可用与回退

- 模型存在性以当前 `codex debug models` / App Server `model/list` 为准，并检查所选推理强度；目录可见只证明客户端识别，实际成功请求才证明当时可调用。不要猜测不存在的 model ID 或 TOML 键。
- 短暂超时/限流仅允许一次有界重试；明确的模型不存在、无权限、额度耗尽不盲目重试。default 不可用可升级 Terra，再升级 Astra；Terra 不可用可升级 Astra。
- Astra 不可用时，低风险任务可以用已验证可用的 Terra 继续；代码审查、架构结论、复杂排障最终判断和高风险修改保持阻塞，等待最强模型恢复，不能静默降级或改用未知供应商。
- 若当前客户端没有 `agent_type`、忽略项目配置或不能加载自定义角色，不伪称路由生效：默认探子只做探索。在受支持的新 CLI 会话中使用项目角色；主代理工作通过上述 `-m` 命令或 `/model` 明确选择。仍不能切换时报告当前模型与限制。
- 路由与重试由主代理按本节编排，TOML 不提供按任务内容自动分类、失败自动升级的执行引擎。不要添加未经验证的 `fallback_model`、`model_router` 等配置项。
- 保持现有 provider、认证、MCP、权限及全局角色；运行时权限覆盖可能优先于角色的 sandbox_mode，探索角色还必须遵守只读指令。配置变更需在新会话中核验。

验证、备份及恢复说明见 `.codex/MODEL_ROUTING.md`。
<!-- eid-model-routing:end -->
