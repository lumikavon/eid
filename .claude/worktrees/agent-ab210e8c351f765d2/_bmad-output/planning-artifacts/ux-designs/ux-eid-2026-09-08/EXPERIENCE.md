---
name: Enterprise Intelligent Document Workbench
status: draft
created: 2026-09-08
updated: 2026-09-08
stage: S2
intent: create
mode: headless
approval: author self-check only; independent S2 review pending
delivery: permitted-worktree draft; main-project persistence not performed
sources:
  - D:/Desktop/eid/AGENTS.md
  - D:/Desktop/eid/.claude/bmad-interview.md
  - D:/Desktop/eid/_bmad-output/planning-artifacts/prds/prd-eid-2026-09-08/prd.md
  - D:/Desktop/eid/docs/README.md
  - D:/Desktop/eid/docs/01-软件技术规格说明书.md
  - D:/Desktop/eid/docs/02-系统架构与模块设计.md
  - D:/Desktop/eid/docs/03-数据模型与API接口规范.md
  - D:/Desktop/eid/docs/04-LLM-RAG与文档生成编排规范.md
  - D:/Desktop/eid/docs/05-安全权限审计与NFR规范.md
  - D:/Desktop/eid/docs/06-测试验收与实施计划.md
  - D:/Desktop/eid/docs/07-技术栈基线与工程规范.md
  - D:/Desktop/eid/docs/prototype/index.html
peer: DESIGN.md
assumptions:
  - Supplemental screen grouping is a UX design decision within confirmed category authorization, not separately approved new business policy.
  - Standard-browser 16px body default is a baseline test assumption; actual resolved fonts and UA defaults need verification.
  - No new named research personas are invented; journey actors are named source-role enactments, not interview subjects.
open_questions:
  - OQ-1 L2 external exception remains unconfigured and denied.
  - OQ-2 Waiver authority and required critical-Evidence threshold remain policy inputs; absent configuration blocks waiver/publication.
  - OQ-3 Public sharing and physical deletion remain disallowed; recycle retention/restore rules require explicit policy.
---

## Foundation

Desktop-first Chinese enterprise web application. [DESIGN.md](DESIGN.md) owns the visual reference, including exact source CSS and new-surface geometry; this contract owns interaction, navigation, states, accessibility and testable journeys. React/TypeScript/Vite/Ant Design is inherited from S07. Use Ant Design's semantic control behavior where compatible, without inheriting a default theme that changes the prototype. Tiptap editing JSON is not the business Document AST. No new mobile app, realtime collaboration platform, OA/e-signature replacement or unbounded autonomous agent is introduced.

Scope is all three phases across exactly `edw-web`, `edw-api`, `edw-worker`. The API's persisted business state is authoritative; worker output is a proposed/versioned result. Knowledge Gateway/LLM Gateway remain shared internal modules. The UX exposes contracts C-1–C-8 without inventing approval/bid/form endpoint paths or database schemas. This document performs no execution,external publication,production deployment,paid API use,Git commit,PRD edit or prototype edit. Current allowed worktree drafts are not main-project delivery.

**Core distinction:** Template → authorized Evidence → confirmed outline → section proposal/Patch → Claim/Reviewer checks → human decision → publication → formal export/eligible knowledge return. A task completed,review accepted,download finished or score displayed never independently means Published or trusted Golden Knowledge.

**Source conventions:** P denotes `docs/prototype/index.html`; S01–S07 are the seven numbered source documents. P-00–P-12 and SUP-1–SUP-9 are the PRD IDs. X-01–X-20 are detailed supplemental screens with full geometry in DESIGN.Components. B/R/S classification is defined there. All source paths are local,read-only inputs; no imported/generated mock files exist. For the inherited surfaces the original prototype is authoritative; for new derived mocks both spines govern. No unsupported browser-fidelity assertion is made.

### Permission model used by every control

Role labels below describe source roles, NOT newly granted permissions. A person may hold several roles, but every action requires **RBAC operation AND ABAC object scope AND classification clearance**, valid authentication,current policy,version preconditions and any required approval. A system administrator does not automatically gain content clearance,approval or waive authority.

| Code | Required capability, bounded by current object scope |
|---|---|
| V | Read current authorized project/document/template/task/source; source access checked separately from document access |
| E | Author/edit a draft or editable successor, including permitted AI requests and Patch acceptance |
| R | Assigned expert/quality Review handling; never implicitly approver |
| A | Named approver under pinned template approval policy; no universal inferred approver role |
| T | Template/Schema administration in allowed scope |
| K | Knowledge/quality-rule/evaluation administration in allowed scope |
| O | System/policy/connector administration with specific operation grant |
| D | Export/download permitted pinned content/artifact; classification and current ACL rechecked |
| W | Explicit configured waiver authority plus authorized approver and rationale; if unknown,denied |

Navigation to forbidden objects returns a generic unavailable/denied message without title,excerpt,count or existence leaks. When a user can read a resource but not perform an operation,show its control disabled with the precise allowed-to-disclose reason. New admin destinations are hidden from non-admin navigation but direct access is also denied server-side. Disabled UI is explanatory,never enforcement. Recheck authorization at retrieval,before model context,source view,citation,Patch acceptance,approval,publication,export and download. Historical permission snapshots are provenance,not access tokens.

## Information Architecture

The existing six top and side entries remain. Direct routes carry stable object IDs and version/task context; their exact route syntax is downstream implementation,not new APIs. Back restores permitted filters,selection and scroll; project changes invalidate prior-project results and subscriptions before displaying new content. No new global topnav tab is needed for specialist or administrative screens.

| ID / source entry | Landing and downstream paths | State profile / primary flow |
|---|---|---|
| P-00 Shell | `home` workbench; `editor` project documents/current authorized document; `knowledge` P-10; `templates` P-07; `review` P-08 or authorized review list; `analysis` P-11. Search/project/account X-18; notifications X-16; collections X-17. No selected document → real list/selection,not sample paper. | READ/CONTEXT; UJ-1,UJ-6 |
| P-01 Workbench | Four KPI/quad regions,recent four tabs,quick-create P-02,recommendation selected template P-07/context X-15; task/review rows go to their IDs. | READ; UJ-1,UJ-6 |
| P-02 Create | Enter from all five quick entries,template use,More complete-type picker. Valid save returns new document ID,then P-03 with X-15 context step; form type enters X-07/X-08; bid enters X-05 with draft reference. | WRITE/CONTEXT; UJ-1,UJ-4,UJ-5 |
| P-03 Editor/tree | Actual document,selection and pinned version; contextual More → X-01,X-02,X-03/X-04,X-15,X-19 and type-specific matrices. | EDIT; UJ-1,UJ-2 |
| P-04 Copilot | Same document/section; read-only answers stay here; writes → X-01; knowledge queries → P-05/P-10; missing info → P-06. | TASK/WRITE; UJ-1 |
| P-05 Evidence | Selected section/Claim's Evidence Pack; source details → X-10; conflicts → X-11; precise citation back to P-03. | SOURCE/TASK; UJ-1,UJ-3 |
| P-06 Pending | Real missing/confirmation items; Process → resolver dialog; resolved evidence/fact → linked block and recheck. | WRITE/GATE; UJ-1,UJ-2 |
| P-07 Templates | Existing three scope tabs,eight categories/cards; complete type and product-line/project filters; preview/use; upload/admin → X-14; forms → X-07. | READ/WRITE; UJ-1,UJ-3,UJ-5 |
| P-08 Review | Results for pinned doc/run; issue list/detail/trace; handling,rerun; download/share X-19; approval X-03 via contextual action,not conflated with Review. | REVIEW; UJ-2,UJ-4 |
| P-09 Review subviews | Exact tabs 审校结果=P-08,引用追溯=source/Claim linkage,版本对比=X-02,审校记录=run/disposition timeline. | READ/SOURCE/EDIT; UJ-2 |
| P-10 Knowledge | Replace only placeholder body with X-10; management X-11; retain return-to-workbench path. | SOURCE; UJ-3 |
| P-11 Analytics | Replace only placeholder body with X-12; rule/evaluation administration X-13; role-gated system config X-20 through account/admin route. | READ/ADMIN/TASK; UJ-3,UJ-6 |
| P-12 Toast/narrow note | Cross-surface toast actual result; durable tasks remain X-16; narrow note exactly source breakpoint text. | FEEDBACK; all |

| Supplement | Complete scope and screens | Source obligations |
|---|---|---|
| SUP-1 | X-01 AI Diff,selected Patch acceptance/rejection; X-02 version history/base-local-server conflict and merge | FR-6,FR-21 |
| SUP-2 | X-03 approval inbox/request/detail/history; X-04 current-version publication gates | FR-27–FR-29 |
| SUP-3 | X-05 tender intake/parse/qualification/disqualification/scoring; X-06 compliance matrix/name/parameter checks | FR-35–FR-38 |
| SUP-4 | X-07 Form Builder/version; X-08 instance/validation/print/scan/multiformat; X-09 governed integration | FR-39–FR-43 |
| SUP-5 | X-10/X-11 knowledge; X-12 quality/coverage/monthly; X-13 rules/Golden evaluation; X-20 operational governance | FR-12–FR-16,FR-31,FR-33–FR-34,FR-46–FR-47 |
| SUP-6 | X-14 template lifecycle/all types; X-15 facts/glossary/constraints/attachments/outline | FR-7–FR-11,FR-17–FR-18,FR-32 |
| SUP-7 | Shared full state contract,errors,task/notification X-16 and safe environment labels | FR-44–FR-48,NFR-1–NFR-18 |
| SUP-8 | All inert controls and demo-target fixes below; X-17 collections,X-18 search/context,X-19 export/internal link | FR-1–FR-8,FR-20–FR-30 |
| SUP-9 | All numbers,names,dates,counts,context,recommendations,Review/Evidence and success messages become real permission-filtered data or explicitly labeled development fixtures | FR-2,FR-18,FR-24,FR-33–FR-34,FR-47–FR-48 |

### Full three-phase document catalog

All types use P-02 → X-15 → P-03/P-04/P-05/P-06 → X-01 → P-08 → X-03/X-04 → X-19 → X-11 eligible-return chain unless their specialized entry is noted. A missing formal template produces a labeled development example and blocks formal use where policy requires an approved template. No hardcoded sample chapter is promoted to a company standard.

| Phase / type | Type-specific authoring and inspection requirement |
|---|---|
| 1 技术方案 | Mandatory approved-template chapters; current-project facts before historical/LLM knowledge; cross-chapter parameters/architecture claims linked to Evidence; unknown scale/ports/versions create pending items |
| 1 PRD | Structured FR-ID,name,role,scenario,prerequisites,normal/exception flows,rules,inputs/outputs,permissions,NFR and acceptance criteria; per-field missing summary linked to section |
| 1 测试方案 | Requirement ↔ Test Item ↔ Test Case ↔ Acceptance Criteria matrix; links editable with version checks; missing and redundant coverage are visible in Phase1,not deferred to Phase2 |
| 1 技术要求 | Statement fields condition,metric,threshold,verification method; vague adjectives flagged; AI suggestions cannot silently alter confirmed acceptance thresholds |
| 2 质量大纲 | Template-defined quality objectives,responsibilities,checkpoints and acceptance rows; quality-rule/version provenance and unfilled mandatory items |
| 2 项目计划 | Template-defined scope/resources/tasks/milestones/dependencies; contradictory dates/resources surfaced for confirmation rather than invented scheduling authority |
| 2 功能测试大纲 | Functional requirement/test scope/verification linkage under approved template; coverage matrix with explicit denominator |
| 2 性能测试大纲 | Workload,environment,metrics,thresholds,method/result references under template; missing workload/threshold blocks claims of validation |
| 2 项目总结 | Actual outcomes,deliverable/Evidence links,issues/lessons and acceptance references; reported outcome distinct from generated prose |
| 3 标书 | X-05/X-06 tender-derived qualification,commercial/technical,mandatory/disqualification/scoring,response mapping and residual-name/parameter checks |
| 3 生产表单 | X-07/X-08 independent Form Schema/Instance with declared fields/layout/rules; same values in Web,DOCX,PDF,XLSX,print; controlled scan/integration X-09 |

## Voice and Tone

Chinese UI copy is precise,calm and outcome-specific. Preserve source control labels/locations; replace misleading sample-result prose only within R/S authority. Never label a similarity/rerank score as a calibrated probability or proof of truth. Use readable source/status text beside baseline status pills.

| Condition | Required example copy / treatment |
|---|---|
| Create persisted/context not ready | “文档已创建，尚未完成上下文准备。” with context action; never “知识库已加载” merely on close |
| Saved / unsaved | “已保存 · {server_time} · {version}” / “尚未保存” / “保存失败，内容仍在当前页面” |
| Queue / retrieval / streaming | “排队中” / “正在检索授权资料” / “正在构建证据包” / “正在生成草稿，尚未应用” |
| Proposal ready | “修改建议待确认；正文尚未更改” with Compare; accepted only after server version acknowledgement |
| Missing info | “缺少已确认的并发规模，无法生成该关键参数。” with Resolve; not invented figures |
| Source unavailable | “来源当前不可访问，无法查看或继续引用。” No forbidden title/excerpt in error |
| Stale evidence | “引用版本已失效，请重新选择有效来源并复核。” |
| Missing threshold / waiver policy | “尚未配置必需的证据覆盖阈值，禁止发布。” / “未配置授权豁免规则，不能豁免。” |
| Disposition vs approval | “修改已应用，待复核” / “审批待处理” / “审批已拒绝” / “已发布” distinct |
| Unconfigured enterprise/model | “未配置：{allowed_reason}” with local test-double label where applicable; never “已接入” |
| Export failure | “导出失败，文档版本未改变。可查看任务并重试。” |
| Internal route | “仅复制内部访问地址；不会授予权限，不支持公开分享。” |
| Analytics no data | “尚无评估结果” or “无符合筛选条件的数据”; unknown values use em dash with reason,not zero |
| Recovery unknown outcome | “结果尚待确认，正在查询原任务；请勿重复提交。” |

## Component Patterns

Shared names match DESIGN.Components. All controls inherit State Patterns profiles plus permission codes; a control row never opts out of loading/empty/error/denial/recovery because it is small. Physical appearance uses `{components.button.height}`, `{rounded.card}`, `{spacing.gap}` etc. from DESIGN; behavioral thresholds below are UX timing choices unless explicitly sourced NFRs.

| Component | Behavior and profile |
|---|---|
| Shell navigation | READ/CONTEXT; route only authorized destination,keep active state synchronized; project change verifies leave/save and scope; unread count is authorized task/notification count |
| Button and input | WRITE or READ by action; native keyboard semantics,visible label,validation summary; prevent duplicate pending submission; no optimistic critical-success state |
| Tabs and filters | READ; selected tab is URL/history-restorable UI state,not business state. Search/category/type/scope filters intersect; reset selection when selected result leaves scope; retain typed filter on error |
| Data list/table | READ; columns remain labeled; keyboard row-open separates row selection from action clicks; pagination has total/page controls and preserves filters; no phantom fixture rows on empty |
| Status and task card | TASK; state from durable API record; task ID,category,step,created/updated,attempt,error,trace and result reference; retry/cancel only when server permits; no timed fake completion |
| Metric summary | READ; attach scope,time window,definition/version,denominator,run and freshness. Unknown ≠0; inconsistent/noncomparable definitions show no delta. Gauge ring decorative,number/table authoritative |
| Document canvas and toolbar | EDIT; stable section/node IDs,selection-scoped changes; no unsanitized generated HTML. Autosave after1000ms typing idle (UX debounce),separate from server-save P95; explicit Save in More or Ctrl/Cmd+S. Keep in-memory unsaved content on failure; no assumed sensitive local persistence |
| Copilot and prompt | TASK/WRITE; visible operation,target section/selection and context preview before submit; unconfigured/forbidden route disabled; read-only operations never produce automatic document writes; writes become Diff |
| Evidence and source viewer | SOURCE; actual Claim/Evidence bindings/source locator/version; current ACL/freshness rechecked; denied excerpt cleared; contextual/conflicting evidence visibly differentiated from supporting evidence |
| Pending item resolver | WRITE/GATE; location,reason,owner if assigned,proposed resolution,history; resolve with confirmed fact/Evidence and revalidation; exceptions require explicit W policy and audit,no hide-on-click |
| Template browser/editor | READ/WRITE/ADMIN; selected version detail/outline/preview consistent; deprecation does not mutate pinned documents; publish requires valid template and authority; no physical removal of referenced formal versions |
| Issue inspector | REVIEW; selected issue ID/location/quote/impact/suggestion/Evidence change together; accept/reject/modify/handled semantics below; old run remains inspectable with stale-version warning |
| Dialog and toast | WRITE/FEEDBACK; focus trap,accessible name,return focus on close; cancel closes idle modal without write; Escape while submitted does not cancel accepted server work. Toast only supplemental,never only error/task evidence |
| Diff and version comparison | EDIT/GATE; compare known base to proposal/latest; only selected compatible Patch accepted; Reject preserves body; three-way conflict uses explicit choices/new checked version; Published cannot mutate in place |
| Approval and release gate | GATE; request pins version,policy and assigned approvers; decision audit includes rationale; release rechecks all gates; stale/expired/unconfigured approval cannot release |
| Tender workbench | TASK/WRITE/REVIEW; parse result is proposed extracted requirements; correct against source with provenance; partial document cannot claim completed analysis; mandatory gaps remain release blockers |
| Form Builder | WRITE/ADMIN; schema separate from document AST; palette/keyboard insertion,reorder,typed properties and rule checks; AI changes diff before accept; active schema immutable version reference |
| Form instance and scan | WRITE/TASK; frontend/backend validation parity; formula whitelist only; scan is user-triggered,extracted values reviewed before write; identifier lookup independently authenticated |
| Export and artifact viewer | TASK/SOURCE; request pins version/format/render-theme; only complete permitted artifact downloadable; each download fresh ACL; preview not publication; draft export labeled as draft when allowed |
| Knowledge and conflict management | SOURCE/WRITE/GATE; enterprise source stays authoritative; metadata/return governance not unauthorized source edit; conflicts show competing versions and resolution audit |
| Analytics and evaluation | READ/ADMIN/TASK; rule/dataset/run versions pinned; real vs deterministic fixture distinguished; excluded/failed cases and denominators retained; no score generated from illustrative values |
| Administration and policy | ADMIN/GATE; granular permission/version checks,validation and auditable apply; no raw secrets/no bypass controls; Feature Flags cannot grant rights or disable mandatory gates |
| Context and outline | WRITE/TASK/GATE; facts/glossary/reference/constraints/missing fields persisted; proposed outline confirmed explicitly; mandatory sections cannot be removed without allowed template rules |

### Original control manifest and R/S replacements

The selectors/labels here are the full operational manifest for the source's controls and intended entries. A repeated control uses its containing surface/row ID as part of its identity. Preserve literal source glyphs in implementation (DESIGN.Shapes); labels below omit decorative glyphs. Decorative numbers,hero art,status spans and metadata are not invented as write controls. Where an inert span/div becomes an action,use button/link semantics without changing resting geometry.

| Group / exact selector or label | Required interaction,permission/profile and recovery |
|---|---|
| C00 `[data-page]` all six values `home,editor,knowledge,templates,review,analysis` in top/side | V/READ; switch to authorized real route; show `#docTree` only editor. No selected doc/run → list picker. Preserve selected nav and return path. P placeholder Return `[data-page=home]` remains home navigation. |
| C01 `#globalSearch` placeholder 搜索文档、知识或功能... | V/READ; Enter submits ACL-filtered document,knowledge,function results X-18 with entity type/project/version; empty input does not issue search; no matches explains scope/reset. Source toast-only search is replaced. |
| C02 `.side-title` project chevron,`.project-card` | V/CONTEXT; open permitted project picker,choose stable ID; dirty editor offers Save/Stay/Discard current unsaved edits explicitly; inaccessible project not listed; restore prior scope on failed change. |
| C03 `.bell`,`.avatar`,`.uinfo` | V/READ; bell X-16 unread/open/mark-read actions on actual records; account shows authenticated name/department/roles and sign-out via IdP session flow; O-only admin entry X-20; expired session requires reauthentication,not shared credentials. |
| C04 sidebar 我的收藏 /参考资料 /回收站;count/storage area | V/READ; favorites X-17 has open and toggle favorite (WRITE); references show authorized originals/attachments and X-15 upload; recycle shows policy-permitted lifecycle history only,no physical delete. Restore control unavailable until policy permits. Usage has bytes/limit/timestamp or unknown,not sample26%. |
| C05 P-01 four KPI labels 本周新建文档/已完成审校/AI 生成字数/质量均分 | READ summary; real data and comparable previous period; definition tooltip/focus detail. Source numbers12/8/28560/4.6 are fixtures; no mandatory click action fabricated. |
| C06 quad 待办文档/最近项目/审校提醒/模板快捷入口 + each 更多 | V/READ; rows open respective document/project/review/template IDs. Each More opens its full filtered list. Sample names/deadlines/statuses not copied as live tasks. |
| C07 `.recent-table .tabs` 最近文档/我创建的/我参与的/我的收藏;table rows | V/READ; intersect project/permission with selected ownership relation; rows open own document; real empty/result counts and loading. |
| C08 five `[data-create]` values | E/WRITE; 项目投标文件→标书;产品需求文档（PRD）→PRD;云桌面系统总体技术方案→技术方案;软件测试方案→测试方案;项目总结报告→项目总结. Quick labels remain 新建标书/新建 PRD/新建技术方案/新建测试方案/新建项目总结报告. Persist actual selected type; title/name default are editable suggestions. |
| C09 快速新建 更多;AI 推荐 换一批;recommendation 使用/创建 | More opens complete catalog above; authorized recommendation card includes reason/source/template/model mode; refresh is real read/task not randomized fake data. Use/Create selects that record then P-02; unavailable template disabled with replacement chooser. |
| C10 `#modalTitle,#modalDocName,#modalDocType`,unnamed scope select,`#modalCancel,#modalCreate` | E/WRITE; preserve labels 文档名称/文档类型/参考知识范围; name trimmed and required (no silent 未命名文档 fallback). Source types 技术方案/标书/PRD/测试方案/项目总结 remain,complete catalog supplemented. Scope options exact 当前项目 + 企业技术库 + 质量库 /仅当前项目 /全部有权限知识; “全部” never broadens ACL. Template/version chosen explicitly or visibly supplied from initiating card; valid missing selection leads picker. Cancel no write; Create persists new ID/AST/type/scope/template before editor,failed form retains inputs. |
| C11 `#docTree` root and all chapter controls | V/READ; root opens document top; chapter chooses stable section and updates Copilot/Evidence target; parent chevrons expand/collapse,not generate. Source fixture labels: 云桌面系统总体技术方案;1.项目概述;2.建设目标与需求分析;3.总体技术方案;3.1总体架构;3.2关键技术;3.3部署方案;4.实施计划;5.安全与运维保障;6.项目预算;7.风险分析与应对;8.总结与展望. Real tree follows AST; do not duplicate the source mismatch “建设需求与分析” as a live separate chapter. |
| C12 `.paper`, `#docTitle,#crumbTitle`,doc-top status/time/version/quality | E/EDIT or V read-only. Heading edit governed by AST; metadata not arbitrary contenteditable data. Title/breadcrumb sync only on accepted version. Version opens X-02,quality opens actual run/details; absence shows not evaluated. Source blanket contenteditable replaced with typed AST adapter preserving visible structure. |
| C13 toolbar first two tools undo/redo | E/EDIT; editor-local history bound to current editable version,disabled when history empty; version change requires deliberate merge/reload rather than replaying obsolete operations. |
| C14 toolbar 正文 /14 /B /I /U /A /alignment symbol /list symbol | E/EDIT; style selector chooses permitted body/heading levels; size chooses allowed values; bold/italic/underline toggle selection; A opens permitted text color; alignment and list menus apply only selected block(s). No selection defaults to current caret block; forbidden schema operation disabled. Source buttons remain same order and visual footprint. |
| C15 toolbar link /table /image | E/WRITE; link dialog validates safe URI schemes and label; table chooser inserts schema-valid table and row/column/header controls via contextual menu; image upload uses X-15 validated artifact,alt text and intrinsic aspect ratio. Invalid/unsafe asset never inserted; no arbitrary fetched external resource. |
| C16 `#insertCite` 插入引用 | E+source V/SOURCE; capture current selection/node/bookmark,open authorized Evidence picker,show source/version/relationship,confirm binding; selection stale → reselect. Replace prototype insertion into first `.paper p` and `[NEW-EVIDENCE]` fake marker. |
| C17 toolbar 更多 | V/E/D/GATE according to child; explicit Save,version history,AI Diff,context/outline,attachments,Review request,submit approval,publication gate,export/internal link,type traceability; Copilot extended operation menu below. Unauthorized child disabled/hidden by the shared rule; no additional arbitrary toolbar rearrangement. |
| C18 three `[data-aitab]`: `copilot,evidence,todo`; matching panels;`#aiBody` | V/READ; preserve tab text AI Copilot/知识引用/待确认项 and selected section; actual pending count; no task cancellation on tab switch. |
| C19 six `[data-ai]` exact 生成本章节/续写内容/改写为技术要求/检查事实/总结本章/润色优化 | E for write, V+allowed AI for read/TASK. Generate whole target section;Continue after selected endpoint;technical rewrite/polish target selection or confirm whole section;Check facts creates findings not body mutation;Summary returns answer,Insert requires a Patch. All show target/context,model/Prompt mode and task identity. |
| C20 `#aiPrompt,#sendAi,#aiResponse` | Allowed AI/TASK; blank send disabled; Enter newline,Ctrl/Cmd+Enter send,IME safe; chosen intent and target confirmed where write-like. Untrusted output rendered safely. Replace fixed response/unsafe innerHTML with persisted streaming/proposal/error; no simulated success. |
| C21 Copilot knowledge 更多,`.evi-item`,quality rows/score | V/SOURCE/READ; More opens full Pack; citation/source rows actual source viewer; quality drilldowns pinned run/requirement coverage/pending list. Stale results labeled; no fabricated supporting sources. |
| C22 P-06 three 处理 buttons | E or responsible assigned grant/WRITE; bind actual item ID,not row text. Original examples final concurrency/external access/license mode remain labeled fixture cases only. Resolve needs confirmed value/source; external-policy matter cannot be solved by granting model route in this dialog. |
| C23 `#templateSearch`,type select,`.seg-tabs`, `#chips` | V/READ; AND-combine search,scope,category,type; scope source 企业模板/部门模板/我的模板; type source 全部类型/技术方案/PRD remains supplemented; chip source 全部/标书/PRD/技术方案/测试方案/技术要求/质量大纲/项目计划/生产表单. Product-line/project scope appears in additional filter,not removal of original tabs. Phase2 missing types added to complete type chooser. |
| C24 eight `.tcard[data-name]`,cover/detail selection | V/READ; names: 项目投标文件模板;产品需求文档（PRD）;云桌面系统技术方案模板;软件测试方案模板;产品技术要求模板;项目质量大纲模板;项目计划书模板;生产过程记录表单. Selection updates `#detailName,#detailType,#detailCover` AND all tags,scope,usage,date,description,chapter count/outline and version. Loading selection clears stale detail actions. |
| C25 each card 预览/使用模板,detail 预览模板/`#detailUse` | V preview;E use/WRITE. Preview actual selected version,not static bid outline; Use stop-propagates row event,opens P-02 pinned to that template and creates a new record,not renaming the old paper. Default bid12 chapters are fixture outline only; real outline follows selected template. |
| C26 `#uploadTpl` 上传模板 | T/ADMIN/TASK; X-14 upload/version validation,progress/rejection and preview; no toast-only completion. Insufficient permission gives reason; deprecated/invalid version cannot become formal-use version. |
| C27 Review 下载文档/分享/`#rerunReview` | D X-19;internal route only;R/E where permitted starts real pinned-version Review task. Prior run stays visible with “旧版结果”; completed only after server task state. |
| C28 Review tabs 审校结果/引用追溯/版本对比/审校记录 | V/READ; results,Claim↔Evidence trace,actual version comparison,run/disposition history respectively. Preserve selected doc/version/filter context; approval remains distinct. |
| C29 `.filter` 全部（12）/严重（2）/一般（6）/建议（4）;chapter/status selects;keyword input | V/READ; exact semantic labels and geometry retained,counts live; intersect severity,section,state,keyword; counts share pinned run/visible scope. No color+toast-only filtering; source7 rows vs12 totals corrected with actual records. |
| C30 `.issue[data-issue="0"…"6"]` | V/REVIEW; source fixtures 事实缺少依据/客户名称不一致/指标描述模糊/章节缺失/表述不够严谨/引用过期版本/专业术语不统一 become regression cases. Select updates `#detailSev,#issueTitle,#issueLoc,#issueDesc,#issueQuote,#issueSuggestion`,issue number,impact tags and trace source/count/scores together; pending fetch never leaves actionable previous issue. |
| C31 `.issue-action[data-act="接受"]` | E+R required by policy/REVIEW+EDIT; inspect intended suggestion Patch; validate source/base,apply selected Patch to new version; record accepted then recheck. If no machine-applicable Patch,route to correction editor,never fake applied status. |
| C32 `.issue-action[data-act="拒绝"]` | R/REVIEW; require rationale/evidence,record rejected disposition,content unchanged. Rejecting finding is NOT automatic severe-gate clearance; justified reviewed adjudication must satisfy current policy. |
| C33 `.issue-action[data-act="修改"]` | E/EDIT; open correct block with issue context,retain issue link,save new version,then recheck. No immediate done state. |
| C34 `.issue-action[data-act="标记已处理"]` | R/REVIEW+GATE; requires checked correction or explicitly permitted W exception; server verifies severe gates. Denied/no resolution → item stays open. Waive cannot bypass non-waivable severe safety rules. |
| C35 `.trace .source` and source/count/score | source V/SOURCE; open actual selected supporting/conflicting/contextual passage; source “置信度92/78/65%” replaced by properly labeled score kind/raw scale if available,not invented probability. Show no score when unavailable. Current-source denial clears excerpt and prevents citation/export. |
| C36 `#toast`,`.mobile-note`,modal cancel/backdrop | FEEDBACK; original1800ms toast/200ms transition retained for transient outcome; failures/tasks persist elsewhere. Narrow note exact “建议在 1180px 以上桌面浏览器查看此原型。” Source modal backdrop did not close; keep backdrop non-dismissal. Escape is accessible supplement with dirty/pending rules; Cancel explicit. |

### Supplementary controls and data contracts

Each row has complete field/action/state obligations. Apply READ/WRITE/TASK/SOURCE/EDIT/GATE/ADMIN profiles as marked,including every add/remove/filter/preview/retry child control. IDs shown are conceptual UI fields from sources; exact wire shape remains S03/downstream contract work.

| Screen | Fields and actions | Permission,validation,failure/recovery |
|---|---|---|
| X-01 Diff | document/section,base version,revision,generation_run_id,model/Prompt/Evidence Pack,input/output hashes,token usage; changed-block list,before/after,Claim/evidence/assumption/missing flags; select changes,Accept selected,Reject selected,Open base/latest | V+E/EDIT/GATE; reject affects proposal only; selected operations must remain valid as a subset,otherwise explain dependent changes. Acceptance atomic for selected compatible set; unknown outcome query original action,not resubmit. Changed base → X-02. |
| X-02 versions/conflict | history rows version,author,time,source type,Review/approval relation; two version selectors; diff; conflict base/local/server tab; per-block keep local/use latest/manual merge; Save checked merge/Open latest read-only | V/E/EDIT; show all conflicting stable node IDs; no blanket last-write-wins. Revoke E → retain only policy-allowed in-memory draft,block submission. Published history immutable; permitted edits create successor. Save against latest base can conflict again and returns here without losing choices. |
| X-03 approval | inbox status/project/type/date filters; request ID,version,template/approval policy,requester,assigned approver,history; candidate preview,Review/pending/gates,required confirmation; Submit request,Approve,Reject with reason | E submit,A decide/GATE; policy selects approvers/order,not arbitrary self-assignment. No policy/no eligible approver → blocked. Record each decision and actor; rejection returns actionable author review without inventing new lifecycle enum. Candidate edit makes approval stale; submit new version for required revalidation. |
| X-04 publication | version/template/current-policy summary; checklist below; inspect failed row,confirm version,Publish; result published ID/time,export and knowledge-return links | Authorized publication grant/GATE; mandatory server recheck and audit. No configured required coverage threshold → blocked,never default0/100. Approval unavailable/stale → blocked. Pending response checks original publish action; duplicate cannot double-publish. |
| X-05 tender intake | tender/bid/project/customer identity,source version,classification,file; Upload/Parse/Retry; source page/section; extracted requirement ID,type(qualification/commercial/technical),clause text,mandatory flag,disqualification/scoring fields,source locator; Confirm/correct/save-version | E/TASK/WRITE/SOURCE; media/size/resource limits from configured policy; partial parse shows processed/failed pages and unresolved extraction,not complete. Corrections preserve original extracted text/provenance and actor. Tender instructions untrusted. |
| X-06 compliance | matrix columns requirement ID/type/clause/source+version/mandatory or disqualification/scoring rule+max if declared/response section+version/Evidence/status/owner if assigned; filters and linked row details; Map/unmap response,Open source/response,Run checks,Export matrix | E/R/D/WRITE/REVIEW/TASK; UI statuses unmapped/partial/supported/conflicting/pending-confirmation are display mapping,not new backend enums. Scores only from declared rule; unknown/max not given → no score. Unmap requires confirmation,history retained. Export includes current tender/response/matrix versions and gate outcome. |
| X-07 schema | schema ID/name/scope/version/status,layout/print settings; palette11 field types; selected key,label,type,required/default/help,options,min/max,pattern if supported,formula dependencies,repeating columns and declared validation; Add/reorder/duplicate/remove,AI propose,Validate,Preview,Save version,Activate permitted version | T/ADMIN/WRITE/EDIT; unique stable keys,type-compatible defaults,allowed rule syntax,formula cycle/reference checks. Removal of referenced field lists affected instances; no mutation of prior saved schemas/instances. AI uses X-01; activation policy required; draft invalid schema editable but cannot activate/produce formal output. |
| X-08 instance | schema/version/instance identity/project/classification; text,number,date,select,checkbox,signature,image,barcode/QR,formula,repeating table; add/remove row,attach,signature capture,Save,Validate,Preview/Print,Export,Scan/Upload scan,Review extraction,Send | E/D/WRITE/TASK; values/errors per field plus summary; frontend/backend parity; formula read-only computed,whitelist,no arbitrary code. Signature is a data field,not certified e-sign. Barcode identifies authorized record/version,never grants access; wrong/unknown/version-mismatch scan requests selection/confirmation. Duplicate scan doesn't overwrite. Invalid save retains last valid server instance and unsaved current input. Print/send do not bypass required approval. |
| X-09 integration | connector contract/target/environment/mapping version; artifact/doc/form approved version,classification; delivery/inbound records with correlation,idempotency,outbox/inbox task,attempts,status/receipt; inspect sanitized payload mapping,Retry,Reconcile received vs applied | O or specifically assigned delivery operator/TASK/GATE; only declared contract. Unknown enterprise endpoint “未配置”; local adapter “本地契约替身”. Timeout/partial delivery query receipt/correlation first; retry same business identity,no duplicate external application. Permanent failure inspectable; no blind retry of invalid payload. |
| X-10 knowledge | query,domain,project/customer/product,validity/version/classification,source class; enterprise/authorized attachment/Golden tabs; title/version/effective dates/authority/locator,excerpt,relations,retrieval/rerank score kinds,permission-policy identifier/snapshot hash; search/open/cite/attach/create Pack | V/source V/E as needed/SOURCE/TASK; filters cannot broaden ACL; exact identifiers use supported keyword path as well as semantic query. No unauthorized metadata. Pack shows insufficient support/dedup/source versions. External/LLM material cannot masquerade as formal enterprise evidence. |
| X-11 governance | freshness/conflict/return tabs; two statements and locators,authority/context/validity,affected Claims; disposition/evidence/reason; mark pending/request correction/select permitted resolution; return candidate gate/run/provenance | K/R/E limited/WRITE/GATE/SOURCE; prefer higher authority but never hide conflict. Source-owned enterprise documents are not edited here. Only eligible Published content proceeds to quality-gated return; AI draft/unapproved document denied. Return failure doesn't unpublish; duplicate return is reconciled by formal version identity. |
| X-12 quality | project/type/date/version filters; metric definition/rule version,numerator/denominator,sample/time,result freshness; quality components/Claim support/requirement-test coverage/Reviewer outcomes/monthly rows; drill down,authorized report export | V/D/READ; no data ≠zero; no definition → not configured; score weights are recommendations until approved. Delta only same definition/comparable cohort; report preserves filters/versions. Monthly improvement order Knowledge→Template→Retrieval→Prompt→Reviewer→Model. |
| X-13 rules/eval | rule ID/kind/severity/applicable type/scope/version; permitted structured condition/settings not arbitrary executable script; dataset/domain/query/expected evidence/adjudication/injected defect; Add/edit/version,Validate,Run,Compare,Inspect case | K/ADMIN/TASK; per-domain50–200 Golden Queries from S06; freeze model/Prompt/template/retrieval/reranker/batch/max-length/device/dictionary/rule/dataset versions. Run kinds deterministic-local vs real endpoint explicitly distinct. Unknown real endpoint blocks real run,not local contract use. Errors/exclusions remain in denominator manifest. |
| X-14 template admin | metadata,name,type,company/department/product-line/project/personal scope,classification,version; mandatory sections,chapter rules,retrieval/Prompt/Reviewer references,render theme,approval policy; Upload/Validate/Preview/Save version/Publish/Deprecate | T/ADMIN/TASK; missing/unapproved references prevent formal publication; preview official vs development example label. Deprecation confirms impact and retains pinned references; no physical delete of formal-used version. Version conflict X-02,not overwrite. |
| X-15 context/outline | workspace,intent,template,project facts(value/unit/source/confirmed state),glossary,reference docs,similar formal documents,constraints,missing info; attachment list(upload/parse/OCR/index state); Edit confirmed context,Build context,Propose outline,reorder/add/edit where allowed,Confirm outline,Generate selected/all sections | E/WRITE/TASK/GATE; mandatory sections protected; proposed outline visibly separate; missing key input routes P-06. Context/model token budget reason shown as summary,not raw unbounded Prompt. Source3–10 subqueries per section exposed on diagnostic detail; no vector-only exact-ID assumption. |
| X-16 tasks/notifications | task category,state,step,progress if known,attempt,retryability,created/updated,trace; Open task/result,Retry/Cancel supported; notification Read/Mark read/Open target | V/specific task-operation grant/TASK/WRITE; all terminal failed,cancelled,timeout,dead-letter states inspectable; stale event reconnection banner. Mark read only affects notification,not task/issue resolution. |
| X-17 collections | authorized favorite/reference/retained lifecycle records,type,project,version,date,state; filter/open,toggle favorite; policy-governed restore where configured | V/E relevant/READ/WRITE; no physical Delete/public link; policy missing restore disabled. Archived content remains immutable/history-readable if currently permitted. Source recycle label retained without fabricated retention period. |
| X-18 context/search/account | project list/search,global results type/title/context only if permitted; account identity/department/roles/clearance; select project/open result/session sign-out; O-only membership policy view | V/O/CONTEXT/ADMIN; validate all deep links; session expiry does not lose current in-memory draft automatically,reauth same scope then reconcile version. Sign-out with unsaved edits offers safe save/stay,not silent discard. |
| X-19 export/share | document/form/version,format(DOCX/PDF/HTML/Markdown;forms also XLSX),render theme,classification/watermark/approval-page/appendix availability; Request,Preview,Download,Retry,Copy internal address | D/TASK/SOURCE/GATE; formal export requires policy/gates and approved version; permitted draft export prominently marked draft. Theme/font missing → blocked or labeled development-only preview,never fake corporate style. Download checks fresh ACL/expiry; regenerate expired artifact under current policy. Internal copy does not grant access or create public link. |
| X-20 governance | role/scope/clearance matrix; Model Profile(capabilities/context/latency/cost/security eligibility); Prompt template/version/variables; routing/DLP allow policy; connector contract/config references; audit filter/trace; Feature Flags(target scope/version/default/owner/change reason); retention/TTL reference | O with specific grant/ADMIN/GATE; validation,version diff and audit before apply; no plaintext secrets. Unconfigured external allow denies,L3 external prohibited,L2 internal default. Feature Flag off gives explicit unavailable function; flag on cannot change ACL,waive,release gate or deployment authorization. Audit unavailable blocks permission/approval/publication-critical changes. |

### Publication and trusted-return gates

X-04 uses a row per gate with state `checking/pass/fail/not-configured/stale`,source version/timestamp and actionable link. These are display states,not a new document lifecycle. Server verifies again atomically at transition.

1. Mandatory chapters complete → X-15/P-03.
2. Severe ReviewIssues =0 → P-08,including rejected/handled items not yet legitimately cleared.
3. Pending items closed or explicitly policy-approved exceptions → P-06; no exception to non-waivable severe safety gate.
4. Configured critical-Evidence coverage threshold exists and is met → P-05/X-12; missing configuration blocks publication.
5. Severe unsupported critical Claims =0 → P-08/P-05.
6. No known unresolved KnowledgeConflict → X-11.
7. No unauthorized or invalid references at current access/freshness check → P-05.
8. No sensitive-data/security policy violation → P-08/X-20 authorized diagnostics.
9. Valid approved/non-deprecated-for-use template and render prerequisites → X-14.
10. Required human confirmation AND completed valid approval for this pinned version → X-03.
11. Critical audit available and required record can persist → controlled retry; no bypass switch.

Published-triggered trusted return is a separate quality-gated task (FR-31): eligible formal Published version +valid approval/provenance/current policy → quality gate → parse/chunk/enrich/return → durable result. It cannot be triggered for draft/AI draft/unapproved versions. A failed return keeps the formal document Published but marks return failed; retry retains originating version and deduplicates. Do not promise newly returned knowledge is searchable until authoritative receipt/index availability is confirmed.

## State Patterns

### Global contract G — mandatory for every surface and control

| State | Required behavior and recovery |
|---|---|
| Cold loading | Keep shell/current allowed context,show shape-matched noninteractive placeholders with “加载中”; no sample data. Delay decorative spinner only if useful; never delay essential status. Skeleton isn't selectable content. |
| Refreshing/stale read | Keep last authorized read visibly stale with last-update time; disable version-sensitive mutation until current validation. Never display previously forbidden data after revocation. |
| Empty initial | Explain entity absence with one permitted create/configure action; if user lacks create,offer scope/navigation not false affordance. |
| Empty filtered | Preserve filters and input,show “无符合筛选条件的数据” plus reset; do not clear existing records. |
| No selection | Explain select-a-record/section prerequisite; detail/action controls disabled; don't silently target first paragraph or last source. |
| Focus/hover/pressed | Keyboard focus visible,active tab/row programmatic; hover-only actions also focus/touch accessible. Selection alone never performs a write. |
| Invalid input | Field-level error plus linked summary,retain entered values and last good saved state. No request if known invalid; server errors authoritative; permissions cannot be validated only client-side. |
| Submitting | Keep inputs visible,lock duplicate action,show submitting; no success status before acknowledgement. Retain request/task correlation for unknown outcome. |
| Queued/running/streaming | Durable task card,actual category/step; unknown duration indeterminate. Streaming output provisional/sanitized/not persisted accepted content. No progress percentage inferred from elapsed time. |
| Partial | Explicit which pages/sections/fields succeeded/failed; partial result view-only/proposal unless validated; completion gate remains unmet. |
| Success | Announce actual effect +ID/version; toast supplemental. Navigate only after authoritative record exists; keep provenance/history. |
| Rejected/denied | Operation rejected keeps prior business state; generic not-found/denied for unauthorized read. Do not show cached forbidden content,raw error payload or tokens. |
| Offline | Persistent banner; manual editing may continue in memory on already open allowed draft,marked unsaved. No promise of automatic cross-session/browser persistence. Critical writes disabled; reauthenticate/refresh version before retry; no naive queued release replay. |
| Degraded | Identify unavailable dependency and surviving actions per table below; no fake success/verified content. |
| Error/timeout/unknown | Specific allowed reason +trace/task ID +safe retry/inspect action. Unknown result queries original record/correlation first; do not repeat side effect automatically. |
| Session revoked/expired | Block writes; clear inaccessible content on confirmed revocation; reauthentication for expiry; recheck ACL and version before restoring views. Sensitive unsaved data never exported to another location as recovery. |
| Stale version/conflict | Preserve unsaved local/proposal/base in current session where permitted; display latest separately; route X-02; no silent overwrites or approval inheritance. |
| Cancel | User may cancel idle dialog without write; cancel running task only server-supported and audit; “取消请求中” until acknowledged. Completed task winning race remains completed,not hidden. |
| Retry | Honor retryability,bounded policy and same logical operation identity; permanent invalid/denied requires correction,not loop. Failure stays inspectable. |
| Recovery | Rebuild from persisted API state; reconcile partial/duplicate events and outputs. Missed toast/SSE never loses work or proves completion. |

### Profiles apply G without omission

- **READ:** G loading/refresh/empty/no-selection/focus/error/denied/offline; retry reissues scoped read; no mutation success for navigation.
- **WRITE:** READ +validation/submitting/unknown/duplicate/stale/save result; inputs retained,policy/current-version checks,success only acknowledged.
- **EDIT:** WRITE +in-memory dirty state/undo/history/AST validation/optimistic conflict; generation never directly overwrites.
- **TASK:** WRITE +queued/step/stream/partial/cancel/retry/terminal history/reconnect; durable identity.
- **SOURCE:** READ +current source authorization/freshness/validity/redacted unavailable state; citation WRITE preconditions.
- **REVIEW:** TASK +pinned-run/results/selected-issue state/distinct dispositions/recheck/stale severity gate.
- **GATE:** WRITE +all current prerequisites/configuration/audit checked; denial/unknown fail closed; never optimistic approval/publication.
- **ADMIN:** WRITE/GATE +fine-grained grant/version/impact/reason/audit; missing config not assumed permissive.
- **CONTEXT:** READ +dirty-leave confirmation/scope invalidation/reauthorization; keep previous context on failed switch.
- **FEEDBACK:** G focus/accessibility/persistence; toast not sole error/state; no content acquisition or side effect merely on appearance.

### Surface-specific loading,empty,failure and recovery additions

| Surface(s) | Empty/prerequisite | Loading/partial | Error/denial/recovery beyond G |
|---|---|---|---|
| P-00/P-01/X-18 | No project → permitted picker/create request path; no docs/tasks→empty rows; no metrics→not measured | Load each panel independently,scope change clears old cache | Search failure retains query; denied search no count leak; expired identity sign-in then scope refresh |
| P-02 | No valid template → picker/development-only explanation; missing name field error | Creating blocks second submit;context pending after created | Failure retains form;unknown result queries create identity;never rename already open doc |
| P-03/X-02 | No document/selection→list/prompt;Published→read-only | AST loading no blank editable paper;save pending explicitly | Invalid AST retains prior saved version;revision conflict three-way;offline in-memory unsaved;failed merge retains choices |
| P-04/X-01/X-15 | No Evidence/outline confirmation/model→specific blocker | Separate context/retrieval/Pack/planning/queue/generation/validation/Diff | One structured-output repair attempt only,then failed with context;model denied no provider bypass;stale Patch compare |
| P-05/X-10/X-11 | No supporting source→unknown/unsupported with pending route | Pack building with per-source status;partial not formal support | Revoked/stale source cleared/flagged,reselect and recheck;conflict cannot be hidden by choosing higher score |
| P-06 | No pending items→actual zero+scope/version | Resolving preserves row until server/recheck | Missing confirmation retains item;unauthorized exception denied;concurrent change refresh item history |
| P-07/X-14 | No authorized matching template→reset or T upload;detail unselected | Upload/validate/preview distinct | Invalid/deprecated prevents use;failed preview no fake cover-as-render;version conflict new version workflow |
| P-08/P-09 | No run→Start permitted Review;no findings≠not run | Individual Reviewers incomplete→overall incomplete | Reviewer failed/dead-letter visible;old run readable but not current certification;Issue action requires current target/recheck |
| X-03/X-04 | No approval policy/approver/threshold→not configured block | Request/decision/gate evaluation distinct | Audit outage blocks;stale candidate approval doesn't transfer;rejected decision visible author correction path |
| X-05/X-06 | No tender→upload;unmapped requirement→missing response | OCR/parse per-page progress,partial requirement set | Parse failure inspect/replace file;disqualification/scoring unresolved stays risk;matrix links inaccessible source denied |
| X-07 | No schema→manual draft or AI proposal if permitted | AI schema proposal/validation separate | Bad formula/keys/cycles block activation;unknown type no arbitrary component execution;conflict version compare |
| X-08 | Missing required value→field summary;no saved instance→draft | Save/scan/render/delivery distinct | Invalid server result preserves last valid record;wrong scan schema/version asks selection;camera denied offers file scan if permitted |
| X-09 | No declared target/contract→not configured | Queued/attempting/receipt pending/partially delivered | Timeout check correlation before retry;duplicate receipt no second apply;permanent failure corrected mapping/new controlled attempt |
| P-10/P-11/X-12/X-13 | No metric/dataset/rule→not evaluated/configured,not zero | Eval queue/run with case progress if real | Failures/exclusions retained;incomparable versions disable misleading delta;real endpoint pending not a failed local-double test |
| X-16 | No tasks/notifications→empty | Reconnect/replay explicit,task selected loads independently | Missing event rebuilds snapshot;failed/cancelled/timeout/dead-letter not endless spinner |
| X-17 | No favorite/reference/retained lifecycle record→empty | Scoped load;favorite toggle pending | Retention/restore policy absent → no restore/delete;server conflict reload;access revoked removes item |
| X-19 | No valid output→Request export;no theme/font→reason | Queued/rendering/validating/result separate | Failed output not downloadable;expired artifact regenerate current allowed version;denied download no signed URL reuse |
| X-20 | Missing model/Prompt/DLP/connector/flag policy→not configured | Version validation/apply/audit pending | Reject unsafe allow/unknown route,keep prior valid policy;permission/audit failure never applies partial authorization |
| P-12 | No result→hidden toast;note only correct breakpoint | Live task status elsewhere | Dismissed toast does not delete error/task;reduced motion stops nonessential transition while retaining message |

### State vocabulary and error mapping

Document lifecycle: `DRAFT → CONTEXT_READY → OUTLINE_READY → GENERATING → REVIEWING → USER_REVIEW → APPROVAL_PENDING → PUBLISHED → ARCHIVED`; exceptions `GENERATION_FAILED,REVIEW_FAILED,EXPORT_FAILED,BLOCKED_BY_MISSING_INFO`. Show these as distinct business statuses; an export failure does not change saved content version. Human rejection returns the appropriate existing author-review state plus rejection reason,not an invented auto-published transition.

Orchestration: `CREATED → PREPARING_CONTEXT → CONTEXT_READY → PLANNING → OUTLINE_READY → GENERATING → REVIEWING → USER_REVIEW → COMPLETED`. Section tasks: `PENDING → RETRIEVING → EVIDENCE_READY → GENERATING → VALIDATING → DONE`,also `RETRY_WAIT,FAILED,BLOCKED,CANCELLED`. Do not infer a document transition from a task label.

Claim states `supported,partially_supported,conflicting,unsupported,unknown`; Evidence relation `supports,conflicts,contextual`. A citation count alone cannot make a Claim supported. Inspect type,value/unit/condition,location,criticality,binding and validation provenance. ReviewIssue states `open,accepted,rejected,fixed,waived,closed`; display “已应用待复核” for accepted correction until verified. Fixed/closed requires checked resolution; waived requires explicit W and does not erase severe non-waivable blockers. No Reviewer self-approval of its own severe findings.

| Contract error | UI destination and allowed recovery |
|---|---|
| `DOC_VERSION_CONFLICT` | X-02; preserve local/proposal,compare latest,reapply only through current base_version_id + document_revision |
| `TEMPLATE_DEPRECATED` | P-07/X-14; select allowed version or explicit policy route,keep existing pinned history |
| `KNOWLEDGE_PERMISSION_DENIED` | P-05/X-10; remove inaccessible excerpt,request policy review through available internal procedure or choose another permitted source |
| `EVIDENCE_REQUIRED` | P-05/P-06; gather supporting source or confirm missing fact;do not fabricate |
| `EVIDENCE_STALE` | P-05/X-11; choose valid source and rerun affected Claim/Review |
| `MODEL_NOT_ALLOWED` | P-04/X-20 allowed detail; choose eligible internal model only if configured;manual work remains |
| `REVIEW_GATE_FAILED` | P-08/X-04; linked blockers,correct then recheck |
| `MISSING_CONFIRMATION` | P-06/X-03/X-04; explicit authorized confirmation,not hidden checkbox default |
| `EXPORT_FAILED` | X-19/X-16; inspect safe error/trace,correct config/content,retry same intended version |

HTTP mappings are not invented here. Errors/trace details never include raw secrets or forbidden excerpts.

### Dependency degradation

| Unavailable dependency | Still possible | Restricted and recovery |
|---|---|---|
| LLM | Manual edit,authorized search/citation,templates,versions,approval/export if existing gates satisfied | New model tasks unavailable;no fake generated output;retry eligible tasks after recovery |
| Enterprise knowledge | Manual edit and already authorized readable content under current policy | New Evidence unavailable;formal Evidence-dependent generation blocked;cached snapshot cannot bypass current ACL |
| Reviewer | Draft editing and proposal inspection | Required Review incomplete → publication blocked;rerun pinned current version when restored |
| Export/render | Editing,Review,approved version remains intact | Artifact failed/partial not downloadable;safe retry,no body version mutation |
| SSE transport | Manual work and REST snapshot/task lookup when API reachable | Reconnecting status;resume `Last-Event-ID`,dedup monotonic cursor,rebuild gaps from durable state;large results through REST/storage |
| Redis/cache,broker,worker | Persisted business/version/task truth remains | Expose delayed/retry/failed state from API;not “lost document”;bounded recovery/compensation visible |
| Audit | Permitted reads and noncritical draft actions only as configured | Publication,permission and approval-critical writes fail closed;no administrator skip button |
| Network/API | Already open in-memory draft editing where allowed | Writes unsaved/unknown,critical actions disabled;reconnect same identity and reconcile before saving |

## Interaction Primitives

- Keyboard: Tab/Shift+Tab in DOM reading order; Enter/Space activates buttons; arrow keys/Home/End for tabs/tree/menu with selected and expanded semantics; Escape closes top idle popover/dialog and returns focus. No single-letter global shortcuts intercept Chinese typing. Ctrl/Cmd+S explicit save;Ctrl/Cmd+Z and redo platform shortcut editor-local;Ctrl/Cmd+Enter sends prompt when IME composition ended. Shortcut help is in existing More menu. Browser refresh/close warns when unsaved,without promising reliable browser persistence.
- Selection: stable document/section/node/Claim/issue IDs,never visual row index or first matching paragraph. New async result may update only its originating version context. Opening source preserves return anchor to the exact Claim/issue.
- Search: Enter global search;local template/review filters may debounce300ms (UX choice),cancel superseded reads and ignore old response ordering. All filters AND-combine. Scope change clears former selection;Back restores safe filters,not revoked content.
- Navigation: choose route only after required identity/object load. Dirty leave offers Save then leave,Stay,or explicitly discard in-memory edits; server-accepted tasks keep running when a panel closes. Returning reconstructs from task ID.
- Confirmation: destructive logical changes,template deprecation,field removal with dependencies,approval rejection,publication and permitted policy changes require clear object/version/impact and reason where specified. No public-share/physical-delete confirmation exists because those actions are not authorized.
- Drag: outline/schema reorder is supplemental,never the only path; provide move-up/down or position input. Mandatory structure/rule constraints checked identically for drag and keyboard. No realtime coediting cursors or collaboration service implied.
- Patch writes: AI output/schema changes are proposals;selected acceptance gets new version+provenance;failed/stale acceptance retains proposal. Human author confirms proposed outline separately before generation. Read-only query can be copied only through permitted product behavior,not implicitly inserted.
- Retry/idempotency: one logical action has durable identity;timeout/refresh double-click doesn't duplicate export,publication,return or integration. Cancel is a request,not client erasure. Re-auth/retry rechecks current policy.
- Diagram requests: Mermaid/PlantUML text proposal supported as requested operation;render only configured validated allowlisted path. Mermaid syntax/node/text/options validation and isolated network-disabled rendering required. Unsupported PlantUML runtime returns preview unavailable/plain-source proposal,not arbitrary shell execution or silent runtime addition.

## Accessibility Floor

Target WCAG2.2 AA where compatible with confirmed desktop contract,with recorded fidelity conflicts below; this is an acceptance target,not certification. Semantic/keyboard improvements are R/S deltas and should not change resting baseline geometry. DESIGN owns contrast and precise focus token `{components.focus.outline}` with `{components.focus.offset}`.

- Main/nav/aside regions with labels;one meaningful page heading;route change announces title and focuses main heading without unexpectedly moving focus during background refresh.
- Convert actionable prototype spans/divs (More,quick-create,rows,bell,project selector) into labeled keyboard-operable controls while preserving source display. Decorative glyphs hidden from accessibility tree;icon-only undo/link/send/notification require names and tooltips on focus.
- All labels programmatically associated;modal scope select gets a stable accessible association without changing visible layout. Errors linked via description/invalid state;summary links focus erroneous field. Required state text not color alone.
- Dialogs have name,initial focus to first meaningful field or explanatory heading,trap focus,inert background,and return to opener;backdrop stays non-dismissal. No stacked dialog maze: open source/detail as full screen or replace dialog step with Back.
- Tabs expose role/selected/controls,roving keyboard;tree level/expanded/selected states;table header associations. Scrollable panes reachable with keyboard and not trapped;selection and scrolling don't silently issue writes.
- Polite live announcements for save/task stage/stream completion,not every token;assertive only actionable blocking error. Toast isn't the sole announcement/history. Review status words accompany colors. Unknown/provisional output unmistakable.
- Source document previews have readable text/provenance alternative,not image-only evidence. Images need alt text;tables header semantics;schema/scan errors readable outside canvas. Barcode/QR has textual identifier and authorized lookup alternative;signature optional modality follows schema/accessibility policy,not hand-drawing-only assumption.
- New S controls minimum24×24 effective target,prefer38px standard height;source tiny/inert controls require target-spacing audit without secretly widening baseline. Reduced-motion disables nonessential transitions;forced colors retains outlines,text labels,insert/delete decorations.
- Chinese IME,screen-reader reading order,keyboard-only complete flow,200% text zoom and narrow horizontal-scroll focus must be tested. No default mobile stacking claim.

### Explicit conflict and dependency register

| ID | Fact / decision | Acceptance disposition |
|---|---|---|
| VC-1 contrast/focus | Source outline0 and several pale/small or white-on-status texts are not measured AA;semantic/focus supplements are specified,but changing baseline text colors requires reconciled fidelity decision | Independent review must identify actual failing pairs and approve permitted remediation scope before claiming both AA and1:1;do not silently recolor or falsely pass |
| VC-2 reflow/overflow | Fixed1180px desktop source and wide editor/review can conflict with general320px reflow expectations;source has no mobile redesign | Preserve confirmed desktop behavior;document any accessibility exception/remediation decision separately. Narrow-screen/zoom testing pending;not an S2 source-reading blocker |
| ENV-1/2 | Real enterprise identity/KB/MES/project/archive and model/GPU/evaluation dataset endpoints unavailable | Local contract adapters/test doubles explicitly labeled;real acceptance pending,no invented integration/efficacy |
| ENV-3/4/5/6 | Production/HA/security limits/retention/TTL,official templates/fonts andbenchmark manifest inputs need environment/policy | Present not configured or development example with fail-closed formal gates. No made-up retention days,file limits,waive role or coverage percentage |
| ADMIN-HISTORY | PRD retains earlier blocked-worktree administrative text | Historical resolution from stage assignment;no PRD edit,re-interview or resumed blockage;current output only worktree draft |

## Responsive & Platform

Use exactly DESIGN.Layout & Spacing baseline:64px header,266px sidebar,12px shell gap/padding;P-03 `minmax(650px,1fr)+356px`;P-07 main+310px;P-08 `350px+minmax(420px,1fr)+370px`. At **≤1180px**,body horizontal scroll/app min-width1180px and exact note at right/bottom8px;at1181 no note. No source dark mode/mobile stacking/collapsing sidebar. Browser/OS/font/zoom are pinned comparison variables,not optional visual trivia.

New screens use same desktop overflow,with local table/pane scroll and reachable focused actions. Test keyboard across nested panes;do not hide final buttons beyond inaccessible clipped area. Browser rendering/geometry was anomalous during authoring (empty styles/uniform100×20);no visual pass is claimed. Test matrix and evidence are in DESIGN.Components and below.

## Inspiration & Anti-patterns

Only supplied product documents and original prototype inform this contract;no competitor aesthetic/persona research is invented. Preserve the compact blue enterprise workspace rather than copying generic Ant Design dashboard/chat design. Reject fake instant AI completion,confidence-as-truth,public link sharing,opaque “AI thinking” for every stage,score-as-approval,template-scope filter overwrite and first-paragraph citation insertion. Prototype sample “10万终端”,“登录时延≤10秒” and business outcomes are document fixtures,not platform NFRs or verified claims.

## Key Flows

Named protagonists below are **source-role enactment labels**,not invented researched people. “作者”,“专家”,“审批人”,“模板管理员”,“知识管理员”,“投标专员”,“表单管理员”,“生产填报员”,“系统管理员” are the source roles acting in a scenario. UJ-1–UJ-5 preserve PRD journey identity;UJ-6 closes cross-cutting operational IA coverage. The named role label is the protagonist's identifier throughout each numbered journey.

### UJ-1 — Author creates a technical document

1. **作者** authenticates,selects permitted project from P-00,and opens actual recent/favorite/reference context or quick-create technical solution in P-01.
2. P-02 preserves type/scope/template version,validates name,creates a new document;作者 sees its own ID/AST,not the former prototype paper.
3. X-15 collects confirmed facts,glossary,constraints and authorized attachments;parse/KB/model dependency states visible. 作者 inspects similar formal documents and missing facts.
4. A versioned outline proposal arrives;作者 corrects permitted structure and explicitly confirms it before section generation.
5. P-04 shows retrieval/Evidence Pack/queue/generation/validation;P-05 exposes actual supporting/conflicting/contextual passages. Unsupported critical numbers create P-06 pending items.
6. **Climax:** X-01 shows precisely what AI proposes against the chosen base;作者 accepts only checked changes and receives a saved new version with source/run/model/Prompt provenance. Manual prose is not silently overwritten.
7. 作者 formats selected AST content,adds authorized citation at cursor,uses version history if needed,and submits pinned version to P-08 Review then X-03 approval;export and trusted return remain distinct later actions.

Failure: stale autosave or Patch → X-02 base/local/latest;keep choices and save a checked merge. LLM unavailable → manual work continues;no fake success. Missing Evidence → pending,not fabricated text. Source permission revoked → clear passage and reselect;final gates remain blocked.

Type variants: repeat this chain for PRD structured FR fields,test-plan traceability and technical-requirements measurable statements;Phase2 quality outline,project plan,functional/performance test outlines and project summary use their approved type rules from the catalog,not omitted scope.

### UJ-2 — Expert and approver protect formal release

1. **专家** opens an assigned Review from P-01/X-16;P-08 pins document/run/version and shows all eight Reviewer outcomes:structure,fact,requirement,technical,quality,consistency,style,safety.
2. 专家 filters severity/section/status/keyword,opens each actual issue and source,inspects P-09 citation trace and prior runs/version comparison.
3. Accept applies a checked Patch;Reject records rationale without auto-clearing severe gate;Modify opens proper block;Handled requires verification or explicit permitted exception. Pending facts resolved in P-06.
4. **审批人** opens X-03 inbox,the exact candidate and approval policy,Review/current gate state and provenance;approves or rejects with recorded reason under actual authority.
5. **Climax:** X-04 refuses publication despite a high score if severe unsupported Claim,pending conflict,missing threshold,stale approval or audit outage exists;after every actual prerequisite passes,the authorized human confirms the pinned version and the API records Published.
6. X-19 performs safe formal export/download with current ACL;X-11 displays independent eligible Published-triggered knowledge return. P-09/history retains decisions and versions.

Failure: candidate edited after approval → new version and reapproval/revalidation,not inherited approval. W policy absent → no waive. Rejected approval returns visible correction requirement. Export failure leaves Published content version intact and offers task retry. Return failed remains separate from publication.

### UJ-3 — Template and knowledge administrators enable reuse

1. **模板管理员** browses P-07 all permitted scopes/types,uploads X-14 version with structure,retrieval/Prompt/Reviewer/render/approval rules,validates and previews actual layout.
2. Missing required policy/template/font is labeled development-only or blocked;validated permitted version can be published,previous versions retained. Deprecation does not alter pinned documents.
3. **知识管理员** opens X-10 current enterprise/attachment/Golden source;checks authority/validity and source-located conflict in X-11. Competing statements remain visible until authorized resolution,not hidden by ranking.
4. 知识管理员 inspects eligible Published return candidate,quality gate and correlated task;only verified return receipt becomes trusted searchable material.
5. X-12 shows actual quality/coverage/monthly definitions and denominators;X-13 manages versioned Reviewer rules and Golden cases,then runs labeled local or real evaluations.
6. **Climax:** a failed/unsupported case links back to its exact Claim/source/template/rule/version,so the administrator can improve the responsible asset rather than substituting a higher-looking aggregate score. Monthly improvement follows Knowledge→Template→Retrieval→Prompt→Reviewer→Model.

Failure: unauthorized source read shows no excerpt;invalid template/rule doesn't publish;no real model endpoint → local contract run possible but real-quality result not claimed. Return duplicates reconcile without duplicate trusted entries.

### UJ-4 — Bid compliance specialist closes tender gaps

1. **投标专员** chooses 新建标书 or bid template,creates draft and opens X-05 with actual tender/project/customer versions.
2. Upload/parse exposes queued/OCR/partial/failed page states. 投标专员 compares each extracted qualification,commercial/technical,disqualification and scoring item to its source locator and corrects with history.
3. X-06 maps requirement rows to response sections and Evidence bidirectionally;missing/partial/conflicting/unconfirmed rows remain visible. Declared scoring rules show real calculation or not evaluable.
4. 投标专员 generates/edits responses through normal Evidence/Patch chain and runs residual customer/project-name and contradictory-parameter checks.
5. **Climax:** an unresolved mandatory/disqualification item is traced directly from matrix to tender clause and response;it prevents formal release instead of being concealed by an optimistic score or completed parse task.
6. After correction and common Review/human approval/publication gates,export includes current matrix/tender/response version context and controlled archive/integration path where configured.

Failure: partial tender parse cannot declare complete analysis;outdated tender mapping marked stale and remapped;source revoked blocks relevant citation. Bid actions never bypass shared security,waive or release gates.

### UJ-5 — Controlled production form and delivery

1. **表单管理员** creates X-07 Form Schema manually or reviews AI schema Patch;adds text,number,date,select,checkbox,signature,image,barcode/QR,formula and repeating table as required;validates stable keys,types,rules and formula dependencies.
2. Approved/activated schema version is pinned;**生产填报员** opens X-08 actual instance,enters data and attachments,uses accessible row controls and sees frontend/backend errors without losing last valid save.
3. The same schema/values appear in Web,DOCX,PDF,XLSX and print previews. Signature capture is explicitly not certified enterprise e-signature.
4. 生产填报员 initiates scan or uploads authorized scan;barcode lookup checks identity/schema/version/ACL,OCR values are proposed for review,not blindly saved.
5. Approved artifacts are sent through X-09 declared MES/project/archive contract with classification/mapping/correlation and idempotency.
6. **Climax:** a receipt timeout shows “待核对” with original delivery correlation;authorized reconciliation finds the previously applied business action,so retry/restart does not duplicate enterprise delivery.

Failure: unsafe formula rejected;invalid server save retains last valid instance;unknown/wrong barcode shows no forbidden record;missing connector/real endpoint labels not configured/local contract substitute. Partial delivery inspectable,not success.

### UJ-6 — Recover and administer without bypass

1. **系统管理员** or specifically granted operator opens X-16 from real bell notification,filters category/generation/retrieval/review/parse_ocr/render/integration and inspects task/trace/error.
2. SSE disconnect shows reconnecting;API durable snapshot and `Last-Event-ID` resume reconstruct progress with duplicates ignored and no large payload in SSE.
3. The operator uses only supported cancel/retry/reconcile with original identity;permanent/dead-letter failures remain visible and independent queue failure does not erase saved documents.
4. X-20 shows permitted model/Prompt/connector/policy/audit/Feature Flag versions;unconfigured external allow stays deny and audit outage prevents critical policy/publication/approval changes.
5. **Climax:** enabling a feature flag changes availability only;it cannot confer clearance,waive severe issues,skip release tests or authorize deployment. The operator sees environment-pending status rather than manufactured real-integration evidence.
6. Operators return through P-00/X-18 project/account and X-17 collections;no public share or physical deletion is introduced while managing retained records.

Failure: unknown-outcome side effect is queried before retry;expired session reauths then rechecks ACL/version;scope denied content cleared. A local deterministic test pass is labeled local,not production99.9% or measured real AI efficacy.

## Requirement and Acceptance Traceability

Every row names a testable UX consequence,not an implementation-complete claim. All FRs continue into later phases. Shared G/profile tests apply to every mapped screen/control;specialist flows are not satisfied by a technical-solution-only happy path.

| FR | Surface/control/flow | Required acceptance observation |
|---|---|---|
| FR-1 | P-00/P-02,C02/C08/C10,UJ-1 | Own created ID/AST/type/template/scope;denied scope fails |
| FR-2 | P-01/X-17,C04–C07 | Four recent views/counts/storage from same authorized dataset;empty no samples |
| FR-3 | P-00/X-18/X-17,C01/C04 | Actual searched record/context;recycle no physical delete |
| FR-4 | Permission model,C00–C36,UJ-6 | Role+scope+clearance denies including deep links/background request |
| FR-5 | P-03,C11–C16 | Typed AST stable nodes/Claim/Evidence;invalid AST prior version intact |
| FR-6 | P-03/X-02,C12–C17 | Actual autosave/undo/selection;stale version conflict no overwrite |
| FR-7 | P-07/P-02,C23–C25 | Full scopes,AND filters,selected own outline/pinned creation |
| FR-8 | X-14,C26,UJ-3 | Upload/validate/version/publish/deprecate;referenced history retained |
| FR-9 | Catalog technical solution,UJ-1 | Mandatory chapters,current facts,unsupported parameters pending |
| FR-10 | Catalog PRD,X-15/P-03 | All structured FR fields validated and locatable |
| FR-11 | Catalog test/technical requirements,X-12 | Requirement-test-case-acceptance links;vague metrics flagged,no AI threshold change |
| FR-12 | P-05/X-10,C21/C35 | Before/after retrieval ACL+context+validity,no forbidden model input |
| FR-13 | X-10/X-11,UJ-3 | Nine authority levels shown separately from L0–L3;conflicts visible |
| FR-14 | P-05/P-09,X-10,C16/C35 | Selected Claim/source/version/locator/current access,not fixed trace |
| FR-15 | P-05/P-08 | All supported Claim types,state/bindings;unsupported critical claim not verified |
| FR-16 | X-15/P-05/P-04 | Section-specific Pack provenance,insufficient support,dedup/version handling |
| FR-17 | X-15/X-05/X-08 | Validated attachment,partial OCR/index state,separate enterprise authority |
| FR-18 | P-02/X-15,C09/C10 | Confirm outline after real context;missing info explicit |
| FR-19 | P-04/X-16 | Categorized section tasks/assembly/checks and blocked-input state |
| FR-20 | P-04/C17/C19/C20 | Six baseline +complete extended Copilot operations;read-only no mutation |
| FR-21 | X-01/X-02 | Selected Patch/new version/provenance;Reject unchanged;stale conflict |
| FR-22 | P-06/C22,diagram primitive | Actual resolution/audit;safe table/diagram proposal;no arbitrary execution |
| FR-23 | P-08/X-16,UJ-2 | Eight pinned Reviewers/rule/model versions;real rerun task |
| FR-24 | P-08/P-09,C28–C30 | Combined filters,all selected detail fields/run counts update |
| FR-25 | C31–C34,X-01,UJ-2 | Four distinct dispositions;severe handled only checked/authorized |
| FR-26 | P-08/X-06,X-13 | Seeded number,name,obsolete citation,missing chapter,ambiguity,term andunsupported-fact cases locatable |
| FR-27 | X-03,UJ-2 | Pinned human request/decision/history;edit invalidates inherited approval |
| FR-28 | State vocabulary/X-04 | Normal/exception lifecycle different from tasks/Review/export |
| FR-29 | X-04 gate list | All gate failures fail closed,unknown threshold denies |
| FR-30 | X-19,C27,UJ-2 | Actual permitted version export with formal styling fields/current download ACL |
| FR-31 | X-11,UJ-3 | Published eligible quality gate/return task;draft denied,duplicate reconciled |
| FR-32 | Full catalog/UJ-1 variants/X-14 | All five Phase2 type workflows,official vs development template labels |
| FR-33 | X-12/X-13,P-08 | Actual versioned quality/coverage/rule definitions/denominators/drilldown |
| FR-34 | X-13,UJ-3 | Golden queries/defects/versioned manifest,local vs real run distinction |
| FR-35 | X-05,UJ-4 | Source-located/correctable qualification/commercial/technical parse,partial clear |
| FR-36 | X-05/X-06 | Declared disqualification/scoring source/rules,unresolved mandatory risk |
| FR-37 | X-06,UJ-4 | Bidirectional requirement-response-Evidence/version links and export context |
| FR-38 | X-06/P-08 | Residual name/contradictory parameters enter common release gate |
| FR-39 | X-07,UJ-5 | Eleven field types,independent versioned schema,reviewed AI Patch |
| FR-40 | X-08 | Front/back validation parity,whitelist formula,prior valid record preserved |
| FR-41 | X-08/X-19 | Same values Web/DOCX/PDF/XLSX/print,scan state,signature boundary |
| FR-42 | X-09/X-20 | Declared connectors/local adapters,correlation/authorized retry,real endpoint pending |
| FR-43 | X-09,UJ-5 | Approved artifact controlled delivery,duplicate/partial/restart reconciled |
| FR-44 | X-16/all TASK | Durable categorized state,SSE recovery,final result identity |
| FR-45 | X-16/UJ-6 | Worker/broker/cache restart preserves task/version;failed work inspectable |
| FR-46 | X-20/P-09/X-16 | Critical actor/resource/version/outcome/correlation audit,no secrets |
| FR-47 | P-01/P-11/X-16/X-20 | Real counts/notifications/admin states,not-configured distinct |
| FR-48 | Environment labels/UJ-6 | UI local vs real vs production evidence;no execution authorized by this UX |

### Extended Copilot operation coverage (C17/C19/C20)

The existing six buttons keep position/label. More/context operation chooser adds rewrite,expand,contract,professional rewrite,requirement-to-test conversion,table proposal,Mermaid/PlantUML request,knowledge query,similar solution retrieval,omission check,conflict check andcreate pending item. Each chooser row states target,input needed,read/write effect and required permission. Rewrite/expand/contract/professional/technical/requirement-to-test/table/diagram insertion are E/TASK→X-01;knowledge/similar/summary are allowed read/TASK and never mutate;fact/omission/conflict checks create versioned findings;create pending item is explicit E/WRITE with location/reason. Unknown target requires selection;no Evidence/model/context blocks relevant operation;failed output stays proposal/error. This list completes FR-20 without a seventh arbitrary baseline button.

### Source-defined semantic inventories

Knowledge authority order (FR-13):mandatory law/standards;formal company policy/standards;current formal project material;current formal product material;approved historical projects;department knowledge;ordinary internal documents;allowed external material;LLM general knowledge. Prefer appropriate higher authority but display conflicts and project applicability. This is not classification L0–L3 andnot a permission grant.

Document AST retains S03 §3 top-level `schema_version` and document metadata/sections/claims/citations/review_state, with stable Section and Block identities. S03 §2.5 exact Block types are `paragraph`, `heading`, `table`, `figure`, `diagram`, `requirement`, `citation`, `warning`, `code`, `form`. Formatting lists, images and test-case data must map through the approved AST Adapter/contract rather than inventing replacement wire-type names. Unsupported blocks cannot be silently flattened or lost: use read-only representation with a precise validation message until the adapter supports them. Requirement blocks preserve requirement_id, statement, verification_method and source_refs. S04 §10.1 mandatory Claim checks cover numbers, percentages, performance, capacity, time, dates, model identifiers, standards, regulations, product support capabilities, acceptance thresholds, customer/project names and versions. Display condition/value/unit/version/location and the source-declared type safely; unknown declared types are never dropped or falsely verified. These exact semantic inventories, not generic “facts” coverage, govern regression cases.

### NFR acceptance matrix

| NFR | Observable UX/security/test requirement |
|---|---|
| NFR-1 | Deny matrix across controls/routes/source view/citation/publish/export/download with RBAC AND ABAC AND clearance;revocation mid-flow clears inaccessible content |
| NFR-2 | OIDC Code+PKCE/session expiry flow;API/service identities separate;UI shows authenticated identity andreauth path without collecting/storing shared credentials |
| NFR-3 | X-20 route Classify→DLP→Policy→Redact→Router;no configured external allow denies;L0/L1 require policy/L1 desensitization;L2 internal default;L3 never external;no permissive fallback |
| NFR-4 | Injection fixtures in KB/tender/attachments andescaped AI output;no generated authorization/shell/script;DLP failures explicit without leaking protected content |
| NFR-5 | Critical actions100% auditable with actor/action/resource/version/workspace/outcome/trace/time;audit interruption blocks permission/approval/publication-critical writes |
| NFR-6 | Mask/reference secrets;no ordinary raw Prompt/sensitive-body logs;classification/watermarks/TTL/retention shown from policy;TLS/at-rest evidence downstream,not UI claim |
| NFR-7 | Malicious files/unsafe diagrams/resource timeout show rejection;isolated OCR/render non-root/network/resource/temp restrictions downstream verified;no arbitrary executable formula |
| NFR-8 | Key UI operations P95<1s;home/list API P95<1s;AST retrieval P95<1s;autosave request P95<1s. Client timing andserver timing separate;1000ms UI debounce excluded/labeled rather than concealing end-to-end delay |
| NFR-9 | Search P95<3s;typical Evidence Pack P95<8s;source **S05§10.1**,not S04§19. Freeze corpus/query/ACL/reranker/endpoint/pack-size;permission-error retrieval0 regardless of speed |
| NFR-10 | First token P95<5s;typical chapter P95<60s;configured real route/environment/exclusions recorded,not proven by deterministic fixtures or frontend animation |
| NFR-11 | 50-page DOCX<60s (NOT specified P95);Golden DOCX typography/pagination/tables/references andformal fields validated with actual fonts/theme |
| NFR-12 | ≥99.9% availability,RPO≤15min,RTO≤1h;requires production-equivalent measurements/drills;local start/config files cannot satisfy |
| NFR-13 | Degradation table exercised;manual work persists appropriately,cache/broker/worker failover doesn't lose persisted version;Reviewer unavailable blocks required release |
| NFR-14 | Test100 online,20QPS docs/list,5QPS search;20chapter jobs,50searches,10full Reviews;20exports30–80pages. Suggested sizing not measured capacity;freeze hardware/network/data |
| NFR-15 | Trace HTTP→outbox/worker→retrieval/model/Claim/Review/Patch→SSE;task/trace diagnostics with P50/P95/P99,queue/usage/retry metrics,no sensitive body leakage |
| NFR-16 | Matched viewport/zoom/font/OS/fixture/source-state1:1 screenshots and interaction checks except enumerated C00–C36 R/S deltas;no invented pixel tolerance;source hash not enough |
| NFR-17 | ≤1180 desktop min-width/scroll/note,1181boundary test;loading/queued/Evidence/stream/Review/Diff/pending/forbidden/offline/export/approval separate |
| NFR-18 | Quality medium andindependent downstream review/check→optimize→verify;S2 author check not independent approval;no architecture/Epics/code until coordinator workflow gate |

Feature Flag maintainability (S05§10.5) is explicitly carried in X-20:versioned auditable scoped availability with safe defaults;never releases permissions or disables non-waivable gates. Real acceptance prerequisites remain ENV-1–ENV-6;test manifests separately record local deterministic contract pass,real enterprise integration pass,real model efficacy pass andproduction NFR pass. Recommended S06 initial Recall@10≥.90,current-project Top3≥95%,Citation Precision≥95%,post-review unsupported critical claim rate<2% are evaluation recommendations pending governed acceptance configuration;published severe unsupported remains0. Do not turn these recommendations or S04 score weights into an invented release threshold.

### Mechanical author self-check and downstream evidence required

Author coverage check scope:canonical section shape;resolved DESIGN token references;23 shared component names in both spines;P-00–P-12;SUP-1–SUP-9;X-01–X-20;C00–C36;FR-1–FR-48;NFR-1–NFR-18;UJ-1–UJ-6;full three-phase catalog;all source control groups including inert entries;safe shared state profiles with per-surface differences. No mock/import files created,therefore none claimed as visual references.

Downstream tests must produce evidence for (a) source-fidelity view/state matrix andfont manifest;(b) keyboard/screen-reader/contrast/zoom andVC-1/VC-2 disposition;(c) source-control interaction inventory with positive anddenied cases;(d) optimistic concurrency/selection/provenance;(e) all fail-closed release gates;(f) dependency loss/reconnect/duplicate/unknown outcomes;(g) tender end-to-end andform integration end-to-end;(h) real vs local vs production acceptance distinctions. Source reading andthis author check cannot substitute for independent S2 approval or any executed product test.

**Handoff state:** local permitted-worktree UX pair drafted for coordinator's independent S2 review. Main-project persistence not performed. No request for new business authorization is needed to read these drafts;policy unknowns remain explicit deny/block behavior,not broad re-interview prompts. Stop at UX;do not advance architecture/Epics/application code or claim main-project S2_GATE PASS.
