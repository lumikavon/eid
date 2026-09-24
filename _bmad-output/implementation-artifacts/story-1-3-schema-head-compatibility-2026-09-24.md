# Story 1.3 schema-head receipt compatibility repair

## Source finding

Epic 1 static integration review found that the discovery seeder accepted schema heads 0007–0010 while the UX preflight required the completion receipt to say 0007. The isolated live fixture migrated to the current Alembic head but also asserted 0007. A first compatibility patch exposed a provenance gap: changing only an old completion receipt's supported head could pass a version-only check.

## Software correction

- New seed runs first read the guarded database head without writes, then create an exclusive v2 plan with `creation_schema_head`. The plan is created before any fixture data transaction. A second guarded read and the write transaction both require the pinned head.
- A v2 completion receipt must name exactly the plan's head. The UX preflight accepts only exact v2 plan/completion shapes and checks that the guarded database is not older than the receipt. A mismatched or unknown head fails closed.
- Historical v1 plan/completion bytes remain unchanged and may be replay-checked by the seeder. They cannot authorize a new UX run because they do not independently bind the creation head; a new v2 run is required.
- The isolated live fixture records its observed migration head in `Store` and compares retained receipts and later connections against that observation.

## Verification and limitations

Python syntax compilation, targeted Ruff, and `git diff --check` passed. Independent `eid_reviewer` static review accepted the final patch. The verified Muse Spark 1.3 Contributor model was called for auxiliary read-only review. Test source now covers current and legacy versions, drift, plan pinning, and post-plan schema advancement, but the test suite, database, migration, services, browser, and actual environment were **not run** under the current policy.

The pinned head is the version observed before fixture data writes. A concurrent migration after the final version read has not been exercised; the guarded schema and transaction constraints still require actual migration validation when permitted. The local receipt files remain trusted evidence: a party able to rewrite both plan and completion files can forge a self-consistent pair without a separate immutable anchor. Historical v1 receipts cannot retrospectively prove their original creation head.
