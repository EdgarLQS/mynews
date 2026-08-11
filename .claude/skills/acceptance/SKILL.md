---
name: acceptance
description: Run an independent, evidence-backed acceptance pass for current project changes, including source/plugin packs and expanded collection. Use for /acceptance, implementation acceptance, acceptance-and-fix requests, or validation against repository acceptance rules.
---

# Run Project Acceptance

1. Read `CLAUDE.md`, `docs/README.md`, the feature matrix, the unique Current plan, and `docs/testing/acceptance-rules.md` completely before evaluating changes; for source/plugin scope, also read the authoritative source catalog.
2. Treat `$ARGUMENTS` as the requested file, commit, range, or feature scope. If empty, use the complete working tree relative to `HEAD`, including untracked files.
3. Perform the first acceptance pass read-only. Do not fix, format, install plugins, stage, commit, switch branches, or delete files during this pass.
4. Select every required gate from the change-type matrix and run the applicable commands instead of inferring results.
5. For source/plugin work, record the prepared plugin environment and separately verify entry-point discovery, factory loading, unchanged default collection, plugin-only selection, additive expanded collection, and every affected source's live probe.
6. Treat fixtures and temporary `.dist-info` as Implemented evidence only. A source is Verified only after its own real probe is healthy and parses a valid record; missing environment or external denial is BLOCKED, while missing planned code or a broken contract is FAIL.
7. For watchlist or output-safety work, verify no network/Store/Codex side effects, no sensitive-value echo, atomic failure recovery, and preservation of prior outputs.
8. Distinguish failures introduced by the scoped changes from pre-existing or unconfirmed failures, and return the exact conclusion vocabulary and self-contained report structure defined by the acceptance rules.
9. For an “实施验收” or explicit “验收并修复” request, finish and report the read-only pass first, then fix as a separate development step and rerun affected gates plus full acceptance.

Never count a duplicate built-in source or a test-only/stale source expectation as new coverage. If the user also asks for fixes, finish and report the first acceptance pass before starting implementation, then rerun the affected gates after the fixes.
