# Story 1.1 independent review — round 1

Date: 2026-09-10. Result: **changes-required**. All five layers completed; none failed. The user-approved visual method is exact layout/CSS verification plus independent screenshot review, not pixel identity.

## Finding verdicts before grouping

| ID | Layer | Finding | Verdict and verified evidence | Route |
|---|---|---|---|---|
| B1 | blind | Missing bootstrap modules in supplied diff | high: `git check-ignore -v` confirms global `*_LOCAL_*.*` excludes both required Python modules; they are absent from the generated change list | patch |
| B2 | blind | NGINX replaces incoming request ID | medium: nginx config uses `$request_id`; API is designed to validate the caller ID; reviewer reproduced replacement through localhost:18080 | patch |
| B3 | blind | Non-object JWKS crashes readiness | medium: main.py calls `.get` on response JSON without type validation and does not catch AttributeError | patch |
| E1 | edge | Late account refresh restores logged-out identity | high: App awaits getMe then unconditionally sets account; logout does not fence in-flight loads | patch |
| E2 | edge | Worker accepts old schema revision | medium: worker only selects a constant from alembic_version and never compares required revision | patch |
| E3 | edge | parse_ocr/render have no consumer | false for this Story: no producer or business handler exists in Story 1.1; implementing parsing/rendering belongs to later stories and requires isolation, not adding heavy queues to the normal process. Queue declarations are retained as the architectural seed | reject |
| E4 | edge | Non-object JWKS crashes readiness | medium: same verified cause as B3 | patch |
| A1 | acceptance | Required files omitted from delivery snapshot | high: same verified global-ignore cause as B1 | patch |
| A2 | acceptance | Worker absence does not fail system startup/readiness | high: no Worker healthcheck, API omits Worker state, final compose up omits --wait | patch |
| A3 | acceptance | Incomplete structured error/trace contract | medium: architecture.md:325 requires details/trace_id/retryable, absent in handler and schema; middleware generates no trace when absent | patch |
| A4 | acceptance | Built image tags do not identify tested contents | medium: manifest records reusable 0.1.0 tags only; source/container image IDs must be captured and checked in acceptance evidence | patch |
| V1 | verification | Schemas have no executable contract consumer | medium: schema-backed response assertions are absent; workspace_slug regression would escape current tests | patch |
| V2 | verification | Worker dependency gate not observably tested | high: no real process health assertion or negative dependency-probe check | patch |
| V3 | verification | Bootstrap stop behavior only text-matched | high: source substring assertions cannot prove failed guard prevents Alembic | patch |
| V4 | verification | Logout race not tested/fenced | high: same verified cause as E1 | patch |
| UI1 | visual | Required P-12 toast omitted | medium: App has no toast element; spec requires it; persistent errors alone do not replace transient feedback | patch |
| UI2 | visual | Toast states absent from precise contract | medium: follows UI1 and needs shown/hidden/transition coverage | patch |
| UI3 | visual | Pseudo position/content omitted from comparison | low: current screenshot positions look correct, but the exact-check claim exceeds selected properties; add direct properties | patch |

## Grouped repair plan

1. Deliver ignored bootstrap sources; record source-bound running image IDs; execute failure-stop tests.
2. Preserve request correlation; complete safe error/trace envelope and executable schema tests; reject malformed JWKS shapes.
3. Validate Worker schema/marker and expose real Worker health in startup and readiness; add process/dependency tests.
4. Fence late account responses across logout; restore source toast and verify exact hidden/shown styling; extend pseudo checks.

All accepted findings are in Story 1.1 scope and have an unambiguous fix. No product decision or further user permission is needed. No finding is dismissed merely to pass the gate. Independent reviewers must re-review the complete repaired change before done/commit.

## Independent visual assessment

All six required viewports were inspected. Header, sidebar, gaps, icons, borders, radii, shadows and narrow-screen overflow follow the original. Differences in main body, actual identity, unsupported collection counts and unknown storage state are authorized replacements. Loading/authenticated/readiness-error captures are readable. The missing toast prevents approval; screenshots are not claimed pixel-identical.
