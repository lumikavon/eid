# AC、YAGNI 与门禁风暴审计报告

日期：2026-09-14
范围：`_bmad-output/implementation-artifacts` 与 `_bmad-output/planning-artifacts` 中的 Story、PRD、Epic、架构和 UX 验收要求。

## 审计结论

形式 AC 数量已符合“单 Story 不超过 5 条”。本轮发现的主要问题不是条目数，而是单条 AC 将多个可独立失败的行为、测试或环境义务捆绑；同一性能、视觉和真实环境要求又被功能 Story、集成 Story 与最终账本重复持有。这会使失败没有唯一归因，并诱发不必要代码和重复门禁。

已完成以下调整：

| 问题 | 修改 | 唯一验证/Owner |
|---|---|---|
| Story 1.1 的启动、认证、依赖故障、环境 guard 与视觉清单混合 | 改为 5 条单结果 AC；删除把全量视觉属性和多故障域合在一条的表述 | 浏览器 E2E、API 契约、依赖故障、guard、截图审查各一项 |
| Story 1.2 预设 epoch、未来任务/流，以及 DB grant 与审计事务混合 | 以“下一次使用按当前策略决定”为结果；拆分数据库负授权和审计原子性 | 决策表、撤权集成、negative grant、事务故障、浏览器状态 |
| 所有 UI Story 继承全状态与全 viewport 截图 | 每个 Story 只声明改动行为的状态；7-5 作为全基线 owner，12-6/13-6只查证据引用 | 改动控件测试；7-5 baseline manifest；账本 referential-integrity |
| 功能 Story 反复承担 P95/SLA | 功能 Story 仅记录结构化 timing event；13-4 是唯一数值 pass/fail owner | timing-event 契约；13-4 冻结工作负载 |
| Copilot、发布和 DOCX/PDF Story 的实现预设与巨型 AC | 按操作族、版本化 GateSet 和输出结果重写；实现机制下沉至架构/策略 | 每个操作族一张参数表；GateSet 单行翻转；格式 Golden validator |
| 12-6/13-6 再跑全部功能和视觉 | 改为 owner、环境类别、结果和不可变证据引用的闭包检查 | owner/source-clause referential-integrity checker |
| 1:1 视觉与 AA 的冲突 | 保持为两个独立结果；由 VC-1 记录处置，不要求同一 Story 伪造同时通过 | 冲突登记完整性检查 |
| 每次小修重复四层评审 | NFR-18 改为一次独立、风险驱动复审；安全、数据完整性或外部副作用才追加专项复审 | diff、适用回归和未关闭 finding 的独立复审记录 |

## 保留的约束

- 安全、数据完整性、授权、审计原子性、数据库隔离与禁止未授权外部操作继续是硬约束。
- 真实 IdP、企业系统、官方资产、实际质量、容量、HA 与生产等证据仍由 Epic 13 的具名 Story 持有；本地测试不会被表述为真实验收。
- Epic 12.5、13.4、13.5 的安全、兼容、性能和恢复内容没有被删除；本轮只移除了其在无关功能 Story 中的重复验收。

## 独立复核后的补正

- 契约适用性矩阵现在包含“变更新引入或可能影响”的案例；授权、重放、幂等、消息、持久化和外部副作用变更必须保留相应安全/数据完整性回归。
- FR-29 required-gate registry 是 GateSet 的最小不可削减来源。发布先验证 registry 覆盖，缺失、未知或弱化的行 fail closed。
- 13.1 的 evaluation profile 只能细化 FR-34/AC-5 的最低域覆盖和指标，运行前有规范一致性验证，不能自降配额或删指标。
- Story 1.1 readiness 使用一个参数化依赖断开测试覆盖所有必需本地依赖；Story 1.2 明确保留当前 epoch 实现，但验收判定新鲜授权结果。

## 修改的主要文件

- `implementation-artifacts/spec-1-1-runnable-workspace.md`
- `implementation-artifacts/spec-1-2-current-access.md`
- `planning-artifacts/epics.md`、`architecture.md`、`prds/prd-eid-2026-09-08/prd.md`
- `planning-artifacts/epic-1-secure-workspace.md`、`epic-2-controlled-authoring.md`、`epic-3-trustworthy-evidence.md`、`epic-4-controlled-ai.md`、`epic-6-formal-delivery.md`、`epic-7-observable-core.md`、`epic-12-integration-readiness.md`、`epic-13-real-acceptance.md`
- `planning-artifacts/ux-designs/ux-eid-2026-09-08/DESIGN.md`、`EXPERIENCE.md`

## 后续维护规则

1. 每个 Story 至多五条 AC；每条只描述一个结果，并写出一个验证方式。
2. Story 需要新操作族、独立失败域或独立交付价值时，先拆 Story，不在 AC 中堆叠实现细节。
3. 测试包、状态、性能、视觉和真实验收先查适用性/owner 矩阵；不要复制到所有 Story。
4. 汇总 Story 只检查证据闭包，除非它自己新增跨边界行为。
