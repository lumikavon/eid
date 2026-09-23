# Story 1.4 软件门禁取证（2026-09-23）

## 候选与归属

基线 `HEAD` 为 `f43ab41efdd4ebbe201ee0758b5b8bd36e372ac3`；候选为该提交加 26 个 Story 相关源码、契约与测试文件。修复后的逐文件 SHA-256 清单位于仓库根目录 `.local/story-1-4-closeout-20260923/source-hashes-final.json`，清单本身 SHA-256 为 `17006fe06fd78b815f857a2f61d634905eeb29b3cd6873e828496004711fffa1`。开工前 Git 状态保存在 `.local/story-1-4-baseline/2026-09-22/git-status.before.txt`。最终文档审查指出初次暂存遗漏末轮修复，因此提交前将按精确清单重新暂存并核对；`sprint-status.yaml` 的预存规划注释及时间戳只留在工作区，不纳入 Story 提交。`spec-1-4-durable-submission.md` 在基线快照前创建，其归属已按内容核对。S0 的最终归属以提交前暂存差异和提交后的路径清单为准。

## 机器检查的原始输出

所有下列命令仅读取/编译源码或本地构建包，没有运行测试、服务、数据库或 Broker。首轮原始输出保存在 `.local/story-1-4-quality-gate-20260923/`；修复后复查的命令、退出码和原始 stdout/stderr 保存在 `.local/story-1-4-closeout-20260923/final-static-checks.json` 及同目录 `final-*.log`。

| 检查 | 执行方式与范围 | 输出文件 | 退出码 |
|---|---|---|---:|
| Ruff | `.venv/Scripts/python.exe -m ruff check`，覆盖 26 个候选文件中的 Python 源码 | `final-ruff.stdout.log`，`All checks passed!` | 0 |
| Python 编译 | `.venv/Scripts/python.exe -m compileall -q`，覆盖相同受影响 Python 源码 | `final-compile.stdout.log` | 0 |
| JSON Schema 同步 | Python 导入纯 `edw_api.task_contract.contract_schema()`，与 `contracts/task.schema.json` 解析后的对象比较 | `schema-sync.log`，`task schema matches Pydantic export` | 0 |
| API 离线构建 | `uv build --offline --package edw-api` | `final-api-build.stderr.log`，wheel 与 sdist 均生成 | 0 |
| Worker 离线构建 | `uv build --offline --package edw-worker` | `final-worker-build.stderr.log`，wheel 与 sdist 均生成 | 0 |
| 差异空白检查 | `git diff --check` 与 `git diff --cached --check` | `final-diff-check.stderr.log`、`final-staged-diff-check.stderr.log`；仅有 Git LF/CRLF 提示，无空白错误 | 0 |
| head/fixture 源码定位 | `rg -n` 查看 0008 revision/down_revision、API 所需 head、fixture 明确支持的 head 和守卫引用 | `head-fixture-source.log` | 0 |

`head-fixture-source.log` 只证明源码存在且可供审查：0008 继承 0007（迁移第 4–5 行）；API 要求 0008（`config.py:26`）；fixture 只接受单一 0007 或 0008（`seed_access_fixtures.py:29,231–233`、`seed_discovery_fixtures.py:167–177`）。它不能证明迁移 SQL 真正执行、隔离守卫生效或 fixture 能在真实数据库成功；这些仍是非门禁的未验证行为。

修复后构建产物 `dist/edw_api-0.1.0-py3-none-any.whl` 34,584 字节，SHA-256 `69c0bb8a1f3770dddf797438e433b9f1c2f51761ea939444b4358169d98fe448`；`dist/edw_worker-0.1.0-py3-none-any.whl` 11,691 字节，SHA-256 `c38be4bb8d6dc8670409031bc88bb46570cd22659cd558dafc178beda634e3f0`。大小与散列原始记录在 `.local/story-1-4-closeout-20260923/wheel-final.json`。首轮 wheel 内容检查已确认新 task/relay/inventory 模块入包；修复后构建仍不证明进程可运行。

## 人工源码复核锚点

主代理与独立 `eid_reviewer` 已按以下锚点复核软件路径；无命令退出码的人工检查使用源码行号、[软件审查记录](story-1-4-software-review-2026-09-23.md)和仓库根目录 `.local/story-1-4-quality-gate-20260923/independent-code-review.md` 追溯，不冒充运行结果。

- S1：`edw-api/src/edw_api/tasks/repository.py:23–83` 将授权、同键回执、Task/Event/Outbox/Audit 写入同一连接事务；`routes.py:33–42` 在事务退出后返回 202；0008 的表约束/grants 及安全定义函数是待运行核实的源实现。
- S2：`edw-worker/src/edw_worker/relay.py` 使用租约、具名 exchange 和 publisher confirm；`migrations/versions/0008_durable_submission.py` 的 claim 返回数据库 event/task/body/hash 快照，confirm 按 owner、租约、正文与 hash 围栏更新。`app.py` 的 readiness 探针已同步新函数签名。
- S3：0008 的 Inbox/Attempt/完成函数区分 received/processed、重复和隔离；`inventory.py` 把完成结果映射到 ACK/Reject 路径。relay 对持久坏信封在发布前作绑定核对并以数据库快照隔离，诊断不抑制合法 Outbox。对应测试源码已补；实际 ACK 仍未观察。
- S5：首轮独立审查与 Muse 原始记录在 `.local/story-1-4-quality-gate-20260923/`；后续独立审查发现并促成坏信封、绑定、hash 竞态和 readiness 修复。修复后局部 `eid_reviewer` 对 readiness 明确 `approved`，最终全量 `eid_reviewer` 对 API、Worker、0008 和测试源码明确 `approved`，未发现确定的高/中风险问题；两者均声明运行行为 `not-run`。本轮重新以 `opencode models opencode-go --verbose` 核实 `opencode-go/muse-spark-1.3-contributor` 对应显示名 `Muse Spark 1.3 Contributor`，再以禁用工具的 `opencode run` 进行源码审查。模型列表、命令、输入包、禁用工具配置、JSONL 输出、stderr、退出码保存在 `.local/story-1-4-closeout-20260923/muse-*`，退出码 0。Muse 输出称未发现确定缺陷，但行号有误且输入有截断提示，只作辅助意见。

## 非门禁的未验证行为账本

PostgreSQL 原子提交与并发幂等：`not-run`；Broker/confirm/崩溃恢复：`not-run`；重复投递与真实 ACK：`not-run`；有效角色、Broker 权限与连接池边界：`not-run`。按 2026-09-23 用户最新指令，这些不再是 Story 1.4 软件完成门禁；但也没有任何运行通过证据。当前禁止执行，故不填写通过时长、行数、投递次数或现场 trace。
