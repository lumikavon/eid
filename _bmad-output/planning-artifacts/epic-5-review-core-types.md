---
epic_id: epic-5
status: planned
phase: 1
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 5: Review all four core document types

Outcome: experts inspect version-pinned findings and authors produce technical solutions, PRDs, test plans and technical requirements with meaningful type rules. Formal release/output uses epic-6; the core author/review value works beforehand. W/A/K and common guards follow epics.md.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 5-1 AC1–3,Evidence,L/R/P | Eight actual execution contracts,real rule checks,declared model doubles,defect/stale/denial proofs | Actual Reviewer recall/FP-FN/severity →13-1;10 concurrent Reviews →13-4 |
| 5-2 AC1–2,Evidence,L/R/P | Working filters/tabs/selected findings/defined denominators | Expert source-interpretability UAT →13-3; large-run performance →13-4 |
| 5-3 AC1–2,Evidence,L/R/P | Actual distinct decision/recheck/waiver-denial behavior with test roles | Enterprise waiver/approval-role interpretation and real defect-resolution UAT →13-3; actual safety policy →13-5 |
| 5-4 AC1–2,Evidence,L/R/P | Actual technical-solution type author/Review pipeline with fixture standards | Real model/technical-source efficacy →13-1; technical-role3–5 historical tasks/official assets →13-3; chapter load →13-4 |
| 5-5 AC1–2,Evidence,L/R/P | Actual structured PRD fields/validation/type pipeline | Real approved model/data efficacy →13-1; product-role3–5 complete tasks →13-3; load →13-4 |
| 5-6 AC1–2,Evidence,L/R/P | Actual Phase1 bidirectional links/coverage/threshold protection now | Real requirement-to-test quality →13-1; test-role3–5 tasks →13-3; trace-volume load →13-4 |
| 5-7 AC1–2,Evidence,L/R/P | Actual measurable requirement rules and unsupported-threshold defenses | Real model recall →13-1; requirements/quality-role UAT →13-3; load →13-4 |

## Story 5.1: Run eight Reviewers against a pinned version
**ID:** `5-1-pinned-reviewers` | **Status:** backlog | **Projects:** W,A,K
As an expert, I want complete version-aware Review results, so that unavailable or old checks cannot certify the current document.
**Scope:** Structure,fact,requirement,technical,quality,consistency,style,safety Reviewer orchestration, rule/model versions, issue locations/quotes/impact/suggestions, actual rerun.
**Dependencies:** `4-5-pending-safe-graphics`.
**Traceability:** FR-23,FR-26,FR-28; C-3,C-4,C-5,C-7; AD-9,AD-10.
**UI reference:** P-08 `#page-review/#rerunReview/.metrics/.issue`, X-16; C27; SUP-7,SUP-9. R actual tasks/metrics.
**UI fidelity:** Strict existing1:1 visual/interaction layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Source hierarchy/file retained; B/R/S/conflicts explicit; new detail UI follows UX, not invented pixels.
**Acceptance Criteria:**
- **Given** a pinned document and versioned eight-rule set, **When** Review runs/reruns, **Then**202 task and individual Reviewer status/results persist; completion requires all mandatory outcomes, findings retain exact document/section/block/Claim/source and rule/model versions.
- **Given** numeric contradiction,name remnant,obsolete citation,missing chapter/requirement,vague threshold,inconsistent term,unsupported critical fact or wrong standard ID fixtures, **When** appropriate check executes, **Then** seeded defects are locatable and actual FP/FN recorded; deterministic rule successes are not real model accuracy.
- **Given** required Reviewer failure,current access revoked or document edited during run, **When** result commits/eligibility queries, **Then** failed/stale/denied state cannot mark the new version reviewed or publishable; draft editing remains available.
**Evidence:** T-QUALITY/T-TASK/T-CONTRACT pinned-run and defect fixtures; T-SEC revoked worker result; T-UX rerun state.
**L/R/P:** L all eight execution contracts with real rule checks and declared model doubles; R actual Reviewer defect recall/severity assessment13-1; P10 concurrent Reviews13-4.

## Story 5.2: Inspect real findings, trace and review history
**ID:** `5-2-review-inspection` | **Status:** backlog | **Projects:** W,A
As an expert, I want filters and selected details to agree, so that I can act on the exact issue rather than prototype sample content.
**Scope:** Combined severity/section/status/keyword filters; all issue detail fields/counts; four tabs result/trace/version comparison/history; score/coverage denominator display without fabrication.
**Dependencies:** `5-1-pinned-reviewers`.
**Traceability:** FR-24,FR-26,FR-33; C-2,C-4,C-7; AD-10,AD-16.
**UI reference:** P-08 `.review-filters/.filter/.issue[data-issue]/#detailSev/#issueTitle/#issueLoc/#issueDesc/#issueQuote/#issueSuggestion/.trace`; P-09 four `.seg-tabs` buttons; C28,C29,C30,C35; SUP-5,SUP-9. R all selected data.
**UI fidelity:** Strict original1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and intended interactions. Preserve source hierarchy/file; R/S/conflicts explicit; added history bodies follow UX without nonexistent pixel claims.
**Acceptance Criteria:**
- **Given** all seven prototype issue categories represented by actual records and multiple runs, **When** filters combine AND and issue/tab changes, **Then** ID/severity/location/quote/impact/suggestion/source,counts and version-specific numerators/denominators update together; old selected detail cannot remain under another row.
- **Given** no matching issues, missing score definition,stale run or forbidden source, **When** viewed, **Then** explicit empty/unevaluated/stale/denied states appear without92/86/78 sample metrics or protected excerpts. High score and decorated ring do not imply release approval.
**Evidence:** T-UX complete C28–C30/C35 interaction/screenshots; T-CONTRACT filter/denominator tests; T-SEC history/source ACL.
**L/R/P:** L actual local findings; R expert source interpretability UAT; P large-run list performance13-4.

## Story 5.3: Resolve findings with distinct human decisions
**ID:** `5-3-issue-disposition` | **Status:** backlog | **Projects:** W,A,K
As an expert, I want accept,reject,modify and handled to mean different things, so that a severe finding cannot disappear without verification.
**Scope:** Accepted/rejected/fixed/waived/closed transitions, rationale, Patch link/recheck and explicit allowed waiver authorization.
**Dependencies:** `5-2-review-inspection`, `4-4-reviewed-patches`.
**Traceability:** FR-25,FR-29; NFR-5; C-2,C-7; AD-3,AD-10.
**UI reference:** P-08 `.issue-action[data-act="接受"/"拒绝"/"修改"/"标记已处理"]`, X-01,X-02; C31,C32,C33,C34; SUP-1,SUP-9. R distinct decisions,S recheck/reason.
**UI fidelity:** Explicit strict existing visual/interaction1:1 for layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Keep source action order/hierarchy/file; R/S/conflicts registered, new panels use UX not fictional pixels.
**Acceptance Criteria:**
- **Given** authorized issue on current version, **When** Accept/Reject/Modify/Handled are each used, **Then** Accept opens/applies checked selected Patch,Reject records reason without content change,Modify opens precise real block,and Handled requires verification/allowed exception; decisions are auditable and not synonymous with fixed.
- **Given** severe unsupported fact, stale Review,no waiver policy or unauthorized actor, **When** rejection/handled/waive is attempted, **Then** severe unresolved gate remains; fixed/closed requires recheck, explicit waiver cannot override non-waivable safety/publication requirements. Editing produces a new version needing fresh relevant checks.
**Evidence:** T-CONTRACT state-transition table, severe-negative/waiver/audit-failure cases; T-UX four actions; T-AST selected patch/recheck links.
**L/R/P:** L actual human decision endpoints and deterministic rechecks; R enterprise waiver roles/policy supplied before enabling, real defect resolution UAT; P no approval claim from fixture.

## Story 5.4: Compose a source-grounded technical solution
**ID:** `5-4-technical-solution` | **Status:** backlog | **Projects:** W,A,K
As a technical author, I want mandatory solution chapters with supported parameters, so that the proposal is coherent and reviewable.
**Scope:** Technical-solution template rules and fixtures, current project/formal company standards, architecture chapter Evidence, parameter/fact consistency. Reuses context/generation/Patch/Review rather than new pipeline.
**Dependencies:** `5-3-issue-disposition`.
**Traceability:** FR-9,FR-26; C-2,C-4,C-5,C-7; AD-8,AD-9,AD-10.
**UI reference:** P-01 technical-solution create,P-03 paper/tree,P-04/P-05/P-06,P-08; X-15,X-01; C08,C11,C19,C21,C22; SUP-6. R type-specific records.
**UI fidelity:** Strict original visual/interaction1:1 layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button/input states/responsiveness. Preserve hierarchy/source; explicit R/S/conflicts; X surfaces follow UX not imaginary pixels.
**Acceptance Criteria:**
- **Given** versioned solution template and confirmed project facts/standards, **When** create→outline-confirm→Pack→section-generate→accept→Review completes, **Then** required chapters exist, architecture/technical Claims trace to current applicable sources and full-document parameter checks are locatable.
- **Given** absent mandatory chapter,old source or unsupported performance/capacity value, **When** Review checks, **Then** missing/unsupported state persists as severe/pending as policy defines; model cannot invent replacement numbers and historical generic examples are not current project facts.
**Evidence:** T-DOC/T-QUALITY type fixture with positive and seeded conflict cases, T-UX full author/Review trace. Formal export/approval included in7-4 after epic-6.
**L/R/P:** L actual pipeline with labeled model double; R real technical team3–5 historical-project UAT tasks and model efficacy; P chapter load13-4.

## Story 5.5: Author a structurally complete PRD
**ID:** `5-5-prd-composition` | **Status:** backlog | **Projects:** W,A,K
As a product author, I want structured requirements, so that roles,exceptions and acceptance conditions remain traceable.
**Scope:** PRD-specific template/schema validation/Requirement projections and source links; current pipeline.
**Dependencies:** `5-3-issue-disposition`.
**Traceability:** FR-10; C-2,C-4,C-7; AD-2,AD-9,AD-10.
**UI reference:** P-01/P-02 PRD create,P-03 requirement blocks,P-04/P-08,X-15; C08,C10,C11,C19; SUP-6. R PRD fields,S validation detail.
**UI fidelity:** Strict existing1:1 visual/interaction layout/position/size/spacing/fonts/size/weight/color/radius/shadow/border/icon/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; mark R/S/conflicts, added fields follow UX without source-pixel claims.
**Acceptance Criteria:**
- **Given** a PRD template/context, **When** author builds/accepts/reviews a requirement, **Then** FR-ID,name,role,scenario,prerequisites,normal/exception flow,rules,input/output,permission,NFR and acceptance fields are persisted with stable section/source locators.
- **Given** duplicate/missing FR-ID,missing exception/permission/acceptance or unauthorized source, **When** validate/Review runs, **Then** exact missing field is reported and prior valid data preserved; prose summary alone cannot satisfy structured requirements.
**Evidence:** T-AST/T-CONTRACT field/schema/ID tests; T-DOC/T-UX complete PRD author/Review fixture; full approval/export7-4.
**L/R/P:** L real local pipeline; R product-role3–5 complete UAT tasks with real approved data/model; P later load.

## Story 5.6: Maintain Phase 1 requirement-to-test coverage
**ID:** `5-6-test-traceability` | **Status:** backlog | **Projects:** W,A,K
As a test author, I want bidirectional requirement/test/acceptance links, so that missing or redundant coverage is visible before Phase 2.
**Scope:** Test-plan type, Requirement↔TestItem↔TestCase↔Acceptance links and actual baseline coverage/drill-down; requirement-to-test proposals preserve approved thresholds.
**Dependencies:** `5-5-prd-composition`.
**Traceability:** FR-11,FR-20,FR-33; C-2,C-7; AD-2,AD-9,AD-10.
**UI reference:** P-01 test-plan create,P-03 requirement/test blocks,P-04 conversion chooser,P-08 coverage; X-12 coverage detail; C08,C17,C21; SUP-5. R coverage,S trace table.
**UI fidelity:** Strict source visual/interaction1:1 covers layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button/input states/responsiveness. Preserve hierarchy/file; R/S/conflicts explicit; X-12 new body follows UX, not existing source pixels.
**Acceptance Criteria:**
- **Given** versioned requirements and acceptance thresholds, **When** tests are proposed/accepted/linked, **Then** both navigation directions reach correct IDs/versions and coverage uses actual eligible numerator/denominator with uncovered/redundant rows visible.
- **Given** model changes an approved threshold,deleted/stale requirement link or no test authority, **When** save/Review runs, **Then** reject/flag precise mismatch, no silently changed threshold or100% score; new requirement versions mark links stale.
**Evidence:** T-CONTRACT/T-AST link/threshold/denominator cases; T-QUALITY conversion defects; T-UX bidirectional trace.7-4 includes complete formal flow.
**L/R/P:** L genuine link/coverage implementation now, not deferred; R testing-role3–5 real tasks; P trace-volume load later.

## Story 5.7: Make technical requirements measurable
**ID:** `5-7-measurable-requirements` | **Status:** backlog | **Projects:** W,A,K
As a requirements engineer, I want measurable statements, so that technical acceptance cannot rest on vague adjectives.
**Scope:** Technical-requirements type and Reviewer rules for condition+metric+threshold+verification method, immutable approved threshold provenance.
**Dependencies:** `5-3-issue-disposition`, `5-6-test-traceability`.
**Traceability:** FR-11,FR-26; C-2,C-4,C-7; AD-9,AD-10.
**UI reference:** P-07 technical requirements template,P-03 blocks,P-04 `[data-ai="改写为技术要求"]`,P-08 issue detail; C19,C23,C30; SUP-9. R actual measurable proposals.
**UI fidelity:** Strict original1:1 layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interactions. Preserve source hierarchy/file; R/S/conflicts explicit, supplements use UX not fictional pixels.
**Acceptance Criteria:**
- **Given** measurable requirement source, **When** rewritten and accepted, **Then** condition,metric,unit,threshold and verification method remain explicit and source-linked; Review locates missing fields.
- **Given** vague phrases or model-proposed unsupported threshold, **When** Reviewer evaluates, **Then** actionable ambiguity/unsupported finding remains, AI cannot fabricate approval or silently lower standard; unauthorized edits fail.
**Evidence:** T-QUALITY seeded vague/threshold fixtures; T-AST no-threshold-mutation tests; T-DOC/T-UX type flow and7-4 formal regression.
**L/R/P:** L deterministic real pipeline; R requirements/quality-role UAT and real model recall; P later load.
