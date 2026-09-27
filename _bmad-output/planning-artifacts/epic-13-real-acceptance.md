---
epic_id: epic-13
status: planned
phase: cross-phase-real-and-production-equivalent-acceptance
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 13: Establish real efficacy, integration and operational acceptance

**当前安排：13.1–13.6 全部暂停运行验收，结果为 `not-run`。本 Epic 是后续验收责任清单，不是当前软件开发质量门禁；静态检查或编译不能将其标记为完成。仅可整理验收条款、证据缺口和检查相关源码，不启动环境，不执行模型效果、企业联调、UAT、设备、负载、安全故障或恢复实测。恢复须有用户后续明确指令；环境具备或前序软件工作完成不自动恢复。**

Retained future outcome: acceptance owners obtain actual R/P evidence for the whole three-phase product after every local implementation story. These are real-acceptance stories,not local tooling tasks. Sequential order is13-1→13-2→13-3→13-4→13-5→13-6 after12-6; a blocked/failed story remains uncompleted and stops this acceptance epic,never gets skipped or converted to done. No local implementation epic follows. Missing permission/environment is blocked/not-run,not deleted scope. None of these planned stories authorizes paid calls,external messages,production access or existing-data changes. Exact database and operation limits in epics.md remain binding. W/A/K are the same three business projects.

## Story 13.1: Validate real per-domain quality and the source-defined POC
**ID:** `13-1-real-quality-poc` | **Status:** backlog | **Projects:** W,A,K
As a product and quality reviewer, I want representative real model evidence, so that a deterministic demonstration cannot certify efficacy.
**Scope:** Real corpus curation, source/ACL/defect/human labels, model/Embedding/Reranker/Knowledge evaluation, monthly attribution and the bounded source POC. It owns R-quality evidence referenced by the ledger; role UAT/output qualification remains13-3. The evaluation profile may refine sampling quotas and metric details, but cannot reduce the FR-34/AC-5 minimum domain coverage or required metric set.
**Dependencies:** `12-6-full-acceptance-ledger`.
**Traceability:** FR-9–FR-26,FR-32,FR-33,FR-34,FR-35–FR-41,FR-48; NFR-1,NFR-3,NFR-4,NFR-9,NFR-10,NFR-18; C-4,C-5,C-7,C-8; AD-8,AD-9,AD-18.
**UI reference:** X-12 monthly/quality and X-13 datasets/real-run results; P-03–P-09, UJ-1–UJ-5; SUP-5,SUP-9. No new body beyond approved UX.
**UI fidelity:** Strict inherited source1:1 visual/interaction layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; B/R/S/conflicts explicit; X bodies follow UX without invented prototype pixels.
**Acceptance Criteria:**
- **Given** an approved, versioned eligibility/evaluation profile, **When** real datasets are curated, **Then** the profile first conforms to FR-34/AC-5 minimum domain coverage and required metrics, and the manifest satisfies its quota, labels, deduplication and adjudication rules. **Verification:** normative-profile conformance and manifest validator.
- **Given** eligible real data and permitted providers, **When** an evaluation run executes, **Then** its immutable manifest records the required metric set and configured versions, cases, denominators, failures and exclusions. **Verification:** evaluation-manifest schema check.
- **Given** the approved technical-solution POC profile, **When** it runs, **Then** it produces its declared Evidence-to-DOCX artifact and records actual providers/data. **Verification:** POC artifact and provenance review.
- **Given** a failed evaluation result, **When** improvement work is proposed, **Then** it records evidence, responsible domain and revalidation condition without prescribing a remediation order. **Verification:** improvement-record review.
- **Given** absent approval or required real input, **When** acceptance is considered, **Then** the case is blocked/not-run and no unapproved external call occurs. **Verification:** preflight authorization check.
**Evidence:** T-QUALITY real call manifests,full-domain eligibility/human-label register,source POC sample/model IDs and actual DOCX,metric case hashes/denominators/monthly comparisons; T-SEC egress/ACL/no-leak cases. Independent quality review required.
**L/R/P:** R-primary. L protocol already12-6; it cannot satisfy this story. P capacity remains13-4. Done requires all applicable real quality/POC criteria,not merely a prepared report.

## Story 13.2: Prove actual enterprise contracts and reconciled deliveries
**ID:** `13-2-real-enterprise-integration` | **Status:** backlog | **Projects:** W,A,K
As an enterprise acceptance reviewer, I want receiver-confirmed real integration, so that simulated ports are not described as supported vendors.
**Scope:** Former12-3 real identity/KB/S3/MES/project/archive/return scenarios and all earlier R contract/current-ACL/source mapping/receipt obligations. Validate each actual declared vendor/version,including documented alternative-contract/ADR obligations; no generic support inferred from one adapter.
**Dependencies:** `13-1-real-quality-poc`.
**Traceability:** FR-4,FR-12–FR-18,FR-27–FR-31,FR-35–FR-43,FR-46,FR-48; NFR-1–NFR-7,NFR-13; C-1–C-8; AD-7,AD-12,AD-15,AD-18.
**UI reference:** X-09/X-20 target/contract/receipt and X-16 actual tasks; X-05/X-06,X-07/X-08 and UJ-1–UJ-6; SUP-3,SUP-4,SUP-5,SUP-7.
**UI fidelity:** Strict original1:1 visual/interaction layout/position/size/spacing/fonts/family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve hierarchy/source; B/R/S/conflicts explicit; supplementary bodies use UX,not invented source pixels.
**Acceptance Criteria:**
- **Given** explicit operation approval and real isolated endpoints/contracts/credentials/ACL/data, **When** real SSO→workspace→KB current-ACL/Evidence→document/tender/form→human test approval→artifact→MES/project/archive receipt and KB return runs on actual W/A/K, **Then** vendor request/response/correlation/effect/receipt join to stored source/schema/version/approval/artifact identities. Each declared contract exercises denied,malformed,stale,duplicate,timeout,replay and revocation paths.
- **Given** permission changes between retrieval/model/staging/commit/stream/download/Range/retry, **When** each real adapter is used, **Then** actual current authorization and mapping/clearance apply; unavailable current ACL fails closed,not a historic snapshot. Enterprise storage/lifecycle/identity behavior and alternative contract versions are documented,not assumed.
- **Given** external success followed by timeout,partial result or cancel, **When** reconcile/query/callback runs, **Then** verified receiver outcomes obey declared capabilities,no blind resubmission/no unsupported exactly-once; no-query/no-idempotency remains unknown/manual reconcile. Separate publication/return gates and approved form pins remain enforced.
- **Given** missing vendor capability/credentials/authorization or unsafe target, **When** acceptance is attempted, **Then** stop blocked/not-run; do not mutate existing/production databases,send unapproved external messages or call paid services. Simulator logs cannot satisfy this story.
**Evidence:** T-CONTRACT/T-TASK/T-SEC/T-TENDER/T-FORM/T-DOC real vendor logs with secrets redacted,receiver-confirmed effect/receipt,ACL-revocation timestamps,capability matrix and independent integration review. Role-based usability remains13-3.
**L/R/P:** R-primary; real functional integration must pass. No P capacity/HA inference. Any environment alternative requiring performance/recovery evidence also maps to13-4/13-5 and remains open there.

## Story 13.3: Accept official outputs, role UAT and full UX fidelity
**ID:** `13-3-real-output-ux-uat` | **Status:** backlog | **Projects:** W,A,K
As an enterprise product owner, I want official artifacts and actual-user evidence, so that correct local functions are also usable and faithful in the real environment.
**Scope:** Every earlier R official-template/font/theme/Golden-output/policy interpretation/real-user role task/device obligation; former9-5 and12-3 UAT clauses; final real UX/VC acceptance. All four core types,five Phase2 types,tender and forms are included.
**Dependencies:** `13-2-real-enterprise-integration`.
**Traceability:** FR-1–FR-43,FR-47,FR-48; NFR-7,NFR-11,NFR-16,NFR-17,NFR-18; C-1–C-8; AD-13,AD-14,AD-16,AD-18; P-00–P-12,SUP-1–SUP-9,X-01–X-20,C00–C36,23components.
**UI reference:** All original source selectors and approved X/SUP bodies; UJ-1–UJ-6; VC-1/VC-2. No new UX scope.
**UI fidelity:** Explicit strict source1:1 layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interactions. Preserve hierarchy/source; B/R/S/conflicts require measured evidence/authorized disposition; new X bodies use UX contract,not nonexistent source pixels.
**Acceptance Criteria:**
- **Given** official templates/fonts/themes/Golden samples and permitted real records, **When** every document type generates DOCX/PDF/HTML/Markdown, **Then** verify cover/logo/identifier/classification/watermark/header-footer/TOC/headings/numbering/Chinese fonts/page breaks/cross-page tables/approval page/version table/citation appendix and pinned provenance. Actual HTML/Markdown semantic,active-content/unsafe URL/SVG/remote-resource and revoked-download safety tests remain mandatory,not just DOCX review.
- **Given** real production forms/paper/printer/scanner/camera and approved units/date/formula/schema policy, **When** eleven field types and repeating rows traverse Web/DOCX/PDF/XLSX/print→barcode/QR/OCR→human correction, **Then** each canonical value/hash matches,source/schema/instance/device cases are verified,wrong/denied/stale records rejected. Signature is not certified e-signature or approval authority.
- **Given** product/technical/test/quality/project/bid/production-recorder roles and relevant approver/template/knowledge/admin roles, **When** each applicable role conducts3–5 complete authorized historical-project tasks, **Then** record source correctness,output usability,Review FP/FN,Evidence clarity,edit efficiency,formal export quality,bid risks,scan corrections and delivery outcomes with issues/remediation/retest. No missing role/type is silently excluded; real domain owners validate applicable standards,waiver/approval rules and interpretations.
- **Given** frozen OS/browser/fonts/zoom/state/viewport, **When** all P/SUP/X/C00–C36 and23components are rerun at1920×1080,1440×900,1181×800,1180×800,1024×768,768×1024 and200%zoom, **Then** actual positive/negative behavior evidence closes every7-5 deferred entry and12-6 local result is independently rechecked under real assets/users; preserve desktop1180min/scroll/note and source geometry. Missing behavior is not an empty-state pass.
- **Given** contrast/focus/reflow/font discrepancy or missing official assets/UAT, **When** judged, **Then** VC-1/VC-2 have measured selector/evidence and authorized resolution; no unilateral restyle,invented tolerance,source-hash-only pass or unsupported AA claim. Unresolved required evidence keeps this story blocked/failed.
**Evidence:** T-DOC/T-FORM/T-TENDER/T-UX/T-QUALITY official per-type artifacts/value comparison,per-role task records,full per-control behavior matrix,font/screenshots/keyboard/screen-reader/contrast/zoom reports and independent UAT/UX review.
**L/R/P:** R-primary official asset/device/UAT acceptance; L fixtures are insufficient. Performance remains13-4 and security infrastructure13-5.

## Story 13.4: Measure real latency and production-equivalent capacity
**ID:** `13-4-real-performance-capacity` | **Status:** backlog | **Projects:** W,A,K
As a capacity owner, I want actual full-profile measurements, so that harness correctness is not mistaken for a service-level result.
**Scope:** All former12-4 numeric targets and earlier R/P timing/capacity obligations; execute delivered load tools with frozen real model/retrieval/official render assets and production-equivalent infrastructure.
**Dependencies:** `13-3-real-output-ux-uat`.
**Traceability:** FR-48; NFR-8,NFR-9,NFR-10,NFR-11,NFR-14,NFR-15; C-3,C-4,C-5,C-6; AD-18.
**UI reference:** Existing P-00/P-01/P-03/P-04/X-10/X-16/X-19 and specialist matrix/form/report views; no new page.
**UI fidelity:** Strict original1:1 layout/position/size/spacing/fonts/family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness/interactions remains. No performance-driven redesign without authorization; preserve hierarchy/source and B/R/S/conflicts; X follows UX.
**Acceptance Criteria:**
- **Given** approved frozen hardware/network/data/ACL/versions and full workload, **When**100online with doc/list20QPS+search5QPS,20chapter jobs+50searches+10whole Reviews,and20concurrent30–80-page DOCX/PDF exports run, **Then** record P50/P95/P99/errors/queue/DB/cache/broker/pool/provider/resource data and actual achieved versus requested load; disclose all failures/exclusions.
- **Given** measured client/server boundaries, **When** results are judged, **Then** UI key operations/home-list/AST/autosave request P95<1s (1000ms idle debounce separate),searchP95<3s,typical PackP95<8s,real-model TTFTP95<5s,typical chapterP95<60s and50-page DOCX<60s(no invented P95) are checked; permission-error retrieval=0. Actual model/core SLA and public-network exclusions remain separate.
- **Given** insufficient GPU/endpoint/corpus/fonts/production-equivalent hardware or a failing target, **When** acceptance is reported, **Then** story remains blocked/not-run/failed,never done from local timing or fast doubles.500DAU/1Mversions/10Mlinks is sizing guidance,not measured capacity.
**Evidence:** T-OPS/T-QUALITY/T-DOC/T-UX full-load raw timings,traces,manifests,model/embedding/reranker versions,rate/errors and independent performance review.
**L/R/P:** R actual model/retrieval/official samples AND P frozen full capacity evidence required;12-4 harness pass alone does not satisfy any numerical acceptance.

## Story 13.5: Verify real security, compatible rollout, HA and recovery
**ID:** `13-5-real-security-recovery` | **Status:** backlog | **Projects:** W,A,K
As an operations and security owner, I want measured protected recovery, so that configuration-only delivery cannot certify availability or preservation of records.
**Scope:** Former12-5 production-equivalent security/HA/backup/restore criteria and all earlier R/P policy/secret/encryption/retention/resource-limit/alternative-environment recovery obligations. Three independently evidenced WPs: actual compatible upgrade; infrastructure/security; measured HA/restore. All required,not optional subtasks.
**Dependencies:** `13-4-real-performance-capacity`.
**Traceability:** FR-4,FR-44–FR-48; NFR-1–NFR-7,NFR-12,NFR-13,NFR-15,NFR-18; C-1,C-2,C-3,C-6,C-8; AD-6,AD-7,AD-12,AD-17,AD-18.
**UI reference:** X-16/X-20 existing diagnostics/policy/audit and affected outage views; no new dashboard.
**UI fidelity:** Exercised UI preserves strict source1:1 layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interaction. Preserve hierarchy/source; B/R/S/conflicts explicit; X uses UX not fictitious pixels.
**Acceptance Criteria:**
- **Given** explicit approval for isolated production-equivalent target/backup and pinned locks/images, **When** actual N/N-1 API/Worker rollout/migration/backfill/rollback runs, **Then** contracts/events remain compatible,pools/grants separate,locks bounded,no slow external call in DB transaction; irreversible changes require independently reviewed restore route and later contract-drop verification.
- **Given** authorized fault domains, **When** RabbitMQ quorum node/Worker/Redis/NGINX/CloudNativePG failover and Barman Cloud timed restore execute, **Then** PG tasks/versions/approvals/audit/outbox/inbox plus template/Prompt/S3 metadata/formal objects/Golden/parse metadata consistency is verified; authorized local index rebuilds,enterprise KB recovery stays enterprise-owned. Measure availability≥99.9% over recorded window,RPO≤15min,RTO≤1h,not backup creation alone.
- **Given** actual security infrastructure/policies and malicious parse/render/upload/download/diagram/formula/injection fixtures, **When** independent security review executes, **Then** credential-free/network-disabled/non-root/read-only/seccomp/resource/time/temp isolation,TLS/at-rest/backup encryption,secret-manager/no plaintext Helm secrets,current ACL/TTL/retention/DLP/audit protection are verified. Policy limits and OCR triggers must be configured explicitly; no invented values. Failed severity/security controls block readiness.
- **Given** missing execution approval/target isolation/window/policy or unsafe existing/production data target, **When** preparing drills, **Then** stop blocked/not-run; do not delete databases/clean existing data or infer HA/security from config. Enterprise alternatives require documented contract/security/performance/recovery validation and ADR,not vendor equivalence assertions.
**Evidence:** T-OPS/T-TASK/T-SEC/T-CONTRACT separate upgrade/security/HA-restore manifests with timestamps/hashes/measurement window,actual image/dependency inventories and independent reviewer dispositions.
**L/R/P:** P-primary plus real enterprise policy/alternative validation. All WPs and quantitative targets must actually pass; L rehearsal cannot close this story. No production deployment authorization is conferred.

## Story 13.6: Close full three-phase acceptance only with complete real evidence
**ID:** `13-6-full-real-acceptance` | **Status:** backlog | **Projects:** W,A,K
As a release decision owner, I want a reconciled complete evidence ledger, so that a local-done label never hides an unfinished real acceptance obligation.
**Scope:** Final independent all-phase acceptance of FR/NFR/contracts/AD/UX/test packages and every transferred R/P source clause; no unfinished feature implementation disguised as ledger work.
**Dependencies:** `13-5-real-security-recovery`, `13-1-real-quality-poc`, `13-2-real-enterprise-integration`, `13-3-real-output-ux-uat`, `13-4-real-performance-capacity`.
**Traceability:** FR-1–FR-48; NFR-1–NFR-18; C-1–C-8; AD-1–AD-18; all10 test packages; all UX inventories.
**UI reference:** P-00–P-12,SUP-1–SUP-9,X-01–X-20,C00–C36,23components,UJ-1–UJ-6 and VC register.
**UI fidelity:** Strict existing visual/interaction1:1 layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve hierarchy/source; B/R/S/VC dispositions evidenced; new X judged by UX,not invented pixels.
**Acceptance Criteria:**
- **Given** all actual L/R/P results, **When** independent reviewer reconciles every source story+R/P criterion to13-1–13-5, **Then** no obligation is unassigned/unrun/failed; all core/five Phase2/tender/form/delivery flows,real POC,each domain50–200 representative labeled Golden Queries,HTML/Markdown safety,official outputs,allrole3–5tasks,real enterprise receipts,full UX behavior and exact operational targets have evidence.
- **Given** any missing real endpoint/UAT/official font/policy/corpus/GPU/full-load/HA/security/restore/VC evidence, **When** total acceptance is considered, **Then** this story remains blocked/not-run/failed and all-phase completion is withheld even if every local story is done. No empty/not-configured UI can stand in for a positive functionality test; all7-5 deferred items must already be closed in12-6 and reverified13-3.
- **Given** independent review/test failure, **When** readiness is reconsidered, **Then** remediate→rerun→independently verify before the applicable gate passes; no skip of failed epic,no author self-approval,no flag bypass,no automatic production/push authorization. Planned S4 status grants neither S4c nor later execution permission.
**Evidence:** All10 test packages' full immutable manifests,source-clause transfer matrix,artifact/trace hashes and independent dispositions. The final ledger distinguishes L,R,P historical outcomes without turning an unresolved cell into pass.
**L/R/P:** All applicable L/R/P obligations must pass for full acceptance; this last story remains uncompleted otherwise. Any deployment/external operation still requires separate direct authorization.
