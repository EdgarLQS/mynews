---
name: acceptance
description: Run an independent, evidence-backed acceptance pass for current project changes. Use when the user invokes /acceptance after development or asks to validate work against repository acceptance rules.
---

# Run Project Acceptance

1. Read `CLAUDE.md` and `docs/testing/acceptance-rules.md` completely before evaluating changes.
2. Treat `$ARGUMENTS` as the requested file, commit, range, or feature scope. If empty, use the complete working tree relative to `HEAD`, including untracked files.
3. Perform the first acceptance pass read-only. Do not fix, format, stage, commit, or delete files during this pass.
4. Select every required gate from the change-type matrix and run the applicable commands instead of inferring results.
5. Distinguish failures introduced by the scoped changes from pre-existing or unconfirmed failures.
6. Return the exact conclusion vocabulary and self-contained report structure defined by the acceptance rules.
7. For an “实施验收” or explicit “验收并修复” request, stop after the first report, then perform fixes as a separate development step, and rerun the affected gates plus the full acceptance before giving the final conclusion.

If the user also asks for fixes, finish and report the first acceptance pass before starting any implementation work, then rerun the affected gates after the fixes.
