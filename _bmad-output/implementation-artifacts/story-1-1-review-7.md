# Story 1.1 第七轮审查处置

结论：changes-required。四路独立检查已完成；汇总代理催收后仍未交回报告，已中止。下列逐项记录依据四路终态输出，由主控核对实际源文件与冻结约束。盲审自行提出 finding floor，与 PROMPT 禁止凑数冲突，不采纳该数量要求。

## 原始意见与逐项裁定

| 来源 | 原始问题及位置 | 裁定 |
|---|---|---|
| blind 1 | compose.yaml:71 未消费 parse_ocr/render | 不采纳：本 Story 明确不增加业务 handler，重任务运行隔离随实际用途交付，不能为健康检查提前引入消费者。 |
| blind 2 | compose.yaml:49 API 使用 Worker RabbitMQ 账户 | 本轮非阻塞：当前独立数据库身份已落实，细粒度服务身份/授权在明确依赖的 Story 1.2 交付，任务传输在 1.4。本地专属 broker 身份没有被作为用户身份回退。记录后续约束，不声称生产最小权限完成。 |
| blind 3 | main.py:175 Keycloak client 运行后漂移未探测 | 不采纳，沿用已核实第六轮裁定：启动核对实际 client，运行 discovery/JWKS；管理员后续变更需重新验证，不引入无定义的配置证明机制。 |
| blind 4 | main.py:111 marker/revision 不能发现表缺失或读权限撤回 | 采纳：实际最小账户表及必要读取能力需要探测，保留不读取敏感内容的只读检查。 |
| blind 5 | nginx/default.conf:14 动态健康结果缺少 no-store | 采纳：健康响应明确禁止缓存。 |
| blind 6 / acceptance 1 | api.ts:40 丢弃结构化依赖原因 | 采纳：按白名单呈现持久可读的依赖失败原因，不直接反射原始服务器内容。 |
| blind 7 | api.ts:42 非法成功 JSON 泄露浏览器解析错误 | 采纳：转为可读、稳定的无效响应状态。 |
| blind 8 | db.py:12 账户查询缺少 statement timeout | 采纳：服务端查询加时限并覆盖失败响应，浏览器取消不等于数据库取消。 |
| blind 9 | main.py:53 未预期异常无日志 | 采纳：记录脱敏错误类别和关联 ID，不记录异常正文、请求内容、token 或密钥。 |
| blind 10 | verify_local_environment.py:141 指纹遗漏 .dockerignore 与宽 COPY 输入 | 采纳：精确收紧构建 COPY 输入并同步指纹，将 .dockerignore 纳入。 |
| blind 11 | verify_versions:81 未强制 Docker/Compose 精确版本 | 不强制 Docker 29.1.3：冻结规范仅说已知可用，不是唯一允许版。补充实际 Docker/Compose 版本证据与所需能力说明。 |
| blind 12 | verify_image_manifest:105 未核验实际架构 | 采纳：核验本地 Linux amd64，未知架构安全失败。 |
| edge 1 | auth.py:19 JWKS 使用库默认网络期限 | 采纳：显式有界 JWKS 获取期限，保留真实 HTTP 轮换测试。 |
| edge 2 | worker/app.py:27 多操作累积超过调用期限 | 采纳：Worker 探测使用总期限，并约束持续停滞时的资源占用。 |
| edge 3 | main.py:160 S3 客户端未关闭 | 采纳：finally 释放。 |
| edge 4 | worker/app.py:49 Redis/S3 客户端未关闭 | 采纳：finally 释放。 |
| edge 5 / verification | verify_runtime_logs.py:85-92 大小写变体令牌字段漏检 | 采纳：字段模式大小写不敏感，参数化负例覆盖 Bearer/bearer/BEARER/混合大小写。 |
| acceptance 2 | epic-1-context.md:25 缺依赖许可证清单 | 采纳：基于已锁定/实际安装元数据生成许可证/依赖清单，明确未知项及容器组件边界，不编造法律结论。 |
| acceptance 3 | verify_versions:81 版本错误缺实际值和修复方法 | 采纳：每种工具报告实际值、要求值与具体修复方向，拒绝时不进入迁移。 |

## 修复前验证

Python 162 passed/9 opt-in skipped；Web units 26 passed；浏览器 19 passed；实际本地测试 9 passed；bootstrap exit 0；九服务日志零配置模式匹配。以上证明修复前快照，不能代替本轮修复后的验证与独立审查。当前仍 in-progress，未提交，未进入下一 Story。

## 汇总报告恢复与裁定修订

主控在 finalreport.local/review7.md 找到汇总代理已写入但未回报的完整报告，现迁入 .local/review7-complete.md。以下保留完整原文。复核其服务身份约束后，修订 blind 2 为采纳：为 API 配置独立且仅足够健康控制命令/回复所需的 RabbitMQ 身份，实际验证不能消费或配置业务队列。本修改属于当前三工程服务隔离，不提前实现任务业务。平台校验按已完成的保守实现保留；原始审查反对追加精确 Docker 版本策略的意见已满足。

# Story 1.1 Round 7 independent code review

Review target: `1-1-runnable-workspace` at baseline `3440d2f89647aaeacf49213285c055dbe365df7d`, including the 123-file authoritative Round 7 inventory. The generated unified diff was 628,602 bytes. All four configured review layers completed.

## Consolidated verdict

`changes-required`: 0 decision-needed, 14 patch groups, 0 deferred, 4 rejected raw findings. The 14 patch groups contain 17 independently filed raw findings; duplicates were retained below before grouping.

1. **[medium][patch] Give the API a distinct least-privilege RabbitMQ identity.** The API receives `eid_worker` credentials and that user has configure/write/read `.*` over the whole vhost, so the API health probe crosses the intended service-identity boundary. Evidence: `deployment/compose.yaml:26`, `deployment/compose.yaml:49`, `scripts/verify_local_environment.py:378-392`.
2. **[medium][patch] Make PostgreSQL readiness prove the Story 1.1 runtime schema and API privileges.** `_postgres_status` checks only the database marker and Alembic revision; missing identity tables or revoked SELECT privileges still return ready while `/api/v1/me` fails. Evidence: `edw-api/src/edw_api/main.py:111-129`, `edw-api/src/edw_api/db.py:16-30`.
3. **[low][patch] Mark health responses `Cache-Control: no-store`.** `/api/` has the header but `/health/` does not, allowing stale health state to be reused by a cache. This is a direct configuration correction. Evidence: `deployment/nginx/default.conf:13-14`.
4. **[medium][patch] Preserve actionable dependency failure details in the SPA.** The API returns exact `details.checks`, while `getReadiness` discards the response body and displays a generic message. Evidence: `edw-api/src/edw_api/main.py:329-340`, `edw-web/src/app/api.ts:39-47`, `edw-web/src/app/App.tsx:69`.
5. **[low][patch] Normalize malformed successful readiness responses.** `response.json()` failures escape as browser-generated parser text and become the persistent UI readiness state. A direct parse guard should emit the existing readable invalid-response message. Evidence: `edw-web/src/app/api.ts:40-47`, `edw-web/src/app/App.tsx:69`.
6. **[medium][patch] Bound `/api/v1/me` SQL execution.** The shared connection has only a connect timeout; a blocked account query can occupy a server thread after the browser aborts. Evidence: `edw-api/src/edw_api/db.py:10-30`.
7. **[medium][patch] Record sanitized unexpected-exception diagnostics.** Middleware consumes every unexpected exception and emits a correlated 500, while Uvicorn access logging is disabled and no exception diagnostic is recorded. Log only safe exception type plus request/trace identifiers. Evidence: `edw-api/src/edw_api/main.py:44-63`, `deployment/compose.yaml:45`.
8. **[medium][patch] Include all Docker build semantics in runtime source fingerprints.** `_source_paths` omits `.dockerignore` while the Web Dockerfile broadly copies `edw-web`; a build-context rule can change image contents without invalidating the recorded fingerprint. Evidence: `scripts/verify_local_environment.py:141-199`, `deployment/web.Dockerfile:7`, `.dockerignore:1-16`.
9. **[medium][patch] Bound authentication JWKS retrieval.** `PyJWKClient` is created without a timeout and the installed library defaults to 30 seconds, well beyond the browser's eight-second request budget. Evidence: `edw-api/src/edw_api/auth.py:16-24`, `edw-web/src/app/api.ts:9-16`; verified installed signature reports `timeout: float = 30`.
10. **[medium][patch] Enforce one shared deadline inside Worker dependency readiness.** PostgreSQL, Redis, and S3 operations each receive independent timeouts, so their sequential worst case can exceed the caller's control-command deadline and create false Worker failures. Evidence: `edw-worker/src/edw_worker/app.py:27-66`, `edw-api/src/edw_api/main.py:251-275`.
11. **[low][patch] Close S3 and Redis readiness clients deterministically.** API S3 polling and Worker Redis/S3 probing create clients without `close()` paths; repeated health traffic can retain connection pools until garbage collection. This is a direct resource-lifecycle correction. Evidence: `edw-api/src/edw_api/main.py:160-172`, `edw-worker/src/edw_worker/app.py:49-66`.
12. **[medium][patch] Make runtime credential scanning case-insensitive.** `[Bb]earer` misses `BEARER` and mixed-case schemes even though request authentication accepts case variants; both the scanner and its tests omit those forms. Evidence: `scripts/verify_runtime_logs.py:85-92`, `tests/ops/test_runtime_logs.py:79-119`, `edw-api/src/edw_api/auth.py:40-49`.
13. **[medium][patch] Produce the required dependency-license inventory.** The Story/Epic constraint requires dependency lock, license inventory, and compatibility evidence, but the implementation contains only package/image locks and no license or SBOM artifact or gate. Evidence: `_bmad-output/implementation-artifacts/epic-1-context.md:25`, `deployment/images.lock.json:1-20`, repository search found no license/SBOM artifact.
14. **[medium][patch] Report detected, required, and remediation values for version failures.** Node/pnpm/Python/uv predicates emit fixed required-version strings, and most omit both the detected value and a repair action required by the startup error contract. Evidence: `scripts/verify_local_environment.py:81-96`, `_bmad-output/implementation-artifacts/spec-1-1-runnable-workspace.md:38`.

## Raw findings and individual verdicts

Raw text is preserved before deduplication. `BH` = blind-hunter, `EC` = edge-case-hunter, `VG` = verification-gap, `AA` = acceptance-auditor.

1. **BH / false / rejected:** "Worker starts with only generation,retrieval,review,integration although six queues are declared; parse_ocr and render jobs will remain unconsumed." Refutation: Story 1.1 intentionally has no business producer/handler, and the frozen triage already records this exact later-scope claim as rejected at `spec-1-1-runnable-workspace.md:143`.
2. **BH / medium / patch:** "API has the same unrestricted RabbitMQ account used by the Worker." Verified at `deployment/compose.yaml:26,49` and `scripts/verify_local_environment.py:378-392`; grouped as patch 1.
3. **BH / false / rejected:** "API readiness does not verify the enabled client, redirect URI, public client, PKCE, and audience mapper after bootstrap." The facts are true, but the bad outcome is assigned to the wrong layer: the API's six dependency probes intentionally verify reachable discovery/JWKS and contain no Keycloak administrator credentials; workspace bootstrap independently validates exact client and mapper configuration at `scripts/verify_local_environment.py:395-453`. Adding admin credentials to the API would violate the service boundary.
4. **BH / medium / patch:** "PostgreSQL marker and Alembic revision do not prove required tables or API privileges." Verified at `edw-api/src/edw_api/main.py:111-129`; grouped as patch 2.
5. **BH / low / patch:** "NGINX health responses omit Cache-Control: no-store." Verified at `deployment/nginx/default.conf:13-14`; grouped as patch 3.
6. **BH / medium / patch:** "SPA discards structured readiness details and always shows a generic dependency message." Verified at `edw-web/src/app/api.ts:39-47`; grouped as patch 4.
7. **BH / low / patch:** "Malformed readiness JSON exposes parser text instead of a readable dependency state." Verified through `api.ts:42` and `App.tsx:69`; grouped as patch 5.
8. **BH / medium / patch:** "The account query lacks a statement timeout." Verified at `edw-api/src/edw_api/db.py:10-30`; grouped as patch 6.
9. **BH / medium / patch:** "Unexpected application exceptions are converted to 500 without an operator diagnostic." Verified at `edw-api/src/edw_api/main.py:44-63` with Uvicorn access logging disabled at `deployment/compose.yaml:45`; grouped as patch 7.
10. **BH / medium / patch:** "Runtime source fingerprints omit `.dockerignore` and do not fully bind broad Docker COPY inputs." Verified at `scripts/verify_local_environment.py:141-199` and `deployment/web.Dockerfile:7`; grouped as patch 8.
11. **BH / low / rejected:** "The guard does not enforce Docker/Compose 29.1.3." Story startup predicates explicitly require Node/dependency/image versions, while Docker 29.1.3 is a documented known prerequisite; incompatible Compose commands fail loudly. The proposed extra engine-version policy is unlikely to affect the declared Windows/x86 local workflow and adds a new compatibility guard beyond the frozen AC.
12. **BH / low / rejected:** "The manifest platform string is trusted without checking engine architecture." `verify_engine` already requires local Linux containers, and pinned architecture-specific digests fail or run under Docker's configured emulation. The remaining risk is limited to atypical ARM hosts outside the declared environment; adding a platform policy branch is not justified for this low-probability case.
13. **EC / medium / patch:** "JWKS endpoint slow-connect can block authenticated requests because `PyJWKClient` has no explicit timeout." Verified; installed default is 30 seconds. Grouped as patch 9.
14. **EC / medium / patch:** "Worker dependency operations can cumulatively exceed the caller deadline." Verified at `edw-worker/src/edw_worker/app.py:27-66`; grouped as patch 10.
15. **EC / low / patch:** "API readiness creates an S3 client on every poll without closing it." Verified at `edw-api/src/edw_api/main.py:160-172`; grouped as patch 11.
16. **EC / low / patch:** "Worker readiness creates Redis and S3 clients without closing them." Verified at `edw-worker/src/edw_worker/app.py:49-66`; grouped as patch 11.
17. **EC / medium / patch:** "Runtime log scanner misses uppercase and mixed-case Bearer credentials." Verified at `scripts/verify_runtime_logs.py:91`; grouped as patch 12.
18. **VG / medium / patch:** "Runtime log gate misses case-variant Bearer credentials." Pre-verified layer evidence: current `[Bb]earer` covers only two casings, the browser gate trusts the scan, and `tests/ops/test_runtime_logs.py:95` exercises only title case. Grouped as patch 12.
19. **AA / medium / patch:** "Dependency degradation reason is discarded by the SPA." Verified at `edw-api/src/edw_api/main.py:329-340` and `edw-web/src/app/api.ts:39-47`; grouped as patch 4.
20. **AA / medium / patch:** "Required dependency-license inventory is absent." Verified by the Epic constraint and a repository-wide license/SBOM search with no implementation artifact; grouped as patch 13.
21. **AA / medium / patch:** "Version failures omit detected value required by startup error contract." Verified at `scripts/verify_local_environment.py:81-96`; grouped as patch 14.

## Rejected appendix

- **false:** Consuming `parse_ocr` and `render` in Story 1.1 contradicts its no-business-handler boundary and repeats an already rejected finding.
- **false:** Exact Keycloak client configuration is workspace bootstrap/operational verification; checking it in API readiness would require forbidden administrative capability in the API.
- **low:** Exact Docker/Compose version enforcement expands the frozen startup predicates and has low practical value in the documented local environment.
- **low:** Host architecture enforcement addresses an atypical environment and adds policy complexity beyond the declared local target.

## Review boundary

This reviewer did not edit application code, the Story status, or sprint tracking. The root development agent owns fixes, final validation, Story action-item integration, and commit.

## 实际 broker 探针发现与安全更新

独立 API 身份初始化和 bootstrap 已通过，但实际 passive queue declare 对 generation 未被拒绝，探针 exit 1。官方 GHSA-9q2j-2hq8-22r2 确认旧版 RabbitMQ 未授权检查导致队列元数据泄露，4.2.6 为修复版本：https://github.com/rabbitmq/rabbitmq-server/security/advisories/GHSA-9q2j-2hq8-22r2 。保留负例，不弱化断言。4.1.11-management-alpine 公共镜像不存在，选择官方可用 4.2.6-management 并锁定实际 linux/amd64 manifest sha256:f153635c99366bccfb869df82d466c1e4c1b0e432b0768984c4ee041c001f32c。同步镜像和依赖清单，实际更新与回归验证待完成。passive declare 检查的是元数据可见权限，已纠正原探针中将其等同 configure 权限的描述。

## 最终修复验证

全部有效修复已完成。Python 184 passed/9 opt-in skips，Web 30 passed，完整浏览器 19 passed，实际环境 9 passed (84.73s)，完整 bootstrap exit 0。RabbitMQ 4.2.6 上 API 控制请求/回复成功且 generation passive declare 被 ACCESS_REFUSED 拒绝。最终九服务日志扫描零匹配，时间及运行镜像绑定见对应 JSON。此记录为开发侧验证，独立第八轮审查仍待完成。
