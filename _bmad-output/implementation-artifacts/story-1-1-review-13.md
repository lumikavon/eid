# Story 1.1 第十三轮审查处置

结论 changes-required。三份独立报告完成；acceptance 催收后仍未提交终态，已中断，不能计为通过。


## 原始报告 blind

# Story 1.1 Review 13 — Blind Layer

**Verdict:** changes-required

Reviewed the complete Story 1.1 change set against baseline `3440d2f89647aaeacf49213285c055dbe365df7d`, with emphasis on security boundaries, isolation, readiness semantics, failure behavior, and executable contracts.

## Findings

### 1. API and Worker share one S3 administrator credential

- **Trigger:** Either the API or Worker process is compromised, misconfigured, or later starts using its already-injected S3 client credentials.
- **Evidence:** `deployment/compose.yaml:62-69` places `EID_S3_ACCESS_KEY=eid-local` and `EID_S3_SECRET_KEY=eid-local-secret` in the shared `&runtime` environment; `deployment/compose.yaml:88-91` inherits that same environment for the Worker. `deployment/seaweedfs/s3.json:1` defines that single identity with `Admin`, `Read`, `Write`, `List`, and `Tagging` actions. This conflicts with the Story boundary that rejects shared credentials and with the Worker independent-identity/resource-boundary requirement.
- **Impact:** The API and Worker are indistinguishable to object storage, and either business service can exercise administrative object-storage capabilities. A service compromise can create/delete or alter storage state outside the service's intended role, while audit evidence cannot attribute the action to the responsible process.
- **Required fix:** Provision separate host-only/bootstrap, API, and Worker S3 identities. Do not inject the administrative identity into either business container. Grant each runtime identity only the bucket/object operations Story 1.1 actually requires, verify the exact identities and grants in the isolation guard, and add positive and cross-role negative tests.

### 2. Public readiness stays green after the Keycloak client loses required PKCE/flow configuration

- **Trigger:** After bootstrap, the persisted `eid-web` Keycloak client is changed (for example PKCE S256 is removed, implicit flow is enabled, the redirect URI changes, or the audience mapper is removed) while the realm issuer and signing keys remain available.
- **Evidence:** The bootstrap guard checks those client properties in `scripts/verify_local_environment.py:624-665`, but the runtime `_keycloak_status` probe in `edw-api/src/edw_api/main.py:258-331` checks only configured audience/JWKS URLs, discovery issuer/JWKS URI, and usable signing-key material. `/health/ready` treats that narrower result as the complete Keycloak dependency status at `edw-api/src/edw_api/main.py:373-423`.
- **Impact:** `/health/ready` can return 200 and the UI can display “依赖已就绪” even though the required Authorization Code + PKCE login path is no longer correctly configured. This violates the Story requirement that readiness reflect required configuration and the actual state of Story dependencies.
- **Required fix:** Bind readiness to a current, fail-closed verification of the persisted `eid-web` client configuration (including enabled/public client, standard flow enabled, implicit/direct grants disabled, exact redirect/origin/logout URI, PKCE S256, and audience mapper). Use a narrowly scoped verification mechanism or a freshness-bound bootstrap attestation rather than injecting the bootstrap administrator credential into the API. Add a drift regression proving readiness becomes 503 when one of these properties changes.

### 3. The ownership guard does not prove exclusive attachment of managed volumes

- **Trigger:** A container outside Compose project `eid-local` mounts `eid-local-postgres`, `eid-local-keycloak`, or `eid-local-seaweedfs` after the ownership record and volume labels have been created.
- **Evidence:** `scripts/verify_local_environment.py:372-400` enumerates managed volume names and validates their labels, but it enumerates containers only with `label=com.docker.compose.project=eid-local`. It never asks Docker which other containers mount the managed volume names. `verify_database` subsequently confirms only that the expected PostgreSQL container mounts the expected volume (`scripts/verify_local_environment.py:404-442`).
- **Impact:** The guard reports ownership/isolation verified while an unowned container can concurrently read or modify the same persistent database, identity, or object-store data. Migration and startup may proceed despite the required project exclusivity being false.
- **Required fix:** Enumerate all containers, including stopped containers, that reference each managed volume; require every attachment to belong to the expected owned Compose service and nonce, and reject unexpected or duplicate attachments before initialization, migration, or startup. Add a negative guard test with a foreign container attached to each managed volume class.

## Verification run

- `uv run --frozen pytest tests/contract tests/security tests/ops tests/worker` — 232 passed, 11 skipped.
- Pinned Node 24.20.0/Corepack pnpm: Web unit tests 42 passed; TypeScript typecheck and ESLint passed.
- Live container, browser, and production/enterprise acceptance were not rerun by this blind layer.


## 原始报告 edges

[
  {
    "location": "scripts/verify_local_environment.py:303-329",
    "trigger_condition": "Source changes after image build but before runtime manifest recording",
    "guard_snippet": "require(image_labels['io.eid.source-fingerprint'] == source_fingerprint(service), 'image/source mismatch')",
    "potential_consequence": "Manifest certifies a stale image against newer source"
  },
  {
    "location": "scripts/verify_runtime_logs.py:98-125",
    "trigger_condition": "A service container is replaced after inventory but before log collection",
    "guard_snippet": "if _owned_service_containers(state['nonce']) != containers: raise RuntimeError('container set changed during scan')",
    "potential_consequence": "Clean result excludes the replacement container's logs"
  }
]


## 原始报告 verification

No verification gaps found.


## 主控逐项处置

| ID | 判定 | 依据与处理 |
|---|---|---|
| B1 | high / patch | 真实 S3 配置把同一 Admin 凭据注入两个业务进程，违反独立身份与最小权限边界。拆分 bootstrap/API/Worker 身份，仅保留本 Story 需要的 bucket 探测权限并验证拒绝越权。 |
| B2 | medium / patch | 当前 runtime 只检查 discovery/JWKS，持久客户端配置漂移不会降级。使用最小权限、失败关闭且有界的当前配置核验，不把 bootstrap 管理员注入业务服务。 |
| B3 | high / patch | ownership 仅按项目标签列容器，无法发现外部容器挂载受管卷。核查包括停止容器的全部卷引用，拒绝外部/非预期/重复挂载。 |
| E1 | medium / patch | 记录时计算工作区指纹未绑定实际构建输入，构建后修改可误绑定。构建前后及实际镜像绑定校验，增加时序负例。 |
| E2 | medium / patch | 日志扫描只核验开头容器集合，替换后仍可返回旧容器通过。扫描末尾再核验容器集合与运行镜像，变化即失败。 |

Verification 返回 No verification gaps found；这不覆盖其他层的新缺陷。所有有效修复后重新运行必要验证并进行完整独立审查；不提前 done 或提交。

## 真实整合失败与修复

第一轮 bootstrap 在 Keycloak 只读角色精确检查处失败。主线程读取实际 26.3.3 角色定义，确认 view-clients 是含 query-clients 的复合角色；直接授予仍限 view-clients/view-realm，有效令牌严格要求三个只读角色，额外管理角色仍拒绝。该修复后 Python 267 passed / 11 live-gated skipped、Web 42 passed。

第二轮 bootstrap 通过 Keycloak 后，S3 运行身份的 HeadBucket 403；失败没有被跳过。主线程以新主机凭据复核 GetBucketLocation 为 AccessDenied，实际容器版本是 3.97 commit 76452ab593995ab52b75e681de5b221de1e3f006，挂载配置匹配三身份。独立调查曾使用尚未重建的旧 API 容器凭据获得 InvalidAccessKeyId，故其“新密钥未加载”的诊断不适用于本次失败，已驳回。

实际根因在该提交 auth_signature_v4.go 的 doesSignatureMatch：签名认证阶段无条件检查 ACTION_WRITE，导致合法只读 SigV4 请求被拒绝。主线程核对 4.46 源码 verifyV4Signature 已按 GET/HEAD 选 Read，其他方法选 Write。固定到官方 4.46 linux/amd64 摘要 sha256:6a602956ac4915057199a5271343e9c86c403a561db7c21033362f6791aa29c9；不授予运行身份 Write/Admin、不使用共享密钥、不变更 bucket ACL、不删除数据。后续实际通过仍待重跑。

来源：[原镜像对应签名代码](https://github.com/seaweedfs/seaweedfs/blob/76452ab593995ab52b75e681de5b221de1e3f006/weed/s3api/auth_signature_v4.go#L187-L197)、[4.46 签名代码](https://github.com/seaweedfs/seaweedfs/blob/4.46/weed/s3api/auth_signature_v4.go#L247-L258)、[官方发布](https://github.com/seaweedfs/seaweedfs/releases/tag/4.46)。原始失败日志保留在本地 bootstrap-round13.log 与 bootstrap-round13-retry.log，未计为通过。

Round-13 current evidence (2026-09-11 01:19 UTC): separate bootstrap/API/Worker S3 identities retain bucket-scoped runtime Read only; all managed-volume attachments, including stopped containers, are checked. Keycloak runtime readiness uses a dedicated read-only monitor and validates current persisted realm/client/mapper contracts. Its two granted roots expand to exactly three effective read-only roles. Build fingerprints are bound to immutable image labels, and log scans recheck the exact container/image/source set after collection. Actual integration exposed the Keycloak composite-role mismatch and SeaweedFS 3.97 SigV4 Write precheck; both failed runs were retained. SeaweedFS is now pinned to verified 4.46 linux/amd64 digest, and the unchanged S3 positive/negative guard passed. Full bootstrap exit 0; Python 267 passed / 11 opt-in live skipped; explicit live 11 passed (71.55s); Web units 42 passed; browser 19 passed (58.3s); scoped Ruff and license regeneration check passed. All 18 screenshots were refreshed at 2026-09-11T01:19:02.331213+00:00 and bound to the new runtime. Post-flow nine-service scan at 2026-09-11T01:19:10.282503+00:00 has zero configured matches. Independent round 14, including current visual approval, is required before done or commit.
