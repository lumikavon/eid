# 2026-09-17 可信部署根目录切换记录

用户已明确批准 `docs/remote-deployment-path-authorization.md` 并要求继续。授权覆盖新建 `/opt/eid`、保留旧目录及原数据卷、按门禁纠正五个基础服务；不需要再次请求相同授权。

## 已完成的本地修复与复核

- 固定新部署根为 `/opt/eid`，祖先为 root:root `/` 0555、`/opt` 0755；普通守卫继续要求 private cgroup，不自动采用旧收据。旧目录仍受外来绑定保护。
- 首轮根目录审查发现旧受保护路径经符号链接改指后可漏检；已通过实际 collector 回归复现并修复。保留可选 OriginalSource，同时检查原始与解析路径；采集前拒绝旧根或祖先被重定向。最终相关七组测试445项通过，独立审查通过。
- 过渡脚本两项审查缺陷已修复：准确匹配完整祖先清单；RabbitMQ 重建前再次检查原对象与专有探针、完整定义和连接。独立审查及最终候选27项本地过渡测试通过，远端 I/O 在这些测试中为替身。
- 新候选包 `candidate-trusted-root-20260917-002.tar.gz` SHA256：`a976e6a6199eed65cef8b0cd2c5dbe3cfe432e28f5c8392f25c1d3c876d61629`。
- 冻结执行包 `trusted-bundle-20260917-002` 的 bundle SHA256：`424e299015640ee88f781eb3b959f192750c9ce5994a2445bbacc8c48859ef25`。包内生产源文件、生成 YAML 语义及执行/采集脚本均与已审查候选核对一致。

上述文件位于 `.local/remote/acceptance-20260916/`。根契约精确增量在 `.local/remote/root-contract-20260916/`，保留目录修复证据在 `.local/remote/retained-root-fix-20260917/`。

## 真实检查与首次执行

同一冻结包的 `trusted_root_launch.py check` 退出0，确认新根不存在、五个原完整容器 ID 及资源归属满足前置条件。正式隧道已重新启动，PID44532；七个 IPv4 loopback 监听、进程和完整 argv 经守卫验证，记录在 `tunnel-20260917.json`。

随后在已有授权下执行同包 `execute`，退出1：

1. 创建 `/opt/eid`，root:root0700，device/inode `64768/29497029`。
2. 写入 owner 收据和 `.eid-root-transition.json` 来源记录。
3. 部署 `/opt/eid/release-20260917-002`，保留上传包及全部旧目录。
4. 创建专有 RabbitMQ 用户/vhost `eid-cgroup-20260916-a976e6a6199e` 和 `persistent-proof` 队列，发布一条持久验证消息。
5. 随后发生 KeyError，原日志未记录缺失字段名与栈位置；没有任何 `recreate_begin` 事件。

原始结果为 `trusted-execute-20260917-002.json`。独立只读排障确认五个原容器 ID 仍完全一致、全部运行中且仍使用 host cgroup namespace；原执行进程已退出，两个部署锁无持有者。未重建容器、删除数据、执行数据库迁移或 fixture。

## 已核验的恢复检查点

| 对象 | 身份或 SHA256 |
|---|---|
| 新 owner 收据 | `4a7d7be0e3bcb732029a4af1859f6907bca6408edc261281cc0417c39558b95a` |
| 新根 provenance | `72ad4e096923261642a532439264df5b214e0c040552b8e133bdabb7694422ff` |
| 原六行事件完整字节 | `2466c9a53037a0aa4ebf659a8ad886b4bf4a39aa3797eb475d4a45a83c0625fa` |
| release inode | `29497034`，root0700；84个候选文件及源包共85文件哈希匹配 |
| 探针 receipt | inode `29497142`，root0600；SHA `f695429531888808146d3a5a01a02e501eab9a4427d0b4ff9206a1db5b11a310` |

探针当前消息数、ready、persistent均为1，unacked/消费者为0，持久消息87字节；publish=1、get=1、ack=0。只读排障没有再次调用消息 get。统计证明已执行过一次 get，但不能证明原 payload 验收通过，也无法恢复原 KeyError 的确切缺失字段。

首次执行前完整 definitions 仅存在已退出进程内存，未落盘。当前非探针 users（含凭据摘要）、vhosts 与冻结基线相等，原队列为空、无连接；不能据此伪称完整历史 definitions 已核对。恢复将采集并保存明确标记时间的新完整快照，作为后续重建的保护基线；缺失历史证据继续如实保留。

## 后续执行约束

独立恢复入口正在 `.local/remote/resume-20260917/` 准备。必须在两把既有锁下再次核验来源、目录与文件身份、原事件完整字节、候选/脚本哈希、五个原 ID、卷/网络、探针和无额外客户端；只跳过已证明的目录创建、staging 和 probe setup。保留原失败日志，使用新事件文件，不重放一次性 launcher，不重建或重发探针、不清理现场。

先完善字段类型、必需字段及阶段诊断，再完成恢复入口独立审查与实时只读 check。按原门禁执行五服务纠正、持久性及普通守卫核验后，才继续 local owner 收据的有来源切换、初始化/迁移、三工程运行及 Story1.3。Story1.3仍为 ready-for-dev，1.4以后未启动；无新 Commit/Push。

## 第二次执行：五服务已重建，最终持久性检查待完成

恢复入口精确接受现场两条探针 vhost 权限（探针用户及既有管理员），拒绝第三条或字段变化。10项纯本地测试及独立审查通过；最终冻结包 `.local/remote/resume-20260917/bundle-002` SHA256为 `d7751f76107df82cc03213a692c752baa6410e850b5ef2e273a7042e227981e6`。同包只读检查退出0后执行，结果保存在 `execute-002.json`。

五个服务均完成重建，逐项库存、原卷/网络、健康与实际 private cgroup namespace 检查通过：

| 服务 | 新容器 ID |
|---|---|
| redis | `9d62405293a4cade8a8f434458255e8b2045c326d2db0ffc1fb7804d549a762e` |
| seaweedfs | `af9135dca52ffe32e81ed612b0d46b57d85976edbf9839cfd0fc414cf311fc19` |
| keycloak | `a65b0ce4739b7227c498bdea203ddd1f09a642502a6eee923cc9d3eb7b0b6a89` |
| postgres | `d3bd8cb7a5f7671dbc654c9ce612ff59142bfdb38909cb84cb7611e22966fbd4` |
| rabbitmq | `5cbdfff0e515e7833188b2dcb4d24c150a9ed9c44d049d8fc2a80fc8298f126b` |

随后在 `rabbit-preservation` 阶段以 `RabbitMQ node directory replaced` 停止，退出1；尚未进入本次专有消息 GET，也未执行最终普通守卫。不能将五项重建成功宣称为完整环境验收。

只读 stat 证实两个持久数据目录 dev/inode 均保留：当前节点 `64768/5515044`，旧节点 `64768/5533833`；旧插件目录 inode5533905保留。只有当前 `rabbit@5e8cac11b089-plugins-expand` 的 inode 从5506256变为5506113，dev64768、UID/GID999、0755、nlink2不变。[RabbitMQ 官方文档](https://www.rabbitmq.com/docs/plugins)说明该目录用于启动时展开插件。原检查把四个目录全部按持久身份比较，误拒绝了此变化；后续完成入口必须对本次已核实的插件目录身份作精确限定，继续保留数据目录及普通守卫，不得宽泛豁免路径检查。

重建前恢复时完整定义快照已落盘：`/opt/eid/resume-definitions-baseline-20260917.json`，root0600、dev64768/inode29497144、nlink1、3620字节，SHA256 `c9fbe021ef47b905b1b3065710928de458ef9cb8dccd9691c05032b74a953892`。恢复事件文件 inode29497143、root0600、nlink1、2928字节，保留原始日志。后续仅完成验证，不重放容器重建；本机 owner 收据仍保留旧root，迁移、fixture、应用启动和Story状态仍未推进。

## 最终完成验证与本机收据同步

完成入口经过独立全量审查后，真实只读CHECK又发现两处过度约束：SeaweedFS固定候选本来无Docker健康检查；目录nlink随子目录增加而变化，原runner只比较真正身份字段。两项分别修复、补充拒绝测试并经独立审查。最终21项纯本地测试通过；目录device/inode/type/uid/gid/mode、文件nlink1以及所有原普通守卫保留。

最终冻结包 `.local/remote/complete-20260917/bundle-003` SHA256：`9a46d6206a63b1e6a99cb08c3c70571b7df9792cf59496fb06b3d5de3131c702`。同包 `check-003.json`、`execute-003.json` 均退出0。实际验证专有消息payload和delivery_mode2，并以ack_requeue_true放回；完整definitions仍匹配恢复时快照，原数据目录身份、五个新ID/private namespaces、原卷/网络、旧目录保护及普通隔离守卫通过。未重建任何额外容器，未删除原资源。

原网络ID：`c39210ed5f0e98e520abc2857dc6050ac0d945239dfadae090802875e13ed8b8`；五个原named volume继续使用。完成事件库存摘要：`3a338207b9cb688ff7fcbdb43a6a9c81aa0c46f554a98402da8e4664db7e9cae`。`runtime_verified`仍为false，限定完成不等于应用验收。

之后主线程用当前源码重新核验 `validate_guard_state`、精确五ID及隧道，才将 `.local/remote/seadee-develop/ownership.json` 沿同一nonce切换新root。旧收据字节保存在 `.local/remote/complete-20260917/ownership-before-root-transition.json`，来源记录为 `owner-reconciliation.json`。没有更改远端收据或普通守卫来绕过检查。下一步按已有授权执行初始化、迁移与九服务验收；Story状态尚未推进。

## 探针辅助管理员权限收尾

首次初始化在写入前被原有RabbitMQ权限守卫拒绝：探针vhost创建带来的管理员附加grant使管理员不再仅有eid-local一条授权。经架构复核，此新增辅助grant不属于必须永久保留的验证对象，探针自身窄权限足以保留认证和消息。日常守卫未修改。

新收尾脚本经独立审查，2项纯测试含13项拒绝变体通过；组合源码SHA256 `f9a458784650a0e7bbbfe064ae3cfc102c2ced0cdc262727b55907eb504acd93`。同源码只读检查及实际执行均退出0，证据 `grant-check-001.json`、`grant-execute-001.json`。在部署锁和完整归属/检查点验证下，先root0600备份完整定义，再只撤销 eid_broker_admin 在 eid-cgroup-20260916-a976e6a6199e 上的 `.* / .* / .*` grant。完整定义后验只相差这一条；原eid-local grant、用户、vhost、窄权限、队列和消息均保留，没有再次get消息。

远端前后文件 `probe-admin-grant-before-20260917.json` / `probe-admin-grant-after-20260917.json` SHA分别为 `9328e30c9a50c9ff0abc05307b852a4d2847f2dd7c8517c6b674d3ee10fa3993` / `035d894dc3c0de41efac0497a8e81a18c6b4f82408abf054d5fa66c251e0e1e9`；均保留，不打印含凭据摘要的完整内容。旧恢复入口两权限断言不再适用，禁止重放。

随后重新运行初始化，实时只读确认eid_api/eid_worker用户已创建；最终初始化成功仍待进程返回，日志为 `initialize-002.log`。当前不宣称迁移或应用验收完成。

## 初始化及迁移通过

`initialize_local_storage` 最终退出0，日志 `initialize-002.log`。随后显式选择远端环境运行 `alembic upgrade head` 退出0；该命令无输出，PowerShell Tee未创建空日志，实际工具结果另记于 `migration-001-execution.json`，没有补造迁移日志。

主线程再经当前数据库归属守卫，以只读连接确认 `current_database=eid_local_dev`、`current_user=eid_migrator`、数据库comment标记 `eid-local-dev-v1`，且实际 `alembic_version` 唯一值为 `0006_api_write_only`。记录文件生成时曾因空日志不存在失败，随后修正证据来源；一次连接超时经远端PostgreSQL running/healthy及隧道监听只读核对后，有界重试成功。

最终收据 `.local/remote/complete-20260917/migration-success.json` 包含初始化/迁移退出码0及原证据SHA256，实际数据库身份已验证。当前仅五个基础服务运行；API/Worker/Web/NGINX启动入口正准备独立审查，fixture、运行清单、日志及浏览器验收仍未完成。

## 九服务启动、fixture 与首批真实验收

启动前生成了含当前完整基础容器 ID 和 owner 的 `migration-success-v2.json`，SHA256 `2fe8bc471d021c8c147a8d9416bd6ca25df2a59f580b32175543603f2ccc2052`，实际再次查询数据库身份和唯一 revision。应用启动入口完成独立审查；修复外来镜像动态年龄字段及挂载列表顺序引起的快照误报后，17项针对性测试通过。最终冻结包 `.local/remote/app-start-20260917/bundle-004` SHA256 `c726552518b06cd7b4014495a5640571226081d47a02a6e5d43516d4454d1461`，同包 `check-003.json` 和 `execute-002.json` 均退出0。

四个应用服务已启动；原五基础服务 ID、卷和网络保持不变。新增完整 ID：

| 服务 | 容器 ID |
|---|---|
| api | `65ddb07ffb60bfa606e3802e693ac52635631b3be13e7105b8d20321e219f863` |
| worker | `39194e90cc3d57ad786a6a21e4a9703e7e5ad9590393fe5560fef5f90a44b069` |
| web | `638030254e92fa850a9fbf39a283704bc0c54f5d221be7d205530c36f548e339` |
| nginx | `38f2dd04867564098a0a96b9c8c955a12d9c4ee7a8cebf76fb8b1a31d54aad63` |

显式远端 selector 下 `scripts.seed_access_fixtures` 退出0，七角色全部通过新 PKCE 登录并写入专用数据库，两个项目及七个资源创建成功。原输出 `fixtures-001.log` SHA256 `378487b86537fe991100d8a42a315ec617b5977f6c10a181dbb3e70d9bf1e286`；只从成功输出提取环境专属 `access-fixtures.json`，校验 owner、七份身份创建收据和全部 nonce 派生 UUID，没有重放 seed。提取来源在 `fixture-output-provenance.json`，运行前仍需当前远端守卫。

真实测试结果：`test_live_access.py` 11 passed；`test_live_migration.py` 2 passed（独立 schema 事务回滚）；`test_live_dependencies.py -k 'not loss'` 6 passed、3 deselected。对应原始日志保存在 `app-start-20260917/`。三项故障恢复测试本轮尚未执行，不计为通过。

BrowserOS 独立页面实际完成作者登录、A/B项目切换、自有资源深链允许，以及他人资源深链拒绝且清除受控内容；保存 `browser-author-allowed.json`、`browser-author-denied.json`。这些是当前现场冒烟，不能替代完整浏览器回归。

正式运行清单尚未写入。第一次记录因调用参数缺少 `sha256:` 前缀而拒绝；修正已冻结指纹后，第二次在前后候选比较处失败。独立只读排障重现仅 PostgreSQL 两挂载项顺序互换，完整挂载字段、owner、隧道、九ID、镜像和候选均不变。原失败记录保留；采集器顺序修复及拒绝回归正在进行。另有旧 UX 工具读取本机夹具/Worker清单、默认项目排序及恢复保护问题，正在修复。完整运行清单、Worker委派、浏览器回归和日志门禁尚未完成，Story1.3仍为 ready-for-dev，无新 Commit/Push。

## 正式清单、故障恢复与日志检查通过

采集器只在完成 RW 配对及路径解析后按完整挂载对象 JSON 排序，不去重、不丢字段。237项相关测试通过，独立审查 approved，并复跑新增15项正反测试通过。三工程镜像源指纹不变。随后 `record-runtime-003.log` 实际退出0，远端 `.local/remote/seadee-develop/runtime-images.json` schema3已原子生成，SHA256 `599b5b0287def39e9ff52a78194df9c27ec1922bf16aca8c8b8aecc9d2eb623a`；记录日志SHA256 `fd0f2f566f09a229d70b99550bc1ce424960cfd468e19ddf0504a41052c28298`。清单绑定完整九ID、镜像、配置、owner、SSH及Compose摘要 `d5a434ec6b85fc9761b940c5a6200b7816509b1bcc245e34139e966f5231ae42`，前后真实就绪与候选比较通过。缺少buildx，记录明确采用源指纹匹配的导入镜像，不声称远端构建。

`test_live_dependencies.py -k loss` 实际3 passed（317.81秒），验证数据库停机、Worker停机及Worker数据库身份失效后的拒绝就绪和恢复；与前述6项合计9项真实依赖测试均通过。`fixture-preflight-001.log` 实际退出0，仅验证当前七角色收据、派生UUID及远端隔离边界，没有重新seed或修改成员。

当前九服务日志扫描 `runtime-logs-001.json` 实际退出0，截止UTC `2026-09-17T09:53:41.861786+00:00`。九个完整ID与清单一致，JWT、token、认证code URL、Bearer及14种开发凭据清单的匹配均为0；原始日志未打印。完整UX执行后的新增时间窗仍需最终复核。

Worker探针已改用当前环境运行绑定，广播前后核对owner/实例/候选/隧道；48项隔离测试及独立复跑48项通过，审查approved，实际Worker委派路径尚未执行。UX工具三文件的四层审查发现迟到写入、失锁期间恢复、同值并发修改归属及异常锁退出测试缺口，逐项分诊见 `.local/remote/app-start-20260917/UX-REVIEW-001.md`，正在修复。完整UX/委派验收仍未通过，Story1.3状态不变。
## 浏览器验收首轮失败与恢复核验

远端 UX 前置检查通过后运行 `tests/ux/access.spec.ts`：15 passed、1 failed、17 did not run，退出1，日志 `.local/remote/app-start-20260917/ux-run-001.log`。第16项在初次 Worker 允许探针之后未找到管理员成员表中的作者编辑按钮，420秒超时；不得将此结果视为完整浏览器验收通过。

恢复归档 `.local/remote/seadee-develop/access-ux-recovery/41a5cb6b-ff9d-457f-a3cd-f0b90d70639c.json` 的状态为 `unchanged`、`writes=[]`，完整原权限与预期相同，没有提交撤权，没有待恢复标记。独立诊断发现同步 `spawnSync` 会阻塞安装 `page.route` 后的 Playwright 请求续传，与账户读取超时、恢复后成员面板重挂的现象一致。此次未记录网络 trace，不能追认具体请求时间线或声称令牌过期；修复目标是异步执行有界探针并验证请求可继续处理。

此前第二轮四层审查已完成，唯一 HTTP503 未知提交结果的覆盖缺口已补充，并通过独立窄范围审查及回归。当前继续修复现场发现的测试调度问题，所有原隔离、恢复归属与委托有效期门禁保留；Story1.3仍为 ready-for-dev。

异步修复已通过独立增量审查：Worker 与审计查询均使用异步有界子进程，保留180秒超时、64KiB合并输出限制、异常终止和原授权/恢复守卫。执行者与审查者分别运行37项聚焦回归均通过；真实Chrome本地伪站在两个辅助进程等待期间分别完成33/32次账户请求，零超时，成员表保留。精确增量与浏览器证据位于 `app-start-20260917/async-probe-fix/`，本地替身不充当远端验收证据。

真实撤权单项重跑 `ux-revocation-003.log`：1 passed（5.4分钟），退出0。通过原委托允许、等待后成员表仍可见、真实页面撤权、作者HTTP403与刷新清屏、原委托有效期内Worker拒绝断言。恢复归档 `edf406e9-046c-40a1-bcc9-f060d7ee3ba9.json` 包含撤权及恢复两次写入，状态 `restored:56a1d174-eb36-4834-a78a-feaa737dbe82`，无待恢复标记。此前 `ux-revocation-002.log` 因筛选正则锚定完整测试标题导致未找到测试，退出1，未运行前置检查或远端写入；保留该记录。其余17项正在单独继续，尚不宣称完整UX通过。
