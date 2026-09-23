# Story 1.4 软件开发与静态审查记录（2026-09-23）

## 状态与边界

- 基线：`f43ab41efdd4ebbe201ee0758b5b8bd36e372ac3`；目标 `1-4-durable-submission` 的软件门禁和最终全量源码审查已通过，状态按本 Story 有限例外记 `done`。
- 本轮仅实施源码、测试源码、配置与静态/编译验证。未运行测试、迁移、fixture、Web/API/Worker、PostgreSQL、RabbitMQ、远端环境、部署或故障演练。
- Epic 1 原 Story 1.4 的 AC1–AC3 运行验收均为 `not-run`。静态代码审查和 wheel 构建不能证明原子提交、实际 Broker 投递或 ACK 恢复已通过。用户于 2026-09-23 明确剔除这些运行时质量门禁；独立源码审查已 `approved`，本 Story 按软件完成口径记 `done`，但须精确提交后才能进入 1.5。

## 软件实现

- 新 C-3 任务契约、信封向量、API 提交/当前授权重放/任务与结果读取、0008 expand 迁移及最小 grants。
- Task、Attempt、依赖、Event、Outbox、Inbox、结果与隔离记录；relay 短租约领取、具名 exchange publisher confirm、已确认未完成消息的持久恢复；Worker 只读 inventory 与受保护完成事务。
- 依赖阻断有界传播，授权委派过期保留可见阻断，不自动续签。非法输入、存储信封损坏和终态 Inbox 不一致保留可检查状态/隔离记录；外来坏信封不会隔离合法 Outbox。
- 同步 Compose Worker supervisor、schema head/就绪、fixture 兼容和相应契约、授权、故障点、迁移测试源码。
- 独立审查后补强 relay：claim 返回数据库事件/任务/正文/hash 快照；发布前核对绑定及规范化 hash，坏信封经租约/owner/正文/hash 围栏持久隔离；confirm 同样受快照围栏。普通诊断不抑制合法 Outbox。Worker 就绪探针同步 0008 的新函数签名，并补相应测试源码。

## 检查和审查

| 项目 | 本轮结果 | 证明范围 |
|---|---|---|
| 受影响 Python 文件 `ruff check` | 退出 0 | 静态规则 |
| 受影响 Python 文件 `compileall -q` / 最后测试文件 `py_compile` | 退出 0 | Python 语法/字节码编译 |
| `git diff --check`（已跟踪 Story 文件）与 JSON 解析 | 退出 0 | 空白与 JSON 语法 |
| `uv build --offline --package edw-api` | 退出 0 | wheel / sdist 构建 |
| `uv build --offline --package edw-worker` | 退出 0 | wheel / sdist 构建 |
| wheel 内容检查 | 退出 0 | 新 API task 与 Worker relay/inventory/store 文件已入包 |
| 独立 `eid_reviewer` 静态审查 | 完整差异审查发现持久坏信封缺隔离；后续复核又发现绑定、hash 竞态和 readiness 签名缺陷。代码已修复；readiness 局部及最终全量源码复核均明确 `approved` | 源码审查，不是运行验收 |
| `opencode`，`opencode-go/muse-spark-1.3-contributor`（显示名 `Muse Spark 1.3 Contributor`） | 修复后重新核实模型并留存禁用工具调用，退出 0，未报告确定缺陷；其部分源码行号不符且输入有截断提示 | 辅助源码审查，不能单独作为通过或运行验收证据 |

修复后 API wheel `dist/edw_api-0.1.0-py3-none-any.whl` 为 34,584 字节，SHA-256 `69c0bb8a1f3770dddf797438e433b9f1c2f51761ea939444b4358169d98fe448`。Worker wheel `dist/edw_worker-0.1.0-py3-none-any.whl` 为 11,691 字节，SHA-256 `c38be4bb8d6dc8670409031bc88bb46570cd22659cd558dafc178beda634e3f0`。这两项只证明当前源码可以构建为包；原始记录在 `.local/story-1-4-closeout-20260923/`。

## 文件归属

新文件：`contracts/task.schema.json`、`contracts/vectors/task-envelope-v1.json`、`edw-api/src/edw_api/task_contract.py`、`edw-api/src/edw_api/tasks/{__init__,repository,routes}.py`、`edw-worker/src/edw_worker/{inventory,relay,task_store}.py`、`migrations/versions/0008_durable_submission.py`、`tests/contract/test_tasks.py`、`tests/ops/test_live_durable_recovery.py`、`tests/worker/{test_durable_submission,test_durable_supervision}.py`、本记录、`spec-1-4-durable-submission.md`、`story-1-4-quality-gates-2026-09-23.md` 与 `story-1-4-quality-gate-evidence-2026-09-23.md`。

已跟踪修改：`deployment/compose.yaml`、`edw-api/src/edw_api/{config,main}.py`、`edw-worker/src/edw_worker/{__main__,app}.py`、`scripts/{seed_access_fixtures,seed_discovery_fixtures}.py`、`tests/contract/test_discovery_migration.py`、`tests/ops/{test_discovery_fixture_safety,test_live_dependencies,test_live_migration}.py`、`tests/worker/test_worker_health.py`、`_bmad-output/planning-artifacts/development-validation-policy.md` 及 `sprint-status.yaml`（仅本 Story 的例外与状态；文件中的预存规划注释保留）。

开工前已有 `README.md`、Epic 1 context、Story 1.1/1.2 spec、规划与远端文档/脚本、工具目录等未提交修改；均不属于本 Story，未纳入本轮文件归属。开工快照在 `.local/story-1-4-baseline/2026-09-22/`，各次修改前备份在 `.local/story-1-4-baseline/` 和 `.local/backups/`。

## 非门禁的未验证行为与后续边界

- AC1：真实 PostgreSQL 当前授权、并发幂等、审计失败原子回滚及 202 回执。`not-run`。
- AC2：提交前/后、confirm 后的故障点；RabbitMQ 不可用时持久 queued，恢复后同事件至少一次投递。`not-run`。
- AC3：重复/篡改/未知版本信封，received 崩溃、租约重领、结果与 processed 同事务及实际 ACK。`not-run`。
- 当前远端候选更新工具仍限制在 Story 1.3 版本转换和既有 Compose 形态，不能据此声称 Story 1.4 可部署；未来获准运行验收前须设计并审查兼容更新路径。当前不执行部署或改写远端收据。
- 已认证的 `eid_worker` 服务身份仍可调用既有 `eid_task_claim` 伪造异常使任务隔离；这是可信服务身份边界，不能用普通 API 用户路径触发，也未通过本 Story 的新围栏消除。需在后续权限模型审查中单列，不把当前静态审查表述为抵御受损 Worker 凭据。

2026-09-23 的用户指令已移除上述运行结果作为 Story 1.4 软件完成条件。独立源码审查已批准；当前停点是精确提交与串行状态核验。未来如另行授权运行验收，仍须重新核对隔离、候选与权限，不能追认本轮未运行项目为通过。

2026-09-23 更新[软件质量门禁](story-1-4-quality-gates-2026-09-23.md)及[逐项取证](story-1-4-quality-gate-evidence-2026-09-23.md)。首轮记录位于 `.local/story-1-4-quality-gate-20260923/`；修复后源文件 hash、静态/编译/离线构建原始日志及指定 Muse 调用记录位于 `.local/story-1-4-closeout-20260923/`。S 层软件检查和最终源码复核已通过；提交归属仍须核验。原运行项目为非门禁 `not-run`，没有执行任何运行验证。
