---
epic_id: epic-8
status: planned
phase: 2
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 8: Complete project and quality document workflows

Outcome: five additional types use the full controlled pipeline with distinct meaningful rules, not blank template/category entries. W/A/K and L/R/P constraints from epics.md apply. Each story extends existing type registry/template/rules/tests, not a new generation/approval stack. Each includes the entire user's type workflow as regression; the implementation scope is the bounded type adapter/rule set.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 8-1 AC1–2,Evidence,L/R/P | Actual quality-outline type/rules/full pipeline with control/responsibility defects | Real generation/source quality →13-1; official company quality template/rules and quality-role3–5 tasks →13-3; load →13-4 |
| 8-2 AC1–2,Evidence,L/R/P | Actual project-plan fields/full pipeline and date/cycle/missing-owner failures | Real generation quality →13-1; project fact integration →13-2; official plan rules/project-manager3–5 tasks →13-3; capacity →13-4 |
| 8-3 AC1–2,Evidence,L/R/P | Actual functional-test outline/bidirectional coverage/full pipeline and stale-link defenses | Real generation/coverage quality →13-1; official test rules/test-role3–5 tasks →13-3; load →13-4 |
| 8-4 AC1–2,Evidence,L/R/P | Actual performance-outline authored fields/full workflow with threshold protection; not measured NFR acceptance | Real model quality →13-1; official criteria/expert3–5 tasks →13-3; actual NFR performance →13-4 |
| 8-5 AC1–3,Evidence,L/R/P | Actual fact-based summary and all-five-type deferred-control closure | Real model/source quality →13-1; real outcome records →13-2; official assets/project-manager and relevant-role3–5 tasks →13-3; load/security →13-4/13-5 |

## Story 8.1: Produce a project quality outline
**ID:** `8-1-quality-outline` | **Status:** backlog | **Projects:** W,A,K
As a quality owner, I want a quality outline grounded in company controls, so that responsibilities and verification activities are reviewable.
**Scope:** Quality-outline type rules for objectives/organization/responsibility/quality assurance/control/reviews/records/acceptance under versioned template; reuse generation,coverage,Review,approval/export.
**Dependencies:** `6-6-trusted-knowledge-return`, `5-6-test-traceability`.
**Traceability:** FR-32,FR-33; C-2,C-4,C-5,C-7; AD-13.
**UI reference:** P-07 quality-outline chip/card,P-02 type selection,P-03–P-09,X-15,X-01,X-03,X-04,X-19; C10,C23,C24,C25; SUP-6. R complete type data,S required-field validation.
**UI fidelity:** Strict original1:1 layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interactions. Preserve source hierarchy/file; enumerate R/S/conflicts, new X pages follow UX not nonexistent pixels.
**Acceptance Criteria:**
- **Given** approved quality template/current company standards and project facts, **When** create→context/outline-confirm→Evidence→generate/accept→Review→approve→publish→export/eligible return completes, **Then** all required quality responsibilities/control/record/acceptance sections have locatable supported data and pinned provenance.
- **Given** missing required control/responsibility,obsolete standard,unsupported acceptance rule or only development template, **When** Review/publication runs, **Then** precise missing/conflict/development-only state blocks formal use where required; no AI-invented company policy or silent bypass.
**Evidence:** T-DOC/T-QUALITY type-specific positive/defect fixture; T-UX full workflow trace; T-CONTRACT pinned output/approval/return gate.
**L/R/P:** L real W/A/K with labeled model/enterprise doubles and development assets; R official quality template/rules and quality-role3–5 real historical-project tasks mandatory; P common production load13-4.

## Story 8.2: Produce a dependency-aware project plan
**ID:** `8-2-project-plan` | **Status:** backlog | **Projects:** W,A,K
As a project manager, I want a plan with explicit milestones and dependencies, so that resource and schedule assumptions can be checked.
**Scope:** Objectives/deliverables/WBS/schedule/milestones/resources/responsibility/dependencies/risks and acceptance fields from versioned plan template; no invented external project-system integration.
**Dependencies:** `8-1-quality-outline`.
**Traceability:** FR-32; C-2,C-4,C-5,C-7; AD-13.
**UI reference:** P-07 project-plan card/chip,P-02,P-03–P-09,X-15,X-01,X-03,X-04,X-19; C10,C23,C24,C25; SUP-6. R complete plan,S validations.
**UI fidelity:** Strict source visual/interaction1:1 across layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve hierarchy/source; R/S/conflicts explicit; new bodies use UX, no source-pixel claim.
**Acceptance Criteria:**
- **Given** confirmed dates/resources/constraints and plan template, **When** full create→outline→Evidence→generation/Patch→Review→approval→publication→all document exports runs, **Then** milestones/deliverables/dependencies/owners trace to current facts and exported version matches approved content.
- **Given** conflicting dates,dependency cycle,unknown resource/owner or model-made deadline, **When** validation/Review runs, **Then** located conflict/pending prevents false feasible plan; formal release obeys shared gates, source-system failure is not fabricated completion.
**Evidence:** T-DOC/T-QUALITY date/dependency/missing-owner fixture and full type E2E; T-UX plan/issue navigation; T-CONTRACT version gates.
**L/R/P:** L actual local chain/deterministic provider; R project-manager3–5 real tasks and official plan rules; P shared capacity13-4.

## Story 8.3: Produce a functional test outline with coverage
**ID:** `8-3-functional-test-outline` | **Status:** backlog | **Projects:** W,A,K
As a test lead, I want a functional test outline linked to requirements, so that later cases retain complete verifiable coverage.
**Scope:** Functional-test-outline type objectives/scope/environment/methods/items/cases/traceability/acceptance/entry-exit rules and versioned links; extend Phase1 coverage rather than defer it.
**Dependencies:** `8-2-project-plan`, `5-6-test-traceability`.
**Traceability:** FR-32,FR-33,FR-11; C-2,C-7; AD-13.
**UI reference:** P-02/P-07 extended type chooser,P-03/P-04/P-08,X-12 coverage,X-15,X-01,X-03,X-04,X-19; C10,C17,C23; SUP-6,SUP-5. S additional type choice,R actual links.
**UI fidelity:** Strict original1:1 layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interaction. Preserve source hierarchy/file; R/S/conflicts explicit; X pages use UX, not fictitious pixels.
**Acceptance Criteria:**
- **Given** versioned FRs and approved test/acceptance rules, **When** full type workflow through formal exports runs, **Then** outline items map bidirectionally to requirements/cases/acceptance and coverage has actual denominator/omissions; output/approval pins same version.
- **Given** orphan/redundant/stale links,missing exception tests or altered approved threshold, **When** Review/publish is attempted, **Then** precise finding remains and no silent threshold alteration/100% score or bypass occurs.
**Evidence:** T-DOC/T-QUALITY functional coverage fixtures/full type E2E; T-CONTRACT stale link tests; T-UX traceability screens.
**L/R/P:** L genuine type/rules/links and actual chain; R test-role3–5 historical-project tasks/real generation; P shared load13-4.

## Story 8.4: Produce a measurable performance test outline
**ID:** `8-4-performance-test-outline` | **Status:** backlog | **Projects:** W,A,K
As a performance engineer, I want explicit load and measurement assumptions, so that performance acceptance is reproducible rather than an invented number.
**Scope:** Performance-outline workload/environment/data/concurrency/metrics/percentile/duration/threshold/exclusions/method fields and requirement links under approved type policy.
**Dependencies:** `8-3-functional-test-outline`.
**Traceability:** FR-32,FR-11; C-2,C-7; AD-13.
**UI reference:** P-02/P-07 extended type chooser,P-03/P-04/P-08,X-15,X-12,X-01,X-03,X-04,X-19; C10,C17,C23; SUP-6,SUP-5. S choice,R measurement data.
**UI fidelity:** Strict source visual/interaction1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button/input states/responsiveness. Preserve source hierarchy/file; R/S/conflicts recorded; new UX body has no claimed source pixels.
**Acceptance Criteria:**
- **Given** approved performance requirements, **When** create→confirmed context/outline→Evidence→generate/accept→Review→approve/publish→export runs, **Then** load,measurement boundary,units,statistic,threshold and verification method remain linked and unknown inputs are explicit.
- **Given** missing hardware/network/load/exclusion assumptions or model alters a strict threshold/percentile, **When** validation/Review runs, **Then** missing/changed fields are flagged and cannot count as measured passing performance. This authored outline is not executed NFR evidence.
**Evidence:** T-DOC/T-QUALITY unit/percentile/threshold/missing-environment cases and complete type E2E; T-UX correct validation fields.
**L/R/P:** L real local author pipeline; R official performance criteria and expert3–5 real tasks; P outline does not itself satisfy production performance,13-4 executes measurements.

## Story 8.5: Produce a fact-based project summary
**ID:** `8-5-project-summary` | **Status:** backlog | **Projects:** W,A,K
As a project manager, I want a summary grounded in actual outcomes, so that lessons and completion claims are defensible.
**Scope:** Project-summary goals/deliverables/results/variance/issues/risks/lessons/improvement/acceptance evidence according to template, actual-versus-planned data separation.
**Dependencies:** `8-4-performance-test-outline`.
**Traceability:** FR-32; C-2,C-4,C-5,C-7; AD-13.
**UI reference:** P-01 fifth quick-create `[data-create="项目总结报告"]`,P-02/P-07 extended type,P-03–P-09,X-15,X-01,X-03,X-04,X-19; C08,C10,C23; SUP-6. R real summary,S type catalog.
**UI fidelity:** Strict existing1:1 visuals/interactions for layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve hierarchy/source file; classify R/S/conflicts, X bodies follow UX not fabricated pixels.
**Acceptance Criteria:**
- **Given** current approved project outcome/evidence records, **When** complete summary workflow through Review/human approval/publication/export/eligible return runs, **Then** actual achievements,variance and lessons cite authorized sources and exported version matches approved candidate.
- **Given** missing outcome evidence,conflicting completion dates or only planned targets, **When** generation/Review runs, **Then** unsupported completion claims stay pending/findings; model cannot convert a plan or task status into achieved business result. Shared hard gates still block.
- **Given** the7-5 deferred ledger for Phase2 C08 summary quick-create and C10/C23/C24/C25 type selection/filter/card/preview/use, **When** each of five delivered types executes those entries and its full workflow with actual local W/A/K data, **Then** record correct selected type/new document ID/pinned template/own outline/output plus denied/deprecated/invalid/failed cases; close each exact deferred sub-action only with positive AND negative proof. Empty/not-configured is not a positive behavior pass;12-6 reruns all rows and13-3 rechecks official assets/users.
**Evidence:** T-DOC/T-QUALITY fact-versus-plan cases and full type E2E; T-UX per-control C08/C10/C23/C24/C25 traces and deferred-row IDs; phase2 all-five-type manifest with no placeholder-only pass,final reruns12-6/13-3.
**L/R/P:** L actual W/A/K + labeled doubles; R project-manager and relevant roles3–5 real tasks with official assets; P common load/security measurements retained.
