# Story 1.1 visual gate — approved final post-format evidence

The post-round-19 whitespace-normalized rebuild passed all 19 browser tests. All 18 generated shell/reference, authentication/loading/failure and toast PNGs have been copied from that completed run. `current-screenshot-metrics.json` records their exact SHA-256 values and the current runtime image/source/container identifiers, alongside decoded per-pair diagnostics. No pixel acceptance threshold is applied.

Exact inherited CSS/layout and geometry checks pass at 1920x1080, 1440x900, 1181x800, 1180x800, 1024x768 and 768x1024. The original prototype source is unchanged. Current failure-state screenshots include the actionable dependency explanation; real identity, storage and task-state text remain authorized replacements. These automated checks do not replace independent screenshot review, which passed for all18 current images in the independent final-format review (see story-1-1-final-validation.md).

The named current images and metrics supersede the stale round-3 copies found during round 10. Earlier `difference-shell-*`, `screenshot-diff-metrics.json` and header-only images remain historical diagnostics; they are not measurements of the current captures.

## Historical round-3 record

The following is retained only as the previous run's record. Its counts, timings and approval apply to that earlier snapshot, not the refreshed images above.

> # Story 1.1 visual gate — round-3 review snapshot, 2026-09-10
>
> ## Automated contract result
>
> The shell test now compares the implementation with the script-disabled original prototype at the exact required viewports: 1920x1080, 1440x900, 1181x800, 1180x800, 1024x768, and 768x1024. It uses exact equality for computed layout and visual properties, element geometry, relevant text-range geometry, source icon text, and `::before`/`::after` artwork. The account strings are normalized in the in-memory reference page only. No pixel tolerance, ignored region, or source-file rewrite is used.
>
> The current coordinated production rebuild completed, and the current browser run passed **13 tests in 24.6s**. The matching screenshots were copied from that completed run. This supersedes the earlier 12-test record whose toast capture independent review found unreliable. That failure remains documented in `../story-1-1-review-2.md`; the erroneous toast files were replaced with the current evidence. Independent round-3 visual review approved these archived screenshots; subsequent code reviews are recorded separately.
>
> ## Preserved artifacts
>
> - `actual-shell-<viewport>.png` and `reference-shell-<viewport>.png`: matched-condition full shell captures.
> - `current-screenshot-metrics.json`: current measured difference counts, maxima and bounding boxes, not acceptance thresholds.
> - `difference-shell-<viewport>.png` and `screenshot-diff-metrics.json`: historical diagnostics from the earlier run, not measurements of the refreshed current captures.
> - `workspace-account-loading.png`, `workspace-authenticated.png`, and `workspace-readiness-error.png`: state evidence.
> - The earlier `actual-header-*` and `reference-header-*` evidence remains preserved and was not deleted.
>
> ## Implementation corrections found by the gate
>
> - The sidebar's third entry now retains the source label `知识管理`; the top navigation correctly retains `知识库`.
> - Sidebar navigation icon and label text now form the same single flex text item as the source markup. The previous React node split introduced an actual extra flex gap.
> - Unknown project storage retains the inherited progress-row geometry while clearly reporting `尚未统计`; it does not reuse the prototype's sample capacity or 26% value.
>
> ## Independent-review boundary
>
> PNG files are deliberately not used as an automatic pass/fail assertion. Their decoded differences remain material review input because real account, workspace, readiness, and Story 1.1 body content replace prototype sample content. The automated result proves the listed shell properties and geometry under the pinned browser conditions; it does not approve the screenshots, claim pixel identity, or replace the required independent visual/code review.
>
> ## Completed toast evidence repair
>
> The repaired contract includes the source P-12 toast in its hidden and shown states. A real search click drives the implementation state; only the script-disabled reference page receives the permitted direct class/text setup. Playwright's browser clock now holds the product's unchanged 1800ms timer while exact CSS/layout checks and bounded screenshots run, proves the toast is rendered rather than merely carrying `show`, verifies it remains shown at 1799ms and expires at 1800ms, and requires the shown implementation image hash to differ from its hidden image hash. Authentication and dependency failures remain in the persistent workspace notice. Exact comparison covers toast geometry, style and transition, and includes `content`, `left`, `right`, `top` and `bottom` for every selected pseudo-element.
>
> The browser suite also contains a logout race regression that shortens only the application's 15-second test interval, holds a periodic `/api/v1/me`, logs out, then releases the response and verifies that the account and authenticated controls stay cleared. A stalled-readiness case proves a readable timeout before the next poll. These changes have now been rebuilt and all 13 browser tests passed. Browser time is explicitly paused for evidence capture; the root agent directly viewed the refreshed shown screenshot and confirmed its visible dark-blue toast. The displayed/hidden image hashes differ. Production timing remains 1800ms.
>
> ## Commands
>
> ```powershell
> $portableNode = (Resolve-Path '.local/tools/node-v24.20.0-win-x64').Path
> $env:PATH = "$portableNode;$env:PATH"
> & "$portableNode\node.exe" "$portableNode\node_modules\corepack\dist\pnpm.js" exec playwright test tests/ux/shell.spec.ts
> ```
>
> At this archived snapshot, production build, Web static checks and 8 unit tests passed. The shared-runtime browser run completed, and independent round-3 visual approval was granted. Later unit/browser counts and code-review state are maintained in ../story-1-1-verification.md. No pixel identity, Story completion or enterprise/production acceptance is claimed.
