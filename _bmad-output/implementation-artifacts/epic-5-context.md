# Epic 5 Context: Review all four core document types

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Experts inspect version-pinned findings and authors complete technical solutions, PRDs, test plans and measurable technical requirements using current authorized sources. Review results and human decisions must not turn a stale or incomplete document into a publishable one.

## Stories

- Story 5.1: Run eight Reviewers against a pinned version
- Story 5.2: Inspect real findings, trace and review history
- Story 5.3: Resolve findings with distinct human decisions
- Story 5.4: Compose a source-grounded technical solution
- Story 5.5: Author a structurally complete PRD
- Story 5.6: Maintain Phase 1 requirement-to-test coverage
- Story 5.7: Make technical requirements measurable

## Requirements & Constraints

- Eight categories (structure, fact, requirement, technical, quality, consistency, style, safety) each persist execution state, findings, input version, rule/model provenance; missing or failed mandatory checks never imply completion. Findings locate the exact document/section/block/Claim/source and carry quote, impact and suggestion.
- Review management combines severity, section, status and keyword filters and keeps selected detail, counts, trace, version comparison and history consistent with the pinned run. Undefined metrics and zero denominators are unevaluated, never fabricated 100% or approval.
- Human decisions accept/reject/modify/handled are separate: applied changes need recheck, rejection requires a reason, severe unresolved issues remain blockers, waiver requires configured authorization and cannot bypass non-waivable safeguards.
- Technical solutions need approved template chapters, current project facts and standards, supported architecture/parameter claims; unknown values remain pending. PRDs persist structured requirements with stable IDs and locators, including exception flows, permissions and acceptance criteria.
- Phase 1 test plans preserve bidirectional versioned requirement/test-item/test-case/acceptance links, show uncovered and redundant coverage and reject altered approved thresholds. Technical requirements retain condition, metric, unit, threshold, verification method and source provenance; vague or invented thresholds stay actionable findings.
- Current scope allows software implementation, source/static checks and offline compilation. Test suites and live services, migration, browser, real model, enterprise and field validation remain not-run. Independent quality review is deferred by the current user instruction; story implementation stops at review.

## Technical Decisions

- API owns authoritative persisted document/version, Review and issue decisions; Worker outputs versioned proposals and may not grant publication/approval. Immutable AST versions and stable Section/Block/Claim IDs are authoritative; allowed block kinds are paragraph, heading, table, figure, diagram, requirement, citation, warning, code, form.
- Durable task/outbox/inbox and current access/policy rechecks bracket worker execution and final commit. Revocation, changed document head, missing policy or failed checks fail closed. Task completion, Review completion and Published are distinct states.
- Evidence is versioned, authorized and source-located. Check source applicability before exposing excerpts or supporting critical facts; model substitutes must be labeled and cannot prove efficacy. Review pin includes rule, template and model provenance.
- Per-type template structure and rules are versioned; missing corporate-approved templates cannot be represented as official. Metrics retain definition version, numerator, denominator, sample and environment, with explicit unevaluated state.

## UX & Interaction Patterns

- Preserve prototype review page shell, four tabs, list/detail/trace columns, filters and four action labels. Replace example counts and scores with authorized records or explicit empty/stale/denied states. Changing selection clears old details.
- Existing create/editor/outline/Copilot/Diff/Review flow remains common to all four types; supplement missing bodies according to UX without claiming source-pixel equivalence. A fresh task is required to rerun; edited documents need fresh review. Do not expose revoked excerpts.

## Cross-Story Dependencies

- 5.1 builds on safe model/graphics and task foundations; 5.2 consumes real runs; 5.3 uses findings and reviewed Patch mechanics. 5.4 and 5.5 reuse the shared author/Review chain. 5.6 depends on structured PRD requirements; 5.7 uses issue decisions and test traceability. Formal approval/export belongs to Epic 6 and real efficacy/UAT/capacity to Epic 13.
