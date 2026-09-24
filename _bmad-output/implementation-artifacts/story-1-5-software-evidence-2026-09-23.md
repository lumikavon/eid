# Story 1.5 软件实现与验证记录（2026-09-23）

状态：`done`（仅软件开发关闭）。基线提交：`f60aaccd663f794adeb7d2838e867fd82d7e8ad2`。用户于 2026-09-23 明确要求跳过测试、迁移、数据库、Broker 等运行时验证并推进本 Story 到 `done`；该例外仅适用于 Story 1.5。本记录只覆盖开发、源码审查、静态检查与编译；没有运行 pytest、PostgreSQL、RabbitMQ、服务、迁移、fixture、故障注入、SSH 或现场验收。

## 实现候选

- `migrations/versions/0009_fenced_recovery.py` 前向扩展 Task/Attempt 的 fence、按 attempt staging、完成与取消事务、DB 重试计划和调度器租约；旧 `0008` 未修改。毒消息仅按持久 Outbox 绑定隔离，取消函数对含 NULL 的范围匹配拒绝放行。
- API 任务快照、取消路由及授权边界，Worker v2 领取、续租、暂存、完成、失败和安全停止；独立 scheduler 使用数据库租约。健康检查新增 scheduler 租约探针，Web、健康 JSON Schema 与公开 readiness 校验同步为七项。
- Compose 增加 `worker-scheduler` 独立容器，复用 Worker 镜像与源指纹。远端与本地服务清单、日志扫描纳入第十项；旧九服务运行收据继续被新版精确清单拒绝。fixture 修订守卫接受 `0009`，现行迁移及 Worker 健康测试源码随之更新。
- 新增及更新合同、Worker、PostgreSQL 与远端清单测试源码。PostgreSQL 测试使用独立私有 schema 的回滚事务；目前双调度和取消顺序用例仍是单连接顺序调用，不构成真实并发证明。Worker mock 中手工标注的 ACK 也不构成 Broker ACK 证据。

## 允许范围内的检查

| 检查 | 结果 | 边界 |
|---|---|---|
| 更改 Python 文件的 Ruff `check` | 退出码 0 | 静态规则，不执行测试 |
| 更改 Python 文件的 `compileall -q` | 退出码 0 | Python 语法/编译，不执行 SQL |
| `uv build --offline --package edw-api` 与 `edw-worker` | 各退出码 0 | 构建包，不启动服务 |
| `edw-web` 的 `npm run typecheck` 与 `npm run build` | 各退出码 0 | 类型检查和静态构建，不运行浏览器 |
| Compose 十服务及共用 Worker 镜像、JSON 契约解析 | 退出码 0 | 结构检查，不连接 Docker |
| `git diff --check`；新建 Story 文件的行尾空白及末尾换行检查 | 各退出码 0 | Git 报现有 LF/CRLF 转换提示；不影响退出码 |

`opencode models opencode-go --verbose` 已核实显示名 **Muse Spark 1.3 Contributor** 对应 `opencode-go/muse-spark-1.3-contributor`。主代理以禁用工具的 `opencode run --pure --model ... --agent plan --format json` 完成两轮辅助源码审查，均退出码 0；原始包、模型清单、限制配置、JSONL 和状态分别留在忽略目录 `.local/story-1-5-static-20260923/` 与 `.local/story-1-5-final-review-20260923/`。首轮输入在迁移第 840 行截断；第二轮只含最终改动片段。第二轮将 PostgreSQL `LEAST(NULL,t)` 误判为 `NULL`，已按 [PostgreSQL 官方条件表达式文档](https://www.postgresql.org/docs/current/functions-conditional.html) 核对：NULL 参数会被忽略，故未据此改 SQL。任何 Muse 输出均不是运行验收。

独立 `eid_reviewer` 曾提出并推动修复：有效 Outbox 被伪报为 `INVALID_ENVELOPE`、暂存资源在完成前到期、重复取消返回冲突、scheduler 故障时 API 假就绪、取消函数 NULL 范围、Web 七项响应、远端十服务清单以及测试源码角色恢复/旧夹具。修复后的 SQL/API/Worker 审查未发现其他已确认生产缺陷；最终角色恢复、十服务测试夹具、Story 状态和证据文档的独立复核也未发现确定缺陷。该结论只针对审阅源码。

## 未取得的证据与关闭边界

五项 AC 的主验证分别依赖失租/迟到完成、提交 guard 与故障点、双调度并发、取消两种事务胜序及外部效果回执的运行试验，全部 `not-run`。PostgreSQL 对 `0009` 的实际语法和迁移结果、RabbitMQ 重投与 ACK、真实进程故障和多节点竞争均无通过证据。旧 `remote_candidate_update.py` 明确绑定历史九服务收据，不能作为十服务候选更新路径；将来的实际部署须另定受审路径和证据。独立测试源码不等于测试执行。本 Story 的 `done` 只关闭软件开发门禁，不表示 AC 运行通过、迁移成功、可部署或产品全量验收；本轮不推送或部署。
