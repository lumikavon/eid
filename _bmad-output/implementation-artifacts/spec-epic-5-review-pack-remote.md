---
title: 'Epic 5 全量审查修复、openEuler 打包与远端验证'
type: 'bugfix'
created: '2026-09-30'
status: 'in-review'
baseline_commit: 'c58df950f84679e96359d21ac3b89f94d9583731'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '_bmad-output/planning-artifacts/epic-5-review-core-types.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Epic 5 的已实现故事存在审校状态、引用版本、安全检查与界面契约缺陷；尚无独立 openEuler Compose 打包环境及 seadee-test 验证证据。

**Approach:** 审查全部七个故事，修复确认的问题，提供容器化打包入口，并通过 SSH 对同一候选源码执行可复现验证。保留并纳入用户已确认的未提交 Story 5.5 工作。

**用户范围决策：** 同时实现 backlog 的 Story 5.6 和 5.7；容器目标采用已确认的 openEuler 24.03 LTS-SP2，替代原请求的 24.04；允许在 seadee-test 安装并启用 Docker/Compose，在 `/opt/eid-test` 创建隔离测试环境。

## Boundaries & Constraints

**Always:** 按故事验收条件核对，使用独立审查和有意义的回归验证；稳定区块身份、当前授权来源、固定版本和人工决策必须一致。新请求授权运行本地及远端测试，覆盖旧文档仅静态验证的限制；历史证据原样保留。产物记录实际源码校验和，排除本地凭据与缓存，运行时密钥不写入产物。远端使用隔离测试目录、Compose 项目和数据卷。

**Never:** 不把高分或规则通过等同正式批准；不关闭仍存在的严重缺陷，不伪造来源、模型准确率或未执行结果；不删除既有远端数据或修改 seadee-develop 部署。不提交或推送 Git。

## I/O & Edge-Case Matrix

| 场景 | 输入/状态 | 预期输出/行为 | 错误处理 |
|---|---|---|---|
| 跨版本复查 | 无关编辑后同一缺陷仍存在 | 保留阻断，以稳定区块及规则身份匹配 | 不以新 Claim UUID 误判修复 |
| 多条需求引用 | 顺序绑定两个需求来源 | 当前版本保留经重新核验的全部有效绑定 | 过期、冲突或撤权来源拒绝认证 |
| 手工修改 | Modify 后保存并独立复查 | 缺陷消失方可 handled，保留历史决策 | 严重未解决问题不可关闭 |
| 结构化需求 | 字段内敏感信息或缺项 | 字段级安全及完整性问题可定位 | 不只检查 statement |
| 来源搜索 | 当前获授权的可见引用原文 | 搜索、数量与展示一致 | 禁止检索暴露撤权原文 |
| 容器打包 | 明确 openEuler 镜像及候选源码 | Compose 打包产物、清单及校验和 | 镜像或输入缺失时明确失败 |
| 远端验证 | SSH 可达、隔离运行环境 | 记录真实执行命令、结果及环境 | 前置失败记录阻塞，不宣称通过 |

</frozen-after-approval>

## Code Map

- `edw-api/src/edw_api/review/routes.py`：版本资格、来源复核、筛选与决策；修复 same_defect 及 modify 闭环。
- `edw-api/src/edw_api/review/rules.py`：八类规则及 PRD 字段检查；遍历结构化内容并保留定位。
- `edw-api/src/edw_api/documents/{claim_routes,claims,editor_repository,editor_domain}.py`：引用命令、Claim 投影、版本保存与 AST 校验；保持事务/CAS 权限边界。
- `edw-api/src/edw_api/knowledge/governance.py`：当前适用性、冲突及来源治理复核。
- `contracts/document-ast-v1.schema.json`：对齐 PRD 草稿与完整需求约束。
- `edw-web/src/features/templates/{ReviewStatus,DomainEditor}.tsx`：人工修改闭环与字段展示，复用现有布局。
- `scripts/remote_environment.py`、`deployment/compose.yaml`：现有打包及十服务运行栈；原脚本绑定 seadee-develop，避免直接用于新测试主机。
- `deployment/{python,web}.Dockerfile`、`deployment/images.lock.json`：锁定工具、镜像及应用构建输入。
- `tests/{contract,security,ops}/`：复用并补充真实行为回归；不以源码字符串断言代替事务验证。

## Tasks & Acceptance

**Execution:**
- [ ] `edw-api/src/edw_api/documents/`、`review/`、`edw-web/src/features/templates/`、`migrations/versions/` — 实现 5.6 双向版本化需求/测试项/用例/验收链接、真实覆盖分母与缺失/冗余/过期提示，保护批准阈值；实现 5.7 条件、指标、单位、阈值、验证方式与来源的结构化字段和审校，拒绝无依据阈值替换。
- [ ] `edw-api/src/edw_api/review/`、`documents/`、`knowledge/` — 核实并修复已发现状态、引用、授权和字段检查问题。
- [ ] `contracts/document-ast-v1.schema.json`、`edw-web/src/features/templates/` — 对齐草稿契约并恢复手工修改后的关闭路径。
- [ ] `tests/contract/`、`tests/security/` — 补充跨版本、顺序引用、治理变化、字段敏感信息和人工复查用例。
- [ ] `deployment/`、`scripts/`、`docs/` — 添加 Compose 打包容器、产物校验及使用说明。
- [ ] `_bmad-output/implementation-artifacts/` — 汇总七故事审查、独立复核、测试与远端证据，准确记录未完成项。

**Acceptance Criteria:**
- Given 已实现故事与候选工作树，when 审查修复并独立复核，then 已确认问题有修复及回归证据，故事范围不被静默扩大或缩减。
- Given 明确的 openEuler 目标，when 运行 Compose 打包，then 产生包含部署输入、源码清单及校验和的可核验产物。
- Given seadee-test 隔离测试环境，when 通过 SSH 验证候选产物，then 记录环境、执行结果及失败原因，不能借用历史证据证明通过。

## Implementation Notes

## Spec Change Log

## Review Triage Log

## Verification

- `uv run --no-sync pytest -q tests/contract tests/security tests/ops`：按实际改动选择相关用例并处理失败。
- `npm --prefix edw-web run typecheck`、前端 lint/build：成功。
- `git diff --check`：无空白错误。
- SSH `seadee-test`：候选源码/产物校验、容器打包与隔离运行验证，保留退出码及脱敏证据。
