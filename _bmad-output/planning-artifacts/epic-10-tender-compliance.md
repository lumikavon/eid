---
epic_id: epic-10
status: planned
phase: 3
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 10: Turn tender clauses into compliant responses

Outcome: bid specialists correct source-located requirements and expose unresolved mandatory risks through common release gates. W/A/K and global guards apply. No unapproved vendor/system integration is implied.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 10-1 AC1–2,Evidence,L/R/P | Actual parser/OCR/page correction/provenance and negative states | Authorized real tender corpus/extraction quality →13-1; bid specialist interpretation →13-3; tool security/load →13-5/13-4 |
| 10-2 AC1–2,Evidence,L/R/P | Actual declared deterministic risk/scoring rules and unresolved defenses | Real tender domain Golden labels →13-1; actual legal/business interpretation →13-3; no award/legal guarantee |
| 10-3 AC1–2,Evidence,L/R/P | Actual bidirectional matrix/navigation/stale/export-context cases | Actual mapping adjudication/official output sample →13-3; larger-matrix load →13-4 |
| 10-4 AC1–2,Evidence,L/R/P | Actual specialist checks/common hard gates/test-profile release without bypass | Real model/defect efficacy →13-1; bid-team policy/official templates →13-3; actual security/load →13-5/13-4 |
| 10-5 AC1–3,Evidence,L/R/P | Actual complete specialist E2E and deferred-control closure; tender-domain eligibility validator | AC2 actual50–200 representative tender-domain queries with defect/ACL labels and actual model/corpus →13-1; real enterprise chain →13-2; bid-role3–5 full historical tasks →13-3; production targets →13-4/13-5 |

## Story 10.1: Parse and correct tender requirements page by page
**ID:** `10-1-tender-intake` | **Status:** backlog | **Projects:** W,A,K
As a bid specialist, I want source-located extraction with corrections, so that incomplete OCR does not become a complete tender analysis.
**Scope:** Bid/tender/source revisions,qualification/commercial/technical fields,per-page parse/OCR states,original excerpt comparison/manual correction/history. Reuse safe attachment workers.
**Dependencies:** `7-4-core-integration`.
**Traceability:** FR-35,FR-17; C-2,C-3,C-4,C-6; AD-6,AD-13.
**UI reference:** P-01 bid quick-create,P-07 bid template; X-05 upload/source-page index/excerpt/requirement inspector/history; C08,C24; SUP-3. R bid entry,S full intake.
**UI fidelity:** Strict existing1:1 visual/interaction layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; R/S/conflicts explicit; X-05 follows UX, not nonexistent original pixels.
**Acceptance Criteria:**
- **Given** authorized tender PDF/scans with multiple clause types, **When** parse/OCR and manual correction run, **Then** every requirement has tender/page/section/locator/version,category/value/current confirmation and correction actor/history; actual per-page queued/OCR/partial/failed state is inspectable.
- **Given** missing pages,OCR ambiguity,malicious instructions or revoked tender source, **When** analysis/use occurs, **Then** not complete/needs confirmation/denied is explicit, no fabricated clause or elevated model instructions; corrected new revision makes affected downstream links stale.
**Evidence:** T-TENDER/T-DOC page/scan/correction fixtures; T-SEC malicious/revoked source; T-UX X-05 trace and task states.
**L/R/P:** L real parser/OCR/W/A/K with labeled model double; R real authorized tender corpus and bid specialist review; P tool security/load later.

## Story 10.2: Expose mandatory, disqualification and scoring risks
**ID:** `10-2-tender-risk-rules` | **Status:** backlog | **Projects:** W,A,K
As a bid specialist, I want declared scoring and disqualification rules, so that unsupported optimistic scores cannot hide a losing condition.
**Scope:** Mandatory/disqualification/scoring fields and source/rule versions,manual confirmation,deterministic calculation where declared and not-evaluable states otherwise.
**Dependencies:** `10-1-tender-intake`.
**Traceability:** FR-36,FR-29; C-4,C-7; AD-10,AD-13.
**UI reference:** X-05 mandatory/disqualification/scoring inspector; X-06 risk filters/calculation detail; SUP-3. S specialist rule views.
**UI fidelity:** Strict source1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and intended interaction. Preserve hierarchy/source file; identify R/S/conflicts; X bodies follow UX, not source-pixel fiction.
**Acceptance Criteria:**
- **Given** confirmed clause with explicit scoring formula/conditions and evidence, **When** evaluated, **Then** outcome links exact clause/rule/version/input/score and distinguishes mandatory/disqualification risk from score contribution.
- **Given** unclear rule,unconfirmed OCR,missing evidence or unresolved mandatory clause, **When** score/eligibility is requested, **Then** not-evaluable/unresolved is visible and cannot be marked compliant by model confidence/high aggregate; unauthorized rule edits reject.
**Evidence:** T-TENDER scoring/mandatory/disqualification positive/negative fixtures; T-CONTRACT source/version/rule authorization; T-UX risk states.
**L/R/P:** L declared deterministic rule calculation; R actual tender legal/business interpretation and domain Golden labels; P no legal/award guarantee.

## Story 10.3: Navigate bidirectional compliance and stale links
**ID:** `10-3-compliance-matrix` | **Status:** backlog | **Projects:** W,A,K
As a response author, I want requirement-response-Evidence links in both directions, so that every compliance gap can be traced and corrected.
**Scope:** Matrix rows/response locations/Evidence links/version context,missing/partial/conflicting/unconfirmed/stale states,filters and export-context adapter.
**Dependencies:** `10-2-tender-risk-rules`, `3-5-claim-citation`.
**Traceability:** FR-37; C-2,C-4,C-7; AD-2,AD-7,AD-13.
**UI reference:** X-06 full-width horizontally scrollable matrix with requirement/source/type/mandatory/scoring/response/Evidence/state/version fields; X-05 source and P-03 response; SUP-3. S matrix.
**UI fidelity:** Strict inherited source visual/interaction1:1 layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Source hierarchy/file preserved; R/S/conflicts explicit; X-06 uses UX not imaginary source pixels, no card-only substitute.
**Acceptance Criteria:**
- **Given** confirmed requirements and actual response section/Evidence versions, **When** links are created and followed in either direction, **Then** exact clause/page/response/block/source opens and actual coverage state derives from eligible links; exports include current matrix/tender/response versions.
- **Given** tender correction,response edit,source revocation or deleted target, **When** matrix refresh/Review/export occurs, **Then** affected link/review becomes stale/denied,missing/partial/conflict not hidden; must remap/revalidate rather than inherit compliant status.
**Evidence:** T-TENDER/T-CONTRACT bidirectional/stale/export-context tests; T-SEC denied source; T-UX filters/keyboard/scroll/source navigation.
**L/R/P:** L real domain/UI/worker data; R actual tender/response mapping adjudication and official export sample; P larger matrix load13-4.

## Story 10.4: Check responses and enforce common bid release gates
**ID:** `10-4-bid-review-release` | **Status:** backlog | **Projects:** W,A,K
As a bid reviewer, I want cross-response defects in shared Review, so that specialist views cannot bypass common controls.
**Scope:** Bid response generation/Patch reuse,residual customer/project names,parameter conflict detection,mandatory compliance gate contribution,shared human approval/publication/export.
**Dependencies:** `10-3-compliance-matrix`.
**Traceability:** FR-38,FR-36,FR-37,FR-29,FR-30; C-2,C-4,C-5,C-7; AD-10,AD-11,AD-13.
**UI reference:** X-06 residual-name/parameter check/task/findings→P-08/P-09→X-03/X-04/X-19; SUP-3,SUP-2,SUP-8. S specialist checks,R common gate data.
**UI fidelity:** Strict original1:1 visuals/interactions layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve hierarchy/source; R/S/conflicts explicit; new X uses UX contract not original pixels.
**Acceptance Criteria:**
- **Given** current tender/response/project facts, **When** bid generation/Review runs, **Then** residual historical names and contradictory parameters produce located issues tied to common eight Reviewer/current candidate checks; accepted corrections require normal Patch/base/ACL validation.
- **Given** unresolved mandatory/disqualification item,severe unsupported Claim,stale matrix or audit/approval failure, **When** formal publish/export request is made, **Then** publication blocks regardless of bid score or UI flag and formal status is not granted; resolved/current approved version can export with matrix context.
**Evidence:** T-TENDER/T-QUALITY name/parameter/mandatory defects; T-CONTRACT common-gate no-bypass tests; T-DOC bid outputs; T-UX issue-to-source-to-release.
**L/R/P:** L actual pipeline with deterministic model; R real model/tender defects and bid-team policy/official templates; P shared security/load later.

## Story 10.5: Prove the complete three-project tender workflow
**ID:** `10-5-tender-integration` | **Status:** backlog | **Projects:** W,A,K
As a delivery reviewer, I want a real tender E2E, so that a successful document demo cannot mask an unimplemented bid workbench.
**Scope:** Specialist integrated regression,source/response revision and fault cases; extend T-QUALITY domain metadata/gold labels for tender.
**Dependencies:** `10-4-bid-review-release`.
**Traceability:** FR-35,FR-36,FR-37,FR-38,FR-34,FR-48; C-1,C-2,C-3,C-4,C-5,C-6,C-7; AD-13,AD-18.
**UI reference:** UJ-4,P-00/P-01/P-02/P-03/P-08/P-09,X-05/X-06/X-01/X-03/X-04/X-19/X-16; SUP-3,SUP-9.
**UI fidelity:** Explicit strict source1:1 layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interactions. Preserve source hierarchy/file; list R/S/conflicts; new specialist bodies follow UX, no pixel claim.
**Acceptance Criteria:**
- **Given** actual W/A/K+OIDC/PG/MQ/S3/SSE and real parser/render tools, **When** tender upload→page correction→mandatory/scoring→bidirectional mapping→response/Evidence/Patch→Review→approval/publish→all document exports executes, **Then** source-to-output provenance joins across projects and genuine bid artifact contains current matrix context; only external model/enterprise ports may be doubles.
- **Given** partial parse,changed tender,revoked source,worker restart and unresolved mandatory risk, **When** chain repeats, **Then** respective incomplete/stale/denied/recovered/blocked outcomes are visible with no fake success. Tender domain real-quality eligibility requires50–200 representative queries+defect/ACL labels, not local tiny fixture.
- **Given**7-5 deferred tender C08 quick-create/C24 template entry and Tender workbench component rows, **When** user opens the actual bid intake,corrects pages,filters risks,follows both matrix directions and completes response/release/export, **Then** preserve exact IDs/source locators and positive action traces plus denied/partial/stale/failed/mandatory-block cases; close each deferred sub-action explicitly. Visible entry/empty/not-configured is not positive functional evidence;12-6 reruns and13-3 revalidates real users/assets.
**Evidence:** T-TENDER/T-CONTRACT/T-TASK/T-DOC/T-SEC/T-UX/T-QUALITY actual E2E manifests/screenshots/artifacts including C08/C24 and all X-05/X-06 deferred-row closure with positive-negative traces; no all-mock chain; final reruns12-6/13-3.
**L/R/P:** L local full specialist E2E; R authorized real tender corpus/model and bid personnel3–5 complete historical tasks remain mandatory/blocked until ready; P production targets separate13-4/13-5.
