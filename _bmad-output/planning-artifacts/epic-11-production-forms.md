---
epic_id: epic-11
status: planned
phase: 3
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 11: Control production schemas, values and scans

Outcome: users author independent schemas, save validated instances and compare identical canonical values across formats before controlled delivery. W/A/K and guards follow epics.md; Signature is capture only, not certified enterprise e-signature.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 11-1 AC1–2,Evidence,L/R/P | Working eleven-type schema builder/versioning/validation and attacks/denials | Official schema/policy/user validation →13-3; scale/security →13-4/13-5 |
| 11-2 AC1–2,Evidence,L/R/P | Actual reviewed SchemaPatch/base/hash/subset/stale and policy checks | Real schema-generation efficacy →13-1; official type policy →13-3; no automatic production activation |
| 11-3 AC1–2,Evidence,L/R/P | Actual server/Web parity,decimal/date/formula/canonical/CAS safety | Company unit/date/formula/recording policy and UAT →13-3; actual governed formula resource limits →13-5 |
| 11-4 AC1–2,Evidence,L/R/P | Genuine five-format outputs against same canonical hash with local assets; safe spreadsheet/artifact tests | Official paper/fonts/Golden samples/operator review →13-3; output peak →13-4 |
| 11-5 AC1–2,Evidence,L/R/P | Actual OCR/generated-code lookup/human confirmation and wrong/stale/denied cases | Real paper/device/operator correction accuracy →13-3; device/storage security →13-5 |
| 11-6 AC1–3,Evidence,L/R/P | Complete actual three-project standalone lifecycle and deferred-control closure; domain eligibility validation | AC2 actual50–200 representative form-domain queries with ACL/defect labels and real model →13-1; actual enterprise delivery →13-2; official forms/devices/production-recorder UAT →13-3; production capacity/security →13-4/13-5 |

## Story 11.1: Author an independent eleven-field Form Schema
**ID:** `11-1-form-schema` | **Status:** backlog | **Projects:** W,A
As a form administrator, I want versioned schemas, so that data-entry structure is independent from document prose and historical instances stay stable.
**Scope:** FormSchema/FormSchemaVersion,manual builder/palette/tree/properties/validation/preview/activate; eleven fields Text,Number,Date,Select,Checkbox,Signature,Image,Barcode,QR,Formula,Repeating Table. JSON Schema2020-12 approved subset/stable keys.
**Dependencies:** `7-4-core-integration`.
**Traceability:** FR-39; C-8; AD-2,AD-14.
**UI reference:** P-07 production-form card→X-07 palette/tree/canvas/properties/version/actions; SUP-4. R entry,S full Builder.
**UI fidelity:** Strict existing1:1 visuals/interactions for layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; mark R/S/conflicts; X-07 uses UX contract not nonexistent prototype pixels.
**Acceptance Criteria:**
- **Given** authorized schema owner, **When** each of eleven types and repeating rows are configured/validated/saved, **Then** stable keys/types/constraints/units/options/layout/version persist independently of DocumentVersion; activated schema is immutable and old instances keep pinned version.
- **Given** duplicate keys,unknown component,remote `$ref`,arbitrary script or unauthorized activation, **When** validation/commit runs, **Then** reject precisely and preserve last valid schema; JSON schema cannot become remote executable configuration.
**Evidence:** T-FORM/T-CONTRACT eleven-type/schema/version fixtures; T-SEC ref/script/permission cases; T-UX palette/keyboard/validation.
**L/R/P:** L real builder/API/PG; R official form schemas/validation policies and actual users; P scale/security later.

## Story 11.2: Review AI schema changes before activation
**ID:** `11-2-schema-patches` | **Status:** backlog | **Projects:** W,A,K
As a form administrator, I want a reviewable SchemaPatch, so that AI cannot silently replace an active production schema.
**Scope:** Model-request context/output schema/provenance,stable-key schema changes/base/hash checks,selected accept/reject and new SchemaVersion using dedicated form adapter,not document JSON pointers.
**Dependencies:** `11-1-form-schema`, `4-4-reviewed-patches`.
**Traceability:** FR-39,FR-21; C-5,C-8; AD-9,AD-14.
**UI reference:** X-07 AI proposal/actions→X-01 Diff/X-02 conflict with schema identity; SUP-4,SUP-1. S SchemaPatch.
**UI fidelity:** Strict original1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interactions for inherited surfaces. Preserve source hierarchy/file; R/S/conflicts explicit; new schema Diff follows UX without pixel fiction.
**Acceptance Criteria:**
- **Given** authorized current schema and allowed model, **When** AI proposes then user accepts selected changes, **Then** validated SchemaPatch pins base_version/expected hashes and Prompt/model/run provenance,new immutable schema version is created,activation remains explicit and existing instances are not migrated implicitly.
- **Given** stale schema,malicious rule/component,revoked owner or rejected proposal, **When** action occurs, **Then** conflict/denial/rejection leaves active schema unchanged; same DLP/schema repair/current-policy rules apply as document generation.
**Evidence:** T-FORM/T-CONTRACT Patch/subset/stale/provenance; T-SEC unsafe model schema; T-UX schema Diff/reject/conflict.
**L/R/P:** L actual worker/schema APIs with labeled model double; R real schema-generation efficacy and official type policy; P no automatic production activation.

## Story 11.3: Save server-validated instances and safe formulas
**ID:** `11-3-form-instances` | **Status:** backlog | **Projects:** W,A
As a production recorder, I want validation and formulas to agree, so that an invalid or concurrent update cannot corrupt my last valid record.
**Scope:** Schema-pinned FormInstance/versions,Web field rendering/front-back validation parity,decimal/unit/date normalization,whitelist formula dependency order/cycle/budget checks,Canonical Form Snapshot.
**Dependencies:** `11-1-form-schema`.
**Traceability:** FR-40; C-8; AD-3,AD-14.
**UI reference:** X-08 header/entry/validation rail/repeating-row/add-attachment/signature/save; SUP-4. S instance UI.
**UI fidelity:** Strict inherited source visual/interaction1:1 layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Source hierarchy/file retained; R/S/conflicts explicit; X-08 follows UX, no original-pixel claim.
**Acceptance Criteria:**
- **Given** activated schema and current entry permission, **When** eleven types/rows are filled and saved, **Then** frontend and authoritative server validate type/required/range/declared rules,normalize precise decimal strings/units/date semantics and store versioned canonical values/formula results with stable row/field IDs and schema reference.
- **Given** bypassed browser validation,invalid signature/image reference,formula cycle/unknown function/over-budget expression or stale instance revision, **When** API saves, **Then**422/409/403 preserves last valid snapshot and returns located errors; formulas never eval script,access I/O or network. Signature is explicitly not certified signing.
**Evidence:** T-FORM parity/property/decimal/date/repeating/cycle/budget/CAS tests; T-SEC attachment/role bypass; T-UX retained-field/errors/keyboard.
**L/R/P:** L actual server formula interpreter/PG and browser; R company unit/date/formula/recording policy and real UAT; P formula resource limits later.

## Story 11.4: Render identical canonical values across all form formats
**ID:** `11-4-form-multiformat` | **Status:** backlog | **Projects:** W,A,K
As a production recorder, I want identical Web,DOCX,PDF,XLSX and print values, so that format conversion cannot change business data.
**Scope:** Canonical Form Snapshot adapters to actual docx/pdf/xlsx/print,layout/page/units/repeating rows/signature-image/barcode/QR resources,artifact pinning/checksum and safe downloads.
**Dependencies:** `11-3-form-instances`, `6-5-controlled-artifacts`.
**Traceability:** FR-41; NFR-7,NFR-11; C-6,C-8; AD-6,AD-12,AD-14.
**UI reference:** X-08 preview/print/export tabs,X-19 artifact; SUP-4,SUP-8. S form previews,R actual outputs.
**UI fidelity:** Strict original1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interactions. Preserve source hierarchy/file; register R/S/conflicts; new body follows UX not fabricated source pixels.
**Acceptance Criteria:**
- **Given** a canonical snapshot with all eleven types and repeating rows, **When** Web,DOCX,PDF,XLSX and print render, **Then** compare every field/key/row/normalized value/unit/formula result against the same snapshot hash; exporters do not independently recalculate formulas. Real document tools and correct page breaks/images/print layout used.
- **Given** missing font,conversion failure,formula-like spreadsheet strings or revoked resource access, **When** rendering/downloading, **Then** safe explicit failure/development label,spreadsheet injection protection and current ACL apply; partial file never downloadable and source instance unchanged.
**Evidence:** T-FORM five-format field-by-field parity and T-DOC actual file/print snapshots; T-SEC XLSX formula injection/artifact ACL; T-UX preview/task states.
**L/R/P:** L real LibreOffice/openpyxl/docx/print artifacts; R official paper/fonts/output samples and operator validation mandatory; P output peak13-4.

## Story 11.5: Confirm scanned values before changing records
**ID:** `11-5-form-scan-proposals` | **Status:** backlog | **Projects:** W,A,K
As a production recorder, I want barcode lookup and OCR proposals checked, so that scanning cannot silently change the wrong or unauthorized instance.
**Scope:** Barcode/QR opaque lookup/no permission grant,authorized scan upload/camera-on-explicit-action,identity/schema/version validation,actual OCR,confidence/source preview and per-field human confirmation.
**Dependencies:** `11-4-form-multiformat`, `3-1-safe-attachments`.
**Traceability:** FR-41,FR-40; C-3,C-6,C-8; AD-7,AD-14.
**UI reference:** X-08 scan tab/420px preview/extracted values/confirmation/state; SUP-4. S scan controls.
**UI fidelity:** Strict inherited source1:1 visual/interaction layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; R/S/conflicts explicit; scan body uses UX contract not original pixels.
**Acceptance Criteria:**
- **Given** authorized printed record barcode/QR and matching schema/version, **When** scan/OCR executes and human confirms selected valid values, **Then** source scan/field locators and corrections are retained and server validation creates new instance version; OCR alone never saves business values.
- **Given** unknown/wrong/replayed code,denied record,stale schema,low-confidence OCR or revoked permission, **When** lookup/confirm occurs, **Then** no foreign data leaks or silent overwrite; barcode contains neither token nor sensitive full row and grants no authority. Camera is not always on.
**Evidence:** T-FORM wrong-record/stale/low-confidence/selected-confirm fixtures; T-SEC code/ACL/scan sandbox; T-UX permission/upload/confirmation states with actual OCR.
**L/R/P:** L actual parser/OCR and generated codes; R real printer/scanner/camera/paper corpus/operator correction accuracy; P device/storage security validation later.

## Story 11.6: Prove the complete three-project form lifecycle
**ID:** `11-6-form-integration` | **Status:** backlog | **Projects:** W,A,K
As a delivery reviewer, I want a complete form lifecycle demonstration, so that a schema mock cannot count as working production forms.
**Scope:** Actual eleven-field manual/AI schema flow,instance validation/cross-format/print/scan workflow and approval-ready artifact handoff. Local delivery extension is12-2/12-3; actual enterprise delivery is13-2,not required for local standalone form use.
**Dependencies:** `11-2-schema-patches`, `11-5-form-scan-proposals`.
**Traceability:** FR-39,FR-40,FR-41,FR-34,FR-48; C-1,C-2,C-3,C-5,C-6,C-8; AD-14,AD-18.
**UI reference:** UJ-5 X-07/X-08/X-01/X-02/X-19/X-16; SUP-4,SUP-1,SUP-9.
**UI fidelity:** Explicit strict existing visual/interaction1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Source hierarchy/file preserved; R/S/conflicts documented; X pages follow UX without fictitious prototype pixels.
**Acceptance Criteria:**
- **Given** real W/A/K+OIDC/PG/MQ/S3/SSE and actual OCR/renderers, **When** build11-type schema→review AI SchemaPatch→activate→enter/validate/formula→save→five-format parity→print/scan→human confirm completes, **Then** schema/instance/canonical/output/scan provenance joins and all real artifacts/values match; only external model ports may be doubles.
- **Given** malicious formula,stale SchemaPatch,invalid instance,wrong barcode,OCR uncertainty or worker loss, **When** workflow repeats, **Then** precise validation/conflict/denial/recovery without lost last-valid records is demonstrable. Extend form-domain Golden requirements to50–200 representative queries+ACL/defect labels for real AI evaluation, not tiny samples.
- **Given**7-5 deferred C24 production-form template entry and Form Builder/Form instance and scan components, **When** actual entry→eleven-type schema/AI proposal→instance/formula→five-format preview/print→code lookup/OCR/human confirmation runs, **Then** capture each positive action's schema/instance/canonical IDs plus forbidden/invalid/stale/failed/uncertain negative paths; close exact deferred rows without treating a disabled/empty/not-configured view as positive proof.12-6 reruns the full local matrix and13-3 rechecks real devices/assets/users.
**Evidence:** T-FORM/T-CONTRACT/T-TASK/T-DOC/T-SEC/T-UX/T-QUALITY actual full specialist chain manifests and hashes,C24/X-07/X-08 deferred-control positive-negative traces and12-6/13-3 rerun ownership. Local delivery integration remains12-2/12-3; actual enterprise receipts remain13-2.
**L/R/P:** L full standalone forms proven with real three projects; R official forms/devices/model and production-recorder UAT required; P enterprise delivery/production metrics not claimed here.
