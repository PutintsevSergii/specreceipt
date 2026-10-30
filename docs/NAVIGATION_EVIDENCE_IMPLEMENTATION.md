# Navigation and evidence implementation tracking

Baseline: 2026-10-29, HEAD and live origin/main
`f322526354655935d7437dabda60d9b0f425a313`, package 0.4.3.
The working directory contains pre-existing uncommitted runner, reporting,
workflow, schema, documentation and test changes. Preserve them. A binary diff
and the pre-existing untracked runner test were saved in
`/tmp/specreceipt-mandate-baseline` before implementation.

Maintenance authorization is the supplied engineering mandate and maintenance
instructions; consumer lifecycle approvals are not used to authorize engine work.

## Sequential boundaries

1. Navigation: `harnesslib/index_context.py`, adoption/installation, core input
   protections, CLI execution requirements, TypeScript install/doctor, agent
   instructions, tests and generated assets. Project-owned
   `.harness/navigation.json` version 1 selects source or named required providers.
   Absence means legacy dual-provider requirements. New adoption/init defaults to
   source only when no existing Harness installation is present. Invalid policy
   blocks. Policy changes affect task definitions and freshness.
2. Worktrees: real two-worktree integration fixture and portable instructions;
   preserve global fingerprints and independent state.
3. Evidence reporting: additive explicit check-only support status, legacy read
   compatibility and consistent report outputs; no historical receipt rewrites.
4. Case receipts: one bounded fresh JUnit adapter through the approved runner,
   distinct semantic attestations and opt-in targeted fault evidence.
5. Scoped inputs: opt-in reviewed independent regions filtered from the existing
   safe inventory, global fallback for unknown inputs; independent write guards.

## Existing coverage and baseline

`tests/test_codegraph_tool.py` covers bounded context and redaction;
`test_installation.py` covers adoption provisioning; onboarding and hardening
tests cover lifecycle, scope and freshness. `tests-node` and package smoke cover
the installed engine and native launch contracts. `docs/TESTING.md` defines full
verification. Missing regressions include source/provider policy, isolated
concurrent worktrees, observed-case evidence and per-check input reuse.

Static baseline: each `index_context.ensure` calls both providers (2 ensure
calls); each collect additionally queries both (2 queries). No timing or speedup
has yet been measured. Concurrent-task and final measurements remain pending.

Each phase requires its focused regressions followed by applicable full checks
and package smoke before the next phase. Platform execution is reported only
for hosts actually exercised. Final report must distinguish PASS/FAIL/BLOCKED
and must not call an unfinished phase complete.


## Final local gate status

All five implementation boundaries have local review snapshots and passing
applicable host checks. See NAVIGATION_EVIDENCE_IMPLEMENTATION_REPORT.md for the
commit list, actual results, measured costs and cross-platform blockers.
Final integration review corrected the tool-only bootstrap/legacy distinction,
Adaptive navigation approval binding, dependency case re-evaluation and effective
environment binding during scoped fallback. No consumer gate was relaxed.
