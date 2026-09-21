# Story 1.3 开发与静态审查接续（2026-09-21）

状态：`in-progress`。本轮只处理源码、静态检查和编译，不执行测试、浏览器、服务、数据库、部署或现场功能验证。原运行验收缺口保留，不以本记录关闭 Story 或推进 1.4。

## 修复范围

- `edw-web/src/features/workspace/discovery.css`：用 `.storage:not(.storage-fallback)` 恢复真实存储卡片的 12px 字号、长词换行和说明行高；占位内容设为 12px/16px，`small` 显式继承字号。外框仍沿用原型规则，`DiscoveryPanel.tsx` 未改。尺寸、换行及视觉效果未实测。
- `scripts/remote_candidate_update.py`、`remote_candidate_update_runner.py`：CHECK 保留完整事件，首次创建 journal 前重新核验来源、阶段、快照和 300 秒时效；同一边界重新核验 schema/migration 收据时效。同 schema 分支继续使用封闭的无迁移收据结构，不执行迁移。
- `tests/ops/test_remote_candidate_update.py`、`test_remote_candidate_images.py`：新增及修正常规合成 fixture、Web 单服务更新与时效拒绝的测试源码；真实历史材料审计另由显式环境开关控制，不让常规 fixture 依赖变化的现场清单。这些测试本轮未运行。
- `scripts/remote_candidate_images.py`、`remote_candidate_images_runner.py`：同步修改后 updater 的两个固定源码摘要；没有执行 prepare、seal、CHECK、import、stage 或 apply。

本轮修改前备份位于 `.local/story-1-3-baseline/static-fix-20260921/` 和 `storage-static-fix-20260921-backup-d70d084a3f374f569c1d73b9b4412265/`。上轮已存在的 Web forward-fix 扩展保持未现场验收；本轮没有增加部署授权。

## 检查和编译

| 项目 | 实际结果 | 边界 |
|---|---|---|
| Node 24.20.0 下 TypeScript `tsc -b` | 退出 0 | 类型检查 |
| 前端 ESLint | 退出 0 | 静态检查 |
| Vite 生产构建 | 退出 0，96 modules | 本地编译产物，没有启动服务 |
| 六个运维 Python 文件的 Ruff | 退出 0 | 包含两个测试源文件 |
| 六文件 AST 和字节码编译 | 退出 0 | 不导入或调用业务入口；pyc 写入 `.local` |
| updater 固定摘要核对 | 两项匹配 | AST 读取常量并与原字节 SHA-256 比较 |
| `git diff --check` | 退出 0 | 仅覆盖 Git 可见差异，不能替代未跟踪文件检查 |

编译后 Web 产物为 `index-BZGbf2cd.css`、`index-D2IVW2xR.js`。前端完整命令、哈希与备份见 `.local/story-1-3-baseline/storage-static-fix-20260921.md`。运维源码快照、审查附件和模型输出位于 `.local/story-1-3-static-20260921/`。

未执行 pytest、Vitest、Playwright、内存浏览器探针或任何真实环境验证；旧测试通过数不作为当前改动的通过证明。

## 独立静态审查

1. 前端静态审查发现真实卡片样式丢失、占位 `small` 字号再次缩小；已修复。最终切片审查确认选择器能覆盖真实 Portal 卡片，且说明字号继承正确；未认证像素结果。
2. 工具静态审查发现 CHECK/收据首写时效窗口和常规 fixture 依赖动态现场文件；已修复。最终切片审查确认完整事件及首写前复核、合成 fixture 和显式历史审计开关。
3. 最终切片审查另发现 updater 两个固定摘要尚未同步；主代理已同步并以 AST 与文件哈希核对。该修正不改变执行逻辑。

固定摘要：`remote_candidate_update.py` 为 `90db6be948db01237eed7b6b76a7f25561dd3deda562a8cab016ebb9e39f9423`，runner 为 `39b57d642df842894acb05d5f46d0cc25f7e4779d6e8d640b20c219cf6c13022`。这是静态切片审查，不是完整 Story 最终审查。

## opencode 辅助审查

已从安装的 opencode 1.18.31 模型目录确认显示名 `Muse Spark 1.3 Contributor` 对应 `opencode-go/muse-spark-1.3-contributor`，实际调用明确指定该标识。采用仅本进程生效的审查配置，禁用工具权限；补审同时关闭无关浏览器 MCP，不修改项目或全局配置。

- 第一次命令因 `--file` 数组吸收后续提示词而在本地报错，未形成审查。
- 修正参数顺序后的第一轮返回成功，但附件受 50KB 输出截断影响；模型仅看到前端及镜像工具开头。因此其报告不覆盖工具实现。
- 两份小附件补审首次调用长时间没有结果，主代理核对进程身份后终止该次调用；原记录保留。随后关闭浏览器 MCP 做一次有界重试，退出0，成功返回完整修复差异的辅助审查。日志为 `opencode-review-004.jsonl`，可读正文为同名 `.md`；事件只有 step_start、text、step_finish，无工具调用。

第一轮模型意见的主代理逐项核验：

| 意见 | 静态核验与处置 |
|---|---|
| 详情页 fallback 与 Portal 双写 | 不成立。`App.tsx:22` 的 `resourceId` 只匹配旧 `/resources/` 路径，发现详情使用独立 `/records/` 路径；第187行的账户分支与 DiscoveryPanel 本身互斥。模型混淆两条路由。 |
| 首次挂载长期空槽 | 未证明在当前 App 可达。账户与工作区初始为 null；父壳层先提交 slot，异步身份加载后才挂载 DiscoveryPanel。不得把独立组件假设直接当作产品故障。 |
| 真实块缺 padding/border 且必然布局偏移 | 缺样式说法不成立，`prototype.css` 的 `.storage` 仍提供 padding、border 等。不同内容实际高度/偏移未验证，不增加任意固定高度或宣称视觉通过。 |
| 未知计量使用普通 storage 样式会误报 | 未发现误报：`StorageInfo` 在无值时明确显示“尚未统计”和未知附件/总配额，符合真实状态要求；重复卡片前提亦不成立。 |
| randomUUID 的非安全上下文/旧浏览器假设 | 未证明当前支持环境中的可达缺陷，且不是本轮样式改动；仅保留为兼容性测试建议，不引入不安全随机键降级。 |

模型的运行/视觉测试建议均未执行；其意见只作辅助，不代替主代理判断或独立代码审查。

小附件补审没有提出新的确定缺陷，主要列出差异片段之外的上下文核对项。主代理静态处置如下：

| 核对项 | 源码证据与处置 |
|---|---|
| 首写拒绝是否因异常类型不一致而失控 | `remote_candidate_update_runner.py:606–734` 的 try/except 包含时效复核，统一捕获 BaseException；本地 checked_snapshot 将预期 RuntimeError 转为 ValueError。未发现新增未捕获路径。 |
| snapshot 为 null/list 时 summary 是否先崩溃 | `summary` 是 JSON 序列化后取摘要，null/list 可序列化；它们与正式字典快照不相等而在写入前拒绝。后续 recent_check 仍要求 dict。 |
| candidate 缺键 | candidate 来自已摘要绑定、经校验的 bundle；run 在收据前核验归属和输入摘要。畸形输入在写入前失败，不构成此次时效修复的可达放行路径。 |
| stage 是否也需要迁移收据 | 原契约 stage 在迁移之前进行，不消费迁移成功收据；forward stage 自行只读核对当前 revision。收据用于 apply-apps，不伪造迁移记录。 |
| candidate_contract 是否仍读现场材料 | `tests/ops/test_remote_candidate_update.py:634–678` 显式生成内存 compose、文件字节和镜像信息，不读取现场清单。 |
| fake_os.readlink 是否落到宿主 | mixed_snapshot 在第1222行先将 remote.os 换为包含 readlink lambda 的替身；依赖它的 forward_guarded_state 第1289行复制的是该替身。 |
| helpers 四元与五元返回值是否冲突 | updater helpers 返回4项，images helpers 在其前添加 update 模块后返回5项；各自调用方对应各自签名。 |
| 合成常量、上游 helpers、实际链与源码 pins | 合成数据覆盖守卫分支，不证明真实历史环境。生产实际链字节审计显式 opt-in；当前两项源码 pin 已由主代理直接核对。模型对片段外依赖的保留意见不等于已证实缺陷，完整运行效果依旧未验证。 |

因此本轮仅记录“指定切片静态修复完成、检查编译通过、Muse 辅助审查已执行”。没有将模型意见称为测试通过，也没有关闭历史运行缺口。

## 遗留项

- 当前源码完整 Story 审查、逐文件 Git 归属与提交仍未完成。
- 新候选运行、52项回归及新增21项发现功能 UX 的遗留缺口保留；依用户最新约束当前不执行。
- 本轮不提交、不推送，不改写已有失败历史，不将 Story 标为 done。

## 搜索空态接续修复

- `edw-web/src/features/workspace/DiscoveryPanel.tsx:97,149–150`：搜索只有功能命中、没有记录时，原先仍显示“无符合筛选条件的数据”。现在从受现有读取守卫约束的 `currentList` 提取功能结果，仅记录和功能同时为空才显示空态；记录计数仍准确显示 0。
- `edw-web/src/features/workspace/DiscoveryPanel.test.tsx:45–52`：补充“仅功能命中”和“两类结果均为空”两条回归用例源码，未执行。
- 修改前两文件及 SHA-256 清单位于 `.local/story-1-3-baseline/search-empty-static-20260921/`；本记录和 Story 规格修改前亦已备份到同目录。
- 主线程核对备份差异，并使用 `.local/tools/node-v24.20.0-win-x64/node.exe` 在 `edw-web` 下分别执行 `node_modules/typescript/bin/tsc -b`、`node_modules/eslint/bin/eslint.js .`、`node_modules/vite/bin/vite.js build`，均退出 0。构建 96 modules，产物 `index-BZGbf2cd.css`、`index-KMcU303j.js`。执行前核对 package scripts 与 Vite 配置，没有运行测试或启动服务。
- 独立 `eid_reviewer` 静态审查本切片未发现确定缺陷；确认功能结果沿用加载/错误/离线读取守卫。既有失败/加载用例没有直接断言缓存功能隐藏，该边界本轮仅由源码确认。此结论不是完整 Story 审查。
- 本轮已核实显示名 `Muse Spark 1.3 Contributor` 的模型标识为 `opencode-go/muse-spark-1.3-contributor`，以禁用工具和浏览器 MCP 的配置实际调用。50 秒超时，日志仅有 `step_start`，没有审查结论，不能记为辅助审查通过。模型映射、完整参数、附件、日志和超时状态分别保存在备份目录的 `model-mapping.json`、`review-command.json`、`review-packet.txt`、`opencode-review.jsonl`、`review-status.json`。
- 实施代理在催收后仍未返回终态，主代理中断并核对落盘文件，另派独立审查并亲自执行上述检查。未以代理的附件内自报检查结果作为验收依据。
- Story 仍为 `in-progress`：运行测试、D01–D12 验收及完整 Story 最终审查未完成；未提交、未推送，未推进 1.4。
