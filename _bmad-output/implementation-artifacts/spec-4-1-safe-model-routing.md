---
title: 'Story 4.1 受控模型路由与版本化 Prompt'
type: 'feature'
created: '2026-09-28'
status: 'review'
route: 'dispatch'
baseline_commit: '988eec0c3d44350dd33f52a0a346d7166add487b'
review_loop_iteration: 0
context:
  - '_bmad-output/implementation-artifacts/epic-4-context.md'
  - '_bmad-output/planning-artifacts/development-validation-policy.md'
---

<frozen-after-approval reason="用户拥有实施意图；批准后仅由用户修改">

## Intent

**Problem:** 现有调用只服务 embedding/rerank；生成模型缺少密级/DLP 路由、版本化 Prompt/模型和可追溯运行记录。

**Approach:** 在现有 API/Worker 内建立受控生成入口、版本化配置与 GenerationRun；先审查/脱敏再路由，校验输出。X-20 展示受权版本和禁用状态，不展示密钥/原文。

## Boundaries & Constraints

**Always:** Classify→DLP→Policy→Redact→Model Router；按输入/来源/当前权限取最高密级，缺政策即拒绝。L3 禁外发；L2 无明确例外仅内部；L1 外发须批准脱敏；拒绝/故障不降级。限制 capability、上下文/token、成本、配额、超时；固定版本并保存安全哈希、路由、用量、修复次数、错误码。KB/标书/附件均不可信，不授工具/ACL/shell。外发/提交前重验授权及版本；关键审计失败即拒绝。

**Never:** 不把 Qwen3-32B 候选/本地替身称为生产批准；Worker 不改文档 head；普通日志、浏览器存储、配置 UI 不留敏感 Prompt/密钥。章节 DAG、Copilot、Patch 接受留给 4.2–4.4。本轮不做质量门禁；测试、迁移、DB、服务、浏览器、真实模型均 `not-run`。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 结果 | 失败 |
|---|---|---|---|
| 合规 | 授权/版本有效，预算内 | schema 合法响应，持久运行/路由/用量 | 撤权/版本变更阻断 |
| 敏感 | L3 外发、L2 无例外、L1 未脱敏、注入 | 外发前拒绝或批准脱敏 | 无权限提升/宽松回退 |
| 故障 | schema 错误/超时 | 最多一次修复；DB 调度瞬态重试 | 安全失败可查询 |
| 配置 | 管理启用或越权/审计故障 | 合法版本原子启用 | 生效版本不变 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/knowledge/routes.py:21`：`model_call` 仅供 embedding/rerank，勿作生成入口。
- `edw-api/src/edw_api/knowledge/evidence.py:54`、`knowledge/evidence_routes.py:31`：借鉴前后重验和栅栏，不拿快照授权。
- `edw-api/src/edw_api/access/policy.py:60`、`access/repository.py`：当前资源/epoch 授权；新增管理操作需明确受控。
- `edw-api/src/edw_api/config.py`、`main.py:50`：服务端密钥与路由，默认禁用。
- `edw-api/src/edw_api/task_contract.py:169`、`tasks/routes.py:25`、`edw-worker/src/edw_worker/app.py:19`：观察/队列；SubmitTask 仅支持 inventory。
- `migrations/versions/0021_epic3_remediation.py:4`：迁移基线；保留身份检查/最小授权，不执行。
- `edw-web/src/app/App.tsx:26`、`features/templates/TemplateWorkspace.tsx:20`：入口及撤权清缓存惯例。

## Tasks & Acceptance

**Execution:**
- [x] `migrations/versions/0022_model_governance.py`、`edw-api/src/edw_api/config.py`：不可变配置版本、生效指针、限额、运行/审计记录与最小授权；缺配置拒绝。
- [x] `edw-api/src/edw_api/model_gateway/`：有界契约、DLP/脱敏/路由、httpx 适配、一次 schema 修复；不执行工具。沿用现有 `task_contract.py` 的 canonical 哈希，不改其公共接口。
- [x] `edw-api/src/edw_api/model_gateway/routes.py`、`main.py`、必要的 `edw-worker/src/edw_worker/`：授权配置/调用/状态、持久重试/栅栏；API 掌管最终提交，Worker 仅受限唤醒/结果。
- [x] `edw-web/src/features/model-governance/`、`app/App.tsx`：受权 X-20 版本/禁用提示，不缓存敏感内容。
- [x] `tests/security/`、`tests/contract/`、`tests/worker/` 及 Web 测试源码：密级/注入/预算/撤权/审计/修复/重试正反例；只写不执行。

**Acceptance Criteria:**
- Given 当前授权及固定版本，when 调用，then 五段链先于外发，限额生效，GenerationRun 存版本/哈希/用量/路由。
- Given 密级、脱敏、权限失败或注入，when 评估，then 无违规外发/权限提升/宽松回退。
- Given 无效输出或瞬态故障，when 恢复，then 最多一次修复或 DB 调度重试；失败可查且正文不变。
- Given 越权、不安全配置或审计故障，when 启用，then 不变更生效版本或泄露原文。

## Implementation Notes

- 仅内部生成入口可接收当前文档范围下的直接文本；客户端自报来源密级一律拒绝，外发策略可配置但生成入口始终拒绝外发，直到后续 Story 建立可信来源证明。此限制不代表 L1/L2 外发已经可用。
- 执行链以当前 `document:edit`、文档 head/revision、`OUTLINE_READY`、授权 epoch、策略版本和激活 revision 作前后栅栏；Worker 仅传 ID 并唤醒 API，不读 Prompt 或提交文档 head。
- 保守额度预留包括最多三次尝试、每次一次结构修复；终态不返还预留，以拒绝超额为先。网络模型协议、权限 SQL 与重试时序未经运行验证。

## Spec Change Log

- 2026-09-28：在非冻结执行区记录 Story 4.1 的候审实现和仅静态/编译验证边界，冻结的 Intent、约束与矩阵保持原样。

## Review Triage Log

- 2026-09-28：已核实标识 `opencode-go/muse-spark-1.3-contributor`，两轮独立只读源码审查。首轮指出 API readiness 的 UPDATE 列授权覆盖不足、无效输出终态混淆、有限 DLP 范围等；补全 readiness 列检查、区分 `FAILED`/`BLOCKED`、记录修复次数并扩充明确的 DLP 特征。第二轮未发现高/中严重度可行动源码缺陷；保守额度可能过度预留、启发式 DLP 非完整分类器及不可达异常状态的运行表现留待后续审查/验收。

## Verification

- `git diff --check`：退出码 0；Git 报告四个已有跟踪文件的 LF→CRLF 提示，非空白错误。
- `python -m compileall -q edw-api/src/edw_api/model_gateway edw-api/src/edw_api/config.py edw-api/src/edw_api/main.py edw-worker/src/edw_worker/model_wake.py edw-worker/src/edw_worker/app.py edw-worker/src/edw_worker/relay.py migrations/versions/0022_model_governance.py tests/contract/test_model_gateway.py tests/security/test_model_policy.py tests/worker/test_model_retry.py`：退出码 0；仅 Python 编译，未执行测试或迁移。
- `npm --prefix edw-web run typecheck`（脚本 `tsc -b`）：退出码 0；仅类型编译。
- 测试套件、迁移 SQL、数据库权限、服务、浏览器、真实模型及 L/R/P 运行验收：`not-run`，不得解释为已通过。Story 状态 `review` 仅表示软件实现候审，不是质量门禁或功能验收结论。
