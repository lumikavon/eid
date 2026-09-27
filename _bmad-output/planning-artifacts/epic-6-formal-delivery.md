---
epic_id: epic-6
status: planned
phase: 1
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 6: Approve, publish and deliver a fixed document

Outcome: human authorities release a version under fail-closed policy, export real artifacts and independently return eligible knowledge. W/A/K and L/R/P follow epics.md.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 6-1 AC1–2,Evidence,L/R/P | Actual pinned human-role fixture approval/rejection/race/rollback | Enterprise approval policy/roles/UAT →13-3; audit durability →13-5 |
| 6-2 AC1–3,Evidence,L/R/P | Same full gate predicate and atomic transaction in isolated test profile; missing real config denial | Actual threshold/waiver/approval interpretation and official assets →13-3; current real ACL →13-2; real policy/durability/security →13-5 |
| 6-3 AC1–2,Evidence,L/R/P | Genuine DOCX/PDF with configured test fields,development labeling,safe tooling and failure proof; local time recorded | Official fonts/themes/Golden samples/formal review and all AC1 fields →13-3;50-page<60s and20 simultaneous30–80-page load →13-4 |
| 6-4 AC1–3,Evidence,L/R/P | Actual HTML AND Markdown semantic/security/no-network/revocation tests | Enterprise permitted style/resource rules and formal reviews →13-3; real source ACL →13-2; real security/load →13-5/13-4 |
| 6-5 AC1–2,Evidence,L/R/P | Actual API/S3/Range/hash/share/IDOR/revocation cases | Enterprise storage/lifecycle adapter →13-2; governed lifecycle/encryption/access policy →13-5 |
| 6-6 AC1–3,Evidence,L/R/P | Actual separate quality gate/parse/effect handling with stateful KB-port simulator; simulator receipts labeled | Actual KB return/verified receipt/current ACL and source policy →13-2; business quality-policy interpretation →13-3; durability →13-5 |

## Story 6.1: Request and record pinned human approval
**ID:** `6-1-human-approval` | **Status:** backlog | **Projects:** W,A
As an approver, I want the exact candidate and its checks, so that my decision cannot silently approve later edits.
**Scope:** Template-policy approval request/inbox/content/Review/pending/provenance/reason/decision/history, policy/current authority and lifecycle transitions.
**Dependencies:** `5-3-issue-disposition`.
**Traceability:** FR-27,FR-28; NFR-1,NFR-5; C-2,C-7; AD-3,AD-7,AD-10.
**UI reference:** X-03 inbox/detail/decision/history; P-03 More,P-01 Review reminder; SUP-2. S approval,R state.
**UI fidelity:** Strict inherited source1:1 visual/interaction layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve hierarchy/source file; R/S/conflicts explicit; X-03 uses UX contract not fabricated source pixels.
**Acceptance Criteria:**
- **Given** current candidate/template approval policy and authorized approver, **When** request then approve/reject with reason occurs, **Then** immutable request/decision pins document/policy/version and Review context; rejection returns actionable correction state, approval is not publication.
- **Given** edited candidate,changed policy/authority,missing required Review or audit failure, **When** decision commits, **Then** revalidation/denial prevents inherited approval; decision/state/audit either all commit or none. No unspecified approver/waiver role is invented.
**Evidence:** T-CONTRACT/T-SEC version/role/race/audit-failure tests; T-UX inbox/preview/decision/history.
**L/R/P:** L actual local human-role fixtures; R enterprise approval policy/official roles/UAT required; P audit-store durability later.

## Story 6.2: Publish only when every current gate passes
**ID:** `6-2-atomic-publication` | **Status:** backlog | **Projects:** W,A,K
As a release owner, I want publication checked at commit time, so that a stale preview or high score cannot bypass hard requirements.
**Scope:** Versioned GateSet evaluation preview and authoritative short commit transaction; Publication/lifecycle/Audit/Outbox atomically, immutable published version/archive visibility. A versioned FR-29 required-gate registry defines the non-removable minimum rows; a GateSet may refine it but cannot omit or weaken a required row.
**Dependencies:** `6-1-human-approval`, `5-4-technical-solution`, `5-5-prd-composition`, `5-6-test-traceability`, `5-7-measurable-requirements`.
**Traceability:** FR-28,FR-29; NFR-1,NFR-5; C-2,C-4,C-7; AD-3,AD-7,AD-10,AD-11.
**UI reference:** X-04 complete gate table/failure links/confirm/publish; P-03 lifecycle; SUP-2. S release,R actual states.
**UI fidelity:** Strict existing1:1 visuals/interactions for layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Source hierarchy/file retained; R/S/conflicts explicit; new X-04 follows UX, no original pixel claim.
**Acceptance Criteria:**
- **Given** a current version and versioned GateSet, **When** publication is requested, **Then** the server first rejects missing, unknown or weakened FR-29 required-gate rows, then evaluates the complete GateSet under current authorization and atomically records GateEvaluation, Publication, lifecycle, Audit and Outbox. **Verification:** required-gate-registry conformance and transaction integration test.
- **Given** exactly one registered GateSet row fails or is absent, **When** publication is requested, **Then** no Publication is created and the result names that single failed or missing row. **Verification:** registry-driven one-row-flip decision-table test.
- **Given** a changed version, revoked authority or audit failure after preview, **When** commit is requested, **Then** preview does not authorize publication and no partial state commits. **Verification:** concurrency/rollback integration test.
- **Given** a Worker identity, **When** it requests publication, **Then** it is denied. **Verification:** service-identity contract test.
**Evidence:** the four named tests; policy coverage is governed by the GateSet policy table rather than duplicated per Story.
**L/R/P:** L real transaction and local policies; R actual policy thresholds/official templates required, missing config stays blocked; P durability/security13-5.

## Story 6.3: Produce real DOCX and PDF with controlled layout
**ID:** `6-3-docx-pdf-rendering` | **Status:** backlog | **Projects:** W,A,K
As an author, I want genuine version-pinned files, so that formal review receives the same governed content and styling.
**Scope:** Version-pinned export request/status, DOCX rendering and PDF conversion with immutable provenance. Renderer implementation may use approved local tools; this Story does not require a framework-specific pipeline beyond producing the artifacts safely.
**Dependencies:** `6-2-atomic-publication`, `3-1-safe-attachments`.
**Traceability:** FR-30; NFR-6,NFR-7,NFR-11; C-3,C-6; AD-6,AD-12.
**UI reference:** X-19 request/task/artifact preview, P-08 download control,P-03 More; C27,C17; SUP-8. R real download,S export view.
**UI fidelity:** Strict original1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interaction entry. Preserve hierarchy/source; R/S/conflicts explicit; new export body uses UX contract, not source pixels.
**Acceptance Criteria:**
- **Given** an authorized pinned version and declared render profile, **When** DOCX or PDF export succeeds, **Then** the artifact records source version, profile and immutable hash. **Verification:** format-specific Golden artifact validator.
- **Given** an unsafe input, failed conversion or incomplete artifact, **When** export finishes, **Then** it is unavailable for download and the source version is unchanged. **Verification:** failed-export integration test.
- **Given** a renderer process, **When** it executes, **Then** it has no business credentials or network authority. **Verification:** sandbox configuration and execution test.
**Evidence:** DOCX/PDF Golden validators, failed-export test and sandbox test. The 50-page timing target belongs solely to13-4; official visual samples belong to13-3.
**L/R/P:** L real LibreOffice/docxtpl and explicitly marked dev fonts/templates; R official fonts/themes/Golden samples and formal output review mandatory; P20 simultaneous30–80-page load13-4.

## Story 6.4: Export safe HTML and Markdown
**ID:** `6-4-html-markdown-export` | **Status:** backlog | **Projects:** W,A,K
As an author, I want portable HTML/Markdown output, so that reuse does not introduce executable content or forbidden resource links.
**Scope:** Explicit HTML and Markdown formats from the same domain AST/version; safe serializers/sanitization/resource manifest, inherited classification/provenance and async status.
**Dependencies:** `6-3-docx-pdf-rendering`.
**Traceability:** FR-30; NFR-1,NFR-4,NFR-7; C-2,C-6; AD-2,AD-6,AD-12.
**UI reference:** X-19 format selector/preview/result; P-03 More/P-08 download; C17,C27; SUP-8. S format choice,R real artifact.
**UI fidelity:** Strict source visual/interaction1:1 for layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; R/S/conflicts enumerated; X-19 follows UX contract without fictitious original pixels.
**Acceptance Criteria:**
- **Given** all AST blocks with tables/links/figures/diagrams/citations, **When** HTML and Markdown export, **Then** each file preserves supported semantic content,stable citation/source/version context and controlled resource references from pinned AST rather than browser DOM; unsupported content is explicit, not silently dropped.
- **Given** script/event handlers/unsafe embedded HTML/javascript or data executable URLs/SVG active content/remote-image tracking/path traversal/Markdown link obfuscation fixtures, **When** export and preview occur, **Then** sanitizer/allowlist prevents execution and network-leaking resources; Markdown embedded HTML is sanitized or escaped, renderer cannot fetch arbitrary URLs.
- **Given** source/resource access revoked at export or later download, **When** used, **Then** current authorization rejects protected content; exported links do not become permanent access grants. Failed/partial output remains non-downloadable.
**Evidence:** T-DOC **HTML/Markdown security regression pack**, DOM/browser no-execution/network tests, semantic round-trip fixtures and T-SEC revoked-resource matrix; T-UX format/error tests.
**L/R/P:** L both actual serializers and malicious fixtures mandatory; R enterprise allowed resource/style rules and document reviews; P security/load13-5/13-4.

## Story 6.5: Download and internally share only currently authorized artifacts
**ID:** `6-5-controlled-artifacts` | **Status:** backlog | **Projects:** W,A
As a document owner, I want controlled artifact access, so that an old link cannot bypass revoked membership.
**Scope:** Authorized API-proxied artifact retrieval/current resource permissions,Range support,expiry/lifecycle metadata/internal route copy; no public-access grant or reusable direct S3 URL.
**Dependencies:** `6-4-html-markdown-export`.
**Traceability:** FR-30,FR-46; NFR-1,NFR-5,NFR-6; C-6; AD-7,AD-12.
**UI reference:** X-19 artifact/checksum/expiry/internal-share, P-08 download/share; C27; SUP-8. R safe actions,S artifact detail.
**UI fidelity:** Inherit strict original1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interactions. Preserve source hierarchy/file; R/S/conflicts explicit; new X body follows UX, not source pixels.
**Acceptance Criteria:**
- **Given** ready artifact and current access, **When** download/Range/internal route copy is requested, **Then** exact hash/version/media/size are returned via controlled endpoint with appropriate safe disposition and audit; recipient still authenticates and independently authorizes.
- **Given** expired/partial/failed artifact,revoked source/doc scope,guessed object ID,old URL or replayed Idempotency-Key, **When** download/Range executes, **Then** deny without existence/content leakage; no permanent S3 capability or token-bearing share URL is exposed. Policy TTL affects temporary objects, not arbitrary formal-version deletion.
**Evidence:** T-SEC every-format and Range revocation/IDOR tests; T-CONTRACT hash/media/state tests; T-UX share disclosure/no-public-link controls.
**L/R/P:** L real API/S3/browser downloads; R enterprise object-store/lifecycle policy validation; P encryption/access operations13-5.

## Story 6.6: Return eligible published knowledge through an independent gate
**ID:** `6-6-trusted-knowledge-return` | **Status:** backlog | **Projects:** W,A,K
As a knowledge administrator, I want only eligible formal content returned, so that drafts cannot contaminate trusted search.
**Scope:** Published event→independent Knowledge Quality Gate→parse/chunk/enrich/provenance→declared return adapter, EffectIntent/Receipt correlation and reconciliation; search eligibility requires verified receipt.
**Dependencies:** `6-5-controlled-artifacts`, `3-3-source-governance`.
**Traceability:** FR-31,FR-43; C-3,C-4,C-6,C-7,C-8; AD-4,AD-11,AD-15.
**UI reference:** X-11 return gate/task/receipt tabs,X-16 integration category; SUP-5,SUP-7. S return operations.
**UI fidelity:** Strict inherited source1:1 visual/interaction layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve hierarchy/source; enumerate R/S/conflicts; X pages use UX not invented source pixels.
**Acceptance Criteria:**
- **Given** approved Published candidate with configured return quality policy and current classification/ACL, **When** return runs, **Then** independent gate records eligible provenance/approval/template/Claim/Evidence versions and controlled parse/chunk/metadata; verified external receipt alone makes trusted searchable entry.
- **Given** draft/unapproved/gate-failing candidate, **When** return is requested, **Then** deny. **And** return failure never rolls back already committed publication or falsely marks trusted success.
- **Given** duplicate Published delivery or external timeout after possible success, **When** worker restarts, **Then** durable EffectIntent plus declared adapter idempotency/query/reconcile prevents blind resend; receipt_pending/unknown remains visible when outcome cannot be known, no unsupported exactly-once guarantee.
**Evidence:** T-CONTRACT/T-TASK/T-SEC draft denial/duplicate/unknown/receipt tests with local external-effect simulator; T-UX separate publication-return state.
**L/R/P:** L real W/A/K and deterministic external KB port; R actual KB return/receipt contract required and blocked until supplied; P durability later13-5.
