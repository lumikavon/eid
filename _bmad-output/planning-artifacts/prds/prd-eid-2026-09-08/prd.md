---
title: Enterprise Intelligent Document Workbench
status: draft
created: 2026-09-08
updated: 2026-09-08
project: eid
stage: S1
workflow: bmad-agent-pm / bmad-prd
upstream_confirmation: .claude/bmad-interview.md
scope: All three phases; one repository; edw-web, edw-api, edw-worker
approval: Not independently approved
original_target_delivery: blocked_by_inherited_worktree_isolation
---

## 当前开发与验证边界（2026-09-21）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件的执行安排统一受[开发与验证规则](../../development-validation-policy.md)约束。下文涉及启动、部署、迁移、fixture、功能测试、浏览器实测、联调、性能和故障演练的条款保留为待执行验收要求，当前暂停执行并记录 `not-run`；其中静态检查与编译可按规则单独执行。历史证据按原日期保留，不代表本轮通过或继续运行的授权。


# PRD: Enterprise Intelligent Document Workbench

> **Draft-only handoff.** Full three-phase requirements are retained. This file is in the agent's permitted worktree, not the requested main-project output location. The tool refused main-project PRD writing because the coordinator accidentally launched this task with worktree isolation. No permission workaround is authorized. This draft is not an S1 success signal, implementation authorization, or final product acceptance.

## 0. Purpose, Authority, and Source Register

This PRD gives UX, architecture, and story owners a testable product contract for a private enterprise document workbench. It defines outcomes and boundaries; technical mechanisms already mandated by the inputs are constraints, not newly selected architecture. Original inputs remain unchanged. The direct S1 task instruction additionally requires strict prototype 1:1 fidelity; this requirement is not falsely attributed to the interview's shorter visual-baseline wording. The sole upstream confirmation record is **`.claude/bmad-interview.md`** (confirmed 2026-09-08); `AGENTS.md` carries the operational quality and authorization entry point, not another approval record.

The confirmed interview overrides older engineering decomposition, phase-scope ambiguity, prototype demonstration semantics, and environment assumptions. `S07` governs the technical stack. All other source requirements remain effective. Any new substantive source/prototype conflict must return to the interview owner rather than be silently resolved. Source section numbers below refer to the original files under `D:/Desktop/eid`, not the worktree's older root-level documents.

| Source ID | Explicit input | Product obligations carried into this PRD |
|---|---|---|
| S00 | `docs/README.md` | Product positioning, input index, trusted document lifecycle, technology baseline authority |
| S01 | `docs/01-软件技术规格说明书.md` | Full three-phase scope, roles, workflows, document types, AI/Evidence/Claim/Review/publication capabilities |
| S02 | `docs/02-系统架构与模块设计.md` | Module responsibilities, job and data boundaries, cross-project behavior |
| S03 | `docs/03-数据模型与API接口规范.md` | Domain entities, durable state, API/event contracts and consistency |
| S04 | `docs/04-LLM-RAG与文档生成编排规范.md` | Retrieval, generation, model routing, prompt governance, quality and recovery |
| S05 | `docs/05-安全权限审计与NFR规范.md` | Authorization, classification, audit, publication protection, operations and NFRs |
| S06 | `docs/06-测试验收与实施计划.md` | Functional, integration, security, AI, capacity, export, recovery and UAT acceptance |
| S07 | `docs/07-技术栈基线与工程规范.md` | Mandatory technology/engineering baseline; replacements require explicit change control |
| P | `docs/prototype/index.html` | Existing visual/interaction baseline and exact page correspondence, detailed in §8 |
| I | `.claude/bmad-interview.md` | Sole confirmed scope, three-engineering-project merge, supplement authority, local/real acceptance split |

Prototype baseline SHA-256: `C876D444167A999D820BFC27D99C59D091C7AC885E93BC89CDF3B65EA1B4198E`. This identifies the inspected source; it is not screenshot-based visual acceptance evidence.

No additional interview, market study, vendor selection, or invented stakeholder confirmation is used. The confirmed brief supplies the enterprise stakes and web form factor. Scope tables and traceability are retained by explicit request despite the generic PRD template's preference for lighter matrices.

## 1. Product Thesis and Success

Enterprise employees need formal documents that reuse approved organizational knowledge without losing source provenance, requirement coverage, or human accountability. A fluent AI draft is insufficient when readers cannot determine where a parameter came from, which template and project revision apply, what is unsupported, or who authorized publication.

The workbench therefore follows **template-driven structure → Evidence-grounded retrieval → section generation → Claim verification → multi-level Review → human approval → formal export → quality-gated knowledge return**. The existing enterprise knowledge base remains authoritative. AI assists planning and expression; it neither grants access nor signs off a document.

The product succeeds when employees can produce complete, evidence-traceable and reviewable technical/business documents in one controlled workflow, reuse approved output safely, and inspect every material AI change. Reduced repetition and author effort are business goals, but the inputs do not provide an approved percentage reduction; this PRD does not fabricate one.

### 1.1 Measurement contract

All values are **targets**, not observed results. Metrics carry dataset, model/template/rule versions, time window, eligible denominator and exclusions. A zero eligible denominator renders `not applicable`, never an invented 100%. Development examples and deterministic-double output are visibly identified.

| ID | Success target and measurement | Validates |
|---|---|---|
| SM-1 | All four Phase 1 types complete create → template → Evidence → sections → Review → approval → DOCX/PDF. Each type has recorded end-to-end evidence. | FR-7–FR-31 |
| SM-2 | Proposed initial Golden Set retrieval gate: Recall@10 ≥0.90; current-project formal material Top3 hit ≥95% for applicable queries; unauthorized retrieval count 0; obsolete-version precedence errors 0. Real environment required. | FR-12–FR-17, FR-34 |
| SM-3 | Proposed initial post-Review Unsupported Critical Claim Rate <2%; published documents have **0 severe unsupported critical Claims**. Numerator is critical Claims lacking valid supporting Evidence; denominator is critical Claims. | FR-15, FR-23–FR-29 |
| SM-4 | Proposed initial Citation Precision ≥95%, measured by sampled source-to-Claim support, not link existence. | FR-14–FR-16, FR-34 |
| SM-5 | Critical AI/knowledge/document/approval audit coverage 100%; severe permission leakage 0. | FR-4, FR-12, FR-29, FR-46; NFR-1–NFR-7 |
| SM-6 | UAT: product, technical, test, quality, project-manager and bidding participants each execute 3–5 complete tasks using real desensitized historical projects; record knowledge relevance, usefulness, Review noise/misses, Evidence clarity, editing effort and output quality. | FR-7–FR-43 |
| SM-C1 | Track serious factual corrections and unauthorized/unsupported output alongside speed and AI retention. More generated text or greater acceptance rate is not success if either worsens. No invented numeric target. | SM-1, SM-3 |
| SM-C2 | Track Reviewer false positives/false negatives, severity appropriateness, human edit distance and manual modification rate alongside quality scores. Never optimize a low issue count by skipping checks or suppressing failures. | SM-3, FR-23–FR-26, FR-33–FR-34 |

Sources: S01 §§2,16–19; S06 §§4–6,11–12; I confirmed decisions. Retrieval/AI targets described as recommendations in S06 retain that qualification until evaluation configuration is frozen; publication safety requirements are not recommendations.

## 2. Users, Jobs, and Source-Grounded Journeys

Primary users are authors and authorized project members; technical experts and quality personnel inspect correctness; template and knowledge administrators govern reusable inputs; approvers authorize publication; system administrators operate identity, models, prompts and audit. Administration does not automatically confer access to all knowledge. Product, testing, project-management and bidding participants use their corresponding document flows. Form access is determined by enterprise role policy, not by an invented new role.

The journeys below organize source-described workflows. Role labels are deliberately used instead of fabricated named customer personas; these are not newly conducted user interviews.

- **UJ-1 — Author produces a technical document.** An authenticated, authorized project member selects project/type/template, supplies context and attachments, reviews the proposed outline, requests section generation, inspects Evidence and unsupported Claims, accepts/rejects AI Patches, resolves issues and submits for approval. Successful resolution is an approved/published immutable version with formal output; missing inputs produce visible blocking items rather than fabricated facts. Realized by FR-1–FR-31.
- **UJ-2 — Expert and approver protect a release.** A technical/quality reviewer opens a version-specific issue queue, inspects the issue's actual Claim/source, proposes or applies an authorized change and rechecks it. An approver receives an explicit request after submission prerequisites pass and records an authorized decision; publication follows that decision and the remaining publication gates. Stale versions, revoked references and severe findings cannot be hidden by clicking “handled.” Realized by FR-23–FR-31.
- **UJ-3 — Template/knowledge administrators improve reuse.** Template administrators govern scoped template versions; knowledge administrators govern source scope, trust, conflicts and freshness. Eligible Published content returns through the configured Knowledge Quality Gate; these roles are not automatically granted authority to approve that gate. Draft AI output never silently enters trusted knowledge. Realized by FR-7–FR-17, FR-31, FR-33–FR-34.
- **UJ-4 — Bidding participant proves compliance.** From a tender attachment, the participant reviews extracted qualifications, commercial/technical requirements, disqualification and scoring items, then links responses and Evidence in a bidirectional compliance matrix. Unanswered mandatory requirements, residual customer names and conflicting parameters are visible before submission. Realized by FR-35–FR-38.
- **UJ-5 — Authorized form user creates and executes controlled records.** The user designs or selects a versioned Form Schema, reviews AI-suggested schema changes, validates entered data, saves a versioned instance, prints/scans and exports it, and monitors authorized MES/project-system delivery. Failed integration remains retryable and visible, not falsely delivered. Realized by FR-39–FR-43.

Sources: S01 §§4,6,8–13,15–16; S06 §11; I. The PRD does not replace detailed UX tasks with these summary journeys.

## 3. Glossary and Invariants

| Term | Definition / invariant |
|---|---|
| Project / Workspace | Authorized enterprise context for documents, members and retrieval scope; not a separate software engineering project. |
| Engineering project | One of exactly `edw-web`, `edw-api`, `edw-worker` in one repository. |
| Document AST | Versioned domain document representation, separate from the editor's JSON; supports metadata, sections, headings, paragraphs, requirements, tables, figures, diagrams, citations, warnings, code blocks and forms. |
| Document Version | Immutable snapshot of AST and provenance used by Patch, Review, approval and export; concurrent changes require explicit conflict handling. |
| Template Version | Versioned structure, chapter/retrieval/Prompt/Reviewer rules, rendering style and approval policy; formal documents pin template ID and version. |
| Evidence | Authorized source excerpt with source/version/section/chunk, authority, scores, access snapshot and validity metadata. A historical access snapshot is not current authorization. |
| Evidence Pack | Section/job-scoped retrieved Evidence used for generation and verification. |
| Claim | Checkable assertion, including performance, quantity, date, version, model, requirement, standard, customer, project or compliance; linked to zero or more Evidence records. |
| KnowledgeConflict | Conflicting source statements requiring surfaced authority/version/context comparison and human disposition, not silent averaging. |
| Patch / AI Diff | Proposed AI edit against a base Document Version; accepting applies an authorized change and produces a new version; rejection leaves content unchanged. |
| Review / ReviewIssue | Version-specific checking result and actionable issue with severity, kind, location, Claim, suggestion and disposition. |
| Pending Item | Missing information or confirmation needing human resolution or a recorded permitted exception before publication. |
| Approval | Authorized human decision over a pinned version; distinct from ReviewIssue handling. |
| Published / Archived | Formal lifecycle states; neither a download click nor model completion implies publication. |
| Golden Knowledge | Approved, quality-gated trusted knowledge derived only from eligible formal content. |
| Golden Evaluation Set | Versioned queries/documents/adjudications for repeatable retrieval, generation and Reviewer evaluation; not proof by itself of model quality. |
| Form Schema / Form Instance | Versioned field/validation/layout contract and versioned data record; not merely a document table. |
| Task / Task Event | Durable asynchronous job and ordered progress history; broker/cache state alone is not authoritative. |
| Local Contract Acceptance | Tests against isolated local infrastructure, fixed fixtures and deterministic model/enterprise substitutes. Does not imply real enterprise or AI efficacy acceptance. |

## 4. Complete Three-Phase Scope and Engineering Coverage

All phases are part of this planning/implementation program, delivered in dependency order. Phase 1 is a foundational milestone, not the end of the authorized scope. Phase 2 and Phase 3 cannot be placeholders. POC/initial four-document validation does not replace later capabilities.

| Phase | edw-web | edw-api | edw-worker | Cross-project acceptance / traceability |
|---|---|---|---|---|
| **1 — Core platform** | Workspace, four document types (technical solution, PRD, test plan, technical requirements), editor, outline, template center, Copilot, Evidence, pending items, AI Diff/versioning, Review, approval and export UI | Project/access policy, domain AST, templates/versions, Evidence/Claim records, Patch/optimistic concurrency, Review/approval/publication, durable tasks, audit | Attachment parse/OCR, retrieval/rerank, planning/generation, Claim/Reviewer execution, safe diagram/render, DOCX/PDF, eligible knowledge return | FR-1–FR-31 and FR-44–FR-48; C-1–C-8; source S01 §3.1, S06 phase 1 |
| **2 — Quality and project extension** | Quality outline, project plan, functional/performance test outline and project summary workflows; real score/coverage/rules/evaluation views | Type-specific template/validation support, quality score and coverage definitions, Reviewer-rule versions, evaluation datasets/results/access | Type-specific generation/Review and reproducible evaluation runs with versioned artifacts | FR-32–FR-34 plus core FRs; C-1–C-8; S01 §3.2, S06 phase 2 |
| **3 — Specialist workbenches** | Tender parsing/qualification/scoring/compliance views; Form Builder, instance entry/validation/print/scan, integration job state | Tender requirements and bidirectional compliance model; versioned Form Schema/instances, formulas/validation permissions, integration mappings/outbox/inbox | Tender parsing and checks, AI form schema proposal, multi-format form render, scanning-related processing, MES/project and archival integration execution | FR-35–FR-43 plus core FRs; C-1–C-8; S01 §3.3/§13, S06 phase 3 |

**Engineering boundaries.** `edw-web` is one unified frontend. `edw-api` is a modular business monolith and durable business authority. `edw-worker` combines generation, retrieval/Review, parse/OCR, rendering and enterprise integration execution. Knowledge Gateway and LLM Gateway are shared internal modules, not additional services/projects. Deployment, migrations, contracts, tests and evaluations are repository directories. PostgreSQL, Redis, RabbitMQ, object storage, model endpoints and identity are infrastructure/dependencies, not additional business engineering projects. Categorized queues and separate safe worker processes/images remain mandatory despite the repository simplification.

**Explicit non-goals.** No autonomous unapproved AI publication; no arbitrary LLM enterprise-system access; no draft-to-Golden-Knowledge shortcut; no replacement for OA, formal e-signature or archive products; no unbounded autonomous multi-agent operation; no extra mobile or real-time collaboration platform. Signature form fields do not constitute certified electronic signing. No production deployment, push, paid API use, external messages or existing-enterprise-database mutation is authorized by this PRD.

## 5. Functional Requirements

Each FR has a stable global ID, owning engineering projects, phase and source references. `W` = edw-web; `A` = edw-api; `K` = edw-worker. A phase label identifies introduction; requirements remain applicable in subsequent phases. Each numbered FR is a capability, not one giant implementation story. Downstream stories must preserve its stated failure conditions and source/prototype links.

### 5.1 Workspace, access and document operations

| ID | Capability and testable consequences | Owners / phase / sources |
|---|---|---|
| **FR-1** | Authorized users can list/select project workspaces and create a document with name, type, template version and permitted knowledge scope. Persist the chosen type/scope; show the created document's own AST and identifier, not the prototype's previously open content. Reject inaccessible projects/templates/scopes. | W,A; 1; S01 §§4–7; P home/modal; I |
| **FR-2** | Provide recent/created/participating/favorite document views, project/document status and actionable tasks using authorized real records. Filtering and navigation must affect matching records. Empty, loading, failed and forbidden states must not masquerade as example rows. Counts and storage usage must reflect the same eligible data. | W,A; 1; S01 §§5–7; P home/sidebar; I |
| **FR-3** | Global search, document lookup, source references and project navigation return permission-filtered results; opening a record navigates to that record and preserves its context. Inert prototype entry points become genuine functions or explicit unavailable states, not success toasts. Favorites/reference/recycle-bin controls must enforce lifecycle/access rules rather than physically erase governed history. | W,A; 1; P shell/home; S01 §§5,7,16; I |
| **FR-4** | Map authenticated enterprise identity and roles into each business request and task. Authors, project members, experts, quality staff, template/knowledge administrators, approvers and system administrators receive only policy-granted operations. Local OIDC/enterprise doubles test allow/deny paths; real SSO verification remains environment-pending. | W,A,K; 1; S01 §§4,16; S05; I |
| **FR-5** | Persist and edit a versioned domain AST independent of editor JSON. Support source-defined node kinds and stable section/Claim/Evidence relationships; invalid AST is rejected without corrupting the prior version. The editor's visible structure and document tree reflect the saved AST. | W,A; 1; S01 §§7,14.1; S03; P editor |
| **FR-6** | Autosave, explicit save, undo/redo and supported formatting/insert operations change the intended selection/section and report actual persistence. Version history records changes. Concurrent edits use version checks/optimistic locking; stale writes fail visibly and offer conflict handling without silently overwriting. No added real-time collaboration service is implied. | W,A; 1; S01 §§7,11; S03; P editor; I |

### 5.2 Templates and type-specific composition

| ID | Capability and testable consequences | Owners / phase / sources |
|---|---|---|
| **FR-7** | Browse company, department, product-line, project and personal-draft templates with permission-scoped search/category/type filters. Filters combine consistently. Preview/detail/usage selects the actual template and displays its own metadata/outline. Applying a template creates a record with that template's structure and pinned version. | W,A; 1; S01 §8; P templates |
| **FR-8** | Authorized administrators upload, validate, version and govern templates, including structure, chapter rules, retrieval/Prompt/Reviewer rules, rendering and approval policy. Invalid/inaccessible versions cannot be used for formal release. Changes do not retroactively mutate documents pinned to older versions. A template version referenced by a formal document cannot be physically deleted; deprecation preserves historical references. | W,A,K; 1; S01 §8; S02 §2.3; S03; S07 |
| **FR-9** | Technical-solution composition prioritizes current project material and formal company standards, includes mandatory chapters and traceable architectural/technical claims, and checks parameter consistency across the entire document. Unsupported parameters are pending/Review items, not invented replacements. | W,A,K; 1; S01 §§3.1,6,9,12; S06 §3.1 |
| **FR-10** | PRD composition supports FR-ID, name, role, scenario, prerequisites, normal/exception flows, rules, inputs/outputs, permissions, NFR and acceptance criteria. Missing required fields are identified and remain traceable to sections/requirements. | W,A,K; 1; S01 §13.2; S06 §3.2 |
| **FR-11** | Test-plan composition maintains Requirement ↔ Test Item ↔ Test Case ↔ Acceptance Criteria traceability and reports coverage from links; missing/redundant coverage is visible. Technical-requirements composition flags vague adjectives and proposes condition + metric + threshold + verification-method statements. AI must not change approved acceptance thresholds. | W,A,K; 1; S01 §§13.3–13.4; S06 §3 |

### 5.3 Knowledge, attachments and evidence

| ID | Capability and testable consequences | Owners / phase / sources |
|---|---|---|
| **FR-12** | Search the existing authoritative enterprise knowledge base with user ACL, domain, project/customer/product context, version validity and classification filters before Evidence enters the model context. A query cannot broaden the user's privileges; unauthorized content is neither returned nor logged as visible output. | A,K,W; 1; S01 §9; S04; S05 |
| **FR-13** | Rank and expose source authority: mandatory law/standards; formal company policy/standards; current formal project material; current formal product material; approved historical projects; department knowledge; ordinary internal documents; allowed external material; LLM general knowledge. Conflicts generate KnowledgeConflict with the competing statements; higher authority is preferred but conflict is not hidden. | A,K,W; 1; S01 §9; S04 |
| **FR-14** | Store Evidence source document/version/section/chunk, quoted text, knowledge level, retrieval/rerank scores, access snapshot and validity. The citation/trace view opens the actual authorized supporting passage for the current selected Claim/issue, not a fixed prototype source. Recheck permission/freshness when cited, viewed or exported. | A,K,W; 1; S01 §§9–10; S03; S05; P evidence/review |
| **FR-15** | Extract checkable Claims of all source-defined types and bind zero or more Evidence records. Lack of support, contradictory support or invalid authority for critical Claims produces an actionable issue/pending item; unbound critical values cannot be presented as verified. | A,K,W; 1; S01 §10; S04; S06 §5 |
| **FR-16** | Build section-specific Evidence Packs with deduplication, relevance/authority/context/version handling and verifiable citations. Show retrieved excerpts and reasons for insufficient support; preserve provenance through accepted edits and version history. Do not treat model general knowledge as formal enterprise evidence. | A,K,W; 1; S01 §§9–11; S04 |
| **FR-17** | Upload attachments through validated, access-controlled storage; parse/OCR/index them via isolated jobs and expose parse failure/partial results. Attachment retrieval is a separate path from the existing enterprise knowledge base; no forced enterprise re-embedding/rebuild. Repeated jobs are idempotent and retain source/parse metadata. | W,A,K; 1; S02–S04; S07 |

### 5.4 Controlled generation and AI edits

| ID | Capability and testable consequences | Owners / phase / sources |
|---|---|---|
| **FR-18** | Build context from project/template/attachments and recommend relevant excellent prior documents within authorization. Produce an outline proposal, show missing information, and require author confirmation before section generation. Display actual outline state; do not claim loaded knowledge on modal dismissal alone. | W,A,K; 1; S01 §6.1; S04; P modal/editor |
| **FR-19** | Generate via controlled section tasks using template rules and Evidence Packs; persist stage progress, output, errors and retryability. Full-document assembly performs cross-section checks, not one opaque free-form response. Missing inputs create `BLOCKED_BY_MISSING_INFO`. | W,A,K; 1; S01 §§6,14.1; S04 |
| **FR-20** | Copilot supports chapter generation, continuation, rewrite, expansion/contraction, professional/technical rewriting, technical requirements, requirement-to-test conversion, tables, Mermaid/PlantUML requests, knowledge query, similar solution retrieval, factual/omission/conflict checks, summary and pending-item creation. Context includes intended selection/section; read-only queries must not mutate the document. | W,A,K; 1; S01 §11; S04; P copilot |
| **FR-21** | Every AI write creates a reviewable Patch/AI Diff against a known Document Version and references `generation_run_id`; accepted versions retain GenerationRun/Evidence Pack, Prompt/model version, input/output hashes and token-usage provenance. Accept validates authorization/base version, applies only the selected patch and creates a version; Reject changes no content. Stale patches show conflict; failures never silently overwrite. | W,A,K; 1; S01 §11; S03; I approved AI Diff supplement |
| **FR-22** | Missing facts/pending confirmations carry location, reason, proposed resolution and status. User actions close or document permitted exceptions with identity/history; counts reflect actual items. Diagram/table proposals are validated and safely rendered; arbitrary generated code is never executed. | W,A,K; 1; S01 §§7,11,14; S04–S05; P todo |

### 5.5 Review, approval, publishing and reuse

| ID | Capability and testable consequences | Owners / phase / sources |
|---|---|---|
| **FR-23** | Run structure, fact, requirement, technical, quality, consistency, style and safety Reviewers over a pinned document version. Store reviewer/rule/model versions, issues, locations, suggestions and actual task status. A rerun starts a genuine asynchronous task; “completed” is shown only after persisted completion. | W,A,K; 1; S01 §12; S04; P review |
| **FR-24** | Review management supports display, filtering and search by severity, section, status and keyword; selection updates issue ID, severity, location, quote, impact, suggestion and evidence for that issue. Counts, scores and coverage derive from version-specific data. Version comparison and history show real records. | W,A; 1; S01 §§7,12; P review; I |
| **FR-25** | Accept, reject, modify and mark-handled have distinct, authorized, auditable outcomes. Accept applies the intended permitted Patch; Modify opens a real edit; rejection records rationale/state. Mark-handled cannot resolve a severe issue without a checked resolution or authorized exception consistent with publication gates; an old Review does not certify a new version. | W,A,K; 1; S01 §§11–12,16; S03–S05; P review |
| **FR-26** | Detect numeric/parameter contradictions, customer/project name remnants, obsolete citations, missing chapters/requirements, ambiguous thresholds, inconsistent terms and unsupported critical facts. Seeded issues in each category must be locatable in regression tests; detection quality with real models is separately evaluated. | A,K,W; 1; S01 §§12–13; S06 §6 |
| **FR-27** | Authors submit a version for human approval according to pinned template policy; approvers view content, Review/pending state and provenance and record authorized decisions/history. Rejection returns a visible actionable state. Editing an approved candidate requires version-aware revalidation rather than inheriting approval invisibly. | W,A; 1; S01 §§8,16; S03; I approval supplement |
| **FR-28** | Track normal lifecycle `DRAFT → CONTEXT_READY → OUTLINE_READY → GENERATING → REVIEWING → USER_REVIEW → APPROVAL_PENDING → PUBLISHED → ARCHIVED`, plus generation/Review/export failures and missing-info blocks. Gate transitions on persisted prerequisites and permissions; task failures and business state remain distinguishable. | W,A,K; 1; S01 §7; S03–S04 |
| **FR-29** | Publication requires mandatory chapters complete, severe ReviewIssues 0, pending items closed or approved exceptions, configured critical-Evidence coverage satisfied, no known unresolved knowledge conflicts/unauthorized references/sensitive violations, valid template, human confirmation and completed approval. Severe unsupported critical Claims must be 0. Audit inability or missing policy configuration must not fail open. | W,A,K; 1; S01 §16; S05; S06 §12 |
| **FR-30** | Export the permitted pinned version through safe asynchronous rendering. Phase 1 DOCX/PDF include configured cover, identifier/classification, headers/footers, TOC, heading/figure/table numbering, fonts, approval page, version record and citation appendix; errors remain visible/retryable. HTML/Markdown and form multi-format outputs remain in overall scope. Downloads/shares enforce current authorization; fake toast success is prohibited. | W,A,K; 1; S01 §§14–15; S06 §9; P editor/review |
| **FR-31** | Only eligible approved/published formal content may pass Knowledge Quality Gate; execute the defined Published-triggered return path, parse/chunk/enrich metadata and retain provenance/approval. Draft, AI draft and unapproved versions are ineligible. Duplicate/retried return cannot create uncontrolled duplicate trusted entries. | A,K,W; 1; S01 §§2,6.3,15; S04 |

### 5.6 Phase 2 quality and project extension

| ID | Capability and testable consequences | Owners / phase / sources |
|---|---|---|
| **FR-32** | Provide genuine templates and complete create/generate/Evidence/Review/approval/export flows for quality outlines, project plans, functional/performance test outlines and project summary reports. Type-specific mandatory structure and rules come from versioned approved templates; absent official templates are labeled development examples, not invented formal standards. | W,A,K; 2; S01 §3.2; S06 phase 2; I |
| **FR-33** | Provide Document Quality Score, Requirement Coverage and Reviewer Rule Center with versioned definitions/rules, authorized management, drill-down and actual denominators. Preserve Phase 1 requirement-to-test links and coverage; Phase 2 adds governance, not a deferral of Phase 1 obligations. Missing rule/data is explicit, not a fabricated score. | W,A,K; 2; S01 §3.2/§13.3; S06 §§4–6; I |
| **FR-34** | Manage Golden Evaluation Sets and repeatable retrieval/generation/Reviewer evaluations; preserve dataset, model, Prompt, retrieval/reranker, template and rule versions with results. Provide per-domain 50–200 Golden Queries and injected defect cases. Distinguish deterministic substitute tests from real endpoint runs; do not report real quality until measured. | W,A,K; 2 governance, 1 baseline tests; S01 §3.2; S04; S06 §§4–6; I |

### 5.7 Phase 3 bid workbench

| ID | Capability and testable consequences | Owners / phase / sources |
|---|---|---|
| **FR-35** | Parse tender documents into source-located qualification, commercial and technical requirements; let authorized users inspect/correct extracted items while retaining provenance/version. Failed/partial parsing must not appear as a complete tender analysis. | W,A,K; 3; S01 §§3.3,13.1; S06 phase 3 |
| **FR-36** | Identify and inspect disqualification and scoring items, link checks to tender clauses and response evidence, and expose unresolved mandatory risks. Scores/check results derive from actual requirements and versioned rules, never prototype numbers or unsupported model claims. | W,A,K; 3; S01 §13.1; I |
| **FR-37** | Maintain a Requirement Compliance Matrix with bidirectional links between tender requirement and response location/Evidence. Show missing, partial and conflicting responses; following either direction reaches the source/version and response. Exports retain the matrix's current version context. | W,A,K; 3; S01 §13.1; S03 |
| **FR-38** | Check bids for residual customer/project names and contradictory parameters across responses and authoritative project material. Findings enter the same Review/approval/publication gates; the bid workbench does not bypass platform policy. | W,A,K; 3; S01 §13.1; S06 §6 |

### 5.8 Phase 3 production forms and enterprise delivery

| ID | Capability and testable consequences | Owners / phase / sources |
|---|---|---|
| **FR-39** | Author/version independent Form Schemas with text, number, date, select, checkbox, signature, image, barcode/QR, formula and repeating table fields. AI Form Builder proposes schema changes for human review; it cannot silently replace active schemas or interpret arbitrary executable code. | W,A,K; 3; S01 §13.5; S03; I |
| **FR-40** | Render Web data-entry from Form Schema; validate type/required/range/declared rules on both frontend and backend; version instances with schema references and access control. Invalid input fails consistently without losing the prior valid saved record. Formula evaluation is a whitelist interpreter. | W,A; 3; S01 §13.5; S03; S05 |
| **FR-41** | Render the same Form Schema and instance to Web, DOCX, PDF, XLSX and print versions with consistent fields/values; support declared print/scan barcode/QR use and attachments/signature fields. Show actual export/scan state and validation failures. Signature fields do not replace enterprise e-signature products. | W,A,K; 3; S01 §§13.5,15; S06 phase 3 |
| **FR-42** | Provide configurable identity/knowledge/MES/project/archive connectors and local contract adapters. Persist outbound/inbound correlation, status and idempotency; expose authorized retry/failure inspection. Only declared contracts are supported; unknown real vendors and endpoints remain pending, not “integrated.” | W,A,K; 1 identity/knowledge, 3 specialist integrations; S02–S03; S07; I |
| **FR-43** | Deliver approved document/form/return artifacts through controlled enterprise integration tasks. Outbox/inbox and duplicate detection ensure repeat delivery or restart cannot double-apply a business action. Partial delivery is visible and reconcilable; sensitive payloads obey classification and audit policies. | A,K,W; 3; S02–S05; S06 §2.2; I |

### 5.9 Cross-cutting task and operational product behavior

| ID | Capability and testable consequences | Owners / phase / sources |
|---|---|---|
| **FR-44** | Expose durable, categorized generation/retrieval/review/parse_ocr/render/integration tasks with authorized progress, errors, retry/cancellation when supported and final artifacts. PostgreSQL-persisted task state exposed by the API is authoritative; reconnecting clients rebuild state from persisted data rather than treating a missed toast as loss of work. | W,A,K; all; S02–S04; S07 |
| **FR-45** | Recover long-running work after worker, broker or cache interruption using persisted task/step state and controlled retry/compensation. Isolate failure categories; duplicate deliveries have no uncontrolled duplicate effects. Failed/dead-letter work is inspectable rather than indefinitely “running.” | A,K,W; all; S02–S04; S06 §10 |
| **FR-46** | Audit critical knowledge queries, Evidence use, model/Prompt operations, AST/Patch/version changes, approvals/publication, exports and integration actions with actor, resource/version, outcome and correlation. Authorized administrators can inspect history without exposing secrets or unauthorized content. | A,K,W; all; S05; S06 §§7,10 |
| **FR-47** | Provide real task/data-backed notifications, dashboard/analytics aggregates and administrative states for modeled functions. Security-sensitive states never rely only on a colored badge. When environment-dependent execution is unavailable, display `not configured`/pending with reason, not sample production outcomes. | W,A,K; all; P shell/home/analysis; S01 §§5,17; I |
| **FR-48** | Supply local runnable three-project configuration, contracts, isolated migrations, fixtures, critical tests/evaluation scaffolding and production deployment configuration without executing production deployment. Document environment prerequisites and local/real acceptance separately. Any database execution must first verify host, database name and project isolation and stop if unprovable; no database deletion or existing-data cleanup is included. | W,A,K; all; S06 §§10,14–15; S07; I |

## 6. Cross-Project Contracts

The following are externally observable requirements across the three engineering projects, not new services or an implementation architecture. Detailed wire/schema definitions continue to come from S03/S07 and must be pinned by downstream contracts; a UI implementation must not invent incompatible shapes.

| Contract | Producers → consumers | Required consistency / failure behavior | FR coverage |
|---|---|---|---|
| **C-1 Identity and request context** | Identity adapter → W/A; A → K and internal Gateways | Preserve authenticated actor/project/ACL/classification/trace context; deny unknown/invalid authorization; no privilege increase in background work or source viewing. | FR-1–FR-4, FR-12, FR-14, FR-42, FR-46 |
| **C-2 Document/version/Patch** | W ↔ A; K proposes outputs to A | Domain AST and template IDs/versions remain stable; base-version/optimistic checks gate modifications; worker results do not overwrite content directly; approvals/reviews/exports refer to the correct version. | FR-5–FR-11, FR-18–FR-31 |
| **C-3 Durable task/event channel** | A → durable state/outbox/queue → K; K → A state/events → W SSE | Persist task identity, category, step, status, progress, errors, correlation, ordering and final outputs. Reconnect/replay reconciles duplicates/gaps; retries are idempotent. SSE delivery is not durable job state. | FR-19, FR-23, FR-28, FR-30, FR-44–FR-45 |
| **C-4 Knowledge/Evidence/Claim** | Enterprise/attachment adapters ↔ internal Knowledge module/K ↔ A ↔ W | Versioned, authorized Evidence and source pointers; current ACL/freshness recheck; Claim binding and conflicts survive generation/edit/review/export; no raw unauthorized passages leak to UI/model. | FR-12–FR-17, FR-22–FR-26, FR-31 |
| **C-5 Model and Prompt** | A/K ↔ internal LLM Gateway ↔ configured providers/doubles | Policy controls data routing; inputs/outputs have validated contracts, provider/model/Prompt versions, timeout/error state and usage audit. Local deterministic responses are labeled test-double data, not efficacy evidence. | FR-18–FR-26, FR-34, FR-39 |
| **C-6 Artifacts and rendering** | W upload → A/object storage → K; K artifact → A → authorized W download | File identity/version, media validation and storage permissions persist; sandboxed rendering/OCR; output status/checksum/provenance distinguish failed/partial/complete; current access rechecked on download. | FR-17, FR-30–FR-31, FR-35, FR-41 |
| **C-7 Review/quality/publication** | K findings → A policy/version store → W reviewers/approvers | Version-specific findings, distinct human dispositions, actual score denominators, fail-closed release gates and complete approval/audit trail; client status alone cannot publish. | FR-23–FR-34, FR-36–FR-38 |
| **C-8 Forms and enterprise integration** | W schema/instances ↔ A; A outbox → K adapter → enterprise; enterprise inbox → A | Schema/instance versions, validation parity, mapping/correlation/idempotency and authorized retry; replay has no duplicate side effects; stub contract passing stays separate from real integration evidence. | FR-39–FR-43 |

Contract tests declare applicable successful and negative cases in a versioned applicability matrix; a Story tests the cases it introduces **or can affect**. A change that touches authorization, replay, idempotency, messages, persistence or external effects must include the corresponding security/data-integrity cases. All three projects participate in one complete locally demonstrable chain; specialist Phase 3 contracts receive their own E2E flows rather than relying only on the technical-solution happy path.

### 6.1 Source-pinned protocol invariants

- REST uses `/api/v1`, Pydantic/OpenAPI contracts and versioning for breaking changes. Source-defined surfaces include documents, plans, section generations, patches (`:accept`/`:reject`), knowledge search/Evidence Packs, Reviews/issues (`:resolve`), templates/versions (`:publish`/`:deprecate`) and exports. Export requests identify `version_id`, `format` and `render_theme`. Plan creation explicitly returns `202 Accepted` with `task_id`; long operations return task identity instead of pretending synchronous completion. Detailed approval/bid/form interfaces require subsequent contract design, not invented PRD endpoints. [S03 §§8–12; S07 §5]
- Optimistic editing uses `base_version_id + document_revision`; stale changes return `DOC_VERSION_CONFLICT`. Preserve explicit contract errors `TEMPLATE_DEPRECATED`, `KNOWLEDGE_PERMISSION_DENIED`, `EVIDENCE_REQUIRED`, `EVIDENCE_STALE`, `MODEL_NOT_ALLOWED`, `REVIEW_GATE_FAILED`, `MISSING_CONFIRMATION`, `EXPORT_FAILED`. Status-to-HTTP mapping is a downstream contract decision. Published versions are never modified in place. [S03 §§16–17]
- Task SSE uses `GET /api/v1/tasks/{task_id}/events`, monotonically increasing ID/cursor and `Last-Event-ID` recovery; retain replay through the task lifecycle or reconstruct from durable state. SSE carries status/small summaries; large results use REST/object storage. Domain-event envelopes retain `event_id/event_type/occurred_at/tenant_id/actor_id/data`; SSE `id/event/data` framing is distinct and need not duplicate every domain-envelope field. The presence of `tenant_id` alone does not authorize a new multi-tenant SaaS product. [S03 §§13–14]
- Business changes and Outbox commit atomically; Inbox deduplicates by event ID/consumer. Tasks have idempotency keys, bounded retry policy and timeout; rolling upgrades support the previous/next adjacent message-version compatibility requirement. No database transaction remains open across slow LLM/RAG calls. API/worker connections are independently limited. [S02 §5; S03 §§13,15,17; S07 §3]
- Document lifecycle (§5 FR-28), orchestration state (`CREATED`, context preparation/planning, generation/Review, `USER_REVIEW`, `COMPLETED`) and section-task state (`PENDING`, `RETRIEVING`, `EVIDENCE_READY`, `GENERATING`, `VALIDATING`, `DONE`, with retry/failed/blocked/cancelled paths) are different entities. Task `COMPLETED` never grants `PUBLISHED`. [S01 §7; S02 §2.4]
- Claim states are `supported`, `partially_supported`, `conflicting`, `unsupported`, `unknown`; bindings distinguish supports/conflicts/contextual. Issue states are `open`, `accepted`, `rejected`, `fixed`, `waived`, `closed`; an approved waiver records authorizer and reason and cannot contradict a non-waivable publication gate. Evidence stores permission-policy identity/snapshot hash, not a permanent “has access” boolean. [S03 §§4–6; S04 §§10–12]
- Source-governed context includes workspace, intent, template, project fact table, glossary, reference documents, constraints and missing information. Section outputs expose content AST, Claims, citations, assumptions and missing information. Query Planner creates 3–10 subqueries per section; exact standard/model/project/contract IDs, customer names, IP/ports, versions and metrics need exact/keyword paths, not vector-only retrieval. Initial recall counts and quality weights in S04 are tuning recommendations, not invented hard acceptance gates. [S02 §4.1; S04 §§3–9,18]
- Generation accepts an Evidence Pack rather than directly querying a vector store. A structured-output parse failure permits one repair attempt; persistent failure preserves context and becomes failed. Transient LLM failures use exponential backoff; terminal failures retain context. Provider fallback never weakens classification. Prompt/Model Profile, AST/Form Schema and database schemas are independently versioned. [S02 §§2.5,7.1; S03 §7; S04 §15; S07 §5]

## 7. Non-Functional Requirements and Guardrails

Every NFR is traceable and must be carried into acceptance evidence. Performance targets retain the source's strict `<` rather than being relaxed to `≤`. Environmental measurement parameters must be frozen in the test manifest before claiming a result; unspecified limits are not fabricated below.

| ID | Requirement and verifiable boundary | Owners / sources / validation |
|---|---|---|
| **NFR-1** | Authorization is RBAC operation permission **AND** ABAC object scope **AND** object classification ≤ user clearance. Scope includes department, project/workspace, customer, product, ownership, approval state and validity. Access is checked before retrieval and after retrieval, and on Evidence viewing/publication/export. | W,A,K; S05 §§2–4; deny-matrix, revoked-user/reference and cross-project tests; FR-4,FR-12,FR-14 |
| **NFR-2** | SPA uses OIDC Authorization Code + PKCE and short-lived tokens; API validates tokens and creates Auth Context. Background work uses service identity/client credentials, not shared human credentials. Edge proxy never substitutes for business authorization. | W,A,K; S05 §2; local OIDC contract tests, real SSO pending |
| **NFR-3** | L0 external routing only by policy; L1 only with policy and desensitization; L2 internal by default/priority, with any external exception unresolved until enterprise policy supplies it; L3 external routing prohibited and restricted to controlled internal environments. Classify → DLP → Policy → Redact → Router; denial never falls back to a more permissive provider. | A,K; S04 §16; S05 §§5–6; model-routing negative tests; OQ-1 |
| **NFR-4** | Retrieved excerpts, attachments and tender content are untrusted data, not system instructions. Explicit user instructions operate only within system policy and authorization and cannot grant privileges. Detect/contain injection, separate instruction/data context and whitelist tools. Model output cannot modify authorization or execute arbitrary shell/scripts. DLP covers secrets/tokens/keys/passwords, personal/customer identifiers, IP/MAC/internal domains, project/device IDs and protected technical data. | W,A,K; S04 §§13–17; S05 §§6–7; injection/DLP/escaping fixtures |
| **NFR-5** | Audit 100% of critical identity, knowledge/Evidence, AI/Patch, Review/Waive, template/Prompt/model policy, approval, export/publication and trusted-return actions; record actor, action, resource/version, workspace, result, trace and timestamp in tamper-resistant storage. Audit unavailable → fail closed for publication, permission and approval critical writes. | A,K,W; S05 §§8–10; audit interruption tests; FR-29,FR-46 |
| **NFR-6** | TLS and enterprise-required at-rest/backup encryption; governed secret management; no secrets or unredacted sensitive body/Prompt in ordinary logs. Govern Prompt retention through policy, preferably metadata/variable summaries/hashes; restricted raw records require explicit encrypted storage policy. Export classification/watermark and separate retention/TTL policies apply. No invented retention days. | A,K; S05 §§9,11,15; secret/log/export checks; ENV-4 |
| **NFR-7** | OCR, document conversion and diagram rendering have non-root execution, network/resource/time limits, temporary-storage quotas, seccomp and read-only filesystem where feasible. Mermaid syntax/node/text/dangerous-option validation precedes isolated, network-disabled rendering. File type/content validation and storage access control apply to uploads/outputs. Resource values require workload/security configuration. | A,K; S04 §17; S05 §14; malicious file/timeout/sandbox tests |
| **NFR-8** | UI key operations P95 <1 s; home/list API P95 <1 s; AST retrieval P95 <1 s; autosave P95 <1 s. Measure client and server boundaries separately against frozen hardware/data/network workload. | W,A; S01 §17; S05 §10.1; Playwright/k6 |
| **NFR-9** | Knowledge search P95 <3 s; typical Evidence Pack P95 <8 s. Record query mix, corpus size/ACL/filter/reranker/endpoint versions and pack size in results. Permission-error retrieval count =0 regardless of speed. | A,K; S04 §19; S05 §10.1; Golden Set/k6 |
| **NFR-10** | AI first token P95 <5 s for configured model routes, excluding uncontrollable public-network anomalies as specified by sources; typical chapter generation P95 <60 s. Separate model SLA from core-backend latency; record excluded failures rather than hiding them. | A,K,W; S01 §17; S05 §10.1; real endpoint evaluation pending |
| **NFR-11** | A 50-page DOCX export completes <60 s; the source does **not** specify P95 for this target. Verify source-required typography, pagination, tables and references with type-specific Golden DOCX snapshots. | K,A,W; S05 §10.1; S06 §9 |
| **NFR-12** | Core platform availability ≥99.9%, RPO ≤15 min and RTO ≤1 h. Evidence requires production-equivalent availability monitoring and timed backup/restore failover drills; configuration files or local successful startup do not prove these targets. Measurement window/failure-domain policy must be recorded. | A,K and infrastructure dependencies; S05 §§10,12; production environment pending |
| **NFR-13** | Persist business/AST/version/task/approval/outbox/inbox truth in PostgreSQL; Redis/cache loss and one worker failure cannot lose it. Broker delivery is not task truth. LLM outage still permits manual edit/search/citation/template/version/approval/export; knowledge outage permits edit but disables new Evidence and limits formal AI generation; Reviewer outage permits drafts but blocks dependent release; export failure leaves content version unchanged. | W,A,K; S02 §§5,8; S05 §§10.3,13; fault/restart tests |
| **NFR-14** | Capacity validation includes 100 online users, 20 QPS document/list and 5 QPS search; AI peak 20 parallel chapter jobs, 50 parallel searches and 10 full Reviews; export peak 20 concurrent 30–80-page DOCX/PDF jobs. S05 suggested sizing (500 DAU,100 simultaneous editors,20 long AI jobs,1M version records,10M Evidence/Claim links) is an initial design basis, not measured capacity. | W,A,K; S05 §10.2; S06 §8; frozen environment k6/worker telemetry |
| **NFR-15** | Correlate HTTP → orchestration/outbox → queue/worker → retrieval/rerank/Evidence → model → Claim/Review/Patch → SSE with trace/task IDs; collect P50/P95/P99, queue depth, provider usage/tokens/cost/retries, DB/cache/broker/resource measures without sensitive-data leakage. Failed/degraded stages remain diagnosable. | W,A,K; S04 §20; S05 §11; telemetry inspection |
| **NFR-16** | Under the direct S1 user instruction, existing prototype pages maintain strict **1:1 visual and interaction fidelity** at matched viewport, zoom, font/assets and state, except for the explicitly enumerated demo-to-real behavior replacements in §8.3. Preserve existing layout, controls and intended interaction entry points; do not reproduce mock success, incorrect targeting or inert semantics. Compare layout/module position/element size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/buttons/inputs/status/responsiveness. Existing controls cannot be arbitrarily removed, rearranged or redesigned. Approved real-state/data supplements are enumerated separately in §8; no pixel tolerance is invented in this PRD. | W; P; I; per-page screenshots plus interactive checks, not source-hash alone |
| **NFR-17** | Desktop/narrow-screen behavior follows prototype: at viewport widths ≤1180px maintain minimum 1180px app width, horizontal scrolling and desktop-view note, without mobile redesign/new project. Distinguish loading, streaming, queued, Evidence building, reviewing, pending Diff, missing information, forbidden, offline/degraded, exporting and approval pending; do not call all of these “AI thinking.” | W,A,K; P CSS; S02 §9; I; viewport/state matrix |
| **NFR-18** | Enforce quality level **medium** from AGENTS.md: core checks, critical tests, independent code review/verification and check → optimize → verify loops; do not bypass failed/blocking gates. Locked dependencies, schema migrations, API contracts, security tests and rollback paths remain required across all three projects. This S1 author self-check is not independent approval. | W,A,K; S06; S07 §5; I |

### 7.1 Additional source-pinned safety and reproducibility constraints

Prompt templates are versioned Registry assets, not business-code constants. Generation prioritizes confirmed project facts; Context Manager enforces a token budget rather than placing all raw knowledge in one Prompt. Model eligibility combines security, required capability, context length, latency and cost budget. Evaluation manifests retain reranker model/batch size/maximum input length/device and enterprise dictionary version in addition to the versions in FR-34. [S02 §§3.3–3.4; S03 §15.2; S04 §§3,7,13,15]

High-frequency query fields cannot live only inside deeply nested AST JSONB. Local attachment index metadata retains source/chunk/embedding/FTS/ACL snapshot and dictionary versions so authorized local indexes can be rebuilt and evaluated. These constraints preserve searchable domain projections; they do not prescribe new table designs in this PRD. [S03 §15]

Backups cover PostgreSQL, templates, Prompt Registry, audit, object-storage metadata and key formal outputs, Golden Knowledge metadata and attachment parsing metadata, with independent fault domains and periodic recovery drills. Local indexes can be rebuilt from authorized originals; the existing enterprise knowledge system retains its own recovery responsibility. Secrets must not appear as plaintext Helm values; application Pods must not receive cluster-level database administration privileges. Maintain traceable image and dependency inventories. [S05 §§12,14]

### 7.2 Technical baseline constraints (not new architecture)

The authoritative S07 stack remains intact despite engineering consolidation:

- **edw-web:** React + TypeScript + Vite; Ant Design; React Router; TanStack Query; Zustand for limited UI state; Tiptap open core with a custom domain AST Adapter. UI-library defaults must be styled to the prototype, not used as grounds to redesign it. Node LTS is frozen by engineering configuration; pnpm lockfile is required.
- **edw-api / edw-worker:** Python 3.12, FastAPI/Uvicorn, Pydantic 2, SQLAlchemy 2, psycopg 3 and Alembic; Celery and RabbitMQ quorum queues, single-active Beat, PostgreSQL-persisted state machine and Outbox. API and Worker have independent deployment units, connection pools and resource limits; categorized queues and dangerous-component isolation are required. Separate worker processes/images implement these boundaries within one worker engineering project.
- **Data/integration:** PostgreSQL/JSONB; Redis for rebuildable caches/limits; S3 API with default SeaweedFS; NGINX; REST/OpenAPI/SSE; Keycloak/OIDC with RBAC+ABAC. Adapters use Python/httpx and outbox/inbox. No default MinIO, WebSocket, or Redis/Celery-result authority substitution. Rust/Java/Go core business services and Tiptap commercial cloud/plugins are not baseline dependencies.
- **Knowledge/model shared modules:** pgvector, PostgreSQL FTS, jieba enterprise dictionary, BGE-M3, bge-reranker-v2-m3 and FlagEmbedding for authorized local attachment retrieval; existing enterprise knowledge remains external authority. Python httpx/Pydantic LLM Gateway; vLLM; Qwen3-32B is the Writer/Planner evaluation candidate, not a guaranteed frozen production model. GPU/weights/precision/context/parallelism/cache/throughput and efficacy require validation.
- **Parse/render/forms:** pypdf, python-docx, openpyxl, PaddleOCR; python-docx/docxtpl and LibreOffice; isolated Mermaid CLI; JSON Schema, React form rendering and Python JSON Schema validation. Mermaid/PlantUML authoring requests do not authorize arbitrary render runtimes or execution.
- **Delivery/operations:** Docker/Compose locally; Kubernetes/Helm production configuration; CloudNativePG/Barman Cloud backups in an independent failure domain; OpenTelemetry Collector, Prometheus/Grafana, Loki, Tempo and Alertmanager. No production deployment occurs in this task.
- **Verification:** pytest, Vitest/React Testing Library, Playwright, k6; Ruff/mypy, ESLint/TypeScript; uv.lock/pnpm-lock.yaml and immutable image tags/digests. Alembic is the migration entry point; provide downgrade or explicit irreversible-change explanation and avoid long-lock migrations. Standard-compatible enterprise IdP/S3/HA/provider substitution requires documented compatibility/security/performance/recovery validation, ADR and rollback, not unilateral replacement.

Technical implementation detail, runtime sizing and new contract design belong to downstream architecture. The list above only preserves supplied mandatory constraints and candidate-versus-frozen distinctions. Sources: S07 §§1–7; S02–S05; I.

## 8. Prototype Page Mapping and Authorized Supplement Register

### 8.1 Shared visual baseline

P is a 315-line standalone HTML prototype with four implemented page layouts, two named placeholder destinations, three editor panels, one modal and one toast. Navigation toggles `.active`; it is not URL routing. Decorative Unicode/text icons are part of the baseline, not permission to replace them with unrelated symbols. No imported fonts or dark-theme design is provided.

- Body background `#f4f8fd`; panel `#fff`/`#f8fbff`; border `#dbe6f5`/`#e8eef8`; text token `#0d2a63` (body `#17325f`); muted `#6f84a6`; primary `#0b6bff`; teal `#11b59a`; purple `#7357e8`; orange `#ff9818`; red `#ff4e55`; green `#12b981`. Radius 14px and shadow `0 7px 24px rgba(21,73,139,.07)`.
- Font stack `Inter,"PingFang SC","Microsoft YaHei",system-ui,-apple-system,sans-serif`; preserve actual resolved font in comparisons. App height 100vh, header 64px, shell columns 266px/remaining with 12px gap/padding. Header padding 0 24px, gap 28px; brand 22px/800, logo 34×34px, avatar 36×36px.
- Buttons 38px tall, radius 9px, horizontal padding 14px and weight 700; pills 12px/700 with 5px 8px padding; tables 13px with 9px 8px cells. Existing semantic statuses retain their presentation while actual text/counts derive from business state.
- At widths ≤1180px, body scrolls, app minimum width is 1180px and the desktop-view note is fixed at bottom/right 8px. Do not invent mobile stacking, collapsed navigation or a dark theme. New supplementary surfaces follow existing style without claiming pixel matching to a nonexistent source page.

### 8.2 Page-by-page and overlay traceability

Every item below must appear in the downstream UX coverage list and page-related stories. This is complete surface-level mapping, not an exhaustive control manifest. Before page-story completion, UX must derive an exact label/selector/state manifest from P: all six `data-page` values, five `data-create` entries, full `#docTree`, six `data-ai` actions, modal type/scope options (including the unnamed scope select), template `#detailName/#detailType/#detailCover`, Review detail IDs and `data-issue=0–6`/four `data-act` values, plus every inert More/recommendation/sidebar/toolbar/tab/select/preview control. Each control maps to preservation, source-grounded real-business replacement or explicit unresolved policy; none is silently dropped. A prototype's illustrative business values (for example “login ≤10 seconds” or “10万 terminals”) are sample document content, **not workbench performance targets**.

| Page ID / exact source anchor | Existing content and behavior to retain | Real-business obligations and FRs | Fidelity scope |
|---|---|---|---|
| **P-00 Shell** — P lines 73–117,261–272; `.app`, `.topbar`, `#topnav`, `#sidebar`, `[data-page]` | Workbench/document/knowledge/template/review/analysis navigation, search, notification/avatar, project card, document tree, favorites/reference/recycle-bin/storage area | Route to genuine selected records and authorized modules; search results, identity/project state, notifications, collections/storage data cannot be fixed samples. FR-1–FR-4,FR-47 | NFR-16/17; 64px header,266px sidebar; preserve icon/position hierarchy |
| **P-01 Workbench** — lines 119–175; `#page-home`, `.home-wrap` | Hero/greeting, four KPIs, four task/project/Review/template blocks, recent-document tabs/table; 330px right rail quick-create and AI recommendations | Real dates/counts/tasks/status, recent filters/rows, project navigation and actionable recommendation entries; 12/8/28,560/4.6 and sample people/projects are illustrative. FR-1–FR-3,FR-7,FR-18,FR-33,FR-47 | 142px hero,29px heading; four-column KPI/quad,12px gaps; preserve card geometry |
| **P-02 Create modal** — line258,274–277; `#modalMask`, `#modalTitle`, `#modalDocName`, `#modalDocType`, `#modalCancel`, `#modalCreate` | Quick-create for bid, PRD, technical solution, test plan and project summary; name/type/knowledge scope; Cancel/Create and editor entry | Persist entry-selected type, template and permission-valid scope; validate/return actual record; do not just change headings or claim knowledge loaded. Existing visual field layout retained; missing types/required fields are listed supplements. FR-1,FR-7,FR-18,FR-32,FR-35 | Modal560px,padding20px,radius14px; fields39px,radius8px; explicit errors/loading/focus are supplements |
| **P-03 Editor and tree** — lines104–110,177–194; `#page-editor`, `#docTree`, `.doc-toolbar`, `.paper`, `#crumbTitle`, `#docTitle`, `#insertCite` | Document breadcrumb/status/version/score, formatting toolbar, document paper/headings/table/citations; section tree | Actual AST/save/time/version/score; real formatting/undo/redo/links/table/image and section selection. Citation inserts at intended cursor/selection, not first paragraph. FR-5–FR-11,FR-14,FR-21,FR-28,FR-30 | `minmax(650px,1fr) 356px`; status48px/toolbar48px; paper max880px,min1040px,padding34px56px60px; headings32/25/18px; body14px,line1.85 |
| **P-04 Copilot panel** — lines195–207,278–283; `[data-aitab="copilot"]`, `[data-aipanel="copilot"]`, `[data-ai]`, `#aiPrompt`, `#sendAi`, `#aiResponse` | Generate chapter/continue/convert to technical requirements/check facts/summarize/polish; prompt/response, references and quality cards | Actual contextual jobs and Patch proposals; no fixed success answer. Safe text rendering, no unsanitized `innerHTML` interpretation. Real Evidence/quality statistics and environment labels. FR-18–FR-22,FR-33,FR-44 | 356px rail,12px cards,padding13px,2-column actions/8px gaps; preserve tab/prompt/control style |
| **P-05 Evidence panel** — lines195,204–206,279; `[data-aitab="evidence"]`, `[data-aipanel="evidence"]` | Evidence Pack and source title/version/section labels | Actual authorized sources; opening trace rechecks access and freshness; counts match records. FR-12–FR-17 | Existing rail/cards preserved; additional provenance/conflict detail separately enumerated |
| **P-06 Pending-item panel** — line207; `[data-aitab="todo"]`, `[data-aipanel="todo"]` | Pending count, three example missing-information entries and Process buttons | Real issue identities/counts, edit/resolve/exception decisions and audit; item cannot disappear by cosmetic action. FR-22,FR-25,FR-29 | Existing list/button/semantic state styles; new resolution details follow approved style |
| **P-07 Template center** — lines213–232,284–293; `#page-templates`, `#templateGrid`, `#templateSearch`, `#chips`, `.tcard[data-name]`, `.use-template`, `#detailUse`, `#uploadTpl` | Enterprise/department/mine tabs, category chips, type/search, upload, eight cards, preview/use, right detail/outline | Functional combined filters, true previews/uploads/permissions/versions and selected-template details. All categories persist: bid,PRD,technical solution,test plan,technical requirements,quality outline,project plan,production form; supplement missing phase2 types. FR-7–FR-8,FR-32,FR-39 | Content+310px detail; four `minmax(180px,1fr)` columns/12px gaps; covers125px/detail190px; search360×38px |
| **P-08 Review results** — lines234–252,295–307; `#page-review`, `.issue[data-issue]`, `.filter`, `.issue-action`, `#rerunReview` | Document/version/status header, download/share/rerun, four stats, severity filters, list/detail/trace columns; issue selection and four actions | Actual filter/search/result job, selected issue/Evidence/impact metadata; distinct accept/reject/modify/resolve behavior. Seven sample rows versus header12 and 92/86%/78% are examples, not acceptance counts. FR-23–FR-30,FR-33,FR-38 | 16px padding;350px/minmax420px/370px columns;12px gaps; min560px;58px gauges/7px borders |
| **P-09 Review subviews** — line237; review `.seg-tabs` labels 审校结果/引用追溯/版本对比/审校记录 | Existing tabs and initial result view | Tabs currently inert: supply genuine source trace, version compare and run/history views; Approval is not implicitly this page. FR-14,FR-21,FR-24,FR-27 | Preserve tab/control geometry; missing subview layouts are supplements |
| **P-10 Knowledge destination** — line254; `[data-page="knowledge"]`, `#page-placeholder`, `#placeholderTitle` | Sidebar/header destinations and placeholder title 企业知识库, Return to workbench | Replace placeholder body with permission-scoped source search/view, metadata/version/conflict and governed knowledge management; retain shell/style. FR-12–FR-17,FR-31 | No source business-page design exists; treat body as authorized supplement, not original pixel baseline |
| **P-11 Analytics destination** — line254; `[data-page="analysis"]`, shared placeholder | 数据分析 navigation/title and Return | Real versioned quality/coverage/Reviewer/evaluation statistics with drill-down and no-data/error/not-evaluated states. FR-33–FR-34,FR-47 | Shell retained; body design is a documented supplement |
| **P-12 Toast / responsive note** — lines66–69,259,263; `#toast`, `.mobile-note` | Center-bottom toast28px,padding11px16px,radius9px,z50,0.2s transition/1800ms display; narrow-screen note | Toast reports real operation outcome; long tasks retain visible durable status beyond toast; failure is never success copy. FR-44–FR-47 | Preserve overlay behavior; additional durable status shown in approved supplementary UI |

### 8.3 Authorized additions and demo-to-business corrections

**Authority:** I confirmed decisions expressly allow missing pages/controls, real async states and live business data while retaining original-page visual baseline. They do **not** authorize editing `docs/prototype/index.html`, unrequested redesign, scope deletion or arbitrary interaction changes. UX must enumerate each addition and its source/FR, then stories must inherit the mapping. The inventory below captures coverage within that category-level authority; it does not claim the user separately approved each new screen topology or detailed layout.

| Supplement ID | Source-derived coverage within approved categories | Scope/limits |
|---|---|---|
| **SUP-1** | AI Diff accept/reject, version/optimistic-conflict comparison and merge feedback | FR-6,FR-21,FR-24. No silent AI overwrite or new collaborative platform. |
| **SUP-2** | Approval request/inbox/detail/decision/history and publication-gate state | FR-27–FR-29. Human approval separate from Review disposition; policy questions in §10 remain explicit. |
| **SUP-3** | Tender parse/qualification/disqualification/scoring/compliance and response tracing pages | FR-35–FR-38. Quick-create/card labels are not a delivered specialist workbench. |
| **SUP-4** | Form Builder, schema preview/version, instance entry/validation, print/scan/export/integration status | FR-39–FR-43. No fabricated electronic-signature certification. |
| **SUP-5** | Real knowledge and analytics bodies; permission/source details and quality/rule/evaluation administration | FR-12–FR-17,FR-31,FR-33–FR-34,FR-47. Keep shell/style and label environment/data limitations. |
| **SUP-6** | Missing Phase2 template/document types, template lifecycle/preview/upload and relevant context/attachment inputs | FR-7–FR-8,FR-17–FR-18,FR-32. Full Phase2 flows, not navigation-only placeholders. |
| **SUP-7** | Empty/loading/streaming/queued/retry/failure/cancelled/blocked/stale/forbidden/offline/export/approval/Diff states; validation and pending-item resolution controls | FR-19–FR-29,FR-44–FR-47; NFR-17. Use truthful task state and existing status styling, without moving existing modules arbitrarily. |
| **SUP-8** | Wire inert search/navigation/favorites/reference/recycle/recommendation/template/review/download/share controls and selector-specific editing; synchronize selected creation type and combine filters | FR-1–FR-8,FR-14,FR-18,FR-24,FR-30. Do not preserve demo bugs such as fixed issue evidence, cosmetic resolution, first-paragraph citation insertion or fake success. Lifecycle/retention/access rules remain governed. |
| **SUP-9** | Replace sample people/projects/dates/quality/coverage/storage/references with authorized real data; display explicit developer fixtures in local demonstrations | FR-2,FR-14,FR-24,FR-33,FR-47. Never infer platform targets from sample document metrics; no fabricated scores/effectiveness. |

**Fidelity verification required downstream:** capture matching viewport/state screenshots for P-00–P-12 where a source layout exists; compare the full NFR-16 property list and test all source interactions plus authorized replacements; record each difference as original-baseline defect, approved supplement or unresolved substantive conflict. Verify desktop and ≤1180px scrolling, explicitly testing the 1180px/1181px boundary. Where absent pages have no baseline, evaluate style consistency and traced requirements rather than falsely claiming source-identical screenshots. This document includes source analysis only; no visual acceptance is claimed.

## 9. Acceptance Layers, Delivery Conditions and Traceability

### 9.1 Three distinct acceptance ledgers

1. **Local Contract Acceptance:** all three projects build/run against project-isolated local infrastructure; deterministic model/enterprise doubles verify contract/state/security paths. Must exercise real persistence, UI transitions, queue/retry/recovery, AST/Patch and artifact generation where available. It proves local behavior only.
2. **Real AI and enterprise acceptance:** actual authorized knowledge/identity/MES/project/archive contracts and configured model/embedding/reranker endpoints; real Golden Set/Evidence/Claim/citation/Reviewer measurements and authorized UAT. Local stubs cannot satisfy this ledger.
3. **Production NFR acceptance:** production-equivalent capacity, availability, fault domains, security, backup/restore and rollout/rollback evidence. Production configuration is not evidence of these operational results.

Full delivery requires all applicable ledgers and phase capabilities to pass. While real AI, enterprise integration or production NFRs remain unverified, reports must say what is local-only and what remains pending; no “full completion” or “Everything is ok.”

### 9.2 Required verification evidence by concern

| Acceptance ID | Checks / evidence | Coverage |
|---|---|---|
| **AC-1 Domain and UI** | AST/template/permission/Claim/Evidence/Patch/export unit tests; Vitest/RTL UI state tests; four Phase1 document-type functional cases and all Phase2 types; fixtures distinguish formal samples from development records. | FR-1–FR-11,FR-15,FR-21,FR-32; NFR-8,NFR-18 |
| **AC-2 Core cross-project E2E** | New technical solution → outline confirmation → section/Evidence → pending information → accept Patch → full Review → serious-issue correction → approval → DOCX/PDF. Include stale edits, denied references and failed jobs. | C-1–C-7; FR-1–FR-31,FR-44–FR-46 |
| **AC-3 Specialist E2E** | Phase2 document/score/coverage/rule/evaluation workflows; tender extraction → correction → scoring/disqualification → bidirectional response → Review; form schema → instance validation/version → multi-format/print/scan → integration success/failure/replay. | C-7,C-8; FR-32–FR-43 |
| **AC-4 Contracts and resilience** | OpenAPI/schema tests, document-template interactions, orchestration→knowledge→rerank and model adapter, generation→Review, AST→artifact, approval→publish→quality gate; outbox→RabbitMQ→Celery→inbox replay, SSE reconnect, OIDC context, S3, parse/OCR→pgvector/FTS. | C-1–C-8; FR-42–FR-48; NFR-2,NFR-13 |
| **AC-5 AI/evaluation** | Golden Queries50–200/domain; Recall@K/MRR/nDCG, project hit/obsolete ranking, Unsupported Critical Claim, Citation Precision/Completeness, Requirement Coverage, Human Edit Distance and Reviewer false positives/negatives. Inject number conflict, residual customer, old version, unsupported performance, ambiguity, absent chapter, missed requirement, forbidden reference and wrong standard. | SM-2–SM-4,SM-C1–SM-C2; FR-12–FR-26,FR-34,FR-38 |
| **AC-6 Security and release** | Cross-user/role/project search/Evidence; NL escalation and knowledge injection; secret/DLP route checks for L2/L3; revoked-member/source export and old links; audit outage during publish/approval/permission writes; severe/waiver gate checks. | FR-4,FR-12,FR-14,FR-25–FR-29,FR-46; NFR-1–NFR-7 |
| **AC-7 Output and fidelity** | Golden DOCX per type checks cover/logo/classification/header/footer/TOC/hierarchy/numbering/cross-page table/Chinese font/page/approval/version/citation appendix; verify corresponding PDF and schema-based form formats. Per-page/state visual and interaction comparison includes P-00–P-12 and SUP register. | FR-30,FR-41; NFR-11,NFR-16,NFR-17 |
| **AC-8 Operations and recovery** | Compose startup/migrations/fixtures; test-cluster Helm rolling update/rollback; NGINX SSE; broker node failure/consumer restart/worker kill; PostgreSQL HA/Barman restore; object version/lifecycle/TTL/permissions; Redis clear/restart; OTel trace correlation. Measure capacity profiles and RPO/RTO, not only infrastructure existence. | FR-44–FR-48; NFR-8–NFR-15 |
| **AC-9 Quality and UAT** | CI runs the test types selected by each Story's change-surface applicability matrix; release checks run their owned critical suites. Role-based UAT executes 3–5 tasks and records findings. | All FRs and NFRs; SM-6; S06 §§11,14–15; S07 |

### 9.3 Source-defined validation sequence and ongoing quality

The S06 §13 POC validates existing knowledge access, Evidence, technical-solution chapter generation and DOCX using **one document type, 3–5 excellent historical solutions, one real project knowledge set and 1–2 LLMs**. vLLM/Qwen3-32B is the Writer/Planner efficacy/GPU baseline candidate; BGE-M3/bge-reranker-v2-m3 is validated only on the local attachment retrieval path. With no real endpoints, this remains a planned real-environment check; local substitutes cannot claim its efficacy gate passed. POC scope does not replace the three-phase commitment.

S06 §14 suggests dependency order M1 document foundation → M2 knowledge/Evidence → M3 AI orchestration → M4 Review → M5 formal output → M6 evaluation/security/performance/UAT/runbook. This is source planning guidance, not new epics, schedule promises, user confirmation or authority to start development.

S06 §6 prioritizes **Recall for severe-issue Reviewers**, without supplying a numeric Recall threshold. After rollout, S06 §15 requires **monthly** analysis of generation success, AI content retention, issue distribution, Evidence gaps, weak-recall queries, manual edit categories, authoring time, approval time and model cost. Improve in order **Knowledge → Template → Retrieval → Prompt → Reviewer → Model**, rather than assuming a larger model is the first fix. This operationalizes FR-33/FR-34/FR-47 and SM-C1/SM-C2 without inventing business improvement targets.

### 9.4 Source-to-requirement completeness matrix

| Source | Principal PRD anchors | Specific retained concerns |
|---|---|---|
| S00 | §0–§1,§4,§7.2,§9–§10 | Formal-document rather than chatbot thesis; source hierarchy and stack authority |
| S01 | UJ-1–UJ-5; FR-1–FR-43; §4; SM-1,SM-3; FR-28–FR-31 | All phases/types, roles, evidence-first human-controlled lifecycle, eight Reviewer kinds, formal export/return |
| S02 | FR-5–FR-6,FR-12–FR-26,FR-39–FR-48; C-1–C-8; §6.1; NFR-13,NFR-17 | Logical module responsibility, async recovery, UI state granularity, safe isolation despite engineering merge |
| S03 | §3,§6–§6.1; FR-5–FR-8,FR-14–FR-15,FR-21,FR-24–FR-30,FR-39–FR-46 | AST/domain/schema versions, Claim/Evidence/Issue states, errors, API/event/SSE and consistency |
| S04 | FR-12–FR-26,FR-31,FR-33–FR-34; §6.1; NFR-3–NFR-7,NFR-9–NFR-10,NFR-15 | Context/query/authority, exact retrieval, bounded structured generation, Prompt/DLP, human pending items, model candidates/evaluation |
| S05 | FR-4,FR-12,FR-14,FR-25–FR-30,FR-46; NFR-1–NFR-15 | Object authorization, classification, audit fail-closed, degraded modes, precise latency/recovery and secret/data policy |
| S06 | §1.1,§9; FR-9–FR-11,FR-26,FR-34,FR-48; NFR-8–NFR-18 | Functional/E2E/AI/security/export/capacity/resilience/UAT with local vs real evidence |
| S07 | §4,§6.1,§7.2; C-1–C-8; FR-17,FR-39–FR-48; NFR-18 | Frozen stack, authoritative storage, queue/connection isolation, deployment/configuration/testing conventions |
| P | §8 P-00–P-12 and SUP-1–SUP-9; NFR-16,NFR-17 | Every existing page/panel/modal/placeholder/overlay and demo correction accounted for |
| I | §0,§4,§8.3,§9.1,§10–§11 | Sole confirmation, no scope shrink, three engineering projects, unchanged prototype, environment/authorization restrictions |

## 10. Resolved Conflicts, Open Decisions and Environment Dependencies

### 10.1 Already resolved by confirmed inputs

| Item | Resolution and source authority |
|---|---|
| Old separate service/project suggestions vs simplified engineering | I mandates exactly three engineering projects; Gateways become shared modules, while queues, resource/connection boundaries and isolated dangerous processes survive. No re-interview required. |
| “Phase1/MVP” wording vs full scope | I confirms all three phases. Phase1 and POC sequencing cannot remove later document types, quality governance, bid or form workbenches. |
| Prototype 1:1 vs absent pages/inert controls/fixed data | The direct task requires strict 1:1; I authorizes missing-surface/state/data categories in existing style. SUP-1–SUP-9 is a derived coverage inventory, not separate approval of every new screen topology. Existing layout remains baseline and original source stays immutable. Demo-specific bugs are not product logic to preserve. |
| Collaboration ambiguity | I selects version/optimistic-lock/conflict handling, not an extra real-time platform. |
| “Python3.12 candidate” vs baseline wording | S07 engineering rules set Python3.12; Qwen3-32B/GPU settings remain evaluation candidates, not frozen production facts. |
| Phase2 Requirement Coverage vs Phase1 testing obligations | Phase1 already includes requirement-test links/coverage; Phase2 adds platform governance and quality/rule/evaluation views. |
| Approved/Published trusted knowledge vs Published-triggered pipeline | Formal eligibility excludes all drafts; use the source-defined Published-triggered quality-gated return flow. No automatic prepublication ingestion. |
| Orchestration COMPLETED vs document PUBLISHED | S01 supplies document lifecycle; S02 task/orchestration states are separate. FR-27–FR-29 prevent task completion from becoming publication. |
| Example Reviewer API list omits quality | S01 requires all eight Reviewer categories; S03 example list is not a scope exclusion. Quality Reviewer remains FR-23. |
| Local substitutes vs integration/effect acceptance | I permits local contracts/doubles but expressly prohibits real efficacy/integration/NFR completion claims without environments. |

### 10.2 Open policy decisions — do not silently infer

These are narrower than the already confirmed product/engineering scope. The draft exposes them rather than claiming green-light readiness for all downstream implementation.

| ID | Decision not supplied | Owner / safe boundary / revisit |
|---|---|---|
| **OQ-1** | Which enterprise policy, if any, permits an L2 external-model exception? Existing rules already require internal priority/default, policy/DLP routing, deny when not permitted and absolute L3 external prohibition. | **Basis:** S05 §§5–6 (lines96–143), S04 §16. **Owner:** enterprise security. **Options:** (a) keep L2 internal-only; (b) configure explicitly approved desensitization/provider/authorizer rules. **Conservative behavior:** no configured allow rule means external request denied; this follows the existing policy gate, not a new customer scope decision. **Impact:** does not block PRD or internal-only local contracts; blocks enabling the optional external exception until policy supplied. |
| **OQ-2** | Which explicit role/policy may waive eligible pending/general issues, and what configured critical-Claim Evidence coverage threshold does each formal template require? Existing rules already require severe issues 0, pending items closed or approved exception, configured coverage, no conflicts/unauthorized references, human approval and audit. Waived issues record approver/reason. | **Basis:** S01 §16 (lines657–670), S03 §6 (lines221–249), S04 §§10–12/§21, S05 §8. **Owner:** quality/security/template policy owners. **Options:** (a) resolve all pending items without waiver; (b) supply least-privilege waiver matrix plus reason/reapproval rules; supply coverage threshold as a versioned template/policy parameter in either case. **Conservative behavior:** no explicit waiver permission → deny waiver; no required coverage policy → block formal publication; severe safety gates remain non-bypassable. **Impact:** not a new scope blocker or reason to stop PRD/local workflow design; blocks real waiver/publication configuration and any detailed policy-dependent acceptance. Do not invent an authorized role or percentage. |
| **OQ-3** | Which business state transitions/retention policy apply to the prototype's inert recycle-bin and share controls? ACL on views/exports and protected formal-version retention are already required; notifications need only actual accessible task/data state, not another policy interview. | **Basis:** P sidebar lines104–117 and review lines234–252 expose controls without behavior; S02 §2.3 prohibits physical removal of template versions used formally; S05 §§3–4,9,15 govern object authorization/retention; I limits database authority and prototype supplements. **Owner:** product/data governance. **Options:** access-checked internal navigation/share with current ACL (no public access), and reversible soft-hide/archive under existing permissions; broader link-sharing or destruction would require explicit policy. **Conservative behavior:** every target reauthorizes; no public/external sharing or physical deletion absent explicit permission. **Impact:** no blocker to PRD scope, read-only/local states or safe internal navigation; unresolved destructive/expanded-sharing semantics must not be implemented or declared accepted. |

**PRD implication:** these are policy/configuration gaps with source-grounded deny-by-default behavior, not a repetition of confirmed phase/engineering decisions. No new product-scope conflict is established. The controller should carry OQ-1–OQ-3 into affected policy/UX/contract work; do not promote missing numeric settings or role mappings into unnecessary customer scope interviews. The concrete S1 delivery blocker remains original-target write isolation. This draft does not assert that environment-specific policy acceptance is complete.

### 10.3 Pending environments and measurement configuration (not missing functional scope)

| ID | Dependency / owner | Revisit condition and acceptance blocked |
|---|---|---|
| **ENV-1** | Enterprise identity/ACL, knowledge, MES/project/archive endpoints, documented contracts, credentials and approved access; enterprise integration/identity owners | Before real integration ledger; local configurable contract adapters continue, without claiming unknown vendor support. |
| **ENV-2** | Model/Embedding/Reranker endpoints, GPU capacity/weights/quantization/context/parallelism and representative datasets; AI platform/evaluation owners | Before real generation/RAG/Reviewer score or throughput acceptance. Deterministic doubles only verify contracts. |
| **ENV-3** | Production-equivalent cluster, fault domains, HA/backups, security and recovery environment; platform/operations owners | Before availability/capacity/RPO/RTO/production-security acceptance. No production deployment is authorized. |
| **ENV-4** | Classification/DLP/retention/TTL/key-management policy, sandbox resource limits and OCR quality trigger configuration; security/data/operations owners | Before policy-specific deployment tests. Source prescribes controls but not exact retention days/resources; do not invent them. |
| **ENV-5** | Official templates, themes, licensed fonts, company-approved output examples and type-specific validation rules; template/quality owners | Before formal DOCX/PDF and type-specific UAT sign-off. Explicit development samples allowed and labeled. |
| **ENV-6** | Frozen definitions for typical chapter/pack, benchmark corpus, hardware/network/queue settings, observation window and approved final recommended AI thresholds; performance/evaluation owners | Before measured NFR/effect gate. Use S06 load profiles as source baseline, retaining recorded target qualifiers and exclusions. |

Detailed API status mappings, complete event catalogs and safe retry numbers belong to downstream contract design within these fixed requirements; they are not grounds to invent business permission policy. `tenant_id` is preserved for contract compatibility, but a separate SaaS multi-tenancy product is not inferred from it.

### 10.4 Assumptions index

No unconfirmed product-success percentages, personal customer personas, vendor support, extra engineering projects, numeric retention periods, waiver roles, external-L2 exceptions or new production privileges are assumed. Derived measurement discipline (explicit denominator and not-applicable/unevaluated states) operationalizes the confirmed “real data, no false acceptance” decision. Proposed UX/contract details outside the supplied sources remain in OQ/ENV rather than being stated as approved facts.

## 11. S1 Draft Self-Check and Handoff State

This is an **author self-check**, not an independent reviewer verdict. Main-project publication remains blocked by tool isolation; `status: draft` is intentional. No architecture, UX design, epic, story, code or deployment has been created by this task.

| S1 gate / requested extension | Draft evidence | Result |
|---|---|---|
| File exists and non-empty | This `prd.md` in permitted worktree | Draft artifact present; original target absent |
| Requirements/range/function description | §4 all three phases; FR-1–FR-48; NFR-1–NFR-18 | Author check covered |
| Every explicit source referenced | §0 source register and §9.4 source mapping; source-extraction agents read all inputs completely | Author check covered |
| Prototype reference / page correspondence | §8 P-00–P-12, source line ranges/IDs | Author check covered |
| Strict 1:1 constraint | NFR-16/17 and §8, including full visual property list and responsive behavior | Author check covered, no screenshot acceptance claimed |
| Three-project/full-phase and cross-project traceability | §4 and C-1–C-8; individual owners/phases/source/AC mappings | Author check covered |
| Supplements/conflicts/environment matters separated | §8.3,§10.1–§10.3 | Author check covered; open policy questions explicit |
| No false final acceptance / no independent self-approval | Frontmatter,§9.1 and this section | Preserved |
| Original main-project S1 delivery | Main-root Write was rejected by inherited worktree isolation | **BLOCKED / NEEDS_INPUT** |
| Policy readiness | OQ-1–OQ-3 have source-grounded deny-by-default behavior; explicit policy is needed before affected production capabilities are enabled | No new scope blocker; policy acceptance remains pending |

**Next action:** controller reviews this permitted-worktree draft and the explicitly open decisions, informs the user of original-target delivery blockage, and obtains an allowed subsequent workflow. Do not copy/merge around the rejected write, change permissions, or proceed downstream on this draft's existence alone. S4c Epics confirmation remains a separate future user approval requirement.
