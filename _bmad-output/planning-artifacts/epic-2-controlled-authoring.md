---
epic_id: epic-2
status: planned
phase: 1
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 2: Create and edit controlled documents

Outcome: authors choose governed templates, preserve immutable content versions and confirm project context/outline. W/A/K and evidence/authorization boundaries follow epics.md.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 2-1 AC1–2,Evidence,L/R/P | Actual catalog/filter/create/denial using test fixtures; no claim later type workflows work | Official templates and role UAT →13-3; load →13-4 |
| 2-2 AC1–2,Evidence,L/R/P | Actual AST/editor roundtrip and safe ordinary image path | Enterprise document/resource samples →13-3; large-version timing →13-4 |
| 2-3 AC1–3,Evidence,L/R/P | Actual CAS/merge/offline behavior and correct debounce/request measurement; record local timing | Real coauthor UAT →13-3; AC3 P95<1s under frozen acceptance workload →13-4 |
| 2-4 AC1–2,Evidence,L/R/P | Real safe validation/versioning/preview and denied formal-use cases with development assets | Official template/font/theme/policy-owner validation →13-3; real hardening →13-5 |
| 2-5 AC1–2,Evidence,L/R/P | Working manual versioned context with sourced local facts | Authoritative enterprise fact contracts/data →13-2; load →13-4 |
| 2-6 AC1–2,Evidence,L/R/P | Manual outline confirmation/revision/required-section checks | Enterprise type-template owner validation →13-3; no model SLA inferred |

## Story 2.1: Choose a template and create the intended document
**ID:** `2-1-template-creation` | **Status:** backlog | **Projects:** W,A
As an author, I want my chosen type/scope/template persisted, so that I begin with the correct structure rather than an old open document.
**Scope:** Template browsing and approved fixture catalog, complete document-type catalog, creation modal, pinned template_version and own initial AST. Later type-specific rules are added in5/8/10/11, not claimed implemented by this catalog.
**Dependencies:** `1-3-workspace-discovery`.
**Traceability:** FR-1,FR-7; NFR-1; C-1,C-2; AD-2,AD-7,AD-16.
**UI reference:** P-01 five `[data-create]`/recommendation entries; P-02 `#modalMask/#modalDocName/#modalDocType` and unnamed scope select/`#modalCreate/#modalCancel`; P-07 `#templateSearch/#chips/#templateGrid/.tcard/#detailName/#detailType/#detailCover/.outline-list/.use-template/#detailUse` and both previews; C08,C09,C10,C23,C24,C25; SUP-6. R actual selection/filter/create, S missing scope/type choices.
**UI fidelity:** Strict original visual/interaction1:1 for layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness; preserve source hierarchy/source file. Mark R/S additions and conflicts without unilateral changes; new bodies follow UX, not fictitious source pixels.
**Acceptance Criteria:**
- **Given** company/department/product-line/project/personal templates, **When** scope,query,category,type combine, **Then** AND results and selected metadata/own outline/preview are correct; create persists name/type/allowed knowledge scope/template version, returns201 and opens a new ID/AST.
- **Given** deprecated/inaccessible template, denied scope, invalid name or concurrent template deprecation, **When** create commits, **Then** API rejects with appropriate TEMPLATE_DEPRECATED/403/422 and retains input; no fake loaded-knowledge claim. Cancel/backdrop create nothing; retries cannot duplicate documents.
**Evidence:** T-CONTRACT/T-UX/T-SEC creation/filter/idempotency tests and screenshots.
**L/R/P:** L real W/API/PG approved development fixtures; R official enterprise template assets and role UAT pending; P load in13-4.

## Story 2.2: Edit a source-compatible domain AST
**ID:** `2-2-domain-editor` | **Status:** backlog | **Projects:** W,A
As an author, I want structured content and formatting preserved, so that editor changes do not destroy document semantics.
**Scope:** `domainToEditor`/`editorToDomain`, AST schema1.0 metadata/sections/claims/citations/review_state, stable IDs and P-03 tree/title/canvas/toolbar; immutable saved versions. Blocks paragraph,heading,table,figure,diagram,requirement,citation,warning,code,form. Implement the minimal C15 authorized image upload/resource path now (type/size/hash/current ACL, no remote fetch, explicit alt text/aspect ratio) for editor insertion;3-1 extends it to multi-format parsing/OCR and4-5 to generated graphics, neither is a prerequisite for ordinary image/table/link editing.
**Dependencies:** `2-1-template-creation`.
**Traceability:** FR-5,FR-6; C-2; AD-1,AD-2,AD-16.
**UI reference:** P-03 `#docTree/.doc-toolbar/.paper/#docTitle/#crumbTitle`; C11,C12,C13,C14,C15; SUP-9. R AST-backed selection/format/undo, S unsupported read-only representation.
**UI fidelity:** Strict source visual/interaction1:1 includes layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button/input states/responsiveness. Preserve source hierarchy/file; enumerate B/R/S and conflicts; new UI follows UX without invented prototype pixels.
**Acceptance Criteria:**
- **Given** round-trip fixtures for every legal block and requirement_id/statement/verification_method/source_refs, **When** editing title/selected text,undo/redo,list/alignment/link/table/image operations and saving, **Then** stable IDs/Claim/citation bindings survive adapter round-trip and tree targets correct sections. Images use authorized resources, not arbitrary remote embedding.
- **Given** unknown supported-future node or malformed AST/unsafe link, **When** loaded or submitted, **Then** unknown data is retained read-only with message; invalid updates reject preserving last valid version, never flatten to plain text. Reader cannot edit and Published is immutable.
**Evidence:** T-AST property/round-trip/schema fixtures; T-UX selection/toolbar tests; T-SEC unsafe URL/resource access tests.
**L/R/P:** L actual editor/API; R enterprise document/asset samples pending; P large-version performance13-4.

## Story 2.3: Save and resolve concurrent versions without loss
**ID:** `2-3-version-conflicts` | **Status:** backlog | **Projects:** W,A
As a coauthor, I want visible save state and explicit merging, so that another writer cannot silently erase my changes.
**Scope:**1000ms idle autosave, explicit save, revision/base CAS, version history/base-local-latest comparison and checked merge.
**Dependencies:** `2-2-domain-editor`.
**Traceability:** FR-6,FR-21; NFR-8,NFR-13; C-2; AD-2,AD-3.
**UI reference:** P-03 `.doc-top` save/version area and toolbar More; X-02 history/conflict; P-09 version compare; C12,C17,C28; SUP-1,SUP-9. R true status,S version/conflict.
**UI fidelity:** Strict existing1:1 layout/position/size/spacing/font-family-size-weight/color/radius/shadow/border/icon/image proportions/button-input states/responsiveness. Preserve hierarchy/source; mark R/S and conflict register without self-deciding; X-02 uses UX contract not source pixels.
**Acceptance Criteria:**
- **Given** two writers share base_version_id/document_revision, **When** saves race, **Then** exactly one CAS succeeds and other returns409 DOC_VERSION_CONFLICT retaining base/local/latest; per-block keep mine/use latest/manual merge creates checked new version, not last-writer-wins.
- **Given** failed/offline save, revoked access or Published base, **When** autosave/retry/history opens, **Then** UI says unsaved/conflict/forbidden as appropriate, no false timestamp; no sensitive offline browser persistence; historic version reads reauthorize. Unauthorized retry never returns a prior protected success body.
- **Given**1000ms idle debounce, **When** a save timing event is emitted, **Then** debounce duration, client request time and server time are separate fields. **Verification:** timing-event contract test.
**Evidence:** T-AST/T-CONTRACT concurrent two-browser saves, merge/version hashes; T-UX state/history and structured timing traces. P95<1s is owned by13-4.
**L/R/P:** L real PG CAS and browser network loss; R real coauthor UAT; P NFR-8 load13-4.

## Story 2.4: Govern reusable template versions
**ID:** `2-4-template-governance` | **Status:** backlog | **Projects:** W,A,K
As a template administrator, I want validated versioned template rules, so that authors reuse controlled standards without historical mutation.
**Scope:** Upload,structure/chapter,retrieval/Prompt/Reviewer/render/approval rules,validation/preview,publish/deprecate and pinned-use records. Safe worker validation handles document assets; no arbitrary template execution.
**Dependencies:** `2-1-template-creation`, `1-6-task-observation`.
**Traceability:** FR-8,FR-30; NFR-5,NFR-7; C-2,C-6,C-7; AD-2,AD-6,AD-12.
**UI reference:** P-07 `#uploadTpl`; X-14 tree/editor/inspector/validation/preview/publish/deprecate; C26; SUP-6. R upload,S governance body.
**UI fidelity:** Inherit strict source visual/interaction1:1 across layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness; source hierarchy/file unchanged. Register R/S/conflicts; new X-14 validated against UX not imaginary prototype pixels.
**Acceptance Criteria:**
- **Given** authorized valid template assets and policies, **When** validate/preview/publish executes, **Then** a new immutable template version and audit are stored; document references remain pinned and preview uses that version's own structure.
- **Given** malformed/archive-bomb/active template content, invalid rules, absent official font/policy or unauthorized administrator, **When** publish/use/deprecate is attempted, **Then** reject or clearly label development-only, never formal-ready; referenced versions cannot be physically deleted and old documents are not rewritten.
**Evidence:** T-DOC/T-SEC asset/rule validation and sandbox tests; T-CONTRACT version/reference tests; T-UX X-14 states.
**L/R/P:** L labeled development fixtures and real isolated validation; R official templates/fonts/themes and policy owner validation required; P renderer hardening13-5.

## Story 2.5: Assemble confirmed project context
**ID:** `2-5-project-context` | **Status:** backlog | **Projects:** W,A
As an author, I want explicit project facts and constraints, so that generation can distinguish known inputs from missing information.
**Scope:** Workspace/intent/pinned template/project fact table/glossary/reference links/constraints/missing information, manual context confirmation. Attachments/retrieval results integrated by3-1/3-4.
**Dependencies:** `2-2-domain-editor`.
**Traceability:** FR-18,FR-22,FR-28; C-2,C-4; AD-2,AD-7.
**UI reference:** X-15 context/facts/glossary/constraints/missing-info inspector; P-02 create destination; C09,C10; SUP-6. S context page.
**UI fidelity:** Preserve inherited source shell1:1 layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button/input states/responsiveness. No source changes; R/S additions/conflicts explicit; X-15 follows UX contract, not claimed source pixel baseline.
**Acceptance Criteria:**
- **Given** authorized fact values with units/source/owner/confirmation, **When** author saves context, **Then** versioned facts/glossary/constraints are retrievable and only satisfied prerequisites permit CONTEXT_READY; missing facts remain located pending items.
- **Given** contradictory facts, foreign references or stale context version, **When** saving/confirming, **Then** conflicts/denials are visible and prior context remains intact; no AI-invented fact or modal-close state transition.
**Evidence:** T-CONTRACT/T-SEC context version/ACL tests; T-UX field/missing states.
**L/R/P:** L manual local context fully usable without model; R authoritative project fact sources remain integration acceptance; P load later.

## Story 2.6: Confirm a complete outline before generation
**ID:** `2-6-outline-confirmation` | **Status:** backlog | **Projects:** W,A
As an author, I want to approve the mandatory outline, so that later generation respects the document's intended structure.
**Scope:** Template/manual outline edit/reorder/validate/confirm, required-section protection and revision-aware invalidation. AI outline producer added4-2 consumes this same confirmation API.
**Dependencies:** `2-5-project-context`, `2-4-template-governance`.
**Traceability:** FR-18,FR-19,FR-28; C-2,C-7; AD-2,AD-3.
**UI reference:** X-15 outline tree/editor/confirm/request-sections; P-03 `#docTree`; SUP-6. S outline controls,R persisted tree.
**UI fidelity:** Explicit strict existing visual/interaction1:1 for layout/position/size/spacing/fonts/size/weight/color/radius/shadow/border/icon/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; record R/S/conflicts, new X-15 uses UX contract not source pixels.
**Acceptance Criteria:**
- **Given** confirmed context and template mandatory chapters, **When** author validates/reorders with keyboard controls and confirms, **Then** exact outline revision/actor/time is saved and OUTLINE_READY is justified by persisted prerequisites.
- **Given** missing mandatory chapter, stale template/context, lack of edit permission or no human confirmation, **When** generation eligibility is queried, **Then** structured missing reasons block it; task completion or selecting a template never substitutes for confirmation. Changing confirmed outline invalidates dependent eligibility.
**Evidence:** T-CONTRACT outline invariant/transition tests; T-UX reorder/required/error states and confirmation history.
**L/R/P:** L fully testable with manual outline; R type-template validation by enterprise owners; P no model performance claim.
