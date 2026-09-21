No blocking defects found for the specified properties.

`edw-web/src/auth/oidc.ts:20`:
- allowlist is exact-match: `/`, `/admin/members`, workspace UUID + `home|documents|favorites|references|recycle|search|project|projects|account|resources/UUID|records/UUID`.
- full-match check `exec(path)?.[0]===path` correctly rejects trailing `$` artifacts (`\n` etc).
- `beginLogin:41` stores only `pathname`, never `search`/`hash`.
- `parseTransaction:28` rejects stored `returnTo` with `?`/`#`/`//`/`javascript:`/traversal/non-UUID/encoded before `fetch`.
- one-shot `removeItem` + `history.replaceState:62` before validation.

`edw-web/src/features/workspace/DiscoveryPanel.tsx:28-37`:
- `kindConflict` home/documents + `kind!=document`, `collectionConflict` references + not `all|references`, `tabConflict` favorites + `tab!=favorites` match spec.
- `canRead:45`, `activeError:55`, `retry:64` early-return, `perform:81` block, `portal:103` + top-level `filterConflict` branch hide cached `list/summary/detail/todo/projects/storage`.
- `rawFilterKey:36` gives distinct keys for `knowledge` vs `reference`; compatible `references?collection=all` stays enabled.
- `reset:73` via `location.pathname` clears query; `ReadState:19-20` shows reset-only when `retryable=false`.

Minor observation, not blocking:
- inner `listUi:94` conflict guards are unreachable because top-level `103` already branches; harmless defense-in-depth.
- `reset` on `records/:id` preserves detail path and drops `from/kind`; clears conflict but differs from old `base/view`.

Future tests only, no execution:
- oidc: `/%2e%2e`, `%0A/%00`, overlong `returnTo`, `returnTo=null/number`, uppercase method, `post_logout` without `id_token`, double `finishLogin` after failure without `beginLogin`.
- discovery: compatible `documents?type=/status=`, `references?kind=knowledge`, `search?kind=`, `favorites?tab=favorites` stay enabled; `records/:id?kind=` without `from`; reset lands on `pathname` without `search`; `perform`/pagination disabled on conflict; storage portal absent on conflict.
