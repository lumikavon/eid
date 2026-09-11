# Story 1.1 review — round 2

Result: **changes-required**. All five layers returned; no failed layer. No human decision is required. The accepted user visual method remains unchanged.

| ID | Source | Verified outcome | Verdict / route |
|---|---|---|---|
| B1 | blind | Compose app health and runtime manifest do not probe final public readiness; live-only API health can remain green | high / patch |
| B2 | blind | Persisted Keycloak client validation omits the required access-token audience mapper | high / patch |
| B3 | blind | JWKS objects with string kid/kty but missing usable RSA material are accepted; use the correctly spelled kid field when reproducing the reviewer's mistyped example | medium / patch |
| E1 | edge | Unexpected endpoint exceptions escape request_context, losing the structured/correlated 500 envelope | medium / patch |
| E2 | edge | Unsupported or unusable signing keys may satisfy JWKS readiness; same cause as B3 | medium / patch |
| E3 | edge | Web fetch has no timeout/cancellation and periodic polls can accumulate when connections stall | medium / patch |
| A1 | acceptance | initialize_local_storage creates a bucket before RabbitMQ/Keycloak live checks; full guard failure does not guarantee zero prior S3 write | high / patch |
| A2 | acceptance | Final public readiness is not a startup success gate; same cause as B1 | high / patch |
| A3 | acceptance | Visual method note still says old bundle/not rebuilt despite later completed-run record | medium / patch |
| V1 | verification | Independent toast run failed before behavioral assertions at screenshot capture; capture path needs deterministic timing and bounded reproducibility | medium / patch |
| V2 | verification | Worker tests do not prove main invokes/rejects its gate or reject Redis/S3 failures | high / patch |
| V3 | verification | API Redis/S3 failure probes lack observable structured-503 tests | medium / patch |
| V4 | verification | /me psycopg failure lacks structured retryable-503 regression test | medium / patch |
| V5 | verification | Visual note contradicts latest run, same cause as A3 | medium / patch |
| UI1 | visual | Saved shown toast screenshot equals hidden screenshot; transient expired before evidence capture | medium / patch |

Grouped patches: 11. Zero deferrals/rejections. Group toast capture/behavior reliability together and retain both outcomes; group duplicate readiness, JWKS and document findings by their actual shared causes.

## Repair intent

- Check DB/ownership/ports, RabbitMQ and Keycloak before any S3 create; allow only empty or exact project bucket inventory, then full post-create validation.
- Gate success and manifest recording on bounded public readiness, with an executable orchestration negative test.
- Verify the audience mapper and parse at least one usable supported signing JWK.
- Preserve safe structured error/trace fields on unexpected failures; add missing dependency/entrypoint tests.
- Bound Web requests; make toast shown/hidden evidence deterministic without altering the product's 1800ms semantics or the original prototype.
- Refresh all narrative and screenshots from one final run; retain prior records explicitly as history.

Core shell visuals were independently accepted across six viewports; that does not waive the toast evidence repair or complete Story 1.1.
