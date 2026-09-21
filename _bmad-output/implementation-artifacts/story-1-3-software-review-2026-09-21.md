# Story 1.3 软件实现与静态审查收尾

状态：`done`，仅适用于用户收窄后的软件实现、静态审查和编译交付。运行验证 `cancelled-by-user / not-verified`，未声明运行 AC 通过，未推送，未进入 1.4。提交归属已重建，提交结果见本次交付的 Git 历史与主代理最终回执。

## 用户范围变更

用户明确“取消实际环境验证，继续”，随后要求“继续开发 story 1.3”。实际环境验证从本次交付范围取消，记 `cancelled-by-user / not-verified`，不再作为等待环境的阻塞项。既有测试、迁移、浏览器、性能和故障演练的历史要求与结果保留用于追溯，不执行测试套件，不启动或访问服务、数据库、浏览器、隧道或部署候选。

## 修复与审查

1. `edw-web/src/auth/oidc.ts`：登录返回白名单补齐发现页面及 `records/{UUID}`，避免未登录打开另一项目记录时丢失目标。只保留 pathname；外部地址、非法 UUID、查询、片段及尾随换行仍拒绝。对应 `oidc.test.ts` 补充正反用例源码。
2. `edw-web/src/features/workspace/DiscoveryPanel.tsx`：固定视图不再静默覆盖冲突的显式筛选。home/documents 的非文档 kind、references 的 todo 集合、favorites 的其他 tab 明确显示校验说明与重置；禁用查询、隐藏旧记录/计数/存储/操作。`records?from` 同样受约束；重置保留完整当前路径并清除查询。兼容的交集与搜索功能空态修复保留。
3. `DiscoveryPanel.test.tsx`：覆盖冲突分支、不同冲突请求键、兼容交集，以及查询禁用后仍返回缓存的替身场景。源码已检查和编译，测试未运行。

独立审查分别覆盖后端授权/事务/游标/迁移权限、前端状态与路由、D01–D12 测试源码及 fixture 安全。后端和覆盖审查未发现确定缺陷；前端发现上述两项 medium 问题，均已修复。主线程补齐首页和详情来源冲突边界后，新的一次性 `eid_reviewer` 复审未发现确定缺陷。没有将代理结论代替主线程差异核对。

## 当前检查结果

| 检查 | 结果 |
|---|---|
| Node 24.20.0，TypeScript `tsc -b` | exit 0 |
| 前端 ESLint 全源检查 | exit 0 |
| Vite 生产构建 | exit 0；96 modules |
| discovery 后端、迁移、fixture、契约/安全/ops 测试源码 Ruff | exit 0 |
| 审查清单中 31 个 Python 文件字节码编译 | exit 0；不导入应用模块，pyc 写入 `.local` |

构建产物：`index-BZGbf2cd.css`、`index-Bx6DCJXp.js`。构建前核对 package scripts 与 Vite 配置，仅执行检查及构建入口。

本轮重新核实 `Muse Spark 1.3 Contributor` 对应 `opencode-go/muse-spark-1.3-contributor`，实际调用退出 0；事件仅 `step_start/text/step_finish`，无工具调用。模型未发现指定修复的阻塞缺陷，指出列表内部部分冲突保护在顶层拒绝后不可达，不影响正确性，保留现有保护以避免扩大本次改动。其测试建议均未执行。模型行号是附件位置，主线程按实际源文件复核，不能当实际行号引用。

## 证据与归属

- `.local/story-1-3-closeout-20260921/login-return-before/`、`filter-before/`：修改前备份；filter 另保留代理交付版本供主线程修正追溯。
- `review-manifest.json`：初始 51 文件审查候选及 SHA-256；`final-manifest.json`：包括新增 OIDC 变更的最终 53 文件快照。它们是审查候选清单，不是可直接全量暂存的提交清单。
- `review-packet.txt`、`model-mapping.json`、`review-command.json`、`review-restrictions.json`、`opencode-review.jsonl`、`opencode-review.md`、`review-status.json`：模型身份、受限调用和原始结论。
- `verification.json`：主线程检查结果。原 Git HEAD 为 `2680247ab3a45bef9246d23328ce18ffe597bdb8`；未改写历史基线。

提交归属已拆分：前置远端支持单独记录，Story 提交只包含相对于该前置版本的业务增量及本次交付文档。采用隔离 Git 索引重建开工 `tracked.diff`，12 个历史文件的 Git blob 均与原差异声明的对象摘要匹配；没有通过回退工作树拆分。全局忽略规则隐藏的远端测试中，`test_remote_manifest_integration.py` 与 `test_remote_guard.py` 是既有测试的直接导入依赖，已与其余六份对应远端测试一起纳入前置候选。候选通过静态导入闭包、Ruff、编译及 diff 检查，未执行测试。

README 仅提交可明确归属的 Story 1.3 段落；标题、远端环境介绍等既有修改保留未提交。Sprint 仅提交本 Story 状态及必要的 Epic 状态。`.agents/`、`.claude/`、`.codex/`、`_bmad/`、其他规划/历史文档及独立 `remote_candidate_*` 运维工具保留原状，不混入业务提交。具体路径见 `story-1-3-commit-ownership-2026-09-21.md`。

## 未验证的行为

全部当前实际环境验证已取消。静态源码无法证明 PostgreSQL 锁/回滚、真实 OIDC 登录链、刷新持久性、浏览器竞态、重置点击导航、视觉和性能结果。回归测试源码存在不等于执行通过；历史运行失败不因本轮修复或取消而改写。需要未来实际环境验收时，必须取得新的明确指令。
