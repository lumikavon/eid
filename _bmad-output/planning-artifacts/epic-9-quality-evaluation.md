---
epic_id: epic-9
status: planned
phase: 2-with-phase-1-baseline
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 9: Govern and measure actual document quality

Outcome: quality owners receive score/rule/dataset/evaluation tooling designed for later local execution. All five stories are software-delivery stories; their L runtime cases and R/P obligations remain `not-run` until separately verified. In9-3 the implementation must enforce50–200/domain eligibility,labels/ACL/representativeness; synthetic fixture tests are deferred. In9-4 internal retrieval/generation/Reviewer transport must be implemented with declared external-port doubles; execution and real efficacy remain deferred. Known implementation or static/compile failures cannot be skipped. W/A/K and the software closure contract in epics.md apply.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 9-1 AC1–3,Evidence,L/R/P | Real calculation/filter/drilldown and deferred C05/C21/P-11/X-12 positive-negative tests with local run records | Enterprise definitions/data and UAT →13-3; projection load →13-4 |
| 9-2 AC1–2,Evidence,L/R/P | Actual versioned safe rule lifecycle and critical-defect activation rejection | Subject-matter adjudication/real model effects →13-1/13-3; real safe configuration policy →13-5 |
| 9-3 AC1–2,Evidence,L/R/P | Actual curation UI/store and eligibility validator; synthetic50/200 boundary positives and49/201/duplicate/ACL/source/label negatives. Human-label fields/authorization tested,not merely schema-only smoke | AC1 actual50–200 representative queries per domain,authorized real provenance and named human adjudication,AC2 real eligibility denial,real human-curation Evidence →13-1; actual governance policy →13-5. A tiny local sample is insufficient even for full validator coverage and never satisfies FR-34 real acceptance |
| 9-4 AC1–2,Evidence,L/R/P | Actual internal task/retrieval/generation/Reviewer calls with labeled external-port doubles,correct manifests/metrics/failures/comparisons | Actual approved model/Embedding/Reranker/KB plus compliant real Golden sets and real reproducibility →13-1; enterprise endpoint/current ACL →13-2; full timing/capacity →13-4 |
| 9-5 AC1–3,Evidence,L/R/P | Actual local protocol/report/monthly attribution and readiness validators; absence of real evidence reported,not false pass | Original real runs/threshold governance/monthly quality →13-1; role UAT/official output →13-3; actual capacity/security/recovery →13-4/13-5 |

## Story 9.1: Explain actual quality scores and requirement coverage
**ID:** `9-1-quality-analytics` | **Status:** backlog | **Projects:** W,A,K
As a quality owner, I want versioned metrics with denominators, so that a score can be explained and never overrides release gates.
**Scope:** Document Quality Score/coverage definition versions,eligible populations/time windows/drill-down,monthly source metrics and actual dashboard projections; no invented weights/threshold defaults.
**Dependencies:** `8-5-project-summary`, `7-1-audit-observability`.
**Traceability:** FR-33,FR-47; C-7; AD-10,AD-16.
**UI reference:** P-11 navigation/placeholder only→X-12 quality/coverage/monthly tables,P-01 four KPIs,P-04 quality card,P-08 metrics; C05,C21; SUP-5. S analytics body,R actual numbers.
**UI fidelity:** Strict existing source1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interaction. Preserve hierarchy/source; mark R/S/conflicts; X-12 has UX contract, not original-body pixel baseline.
**Acceptance Criteria:**
- **Given** versioned definitions and authorized documents/Claims/requirements/reviews, **When** scope/date/version filters change, **Then** score/coverage and monthly generation success,retained AI content,issue distribution,Evidence gaps,low-hit queries,human edits,writing/approval time,model cost derive from actual denominators with drill-down.
- **Given** missing definition/no data/stale run/denied scope, **When** displayed, **Then** unevaluated/unavailable state and reason replace sample score; actual high score never bypasses severe/pending/publication hard gates. Phase1 requirement links remain valid history.
- **Given**7-5 deferred C05/C21 quality sub-actions and P-11 navigation→X-12 analytics, **When** actual local records feed the view and users change filter/scope/version/open denominator/issue/source drilldowns, **Then** each route and calculation has positive trace and matching IDs,plus denied/no-data/stale/error cases; no placeholder/sample score or empty/not-configured state counts as implemented positive behavior. Close named deferred rows here,rerun12-6 and reverify with real users/assets13-3.
**Evidence:** T-CONTRACT calculation/denominator/filter fixtures; T-SEC aggregate access; T-UX C05/C21/P-11/X-12 route/filter/drilldown positive-negative traces with deferred-row IDs and12-6/13-3 rerun owners; T-QUALITY definition hashes.
**L/R/P:** L real local analytics from actual fixture runs; R enterprise metric definitions/data validation; P projection load13-4.

## Story 9.2: Version and validate Reviewer rules
**ID:** `9-2-review-rule-center` | **Status:** backlog | **Projects:** W,A,K
As a Reviewer-rule owner, I want checked rule versions, so that changes are traceable and do not retroactively rewrite previous results.
**Scope:** Rule create/edit/validate/test/activate/deprecate,permissions/versions/test defects/roll-back-to-prior-version selection and references; no arbitrary script rules.
**Dependencies:** `9-1-quality-analytics`.
**Traceability:** FR-33,FR-26; C-5,C-7; AD-9,AD-10.
**UI reference:** X-13 rule tabs/definition/validation/case/run results; X-20 policy links; SUP-5. S governance.
**UI fidelity:** Strict source visual/interaction1:1 for inherited layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; explicit R/S/conflicts; new X-13 uses UX not imaginary source pixels.
**Acceptance Criteria:**
- **Given** authorized rule owner and declared safe rule schema, **When** version is validated against labeled cases and activated, **Then** new Reviews pin new version and old results preserve prior version; reviewer class/severity/condition/location metadata remain inspectable.
- **Given** invalid executable expression,unauthorized edit,failed critical fixture or missing mandatory rule, **When** activation is attempted, **Then** reject with exact failure and last active version retained; no severity downgrade automatically clears existing severe issue.
**Evidence:** T-QUALITY versioned defect regression results/FP-FN; T-SEC no-script/permission tests; T-CONTRACT immutable references; T-UX validation state.
**L/R/P:** L actual rule tests and local model doubles; R subject-matter review/real-model effects required; P safe configuration operations later.

## Story 9.3: Curate representative per-domain Golden datasets
**ID:** `9-3-golden-datasets` | **Status:** backlog | **Projects:** W,A
As an evaluation owner, I want representative permission-aware datasets, so that real quality is measured against explicit gold labels.
**Scope:** Versioned domain catalog/query/source/ACL/negative/defect labels,reviewed data provenance,count/coverage validation and authorized dataset access. Include all supported document domains, not merely technical solution; tender/form-specialist extensions are added with10/11 and checked12-6.
**Dependencies:** `9-2-review-rule-center`.
**Traceability:** FR-34; NFR-1,NFR-6; C-4,C-7; AD-18.
**UI reference:** X-13 dataset/query/case table/version/provenance; SUP-5. S Golden management.
**UI fidelity:** Inherit strict source visual/interaction1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve hierarchy/source file; R/S/conflicts explicit; new body follows UX, not source pixels.
**Acceptance Criteria:**
- **Given** each declared document domain, **When** a dataset is offered for real acceptance, **Then** it contains **50–200 representative Golden Queries per domain** with source/version/locator,relevance,ACL/context/current-formal labels,negative and injected defect gold labels,authorized provenance and named human adjudication; counts and domain coverage are machine-checkable.
- **Given** fewer than50/more than200,only duplicated trivial queries,missing ACL/source/defect labels or inaccessible data, **When** real evaluation eligibility is checked, **Then** block/incomplete with domain-specific reasons. A small local sample may validate schema/runner only and cannot satisfy FR-34 dataset acceptance.
**Evidence:** T-QUALITY per-domain count/representativeness/label validation and human curation manifest; T-SEC dataset ACL and safe export; T-UX incomplete dataset views.
**L/R/P:** L schema/local small fixtures explicitly insufficient for FR-34; R authorized real corpora and50–200/domain human-adjudicated sets are mandatory acceptance dependency,blocked if absent; P data governance policy applies.

## Story 9.4: Execute reproducible retrieval, generation and Reviewer evaluations
**ID:** `9-4-evaluation-runs` | **Status:** backlog | **Projects:** W,A,K
As an evaluation owner, I want repeatable runs and explicit failed cases, so that configuration comparisons are trustworthy.
**Scope:** Dataset/run manifests,actual retrieval/generation/Reviewer calls,metrics/case outputs/denominators/environment labels and reproducible comparison; no cherry-picked success-only reports.
**Dependencies:** `9-3-golden-datasets`.
**Traceability:** FR-34,FR-33; NFR-9,NFR-10,NFR-15; C-3,C-4,C-5,C-7; AD-8,AD-9,AD-18.
**UI reference:** X-13 config/run/task/results/errors/local-vs-real indicators,X-12 drill-down; SUP-5,SUP-7. S evaluation,R actual task state.
**UI fidelity:** Strict original1:1 visual/interaction across layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; classify R/S/conflicts; new X bodies use UX no fictitious baseline.
**Acceptance Criteria:**
- **Given** approved dataset/run settings, **When** evaluation executes, **Then** manifest freezes dataset/ACL/queries,contract/AST/template/Prompt/model/embedding/reranker/dictionary/rule/font versions,device,batch,max input length,seed where supported,budgets/timeouts/thresholds and real versus double route; metrics include Recall@K,MRR,nDCG,current-formal Top3,citation precision/completeness,unsupported critical Claims,requirement coverage,Human Edit Distance,Reviewer precision/recall/FP/FN/severity.
- **Given** denied query,timeout,malformed result or changed config, **When** run finalizes, **Then** failures/exclusions/denominators remain visible and result cannot silently merge incompatible versions or describe doubles as real efficacy. Permission-error retrieval=0 remains absolute.
**Evidence:** T-QUALITY reproducibility/case hashes/metric unit fixtures; T-TASK restart/run result identity; T-SEC denied-case containment; T-UX result comparisons.
**L/R/P:** L runner/deterministic metric correctness using real infrastructure; R actual approved model/Embedding/Reranker/KB and compliant Golden set mandatory; P performance/capacity measured separately.

## Story 9.5: Rehearse quality acceptance and monthly improvement reporting
**ID:** `9-5-real-quality-acceptance` | **Status:** backlog | **Projects:** W,A,K
As a product/quality reviewer, I want real model and user evidence, so that delivery decisions do not rest on deterministic demos.
**Scope:** Implement and locally rehearse the acceptance protocol,role/task manifest,monthly comparisons and failure-attribution report using actual local runs. Stable ID is retained despite its legacy real-quality-acceptance slug; it does not mean real acceptance is complete. Former real endpoint/UAT/official-output acceptance criteria are transferred intact to13-1 and13-3. Templates/prompts/model choices remain governance decisions; no paid endpoint permission.
**Dependencies:** `9-4-evaluation-runs`, `7-4-core-integration`.
**Traceability:** FR-34,FR-32,FR-48; NFR-9,NFR-10,NFR-18; C-4,C-5,C-7; AD-18.
**UI reference:** X-12 monthly,X-13 real run results; UJ-1–UJ-3; SUP-5. S measured-quality view.
**UI fidelity:** Strict source1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interactions. Keep hierarchy/source unchanged; R/S/conflicts explicit; X views follow UX not invented source pixels.
**Acceptance Criteria:**
- **Given** actual local evaluation runs with declared synthetic data/model doubles, **When** acceptance and monthly reports are generated, **Then** hit correctness,usability/FP-FN/Evidence/edit/output fields,role/task/domain coverage,failed cases and route labels are inspectable; missing real runs are recorded as13-1/13-3 obligations,never passed. Rehearse role/task and50–200/domain eligibility validators without claiming synthetic queries satisfy FR-34 real acceptance.
- **Given** source recommendations Recall@10≥0.90,current-project Top3≥95%,Citation Precision≥95%,post-Review unsupported critical rate<2%, **When** results are judged, **Then** treat them as proposed initial evaluation thresholds pending governed freeze, not invented release policy; formal severe unsupported critical Claims=0 and permission errors=0 remain hard gates. Serious missed defects take recall priority without inventing numeric Reviewer targets.
- **Given** environment/official assets/threshold approval missing or failures found, **When** acceptance is reported, **Then** mark blocked/not-run/failed rather than full pass and create evidenced improvements in Knowledge→Template→Retrieval→Prompt→Reviewer→Model order, with monthly comparisons and re-evaluation.
**Evidence:** T-QUALITY actual local-run reports,protocol/coverage-validator cases and monthly attribution; T-UX positive report/filter/drilldown plus failed/denied cases. Original real-call manifests/human labels/UAT and official-output checks are mandatory in13-1/13-3.
**L/R/P:** Software closure covers implemented protocol/reporting with static and compile evidence; local runtime proofs remain `not-run` under this Story. R actual data/endpoints/official assets/policies/UAT stay uncompleted in13-1/13-3; P capacity/security/recovery in13-4/13-5. Marking this software story done never marks acceptance complete or waives its criteria.
