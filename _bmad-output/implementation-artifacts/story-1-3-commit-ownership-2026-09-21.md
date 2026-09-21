# Story 1.3 提交归属

本次按前置远端支持、Story 业务增量分成两个本地提交，不推送、不执行实际环境验证。工作树源码原字节保留；文档仅做本次完成状态和证据登记。

## 前置远端支持

开工差异重建的 12 个 tracked 文件与原 Git blob 摘要一致；其余使用明确依赖文件的当前内容。8 份被全局忽略的远端测试以窄路径纳入，未修改忽略规则。

- `deployment/environments/seadee-develop.yaml`
- `scripts/initialize_local_storage.py`
- `scripts/remote_environment.py`
- `scripts/remote_service_operations.py`
- `scripts/seed_access_fixtures.py`
- `scripts/verify_access_delegation.py`
- `scripts/verify_access_fixtures.py`
- `scripts/verify_local_environment.py`
- `scripts/verify_runtime_logs.py`
- `tests/ops/test_access_delegation_probe.py`
- `tests/ops/test_access_fixture_manifest.py`
- `tests/ops/test_current_account_client_port.py`
- `tests/ops/test_live_access.py`
- `tests/ops/test_live_current_account.py`
- `tests/ops/test_live_dependencies.py`
- `tests/ops/test_live_migration.py`
- `tests/ops/test_remote_environment.py`
- `tests/ops/test_remote_final_readiness.py`
- `tests/ops/test_remote_guard.py`
- `tests/ops/test_remote_manifest_integration.py`
- `tests/ops/test_remote_postgres_client_port.py`
- `tests/ops/test_remote_runtime_snapshot.py`
- `tests/ops/test_remote_seed_paths.py`
- `tests/ops/test_remote_service_operations.py`
- `tests/ops/test_runtime_logs.py`
- `tests/ux/access.spec.ts`
- `tests/ux/shell.spec.ts`

## Story 1.3 增量

以下是相对前置提交的文件清单。README 只含 Story 段落，sprint 只含本 Story 状态；未整文件吸收预存修改。

- `README.md`
- `_bmad-output/implementation-artifacts/spec-1-3-workspace-discovery.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/story-1-3-commit-ownership-2026-09-21.md`
- `_bmad-output/implementation-artifacts/story-1-3-evidence/muse-review-20260921.md`
- `_bmad-output/implementation-artifacts/story-1-3-evidence/static-checks-20260921.json`
- `_bmad-output/implementation-artifacts/story-1-3-software-review-2026-09-21.md`
- `_bmad-output/implementation-artifacts/story-1-3-static-review-2026-09-21.md`
- `_bmad-output/implementation-artifacts/story-1-3-validation.md`
- `_bmad-output/planning-artifacts/development-validation-policy.md`
- `contracts/discovery.schema.json`
- `deployment/compose.yaml`
- `edw-api/src/edw_api/config.py`
- `edw-api/src/edw_api/discovery/__init__.py`
- `edw-api/src/edw_api/discovery/policy.py`
- `edw-api/src/edw_api/discovery/repository.py`
- `edw-api/src/edw_api/discovery/routes.py`
- `edw-api/src/edw_api/discovery/schemas.py`
- `edw-api/src/edw_api/main.py`
- `edw-web/src/app/AccessPanel.tsx`
- `edw-web/src/app/App.search.interaction-harness.tsx`
- `edw-web/src/app/App.search.interaction.test.ts`
- `edw-web/src/app/App.session.interaction-harness.tsx`
- `edw-web/src/app/App.session.interaction.test.ts`
- `edw-web/src/app/App.tsx`
- `edw-web/src/app/discovery-api.test.ts`
- `edw-web/src/app/discovery-api.ts`
- `edw-web/src/auth/oidc.test.ts`
- `edw-web/src/auth/oidc.ts`
- `edw-web/src/features/workspace/DiscoveryPanel.interaction-harness.tsx`
- `edw-web/src/features/workspace/DiscoveryPanel.interaction.test.ts`
- `edw-web/src/features/workspace/DiscoveryPanel.test.tsx`
- `edw-web/src/features/workspace/DiscoveryPanel.tsx`
- `edw-web/src/features/workspace/discovery.css`
- `edw-web/src/http/bounded-json.ts`
- `edw-worker/src/edw_worker/app.py`
- `migrations/versions/0007_workspace_discovery.py`
- `scripts/seed_access_fixtures.py`
- `scripts/seed_discovery_fixtures.py`
- `scripts/verify_discovery_fixtures.py`
- `tests/contract/test_discovery.py`
- `tests/contract/test_discovery_migration.py`
- `tests/ops/discovery_live_support.py`
- `tests/ops/test_discovery_fixture_safety.py`
- `tests/ops/test_discovery_ux_preflight.py`
- `tests/ops/test_live_dependencies.py`
- `tests/ops/test_live_discovery.py`
- `tests/ops/test_live_discovery_upgrade.py`
- `tests/ops/test_live_migration.py`
- `tests/security/__init__.py`
- `tests/security/test_discovery.py`
- `tests/ux/access.spec.ts`
- `tests/ux/discovery-fixtures.ts`
- `tests/ux/discovery.spec.ts`
- `tests/ux/shell.spec.ts`
- `tests/worker/test_worker_health.py`

## 保留未提交

全局/项目技能及代理配置、其他规划和历史 Story 文档、独立候选镜像/更新器工具、README 远端介绍及其他 sprint 历史变更均保留。候选工具不属于本次软件发现功能依赖闭包。

## 验证边界

业务代码已完成独立静态审查、Ruff/ESLint/TypeScript/Vite/Python 编译和指定 Muse 辅助审查；拆分候选另核对 Git 对象、源码哈希、静态 imports 及 diff。未运行测试套件和实际环境验证，历史结果不重新认证。`done` 仅指用户收窄后的软件交付。
