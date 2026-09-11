# Story 1.1 review round 5

Verdict: changes-required. Four fresh independent reviewers completed their assigned reviews. No findings were deferred. Verification independently ran the then-current Python suite; it did not rerun browsers. Binary artifacts were inspected from the workspace; the generated textual diff had missing EOF separators, corrected for the next review snapshot.

| Finding | Source | Disposition |
|---|---|---|
| Conflicting prepare/record flags bypass live checks | edges | Patch: mutually exclusive CLI action group rejects combinations before work. |
| Direct runtime recording lacks public readiness | edges | Patch: public readiness precedes image inspection and atomic recording. Root repaired direct-script package import after actual bootstrap exposed it. |
| prepare plus check-only creates ownership state | edges | Patch: incompatible modes rejected; check-only missing-owner case proves no state creation. |
| ID/refresh token substitution | blind | Patch: signed JWT payload must declare Keycloak Bearer type; wrong/missing type tests. |
| Local-only logout leaves SSO session | blind | Patch: explicit signout submits RP-initiated logout; 401 invalidation remains local. Root changed hint transport to POST form so no token appears in URL. |
| 403 treated as failed authentication | blind | Patch: persistent workspace denial retains session, stops account retries, provides signout. |
| Implicit flow not explicitly guarded | blind | Patch: imported and persisted client explicitly disables it; guard rejects unsafe flow, exact post-logout redirect validated. Actual implicit-flow request was denied with 302 error and no access token. |
| JWKS rotation not executed | acceptance | Patch: real PyJWKClient against controlled local HTTP server caches old kid, fetches new kid, rejects wrong signature. |
| Runtime secret/token log scan missing | acceptance | Patch: owned-container log scanner reports only match counts; actual execution evidence recorded separately. |
| Omitted required claims not tested | verification | Patch: omitted exp/iat/sub rejected; nbf remains optional and future nbf rejected. |
| Real account SQL filters not tested | verification | Patch: rollback-only isolated PG data covers unmapped/inactive identity/inactive membership and valid mapping. |
| API marker/revision mismatch not tested | verification | Patch: all mismatch combinations reach helper and structured 503. |
| RabbitMQ API failure not tested | verification | Patch: failing broker client reaches helper and structured 503. |
| Worker delivery settings not asserted | verification | Patch: quorum/durable queue, confirms and JSON serializer invariants. |
| Exact tool/engine rejection not exercised | verification | Patch: negative low-level version/engine cases alongside failure-stop bootstrap shims. |
| Connected DB/role/marker/port/volume mismatch not exercised | verification | Patch: guard low-level negative matrix. |
| Callback failure UI not observed | verification | Patch: invalid-state callback displays error and fresh-login action. |
| Advertised automatic recovery not observed | verification | Patch: actual registered 15-second periodic retry observed using held response; root removed unreliable one-shot 100ms test substitution, also from logout race test. |

The guard development agent was interrupted after failing to return a terminal report; root inspected its files and ran the complete Python suite (144 passed, 9 gated live tests). Its natural-language completion was not used as evidence. Root also verified Web units after POST logout changes (26 passed). Browser and bootstrap failures during integration remain recorded; only subsequent successful runs count as gate evidence.

POST logout support was verified against [Keycloak 26.3.3 LogoutEndpoint source](https://github.com/keycloak/keycloak/blob/26.3.3/services/src/main/java/org/keycloak/protocol/oidc/endpoints/LogoutEndpoint.java). The hint remains in request body and is never persisted in browser storage or written to logs by application code.
