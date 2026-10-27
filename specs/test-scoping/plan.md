# Scoped test execution plan

Status: APPROVED
Revision: 1
Approval: Developer approved revision 1 in chat on 2026-10-27: "Утверждаю план, реализуй".
Tech-Spec-Revision: 0
Architecture-Revision: 0

## Decision and research

Use the existing stdlib unittest and Node test runner; introduce no pytest migration, plugin or dependency. Apply explicit suites plus conservative test impact selection. Keep expensive filesystem/process integration scenarios; change their invocation frequency before attempting fixture rewrites.

The author's [Practical Test Pyramid](https://www.martinfowler.com/articles/practical-test-pyramid.html) recommends fast early feedback, narrow integration boundaries and avoiding duplicated broad tests. [Paul Hammant's TIA article](https://martinfowler.com/articles/rise-test-impact-analysis.html) distinguishes manually maintained suites from coverage/call-graph selection. Our initial manifest is the former: it must not be described as complete dynamic TIA. [Python unittest](https://docs.python.org/3.12/library/unittest.html) already supports module/class/method selection and failure exit codes. [GitHub's workflow documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) warns that workflow-level path filters can leave required checks pending; keep the workflow triggered and decide work inside it. Use only Node runner features supported across the existing Node 20/22/24 range.

## Observed baseline

- Recorded Python run 55bba3ba-ddf3-4390-9312-4ac203bf8591: 246 discovered, 12 skipped, zero errors/failures, 1189.057 seconds. This is historical evidence, not a fresh run.
- CONTRIBUTING.md currently requests npm tests plus the complete Python self-test for any change.
- verify.yml repeats the same Python suite in six Linux/macOS Node jobs and three Windows Node jobs. Python logic does not need repeating for each Node version; native Node/package compatibility still does.
- HarnessTests.setUp adopts the kit into a new project; reporting/performance/reconciliation tests reuse that fixture. Onboarding has another adopted-project fixture. A test-file change may affect other files through fixture reuse; selecting only the edited filename is insufficient.
- Required external indexes ensured successfully. CodeGraph query self_test located the empty-suite regression and progress implementation. Graphify's bounded query located reporting, fixtures and verification, with an explicit truncation warning. Source inspection, not graph heuristics, supports this plan.
- Connected GitHub tools exist but add no needed evidence for local test dependency mapping. Public research used web access; no repository source was transmitted. Local discovery is CODE_ONLY and agent-attested.

## Implementation sequence

1. Add tests/run_scoped.py and tests/test_scopes.json. Keep them outside production modules and the public harness command registry. Commands: `python tests/run_scoped.py --profile smoke`, `--profile changed [--base REF] [--dry-run]`, and `--profile full`. Support explicit suite/module selection for investigation, labelled manual rather than automatic coverage. Resolve the repository root from the script location and invoke subprocesses with argument arrays.
2. Add tests/test_test_selection.py using tiny temporary Git repositories and fake check commands. Test changed-file collection and plan/execution contracts without adopting the kit, calling models or running real integration suites. Tests must also work when copied into an adopted kit; do not depend on unshipped scripts or Node packages merely to import the selector.
3. Build the manifest from inspected source and test imports, with explicit cross-language/package edges. Select whole existing modules initially; method-level selection is allowed only as a separately reviewed explicit smoke/manual list. Do not pretend name matching establishes impact coverage.
4. Separate CI into a scoped change job, existing native Node compatibility coverage, and one complete Python job per OS on main/release/manual full runs. Do not use workflow-level path filters. Preserve native symlink requirements and controlled real OpenSpec/package integration. Cancel superseded runs for the same PR/ref; do not run two copies of a full suite for one revision in a single job.
5. Update CONTRIBUTING.md and add docs/TESTING.md with local Windows/POSIX commands, scope expansion rules, examples, final acceptance requirements and honest timing. Replace the guide's generic instruction to run the full suite after every edit with a link to the explicit profiles; retain the full self-test's meaning.
6. Run selector unit/contract tests, smoke, dry-run audits of representative diffs, and separately review selection/CI boundaries. Run one final complete Python regression for this migration, not after each edit. Record measured counts, actual durations, skips and limitations. No production build or generated-asset rewrite is needed for this test-only migration.

## Initial impact boundaries

| Changed area | Minimum affected checks / expansion |
| --- | --- |
| One tests/test_*.py file | That module plus transitive test importers/shared fixture consumers; a new unmapped test is an error until mapped. |
| reporting.py / report_operation.py | Reporting and performance modules plus reviewed lifecycle/reconciliation consumers. |
| workflow.py / readiness.py / assessment.py / investigation.py | Corresponding modules plus onboarding, workflow and hardening consumers identified by imports and inspected calls. |
| adopt.py / installation.py / runtime.py / tool adapters | Adoption/installation/tool/platform modules plus affected Node/package integrations; expand for shared consumers. |
| src/ boundary | Corresponding Node modules, TypeScript check and required build prerequisite; engine/filesystem/install/upgrade changes expand to package/upgrade and native checks. |
| core.py / storage.py / verification.py / cli.py / protocol.py / shared fixture / schema / dependencies / launchers / packaging / selector rules | Complete relevant Python/Node/package boundary; do not force a narrow run for a foundational change. |
| Known prose-only documentation | Explicit no-runtime-tests report; documentation assertions/templates referenced by tests are not prose-only. |
| Unknown path or unresolved relationship | Explainable full fallback; bad/missing configuration fails before execution. |

The implemented manifest must enumerate every current production and test boundary and its rationale; this table is a design, not the finished map. Static imports are a conservative supplement, with explicit edges for subprocess/dynamic/configuration relationships. No external graph is required to run the selector.

## Verification mapping

| Criteria | Evidence |
| --- | --- |
| TST-001, TST-004 | Profile/CLI unit tests; no-profile and dry-run subprocess tests; synthetic failing command proves nonzero exit; scoped/empty/skipped labels inspected. |
| TST-002 | Temporary Git repositories: base history, dirty index/worktree, untracked file, rename/delete, paths with spaces/Unicode, missing base and subprocess failure. |
| TST-003 | Known narrow diff excludes unrelated suites; two changed boundaries take union; fixture change includes consumers; unknown/foundation changes widen; stale/malformed rules fail. Audit all current source/test files against the manifest. |
| TST-005 | Inspect CI triggers, merge-base fetch, no checkout of untrusted base commands, no duplicate Python-by-Node matrix, retained platform/real-tool checks; run actual selected entry points locally. |
| TST-006 | Compare full discovery inventory before/after; diff review proves no removed assertions/runtime edits; one final full self-test and structural validate PASS. |

Target smoke runtime is at most 30 seconds on this host and selector unit tests at most 10 seconds, subject to measurement. No promised duration for broad/foundational changes. If the smoke exceeds budget, select a smaller meaningful cross-boundary contract list rather than silently skip checks. Full-suite acceleration itself is outside this slice.

## Approval and rollback

The user requested planning and implementation, but AGENTS.md and the planner require approval of a concrete new plan before implementation. The developer explicitly approved revision 1 in chat on 2026-10-27; implementation of this test-only plan is now authorized. Approval covers the test-only scope and the explicit CI frequency decision above. Historical task gates and runtime evidence semantics remain unchanged. Rollback removes the new runner/manifest and restores prior contributor/CI commands; existing full self-test continues working throughout.
