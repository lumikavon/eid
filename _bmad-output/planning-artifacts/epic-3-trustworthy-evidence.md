---
epic_id: epic-3
status: planned
phase: 1
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 3: Find and use traceable authorized Evidence

Outcome: authors inspect actual source passages and support Claims without enlarging authority. W/A/K and all global guards are defined in epics.md.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 3-1 AC1–3,Evidence,L/R/P | Actual parsers/OCR/S3 and malicious-file/revocation tests | Enterprise scan/output interpretation →13-3; storage adapter →13-2; governed tool/TTL limits/hardening →13-5 |
| 3-2 AC1–2,Evidence,L/R/P | Real search/index plumbing/current ACL with declared endpoint doubles if weights unavailable | Actual BGE/reranker/retrieval efficacy →13-1; enterprise KB/ACL →13-2; numerical load/permission-zero →13-4 |
| 3-3 AC1–2,Evidence,L/R/P | Real authority/conflict data and current-access behaviors | Enterprise authority/validity data mapping →13-2; domain-owner policy interpretation →13-3; load →13-4 |
| 3-4 AC1–2,Evidence,L/R/P | Actual Pack task/search/provenance,limits and revoked-commit tests; local timing captured | Real retrieval/Pack quality →13-1; enterprise contracts →13-2; Evidence searchP95<3s/PackP95<8s under frozen workload →13-4 |
| 3-5 AC1–3,Evidence,L/R/P | Actual Claim/citation/selection persistence and deterministic support cases | Actual extraction/support precision and human gold labels →13-1; usability adjudication →13-3; load →13-4 |

## Story 3.1: Upload and inspect safely parsed attachments
**ID:** `3-1-safe-attachments` | **Status:** backlog | **Projects:** W,A,K
As an author, I want authorized attachments parsed with page-level status, so that incomplete or unsafe input is never mistaken for verified knowledge.
**Scope:** Quarantine upload/content-type/size/hash validation, S3 object ownership, pypdf/docx/xlsx parsing and PaddleOCR on parse_ocr queue, source/page/chunk metadata and partial diagnostics.
**Dependencies:** `2-5-project-context`, `1-6-task-observation`.
**Traceability:** FR-17,FR-22; NFR-1,NFR-6,NFR-7; C-3,C-6; AD-6,AD-12.
**UI reference:** X-15 attachments/task/source state; X-10 attachment sources; SUP-6,SUP-5; C04. S attachment views.
**UI fidelity:** Strict inherited existing-page visual/interaction1:1: layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness; retain source hierarchy/file. R/S and conflicts explicit; new X bodies use UX, not nonexistent source pixels.
**Acceptance Criteria:**
- **Given** allowed PDF/DOCX/XLSX/image fixtures and current workspace clearance, **When** uploaded and parsed, **Then** API stores controlled object identity/hash, actual isolated tools produce page/section/chunk/locator metadata and partial/OCR/failed states; repeated task does not duplicate canonical parse records.
- **Given** MIME mismatch, archive bomb/path traversal/macro/link payload or quota/time violation, **When** validation/tool runs, **Then** reject/quarantine, no published download/result and no network/host/DB/MQ credential access; sandbox is non-root/read-only/seccomp with bounded temp and cleanup.
- **Given** access revoked before parse completion or source viewing, **When** use occurs, **Then** current policy denies exposing artifacts, not old upload snapshot; TTL cleanup never removes retained formal content outside policy.
**Evidence:** T-SEC/T-DOC/T-TASK actual tool fixtures, container identity/network/credential isolation, partial/replay/hash tests; T-UX states.
**L/R/P:** L real parsers/OCR/S3, not OCR stubs; R authorized enterprise scan corpus and storage adapter validation; P configured limits/hardening13-5.

## Story 3.2: Search enterprise and local attachment chains safely
**ID:** `3-2-authorized-retrieval` | **Status:** backlog | **Projects:** W,A,K
As an author, I want scoped keyword and semantic retrieval, so that exact identifiers and current authorized material can be found.
**Scope:** Internal Knowledge Gateway with declared enterprise adapters; local BGE-M3/pgvector+FTS/jieba/reranker chain and versioned index metadata. No forced enterprise re-embedding.
**Dependencies:** `3-1-safe-attachments`.
**Traceability:** FR-12,FR-13,FR-17,FR-42; NFR-1,NFR-9; C-1,C-4; AD-7,AD-8.
**UI reference:** P-10 navigation/shared placeholder only; X-10 search/domain/context/version/classification filters and enterprise/attachment/Golden tabs; P-05 evidence panel; C21,C35; SUP-5. S real knowledge body,R scoped data.
**UI fidelity:** Strict existing shell/panel visual and interaction1:1 across layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button/input states/responsiveness. Source hierarchy/file unchanged; R/S/conflicts explicit; P-10 new body is UX-contract-based, not prototype pixels.
**Acceptance Criteria:**
- **Given** permitted and denied sources plus exact standard/model/project/contract/customer/IP/port/version/metric queries, **When** filters combine, **Then** prefilter and postfilter ACL/context/validity apply before model/output; exact/keyword path complements vector search, sources remain from their declared chains.
- **Given** expired/changed membership, adapter outage or unconfigured route, **When** query/retry runs, **Then** unauthorized passages never enter results/logs/model, unavailable chain is labeled and no complete-search claim appears. Index rebuild uses only authorized workbench originals, not enterprise internal vectors.
**Evidence:** T-CONTRACT/T-SEC retrieval deny fixtures; T-QUALITY exact/hybrid/dictionary/embedding/reranker version manifest; T-UX source filters; baseline NFR-9 timing.
**L/R/P:** L real PG/FTS/index plumbing with labeled endpoint doubles if weights unavailable; R actual BGE/reranker and enterprise KB/ACL endpoints + real retrieval quality mandatory; P load/permission-zero targets13-4.

## Story 3.3: Preserve authority, freshness and visible source conflicts
**ID:** `3-3-source-governance` | **Status:** backlog | **Projects:** W,A,K
As a knowledge administrator, I want competing assertions visible, so that ranking does not conceal a material conflict.
**Scope:** Nine authority levels, effective/current version/applicability, KnowledgeConflict with counterpart claims/locators and authorized disposition. Classification remains separate.
**Dependencies:** `3-2-authorized-retrieval`.
**Traceability:** FR-13,FR-14; C-4,C-7; AD-7,AD-8.
**UI reference:** X-10 provenance; X-11 authority/freshness/conflict tabs and counterpart cards; P-05/P-09 sources; C21,C35; SUP-5. S governance,R actual source.
**UI fidelity:** Strict source1:1 visual/interaction includes layout,position,size,spacing,font family/size/weight,color,radius,shadow,border,icons,image proportions,button-input states,responsiveness. Preserve hierarchy/source; identify B/R/S and conflicts; new X screens follow UX without invented pixel references.
**Acceptance Criteria:**
- **Given** law/company/project/product/approved-history/department/internal/allowed-external/LLM-general sources with conflicting numbers, **When** ranked/displayed, **Then** applicable higher authority is preferred but both accessible statements and exact versions remain in KnowledgeConflict; LLM general knowledge never becomes formal Evidence.
- **Given** stale source or unauthorized counterpart, **When** user views/resolves conflict, **Then** safe stale/forbidden state exposes no protected excerpt; only authorized reasoned disposition is saved and downstream dependent findings remain stale until revalidated.
**Evidence:** T-CONTRACT/T-SEC authority/applicability/current-ACL cases; T-QUALITY conflict fixtures; T-UX two-source navigation/history.
**L/R/P:** L deterministic source metadata with real stores; R authoritative enterprise ranking/validity policy and data; P performance13-4.

## Story 3.4: Build a section Evidence Pack and inspect its support
**ID:** `3-4-section-evidence` | **Status:** backlog | **Projects:** W,A,K
As an author, I want a section-specific evidence bundle, so that I know what supports the requested content.
**Scope:** QueryPlanner3–10 subqueries/section, confirmed context budget, exact paths, retrieval/dedup/rerank/authority/current-policy checks, Pack provenance and insufficient-support reasons; similar-document recommendations are authorized actual records.
**Dependencies:** `3-3-source-governance`, `2-6-outline-confirmation`.
**Traceability:** FR-14,FR-16,FR-18; NFR-9; C-3,C-4; AD-3,AD-7,AD-8.
**UI reference:** P-05 `[data-aipanel="evidence"]`, P-04 `.evidence-card`, X-15 similar documents/Pack request, X-10 viewer; C09,C21,C35; SUP-5,SUP-6. R Pack/source/action,S details.
**UI fidelity:** Inherit strict original visual/interaction1:1 for layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; register R/S and conflicts, X bodies use UX not nonexistent source pixels.
**Acceptance Criteria:**
- **Given** a confirmed section and authorized sources, **When** Pack builds, **Then**3–10 scoped subqueries and budgeted results record query/source/version/locator/text/scores/policy hashes; duplicates/version conflicts handled explicitly, references inspect actual passages, task stages persist.
- **Given** insufficient current support, budget exhaustion or revoked source between retrieve and commit, **When** final Pack is checked, **Then** missing support is explicit, sensitive material is removed/denied and Pack cannot falsely certify key facts; transaction does not remain open during retrieval.
**Evidence:** T-CONTRACT/T-TASK Pack/current-policy/failpoint tests; T-QUALITY corpus/ACL/pack-size/reranker manifest and structured timing events. Search/Pack numerical acceptance is owned only by13-4.
**L/R/P:** L actual task/search/store transport with declared planner/model doubles; R real retrieval/endpoint effectiveness and timings mandatory; P peak load13-4.

## Story 3.5: Bind checkable Claims and cite at the intended selection
**ID:** `3-5-claim-citation` | **Status:** backlog | **Projects:** W,A,K
As an author, I want precise Claim support and citation placement, so that a source link truly justifies the selected statement.
**Scope:** All source-defined Claim types, supports/conflicts/contextual bindings, supported/partially_supported/conflicting/unsupported/unknown states, real citation bookmark and source trace.
**Dependencies:** `3-4-section-evidence`, `2-3-version-conflicts`.
**Traceability:** FR-14,FR-15,FR-16,FR-22; NFR-1; C-2,C-4; AD-2,AD-7,AD-8.
**UI reference:** P-03 `#insertCite/.cite`, P-05, P-08 trace source cards/P-09 citation tab; C16,C21,C35; X-10; SUP-5. R selected citation/provenance.
**UI fidelity:** Strict source visual/interaction1:1 across layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button/input states/responsiveness. Preserve source hierarchy/file; B/R/S/conflicts explicit; supplementary viewer uses UX, no fictitious pixels.
**Acceptance Criteria:**
- **Given** numeric,percentage,performance,capacity,time,date,model,standard,regulation,capability,acceptance-threshold,customer/project-name and version Claims, **When** extracted/bound, **Then** condition/value/unit/version/location and zero-or-more Evidence links persist; unknown declared types retained, unsupported/conflicting critical Claims become located pending/findings.
- **Given** a real editor selection bookmark, **When** authorized current Evidence is inserted, **Then** citation lands exactly there and changes correct version; it never appends to first paragraph. Stale selection/base, revoked source or changed quoted support rejects/asks reselection preserving content.
- **Given** selected Claim/issue A then B, **When** trace opens, **Then** exact supporting passage/version follows selection; confidence decoration does not prove support, history snapshot does not grant access.
**Evidence:** T-AST/T-CONTRACT type/binding/roundtrip/selection tests; T-SEC revoked historic citation; T-QUALITY support labels and T-UX trace switching.
**L/R/P:** L full local Claim/citation pipeline and deterministic extraction cases; R actual model support precision/human adjudication13-1; real-user assessment13-3; P load later.
