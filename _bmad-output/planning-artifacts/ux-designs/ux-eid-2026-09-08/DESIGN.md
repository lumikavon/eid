---
name: Enterprise Intelligent Document Workbench
description: Prototype-derived visual contract and explicitly authorized three-phase supplements.
status: draft
created: 2026-09-08
updated: 2026-09-08
stage: S2
workflow: bmad-agent-ux-designer / bmad-ux
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
colors:
  canvas: '#f4f8fd'
  panel: '#ffffff'
  panel-secondary: '#f8fbff'
  line: '#dbe6f5'
  line-secondary: '#e8eef8'
  text-token: '#0d2a63'
  body: '#17325f'
  muted: '#6f84a6'
  primary: '#0b6bff'
  primary-soft: '#e9f2ff'
  teal: '#11b59a'
  teal-soft: '#e7fbf6'
  purple: '#7357e8'
  purple-soft: '#f1edff'
  orange: '#ff9818'
  danger: '#ff4e55'
  success: '#12b981'
  nav-text: '#35517d'
  nav-active: '#eaf3ff'
  button-border: '#cfe0f8'
  button-text: '#1b5ac8'
  pill-neutral-bg: '#edf3fb'
  pill-neutral-text: '#5d7599'
  pill-green-bg: '#e6fbf4'
  pill-green-text: '#0aa979'
  pill-red-bg: '#fff0f0'
  pill-red-text: '#ed4049'
  pill-orange-bg: '#fff5e9'
  pill-orange-text: '#ef8700'
  pill-purple-bg: '#f2edff'
  pill-purple-text: '#7255e7'
  paper-surround: '#fafcff'
  rail: '#fbfdff'
  paper-text: '#345176'
  paper-h1: '#0c2b68'
  paper-h2: '#0c56ce'
  paper-h3: '#11346f'
  table-header: '#f9fbfe'
  table-line: '#edf2f8'
  toast: '#173568'
  note-bg: '#fff7df'
  note-text: '#8a5b00'
  supplement-text: '#17325f'
  supplement-error: '#a51d32'
typography:
  family:
    fontFamily: 'Inter,"PingFang SC","Microsoft YaHei",system-ui,-apple-system,sans-serif'
  base:
    fontSize: 16px
    fontWeight: '400'
    lineHeight: normal
  brand:
    fontSize: 22px
    fontWeight: '800'
  navigation:
    fontWeight: '650'
  heading:
    fontSize: 24px
    fontWeight: '700'
  hero:
    fontSize: 29px
    fontWeight: '700'
  kpi:
    fontSize: 30px
    fontWeight: '700'
  paper-title:
    fontSize: 32px
    fontWeight: '700'
  paper-section:
    fontSize: 25px
    fontWeight: '700'
  paper-subsection:
    fontSize: 18px
    fontWeight: '700'
  paper-body:
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.85'
  table:
    fontSize: 13px
  metadata:
    fontSize: 12px
  micro:
    fontSize: 11px
  button:
    fontWeight: '700'
  pill:
    fontSize: 12px
    fontWeight: '700'
rounded:
  paper: 4px
  tag: 5px
  severity: 6px
  small: 7px
  field: 8px
  control: 9px
  inset: 10px
  project: 11px
  card: 12px
  home-card: 13px
  panel: 14px
  progress: 99px
  pill: 999px
  circle: 50%
spacing:
  shell: 12px
  page: 18px
  card: 13px
  home: 14px
  review: 16px
  dialog: 20px
  gap-small: 8px
  gap: 12px
  gap-wide: 14px
  header-inline: 24px
components:
  shell:
    header-height: 64px
    sidebar-width: 266px
    gap: '{spacing.shell}'
    radius: '{rounded.panel}'
  button:
    height: 38px
    radius: '{rounded.control}'
    padding: 0 14px
  input:
    height: 39px
    radius: '{rounded.field}'
  card:
    radius: '{rounded.card}'
    border: '1px solid #e8eef8'
  dialog:
    width: 560px
    radius: '{rounded.panel}'
    padding: '{spacing.dialog}'
  editor:
    content-min: 650px
    rail-width: 356px
    paper-max: 880px
    paper-min-height: 1040px
  template:
    detail-width: 310px
    cover-height: 125px
    detail-cover-height: 190px
  review:
    list-width: 350px
    content-min: 420px
    trace-width: 370px
  supplement:
    inspector-width: 356px
    filter-height: 38px
    row-min-height: 38px
    field-height: 39px
    section-gap: 12px
    label-size: 12px
    body-size: 13px
    heading-size: 24px
  focus:
    outline: '2px solid #0b6bff'
    offset: 2px
---

## 当前开发与验证边界（2026-09-21）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件的执行安排统一受[开发与验证规则](../../development-validation-policy.md)约束。下文涉及启动、部署、迁移、fixture、功能测试、浏览器实测、联调、性能和故障演练的条款保留为待执行验收要求，当前暂停执行并记录 `not-run`；其中静态检查与编译可按规则单独执行。历史证据按原日期保留，不代表本轮通过或继续运行的授权。


## Brand & Style

A private, Chinese-language enterprise authoring tool: pale blue workspace, white structured surfaces, dark-blue editorial hierarchy and compact controls. The product is a controlled document/Evidence/Review workflow, not a chat application. Ant Design is the supplied component system, but its defaults MUST be overridden to match this contract and the original prototype. The source does not use an Ant Design theme; installing Ant Design is not visual acceptance.

**Authority and delivery.** This is a local Markdown UX contract, not a branded public site, implementation, rendered prototype or approval. Its peer [EXPERIENCE.md](EXPERIENCE.md) owns behavior. Both contracts govern downstream derived mocks; the original `D:/Desktop/eid/docs/prototype/index.html` remains the visual baseline for existing surfaces and is never modified. Where a new specification conflicts with that baseline, record the discrepancy, do not silently change the prototype. The confirmed interview authorizes missing surfaces/controls, live data and demo-to-real replacements; it does not authorize arbitrary redesign. PRD worktree-blocked wording is historical administration, as clarified by the stage assignment; do not reopen it as a requirement question or edit that PRD in S2.

**Notation.** `P-00`–`P-12` are the PRD surface IDs. `B` means baseline extracted from source; `R` means authorized demo-to-real replacement; `S` means authorized supplement with no original body screenshot. `SUP-1`–`SUP-9` retain PRD meanings. Source locators below use literal selectors and section labels, not fragile line numbers. S01–S07 refer respectively to `docs/01`–`docs/07` in the source list. Every dimension is CSS px unless noted. Numeric values copied from source are not rounded to a preferred spacing scale.

**Scope.** One unified `edw-web` frontend; `edw-api` and `edw-worker` provide the business and asynchronous states described in EXPERIENCE. Three phases remain in scope, Knowledge/LLM Gateways remain shared modules, and worker category/security isolation is not weakened. No architecture or code is authored here. New screens are fully specified below, not promises to design them in Phase 2/3.

## Colors

### Exact baseline mapping

`--bg → colors.canvas`, `--panel → colors.panel`, `--panel2 → colors.panel-secondary`, `--line → colors.line`, `--line2 → colors.line-secondary`, `--text → colors.text-token`, `--muted → colors.muted`, `--blue → colors.primary`, `--blue2 → colors.primary-soft`, `--teal/--teal2 → colors.teal/teal-soft`, `--purple/--purple2 → colors.purple/purple-soft`, `--orange → colors.orange`, `--red → colors.danger`, `--green → colors.success`. Body uses `#17325f`, NOT the unused-as-body `--text` token.

| Baseline role | Exact foreground / background / border |
|---|---|
| Brand / page heading | `#0a2763` / `#102d68`; white surface |
| Active navigation | `#0b6bff`; topnav `linear-gradient(#eef5ff88,#eef5ff)` with 3px blue bottom border; sidebar/tree `#eaf3ff` |
| Global search | text `#36507b`, background `#fbfdff`, border `#dbe6f5` |
| Sidebar title / item / tree | `#183567` / `#37527d` / `#4a6389`; tree rule `#d8e6fa` |
| Project card | `linear-gradient(135deg,#edf5ff,#eefbff)`; border `#dceaff`; secondary text `#6b82a7` |
| Project active status | text `#08a576`, background `#e3fbf3` |
| Buttons | white + `#1b5ac8` + `#cfe0f8`; primary `#0b6bff` + white; danger `#ff4e55` + white; success `#12b981` + white; ghost `#f8fbff` |
| Pills | neutral, blue, green, red, orange, purple use frontmatter pairs; blue `#0b6bff/#e9f2ff` |
| Table | body inherited; header `#6e83a5/#f9fbfe`; cell rule `#edf2f8` |
| Paper table | outer `#cbdaf0`; cell border `#d8e3f2`; heading `#203e6d/#eff5fc` |
| Hero | `linear-gradient(110deg,#eaf4ff 0%,#f8fbff 60%,#e8f4ff)`; border `#dfeafa`; title `#0f2b67`; subtitle `#3d5b85`; quote `#587199` |
| Home cards | labels `#39577f`; values `#0c2866`; positive delta `#0aa375`; metadata `#8194b2`; dashed row divider `#e7eef8` |
| Editor header / toolbar / tool | `#5b739a` / `#38567f` / `#35557f`; tool hover `#eef5ff` |
| Paper summary / metadata / citation | background `#f0f6ff`; metadata `#7890b0`; citation `#0b6bff` weight800 |
| Copilot | tab text `#345479`; action `#225598` with `#cfe0f8`; hover `#f4f9ff/#75aaff`; prompt border `#d5e2f2`, text `#46628b`; send white on `#78aefa` |
| Evidence/quality | dashed `#e4ebf5`; key `#1356c5`; score `#0ca774/#e6fbf4`; response `#4e678c/#f4f8fe` |
| Template | card border `#dce6f4`; selected/hover border `#4c91ff`; title `#14356b`; description `#6f84a5`; metadata `#8194b1`; tag `#0b6bff/#eaf3ff` |
| Template chips | `#426187/#f0f4fa`; active `#0b6bff/#e4efff`; detail background `#fbfdff` |
| Review | selected issue `#f0f6ff` and inset outline `#6aa4ff`; issue title `#1f416f`; metadata `#7c90ad`; severity red `#ff4e55`, orange `#f39900`, blue `#4b9bff`, all white text |
| Issue status | open `#ed4049/#fff0f0`; done `#0ba877/#e8fbf5` |
| Quote/source | quote `#4a6389/#f6f9fe`, border `#e3eaf5`; source border `#dbe5f2`, active `#4b93ff/#fbfdff`; excerpt `#4c6489/#f4f8fd` |
| Review filters | `#45658e`, border `#d5e2f2`; active white on `#0b6bff` |
| Dialog / toast / narrow note | mask `#102b5a55`; dialog white; toast white on `#173568`; note `#8a5b00/#fff7df` |

Opacity-bearing colors and gradients are intentionally in this table rather than misrepresented as solid hex frontmatter tokens. No source dark theme exists: preserve a light authored interface, do not automatically invert it.

### Contrast and fidelity conflict discipline

Baseline pale text and several white-on-status fills are not assumed AA-compliant. Examples requiring measurement include `#6f84a6` on white, white on `#78aefa`, white on `#12b981`, and tiny 11px metadata. Preserve exact baseline values in the reference comparison; do not quietly darken them and claim 1:1 fidelity. Register **VC-1** in EXPERIENCE for accessibility/fidelity reconciliation. For new S surfaces, use `{colors.supplement-text}` for normal text, `{colors.supplement-error}` for text errors on white, and pair all color states with words and non-color marks. The existing green/red pills can remain incidental redundant decoration; they cannot be the sole readable statement of a release gate. Target 4.5:1 for normal text, 3:1 for large text and essential non-text affordances; measure every actual pairing before implementation acceptance. No contrast pass is claimed by this design author.

## Typography

| Selector / scope | Font / size / weight / line / margins |
|---|---|
| `body` and controls | Exact frontmatter family; source omits body font-size/line-height and browser reset. `button,input,select,textarea` inherit font. `base=16px/400/normal` is a documented standard-browser assumption for tests, not measured source CSS. Default heading/list/control margins not explicitly overridden must be compared against the same browser UA stylesheet. |
| `.brand` | 22px /800, nowrap; `.topnav button`, `.side-item` weight650 |
| `.project-card b` / `.project-card small` | 14px / bold; small inherits UA small sizing; do not normalize to 12px without comparison |
| `.page-header h1` | 24px, margin0; paragraph margin4px 0 0 |
| `.hero h2` | 29px, margin0 0 9px; subtitle18px margin-bottom10px; quote italic |
| `.kpi strong` / `.up` | 30px, block, margin12px 0 5px; delta13px |
| `.card-title` / `.more` | weight800; More12px; `.list-row`13px, its `.meta`11px with margin-top2px |
| `.doc-top` / `.doc-meta` | 13px; document metadata12px, gap18px, margin-bottom18px |
| `.paper h1/h2/h3` | 32/25/18px; h1 margin0 0 12px; h2 24px 0 10px; h3 15px 0 7px; normal UA bold (700) |
| `.paper p` | 14px; line-height:1.85; margin:5px 0 12px |
| `.summary-box` | Font size inherited from body (16px is a standard-browser assumption, not a measured value; verify against the prototype computed style in the same environment); line-height:1.7; no explicit outer margin; padding:15px 17px |
| `.template-head h1` | No explicit size: UA h1 2em (normally32px); NOT page-header24px. Margin0. Paragraph margin5px 0. |
| `.tcard h3/p` | 14px margin5px 0; 12px line1.5 fixed height38px, overflow hidden |
| `.tmeta`, `.tag` / `.outline-list` | 11px; outline12px line1.85, padding-left18px |
| `.big-cover` / `.score` | 18px /800; score18px |
| `.issue b/small`, `.sev`, `.ist` | 13px bold / UA small with top margin3px; severity/status11px |
| `.issue-detail h2`, `.review-title h2`, detail `h2/h3/h4` | UA heading sizes and weights where not overridden; review title and issue title margin0; template detail headings keep UA margins |
| `.quote` / `.source p` / `.excerpt` | line1.7; source paragraph12px; excerpt12px line1.6 |
| `.field label` | 12px, margin-bottom5px |
| `.uinfo` | line-height1.05; b block, small muted |

The source defines `.list-row .meta`, not a universal `.meta` rule. Other `.meta` nodes therefore inherit their container/UA styles; do not spread the home metadata style across all pages. `Inter` is named but not imported. Record the installed/resolved font and OS fallback in the golden screenshot manifest. No external font download is assumed. Missing corporate output fonts remain ENV-5, not permission to fake formal output.

## Layout & Spacing

### P-00 shell and P-12 overlays

| Selector | Exact layout contract |
|---|---|
| `*`, `html,body`, `body` | border-box; height100%; margin0; overflow hidden by default |
| `.app` | height100vh; grid rows64px 1fr |
| `.topbar` | flex center; padding0 24px; gap28px; white; 1px bottom secondary line; z10. Topnav stretches vertically, buttons padding0 15px, gap7px, bottom-border3px. `.topnav` gap8px. |
| `.brand/.logo` | flex center gap12px; logo34×34px radius9px; pseudo rectangles15×23 at left5/top6 and12×18 at right5/top10, translucent white `#fff8`, radius4px |
| `.global-search` | width280px, height38px, padding0 13px, radius10px, outline0 in source |
| `.bell/.avatar` | bell font20px, notification dot7×7px right-2/top0, white2px border; avatar36×36px circular center grid weight700. Header markup has no `.userarea` wrapper: its declared gap10px does NOT override actual topbar gap28px between bell/avatar/info. |
| `.shell` | min-height0; columns266px 1fr; gap12px; padding12px |
| `.sidebar` | min-height0; flex column; padding14px 12px; border1px; radius14px; overflow auto |
| `.side-title/.project-card` | title margin0 4px 12px, justify-between; project padding11px,gap10px,radius11px,bottom margin10px; icon38×38px radius9px,font20px; status padding4px 7px,11px,pill999px |
| `.side-menu/.side-item` | column gap4px; item padding10px 11px,radius9px,gap10px; hover and active identical fill |
| `.tree` | border-left1px; margin2px 0 8px 25px;padding-left8px; child buttons full width,padding7px 8px,radius7px; indent padding-left23px; selected weight700 |
| `.count/.storage` | count min24px,padding2px 6px,radius10px,12px; storage padding12px,radius11px; bottom anchored by margin-top:auto |
| `.progress` | height8px,margin10px 0,radius99px,clip; blue child radius99px; source width26% is sample data, replace with measured usage without changing height |
| `.page/.workspace` | page min-width/min-height0; hidden except active block height100%; workspace height100%,border1px,radius14px,overflow auto |
| `.toast` | fixed left50%,bottom28px,padding11px 16px,radius9px,z50; hidden opacity0/translate(-50%,20px),shown opacity1/translate(-50%,0); transition.2s;1800ms source display |
| `.modal-mask/.modal` | fixed inset0,z40,hidden then grid place center; dialog560px,padding20px,radius14px; title margin0 0 12px; field margin10px 0; actions flex end,gap8px,margin-top16px |
| `.mobile-note` | hidden above1180px; fixed right8px/bottom8px,padding8px,radius8px,z99; exact Chinese note remains |

The topbar has no wrapping/min-width correction and the review/editor columns can overflow their workspace even above1180px. Preserve that source behavior in B comparisons; do not invent a different breakpoint or sidebar collapse to fix it. Any ergonomic enhancement is separately registered as VC-2, not presumed approved.

### Page-by-page fixed and fluid geometry

| Surface | Exact B layout and internal spacing | Source anchor |
|---|---|---|
| P-01 workbench | `.home-wrap` padding14px,columns1fr 330px,gap14px. Hero height142px,padding22px 26px,radius14px,overflow hidden. KPI and quad each four equal columns,gap12px,top margin12px. KPI padding16px,radius13px; icon38×38 radius10px,gap10px. Mini-card padding14px,radius13px,min-height215px. Card-title bottom11px; rows9px 0,gap9px; doc-icon28×28 radius7px. Recent-table margin-top12px,padding14px,radius13px. Right quick/AI cards padding14px,bottom12px,radius13px. Quick row padding11px,gap12px,margin-top8px,radius10px; icon35×35 radius9px. | `#page-home .home-wrap` |
| P-02 create | Modal560px; three baseline fields name/type/scope stacked in existing order. Inputs/selects39px,padding0 10px,border1px,radius8px. Do not move required supplemental controls into the original three field positions; put template/context details after them or in the following context view. | `#modalMask .modal` |
| P-03 editor | Columns `minmax(650px,1fr) 356px`; main rows48px 48px 1fr; main right border1px. Doc-top padding0 16px,gap10px; toolbar padding0 15px,gap7px. Tool height31px,min-width31px,padding0 8px,radius7px. Scroll surface padding20px; paper max-width880px,min-height1040px,margin0 auto,padding34px 56px 60px,border1px,radius4px. Summary padding15px 17px,radius9px. Paper table margin9px 0 18px. | `#page-editor`, `#docTree`, `.paper` |
| P-04 Copilot | Rail rowsauto 1fr,min-height0. Tabs49px,each flex1,active border3px. Body padding12px,overflow auto. Assistant/evidence/quality cards padding13px,radius12px,bottom11px. Robot42×42 circular,font22px; welcome flex gap10px. Six actions grid2 cols,gap8px,top12px;padding10px,radius9px. Prompt top11px,columns1fr 34px,min-height78px,radius9px; textarea padding10px,resize none; send18px. Response top10px,padding10px,radius8px,12px line1.6. | `[data-aipanel="copilot"]` |
| P-05 Evidence | Same rail/tabs/cards; `.evi-item` padding10px with dashed top rule1px; preserve source text hierarchy, extend on explicit details navigation rather than filling rail with all raw fields. | `[data-aipanel="evidence"]` |
| P-06 pending items | Same rail/card/list; baseline Process buttons float right,height28px,standard button horizontal padding. Supplement details opens a dialog; count remains in its existing tab pill. | `[data-aipanel="todo"]` |
| P-07 templates | columns1fr 310px; main padding18px and scroll. Head flex gap12px; search360×38px,radius9px,padding0 12px. Segment gap20px,margin15px 0 10px,buttons9px 3px. Chips wrap,gap8px,margin10px 0 14px,padding8px 12px,radius8px. Grid `repeat(4,minmax(180px,1fr))`,gap12px. Card padding11px,radius12px,transition.15s. Cover125px,radius8px. Tagrow margin9px 0,gap5px; tag3px 6px,radius5px. Metadata margin8px 0; action rowgap7px,buttonsflex1,height31px,radius7px. Detail border-left1px,padding18px,scroll; cover190px,radius10px; bottom buttonsgap8px. | `#page-templates` |
| P-08 Review | wrapper padding16px,height100%,scroll. Title flexgap10px; icon42×42px (radius inherited7px). Segment as templates. Metrics4 equal columns,gap12px,margin15px 0; metricpadding14px,radius12px,flexgap12px. Gauge58×58px,border7px,circular,center text. Filters flexgap8px,bottom10px; filterpadding7px 12px,radius8px; keyword input width270px. Grid350px `minmax(420px,1fr)` 370px,gap12px,min-height560px. Three panelsradius12px,border1px,overflow auto. Issue headerpadding12px; issue columns58px 1fr auto,gap9px,padding11px. Detailpadding18px; tracepadding14px; sourcepadding12px,top10px,radius10px; excerptpadding9px,radius7px. | `#page-review` |
| P-09 subviews | Preserve Review title and exact four-tab strip; new bodies use the S contracts below, not nonexistent source mocks. Initial results body remains P-08. | `#page-review > .workspace > .seg-tabs` |
| P-10 knowledge / P-11 analytics | Baseline shared placeholder grid centered, centered inner text,large icon64px,heading `#16366c`,body `#7a90af`,Return button. Approved replacement bodies retain shell/header navigation and provide Return through page header. Placeholder prose is not a production design. | `#page-placeholder`, `#placeholderTitle` |
| P-12 toast/note | Exact shared-overlay rules above; persistent errors/tasks must remain in S state panels after1800ms toast dismissal. | `#toast`, `.mobile-note` |

### Responsive & platform visual contract

Single source media rule: **`@media(max-width:1180px)`** changes body overflow to auto, app min-width1180px and displays the note. At1180px it is active;1181px it is not. App still has height100vh. No mobile stacking, collapsed sidebar, resized cards, dark theme, image breakpoint or alternate mobile project is supplied. Existing width overflow is part of baseline evidence, not permission to squeeze columns. Supplemental grids follow the same desktop shell and internal horizontal scrolling; avoid clipping active dialogs at narrower viewports by testing available scroll/focus visibility, without claiming a redesigned mobile mode. Capture 1920×1080,1440×900,1181×800,1180×800,1024×768 and768×1024 under one pinned browser/font setup; inspect 200% zoom separately as accessibility evidence.

## Elevation & Depth

| Element | Exact shadow / layering |
|---|---|
| Sidebar, workspace | `0 7px 24px rgba(21,73,139,.07)` |
| Logo | `0 6px 15px rgba(11,107,255,.22)` |
| KPI | `0 4px 14px rgba(23,70,130,.05)` |
| Paper | `0 3px 15px rgba(30,72,130,.06)` |
| Template hover/selected | `0 6px 18px rgba(19,97,225,.09)` |
| Toast | `0 8px 30px rgba(15,40,85,.22)` |
| Dialog | `0 20px 70px rgba(10,40,90,.24)` |

Keep borders as1px except the explicitly3px active tab rules and7px gauge ring. No added glass/backdrop blur or heavy generic Ant Design elevation. Overlay stacking is topbar10,dialog40,toast50,narrow note99; added popovers must remain inside the dialog's focus context when opened there. A toast never obscures/operates as an approval confirmation.

## Shapes

Source radii are deliberately nonuniform: paper4,tag5,severity6,tool/tree/doc icon7,field/chip/cover8,button/project icon/prompt9,search/inset10,project/storage11,editor/template/review card12,home card13,workspace/hero/dialog14. Pills999,progress99,circles50%. Do not collapse all of these to Ant Design's default radius.

**Artwork and icon fidelity.** No image files, remote image URLs, SVG library, icon font or photo ratio is used by this HTML. Logo, hero decoration and template cover art are CSS. Hero pseudo-element is270×170px,right70px,bottom-45px,gradient145deg `#7fb6ff66,#dceaff44`, polygon `(0 60%,35% 28%,48% 45%,70% 15%,100% 60%,100% 100%,0 100%)`. Cover pseudo-element100×90px,right-20px,bottom-25px,fill `#64a6ff33`,rotate-20deg. Standard/green/purple/orange covers use145deg gradients respectively `#f7fbff→#e5f1ff`, `#f1fffb→#d9f7ef`, `#f8f5ff→#ece5ff`, `#fffaf0→#ffefd2`; big-cover `#fff→#deecff`.

Icons are literal Unicode strings in the source, including font/emoji-fallback-dependent glyphs. Preserve exact code points and positions in baseline mode; do not swap a library icon because it is semantically similar. Existing icon text is decorative when a readable label exists. Important glyph inventory (code points avoid introducing decorative emoji into this contract): home U+2302; document U+25A3; knowledge U+25A4; template U+2318; review top U+2713/side U+25C8; analytics U+25A5; project-space U+25A7; chevrons U+2304/U+203A/U+25BE; project U+2261; favorites U+2606; recycle U+2672; bell U+2667; hero U+1F44B; robot U+1F916; link U+1F517; preview U+1F441; placeholder U+1F9E9; severity filters U+1F53A/U+1F7E7/U+1F537. Keep symbols with their variation selectors as encoded in the HTML when extracting implementation assets; the complete source text, not this mnemonic list, wins for that distinction. No actual image proportion can be certified until uploaded user assets exist; S preview preserves intrinsic aspect ratio (`contain`) inside its fixed viewport, without cropping evidence or documents.

## Components

### Shared visual components and implementation states

These exact names also appear in EXPERIENCE.Component Patterns. Baseline rest/hover/selected styles above remain; supplemental state treatments are named separately.

| Component | Visual specification and state treatment |
|---|---|
| Shell navigation | P-00 geometry. Active top/side entries synchronized. S project/account/notification popover: white,1px line-secondary,radius12,padding13,width356; text13px; item padding9px 8px. Never replace topbar's six entries. |
| Button and input | Exact38px button/39px field; baseline small variants31,30,28px retained. S focus outline `{components.focus.outline}`,offset2; disabled S control shows disabled label/reason,not opacity-only; invalid S field1px `{colors.supplement-error}` and12px inline message below5px gap. Busy indicator occupies existing icon slot, label remains. |
| Tabs and filters | Home tabs gap24px,buttons10px 2px; template/Review segments gap20px,buttons9px 3px; AI tabs49px equal widths. S uses same segment and filter geometry; no generic underline thickness substitution. |
| Data list/table | Baseline13px,cell9px 8px,collapsed borders. S tables keep this geometry; long IDs wrap in detail or expose full value on focus,not page-width expansion. Rows min38px; only explicitly selected row gets existing issue selected fill. |
| Status and task card | Baseline pills/severity/score styles; S persistent task card uses editor cardradius12,padding13,11px bottom gap,header13px700; stage list13px,8px row padding; IDs12px; a progress track only when actual progress exists. State text is always present. |
| Metric summary | P-01 KPI and P-08 fixed decorative quarter-ring gauge geometry retained. This ring is NOT an accurate radial percentage arc. Actual value and numerator/denominator text are truth. S analytics uses text-backed metric tables instead of new chart shapes; no categorical palette invented. |
| Document canvas and toolbar | P-03 exact paper/toolbar; S selection target and unsaved/conflict status appear in existing status area/adjacent contextual panel,not as absolute overlay covering typed text. Added controls go in existing More menu. |
| Copilot and prompt | P-04 geometry. Streaming/draft text stays inside response/task card, never quietly inserts into paper. No additional chat avatar rail. Expanded operation chooser in contextual dialog560px. |
| Evidence and source viewer | P-05/Review card style. S full viewer layout main `minmax(420px,1fr)` +356px provenance inspector,gap12,padding18; source excerpt in quote treatment. Metadata label12px,value13px; long quote scrolls in a420px-high viewport. |
| Pending item resolver | P-06 Process retains28px button; detail dialog560px,label12/input39px,reason textarea minimum96px,S state summary13px; actions bottom-right gap8px. |
| Template browser/editor | P-07 unchanged baseline. S admin body tree260px +`minmax(480px,1fr)`+310px inspector,gap12,padding18. Section/rule fields39px. Preview uses intrinsic-ratio pages inside scroll area,not stretched cover art. |
| Issue inspector | P-08 exact geometry and severity. S reason/recheck results are beneath existing handling actions,13px,top12px; action row remains in original order. |
| Dialog and toast | P-02/P-12 geometry; focus state per shared input. S error dialog body scroll,max-height calc(100vh - 40px),actions remain reachable. Source modal Escape/backdrop semantics are not falsely asserted; supplemental behavior in EXPERIENCE. |
| Diff and version comparison | S main header24px + metadata12px; list of changed blocks with before/after columns `repeat(2,minmax(320px,1fr))`,gap12; panelpadding13,radius12. Text14px,line1.85; deleted text has strike plus label,inserted text underline plus label,red/green soft fills secondary. Source and version bars persist. Conflict third/base view is a selectable tab,not three squeezed columns. |
| Approval and release gate | S list350px +detail `minmax(420px,1fr)`,gap12,padding18. Decision header24px; gate table13px/cell9px 8px; status text plus pill; summary/action footer within detail. Approved is not styled as Published unless published. |
| Tender workbench | S top header24px,context metadata12px,tabs per Review. Parse/detail layout350px source-index +`minmax(420px,1fr)` source/response +356px requirement inspector,gap12,padding18. Matrix is full-width horizontally scrollable with explicit columns in EXPERIENCE; no card-only substitute. |
| Form Builder | S left260px field palette/tree +`minmax(480px,1fr)` canvas +310px properties,padding18,gap12. Palette entries13px,padding9px 8px; canvas white,border1px,radius12,padding18; fields39px,labels12px. Rows/columns are schema-defined,not inferred from sample paper. |
| Form instance and scan | S main `minmax(480px,1fr)` +310px validation/provenance rail,padding18,gap12. Input type/labels align with Builder; repeating-table rows min38px. Scan preview420px-high contain viewport,readable extracted values beside it; no camera always-on view. |
| Export and artifact viewer | S dialog560px for request; task/result view main +356px details,padding18,gap12. Preview page area paper-surround,document contain; format/size/checksum/expiry labels12px,value13px. Failure does not turn the result region into an empty successful download link. |
| Knowledge and conflict management | S source list350px +main `minmax(420px,1fr)` +356px inspector,padding18,gap12. Conflict counterpart cards equal width,quote treatment; each has source/version/effective date. Keep knowledge authority separate from security classification. |
| Analytics and evaluation | S header24px; one filter row38px controls/gap8px; tabs quality/coverage/rules/evaluation/monthly; metric table13px; details below with12px gaps. Four headline summaries may reuse KPI geometry ONLY when actual values/denominators exist. No new plot is required for this design; all comparisons are numeric tables with units and time windows. |
| Administration and policy | S admin navigation260px +detail `minmax(480px,1fr)`,gap12,padding18. Details use cards13px padding and versioned field forms; permissions presented as labeled matrix table,not color-only toggles. Secret-reference fields display masked/reference identifiers only. |
| Context and outline | S header24px; outline tree260px +editor `minmax(480px,1fr)` +310px missing-info inspector,gap12,padding18; field labels12px,controls39px. Mandatory chapters marked textual required; drag alternatives use existing31px tool geometry. |

### Complete supplemental surface layouts

Every row defines a body, not a future-design placeholder. Entry paths are in EXPERIENCE; retain P-00 shell on all full pages. Apply shared component metrics above rather than duplicating widths as arbitrary new tokens.

| Screen ID / supplement | Top-to-bottom / left-to-right body composition | Visual anchor |
|---|---|---|
| X-01 Diff / SUP-1 | Header document/base/current/task; view switch and changed-block list; paired before/after panes; Evidence/Claim disclosure per change; selected accept/reject footer; conflict banner when stale | Diff and version comparison |
| X-02 history/conflict / SUP-1 | Version selectors + author/time/provenance; compare panes; base/local/server toggle; per-block keep mine/use latest/manual merge controls; unresolved-count and checked-save footer | Diff and version comparison |
| X-03 approval inbox/detail / SUP-2 | Inbox filters and candidate rows; selected request metadata; pinned-document preview; Review/gate checklist; decision reason; approve/reject actions; immutable history below | Approval and release gate |
| X-04 release gate / SUP-2 | Pinned version/template/policy header; required chapter,issues,pending,coverage,conflict,ACL,DLP,template,human approval,audit checklist; actionable failure link per row; confirm/publish; export/return status after result | Approval and release gate |
| X-05 tender intake/requirements / SUP-3 | Bid identity/version; upload and parse task; source page index; source excerpt preview; selected requirement fields (type,mandatory,disqualification,scoring,source); validation/save; revision history | Tender workbench |
| X-06 bid compliance / SUP-3 | Bid/version filters; mandatory/response/state filters; matrix; selected row response excerpt +Evidence/source links; residual-name/parameter check task and findings; navigation to Review/release | Tender workbench + Data list/table |
| X-07 schema builder/version / SUP-4 | Schema name/version/mode; palette/tree; schema canvas; selected field properties/rules; AI proposal,validation,preview,save-version actions; changes/conflicts use X-01/X-02 | Form Builder |
| X-08 instance/print/scan / SUP-4 | Schema/instance/version header; data-entry/preview/scan tabs; declared fields; validation rail; add-row/attachments/signature; save/print/export/send actions; authorized integration status | Form instance and scan |
| X-09 integration delivery / SUP-4 | Target/contract/environment/version; delivery records/status filters; payload field-name summary without secrets; selected task attempts and receipt/correlation; retry/reconcile buttons with reasons | Administration and policy + Status and task card |
| X-10 knowledge / SUP-5, P-10 | Search/domain/context/version/classification filters; enterprise/attachment/Golden sources tabs; authorized source list; actual excerpt; provenance inspector; attach/cite/create-pack actions; management via X-11 | Knowledge and conflict management |
| X-11 knowledge governance / SUP-5 | Authority/freshness/conflict/return tabs; source versions; competing quotes/context; disposition reason; pending/Review links; Published-return gate table and task records | Knowledge and conflict management |
| X-12 analytics/quality / SUP-5, P-11 | Scope/date/version filters; quality/requirement-coverage/monthly tabs; definition/version/denominator; metric table and linked document/Claim/requirement rows; unavailable/unevaluated states | Analytics and evaluation |
| X-13 rules/evaluation / SUP-5 | Dataset/rule/run tabs; versioned definition forms; Golden Query/case table; selected model/retrieval/template configuration; run task; results table with denominators/errors; local-double vs real badge | Analytics and evaluation |
| X-14 template administration / SUP-6 | Metadata/scope/version header; upload validation; section/rules tree; editor; rendering/approval inspector; preview,publish,deprecate; affected pinned-document references read-only | Template browser/editor |
| X-15 context/outline / SUP-6 | Actual project/type/template context; fact table/glossary/constraints; attachment tasks; similar-document results; outline proposal; mandatory/missing validation; confirm outline and request sections | Context and outline |
| X-16 tasks/notifications / SUP-7 | Category/status filters; authorized task table; selected step/event details and final artifact; retry/cancel where supported; notification read/open controls | Status and task card |
| X-17 collections/references/recycle / SUP-8 | Existing sidebar destination title; tabs authorized records; filterable table; open/remove-favorite/restore-visibility under policy; no permanent-delete control; archive state text | Data list/table |
| X-18 search/project/account / SUP-8 | Search results with entity type and permitted context; project picker with current scope; account/department/clearance detail and session actions; role-gated project membership panel | Shell navigation + Administration and policy |
| X-19 export/internal share / SUP-8 | Pinned version,format/theme/classification/watermark summary; request/task/artifact; internal route copy disclosure and current authorization; no public-link/access-grant option | Export and artifact viewer |
| X-20 system governance / SUP-5,7 | Users/roles/scopes; Model Profiles; Prompt Registry; routing/DLP; connector contracts; audit; Feature Flags; policy/retention configuration sections. Each section has list,versioned detail,validation and permitted change action; not a raw unrestricted console | Administration and policy |

### Visual acceptance and source extraction evidence

1. The 7-5 baseline suite owns full B-surface P-00–P-12 comparison at matched viewport,zoom,font/OS,source fixture and control state. A functional Story compares only its changed B control/state. Compare layout,module positions,sizes,spacing,font family/size/weight/line-height,colors,radii,shadows,borders,icons,cover proportions,buttons,inputs,statuses and breakpoint behavior. The baseline environment and any approved masks/difference disposition are versioned; an unapproved difference is a finding, not an invented tolerance.
2. Maintain screenshot pairs for home; create modal; editor plus each of three AI tabs; each template selection/filter/detail; seven issues/four Review tabs; placeholder baseline; toast shown/hidden; narrow note at1180/1181. For fixed source sample content, use an explicit local fixture so line wrapping is comparable; for live data test structure and overflow separately. Do not put demo scores into production to force screenshot similarity.
3. Source CSS/HTML/JS were completely read for this authoring pass. A browser measurement attempt returned empty computed styles and implausible uniform100×20 geometry; it is rejected as evidence. No screenshots, pixel-equivalence, resolved font verification or accessibility pass are claimed.
4. S screens X-01–X-20 are spine-only references, intentionally no generated mocks under the Markdown-only/headless task. Validate them against these geometry tables, behavior and source requirements, NOT nonexistent source-identical screenshots. Existing B screen fidelity has priority; functional R/S deltas must appear in the difference register.
5. Use a component-style snapshot inventory to prevent Ant Design reset/UA changes from drifting typography and control height. Preserve unspecified source defaults in the source reference, record their actual browser-computed values in downstream evidence before declaring fidelity. No remote resources or mockups are required to understand the design contract.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Keep existing six navigation entries, four implemented-page bodies and modal/control geometry; extend through contextual menus/detail screens | Shrink the product to four pages or add arbitrary topnav destinations |
| Distinguish B visual baselines,R actual-business replacements,S authorized absent surfaces | Call new tender/form/admin screens source-identical |
| Show true saved/version/task/approval/export state using current permission-filtered records | Preserve hardcoded92/86%/78%,26% storage or1800ms success as business truth |
| Use explicit evidence, status text and accessible controls | Let color,confidence-like decoration or a model answer grant approval |
| Track VC-1/VC-2 and environment dependencies transparently | Silently redesign baseline colors/layout or present untested AA/fidelity claims |
| Keep new field decisions versioned and policy-dependent switches disabled without permission/configuration | Invent waiver roles,coverage thresholds,L2 external exceptions or public sharing |
| Preserve unmodified prototype and PRD | Write architecture,Epics,code or production configuration in S2 |

**Author self-check:** Both spines cover P-00–P-12,SUP-1–SUP-9,full Phase1–3,all48 FRs and18 NFRs through explicit matrices in EXPERIENCE. Token references are intended to resolve against this frontmatter. This statement is author coverage evidence only; independent review,main-project persistence,implementation and visual validation remain separate.
