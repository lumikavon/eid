# Story 1.1 review round 4

Verdict: changes-required. Verification independently ran 92 Python tests, 20 Web unit tests and 13 browser tests successfully against the reviewed snapshot. Acceptance and blind reviewers returned findings; blind coverage was partial for deployment/scripts. Edge reviewer was interrupted after a request to conclude, without a terminal report; its layer must be rerun before approval.

| Finding | Source | Root disposition |
|---|---|---|
| Missing invalid request-ID and zero trace/span boundary tests | verification | Patch. Added parameterized replacement, schema and header/body correlation checks. |
| Missing nbf must be rejected | blind, acceptance | Rejected. Frozen intent requires validation of nbf, not mandatory presence. RFC 7519 section 4.1.5 defines this claim as optional. Existing future-nbf rejection remains; explicit valid signed no-nbf regression documents interoperability. No security gate waived. |
| Readiness accepts wrong runtime issuer/audience | acceptance | Patch. Public discovery issuer/JWKS consistency and fixed local audience are checked before usable signing keys. Negative runtime configuration tests added. |
| Continuously inspect persisted Keycloak audience mapper | acceptance (same finding) | Provisioning boundary, not a new API admin capability. Existing bootstrap guard verifies persisted mapper before migration/startup. Runtime discovery/config checks above address wrong runtime settings. Continuous administrative drift monitoring is not specified for Story 1.1; API receives no Keycloak administrator credentials. |
| Transient account failures clear valid token | blind | Patch. Typed rejection handling clears session only for 401/403; transient failures clear visible account, preserve in-memory token and allow retry. Browser regressions cover 503/recovery using the same token and 401 rejection. |
| Notification Space key unsupported | blind | Patch. Space/Enter handling preserves source DOM/CSS and prevents Space scrolling. Browser regression added. |
| Visual ledger still says round-3 approval pending | acceptance | Patch. Ledger now distinguishes approved archived screenshots from current code review. |

Standard consulted: [RFC 7519 section 4.1.5](https://www.rfc-editor.org/rfc/rfc7519#section-4.1.5). Root additionally ensured 401/403 rejection is classified before reading an optional error body, so a stalled body cannot conceal an already known authentication rejection. Current Python suite: 105 passed, 8 gated live cases; Web units: 24 passed with pinned Node 24.20.0. Rebuild/browser run and fresh independent round 5 remain required.
