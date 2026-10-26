# ADR 001: Historical completion, current regression and bounded dispatch

Status: Accepted for harness maintenance, 2026-10-23
Authorization: User explicitly requested primary-source research, selection of implementable improvements and correction of the audited harness. This decision does not approve any application, provider installation, source transfer, access-policy change or deployment.

## Evidence and alternatives

The audit reproduced three failures: downstream edits invalidate prerequisite DONE tasks, `.env.test` changes leave evidence current, and an unresolved review can authorize DONE. Scope and acceptance were only partly executable; decision blockers were global.

Primary sources consulted on 2026-10-23:

- [Bazel remote caching](https://bazel.build/remote/caching): actions identify commands, inputs and environment, with content-addressed results. Adapted principle: execution evidence has explicit identity separate from workflow progress. We retain conservative whole-workspace verification rather than claiming a complete dependency graph or introducing unsound selective caching.
- [SLSA 1.2 provenance](https://slsa.dev/spec/v1.2/provenance): evidence describes origin and production context. Adapted principle: bind each run to task definitions, checked prerequisite tasks, environment, commands and acceptance results. Local records are not signed attestations and do not establish SLSA compliance.
- [Temporal workflows](https://docs.temporal.io/workflows): persisted events distinguish durable workflow progress from external activities. Adapted principle: save intent before adapter execution and preserve uncertain outcomes after interruption. This small local dispatcher does not implement Temporal's deterministic replay or distributed guarantees.
- [Anthropic long-running harness experience](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) and [application harness experiments](https://www.anthropic.com/research/harness-design-long-running-apps): incremental tasks, structured handoffs and evaluation of actual user flows address premature completion. Adapted principle: separate implementation from review and advance only through executable gates. Reported experiments support these patterns, not a universal success guarantee for our implementation.
- [GitHub check runs](https://docs.github.com/en/rest/checks/runs): execution state and conclusions are structured. Our review contract similarly records a verdict and located findings instead of treating Markdown headings as success.

Importing Bazel, Temporal or a provider SDK would add infrastructure and select a host without addressing the small local failure directly. The selected implementation uses only Python's standard library, independently written code and the existing transaction journal. No external code was copied or package installed.

## Decisions

1. DONE is historical completion under the current task/policy definition and recorded approvals. Source changes mark regression stale, without undoing historical completion. Definition or review changes still require rework. Verification of a dependent executes the deduplicated transitive prerequisite checks. Final dispatcher completion additionally requires each DONE task's regression to be current.
2. Verification inventory is independent of navigation exclusions. Include dotfile configuration, binary assets and executable bits; ignore OS metadata. Refuse symlinks rather than silently omitting them or reading outside the workspace. Installed packages/build outputs remain excluded; their runtime versions must be declared. Do not claim detection of remote service changes.
3. Task start records a snapshot. Subsequent implementation/verification/completion checks reject additions, modifications and deletions outside explicit file or directory-prefix scope. Existing changes are preserved. Reviewed replanning can update policy inputs but cannot absorb unrelated source edits.
4. Every acceptance criterion maps to required checks. Execution records their outcomes. This proves declared checks ran, not that the assertion is semantically adequate. Review requires one typed JSON block, a current task/evidence reference and resolved findings.
5. Decision targets accept explicit task, feature or requirement selectors. Unknown selectors fail closed; legacy prose remains global. Scoped decisions may remain unresolved during baseline sign-off but block the selected task and dependents.
6. Deterministic next actions are read-only. The optional dispatcher persists budgets and only invokes explicitly configured adapters for allowlisted tasks. Implementation and review are separate subprocess invocations. External credentials, sandboxing, source access and provider permission remain the host's responsibility. An exit code alone never completes a task. Required human approval remains a stopping point.

## Consequences and migration

Legacy evidence and heading-only reviews cannot establish new completion. Existing projects need explicit acceptance maps and re-verification/review. Do not invent missing past scope baselines; use reviewed replacement tasks where necessary. Adoption remains conflict-preserving, so updating an existing project requires reviewing the proposed merge.

No Git history is available in this checkout. A baseline was saved under /tmp/harness-before-20261023 before implementation; review compares against it. Temporary fixtures exercise the dispatcher with local deterministic adapters, not a live model/provider. A project must configure and authorize its own adapter before unattended implementation can run.
