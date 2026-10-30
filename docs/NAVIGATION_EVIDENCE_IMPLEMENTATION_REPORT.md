# Navigation and evidence implementation report

Execution: 2026-10-29; report finalized 2026-10-30. All five implementation phases are present and their applicable macOS gates pass. **Full mandate acceptance remains BLOCKED:** native Windows x64 and Linux execution was unavailable. This report does not label those targets verified or mark a maintenance task DONE.

## Reviewable changes and preserved baseline

The starting checkout HEAD and live default-branch revision were both `f322526354655935d7437dabda60d9b0f425a313`, package `specreceipt@0.4.3`. Existing uncommitted changes were inspected and preserved before implementation. The checkout HEAD and its index were not moved or replaced. A separate local branch, `codex/navigation-evidence-review`, contains a preserved workspace snapshot followed by five sequential implementation commits. An alternate Git index was used so the user's staging state stayed intact.

| Change | Commit | Review description |
| --- | --- | --- |
| Existing user work, before this mandate | `2ff2f4b700d860f17e4f3dcca404e51fbfd32f2e` | Preserved baseline; not attributed to this implementation |
| 1. Source-first navigation | `a44517f4b504d957e3444c2fa7ceeba8a8d275ae` | [PR 1](implementation-evidence/navigation-evidence/PR1.md) |
| 2. Independent worktrees | `1556d2d8952dcbeaecf2c43baaa80d55ddc9bbec` | [PR 2](implementation-evidence/navigation-evidence/PR2.md) |
| 3. Honest acceptance support | `474a6c652b67428602202c7fc73b24244b004fb0` | [PR 3](implementation-evidence/navigation-evidence/PR3.md) |
| 4. Case, review and fault evidence | `56a2e44639f35ef65b148aee87401775ff4b7f72` | [PR 4](implementation-evidence/navigation-evidence/PR4.md) |
| 5. Reviewed check-input bindings and final integration fixes | `957d51f6f3b0e24fa7557d48916c518889ca0581` | [PR 5](implementation-evidence/navigation-evidence/PR5.md) |

The last row is the **final implementation commit**. The branch's subsequent report-only commit adds this document; it does not change verified code. Review the mandate diff against `2ff2f4b`, not against the original HEAD, to exclude pre-existing user work. Final integration fixes in phase 5 include dependency case re-evaluation, tool-only bootstrap detection, retained evidence completeness and legacy upgrade regression coverage. No remote PRs, pushes, publication or deployments were performed. Package version, license and public authentication behavior were not changed. Maintenance followed `AGENTS.override.md`; consumer lifecycle commands appeared only in isolated tests, never as authorization for editing SpecReceipt.

## Implementation and public contracts

Python remains authoritative for policy, evidence and lifecycle enforcement. TypeScript installation and diagnostics resolve the same navigation policy. Generated kit copies and integrity manifests come from the canonical build.

New npm installations and Python adoptions create project-owned `.harness/navigation.json`:

```json
{"schema_version":1,"mode":"source","providers":[]}
```

An explicitly required single provider uses:

```json
{"schema_version":1,"mode":"required","providers":["codegraph"]}
```

`graphify` or both may be selected. Required mode enforces exactly that selection. Existing engines without this file retain both providers; malformed policy fails closed. A bootstrap `.harness/tools` directory alone is not mistaken for a legacy engine. Navigation changes bind into definitions, workflow approval material and freshness. Source mode invokes no implicit graph preparation and records no invented source or graph observations. Risk profiles, required commands and final approval semantics remain independent. See [policy resolver](../harnesslib/index_context.py), [installation](../harnesslib/installation.py), [doctor](../src/doctor.ts) and [consumer guidance](HARNESS.md).

[Worktree guidance](WORKTREES.md) uses normal Git operations and independently initialized local state. No workspace manager or copied state/approvals were introduced. Phase 2 retained global fingerprinting; phase 5 separately introduces reviewed per-check opt-in.

Evidence retains legacy command and `acceptance_results` semantics and adds versioned `acceptance_support`. Historical v1 receipts remain readable and unchanged. CHECK_ONLY means successful mapped commands, not observed tests. Explicit `required_cases` mappings require current named observations. CASES_OBSERVED, REVIEW_ATTESTED and FAULT_DETECTED report progressively different evidence, with INSUFFICIENT/FAILED preventing opted-in success. Dependency requirements are re-evaluated in downstream verification too. Terminal, Markdown, JSON and approval packages expose these distinctions.

The real adapter is a bounded stamped JUnit subset, emitted by `python -B -m harnesslib.junit_unittest test_module` through the existing command runner. Unique operation/check/invocation identity, exact input binding, content hashes, counts and stable case names are enforced. XML limits are 1 MiB, 1,000 cases and depth 12; DTD/entities, malformed identities, duplicate/ambiguous cases, stale paths and unsupported outcomes cannot satisfy requirements. Normalized redacted observations are retained; raw XML is removed.

Optional semantic review binds actual Python assertions, exact source text/locations/hashes, behavior, negative scenarios, gaps and reviewer identity/type. It is an attestation, not authenticated approval or proof. Optional probes copy a bounded fixture (100 files/4 MiB), run a good baseline, apply an exact mutation, and require the mapped case's expected AssertionError. Syntax/import/setup errors do not qualify. Probe artifacts retain bounded normalized baseline and mutant observations with hashes. Retained exports include original reused receipts/logs, cases, review/assertion sources and probes, within existing retention limits.

Per-check `input_contract` version 1 declares inputs, known independent regions, substantive rationale, approval reference/hash and reviewed revision. See the exact configuration example and migration instructions in [HARNESS.md](HARNESS.md). The revision binds non-independent inventory, check definition, declared/effective environment and executable identity/content/mode. Full safe inventory scanning and the separate write-scope guard remain in place. Unknown/shared/configuration/test changes fall back to GLOBAL execution until re-review; scope is never copied into evidence inputs. Legacy checks, builtins, case/review/probe checks and explicit regressions execute conservatively. Reuse requires an accessible successful original receipt and logs with matching task/worktree/branch/input identity. Reports distinguish GLOBAL, SCOPED and MIXED and identify `reused_from`; they do not claim full CI from a scoped pass.

## Acceptance matrix

PASS below is bounded by the listed executed macOS evidence. Rows that require unexecuted supported-platform coverage are explicitly BLOCKED.

| ID | Status | Evidence and limits |
| --- | --- | --- |
| NAV-01 | PASS | [Navigation regressions](../tests/test_navigation_policy.py), [packed smoke](implementation-evidence/navigation-evidence/final-package24.log): new source consumers, lifecycle and tool-only bootstrap, zero implicit indexer calls. |
| NAV-02 | PASS | Individual provider and malformed-policy regressions in [test_navigation_policy.py](../tests/test_navigation_policy.py); diagnostic/preflight coverage in [preflight.test.mjs](../tests-node/preflight.test.mjs). |
| NAV-03 | PASS | Absent-policy legacy behavior and [managed legacy upgrade test](../tests-node/engine-upgrade.test.mjs); [upgrade run](implementation-evidence/navigation-evidence/final-legacy-upgrade.log). No archived-package migration claim. |
| NAV-04 | BLOCKED | Inspected lifecycle/install/doctor/adapter/instruction paths and executed macOS paths agree; required native Windows launch execution remains unavailable. |
| WT-01 | PASS | [Actual two-worktree fixture](../tests/test_worktree_isolation.py), [phase 2 full run](implementation-evidence/navigation-evidence/phase2-full.log): separate state/receipts and no B-to-A invalidation. |
| WT-02 | PASS | Same fixture blocks A's unauthorized write, then requires fresh evidence after integration. |
| EVD-01 | PASS | [Legacy support tests](../tests/test_acceptance_support.py): old receipt bytes unchanged; read/report is check-only; invalid extensions rejected. |
| EVD-02 | PASS | [Case consumer CLI tests](../tests/test_case_receipts.py): exit-zero command remains PASS while missing required case makes support insufficient. |
| EVD-03 | PASS | Parser/identity/freshness/tamper/skip/xfail/ambiguity regressions in [case tests](../tests/test_case_receipts.py), [final focused log](implementation-evidence/navigation-evidence/retention-cases-green.log). |
| EVD-04 | PASS | Real unittest runner, bounded assertion review and correct behavioral probe, separately recorded and retained; [case tests](../tests/test_case_receipts.py). |
| EVD-05 | PASS | Syntax/setup fault rejection in [case tests](../tests/test_case_receipts.py); generic failure does not establish fault detection. |
| SCOPE-01 | PASS | [Scoped-input tests](../tests/test_scoped_inputs.py) preserve outside-scope blocking despite valid partial freshness. |
| SCOPE-02 | PASS | Independent reuse versus shared/unknown fallback, n=3 actual measurements; [final full run](implementation-evidence/navigation-evidence/final-confirmed.log). |
| SCOPE-03 | PASS | Path/mode/configuration/definition/environment/executable/branch/original-receipt regressions in [scoped-input tests](../tests/test_scoped_inputs.py), plus full existing safety suite. |
| SCOPE-04 | PASS | Default GLOBAL behavior; explicit report qualification, full final baseline and original receipt retention; [reporting](../harnesslib/reporting.py). |
| REL-01 | PASS | Source and packed consumer CLI, managed-upgrade fixtures, rebuilt kit, real OpenSpec and documented workflows agree on executed host; [final gate](implementation-evidence/navigation-evidence/final-confirmed.log). |
| REL-02 | BLOCKED | Existing local checks pass, but native Windows x64/Linux and Python 3.11 execution are unverified. macOS run skips platform-specific contracts explicitly. |
| REL-03 | BLOCKED | Five sequential review commits, local full gates and measured impact exist; all-platform acceptance cannot be asserted until blocked target checks run. |

## Executed verification

Host: Darwin arm64; Python 3.14.3; Node 20.20.0, 22.13.0 and 24.22.2. Node 24 was obtained from the official distribution with SHA-256 verification. Real OpenSpec 1.14.3 was used. Dependency installation used the pinned lockfile and a dedicated npm cache.

Executed `npm ci`, `npm run check`, `npm run build`, Node test suites, and the complete configured selector. The final command was:

```sh
npm run build
HARNESS_REAL_OPENSPEC=/private/tmp/harness-runner-tools/node_modules/.bin/openspec \
HARNESS_TEST_NPM_CACHE=/private/tmp/specreceipt-mandate-npm-cache \
python3 -B tests/run_scoped.py --profile full
```

The selector's logged commands include complete `harness self-test`, structural validation, version synchronization, TypeScript checking/build, asset generation, full Node tests, real package testing and wizard integration. It is the documented full baseline, not scoped substitution.

| Gate | Actual result | Evidence |
| --- | --- | --- |
| Phase 1 complete baseline | PASS, 164.549 s | [Log](implementation-evidence/navigation-evidence/phase1-full.log) |
| Phase 2 complete baseline | PASS, 167.285 s | [Log](implementation-evidence/navigation-evidence/phase2-full.log) |
| Phase 3 complete baseline after selector fix | PASS, 170.014 s | [Log](implementation-evidence/navigation-evidence/phase3-full-fixed.log) |
| Phase 4 complete baseline | PASS, 178.864 s | [Log](implementation-evidence/navigation-evidence/phase4-full.log) |
| Final complete baseline | PASS, 203.261 s; 317 Python tests: 309 passed, 8 skipped; 83 Node tests: 79 passed, 4 skipped; all nine configured checks exit 0 | [Final log](implementation-evidence/navigation-evidence/final-confirmed.log) |
| Full Node suites, 20/22/24 | Each 83 total, 79 passed, 4 skipped | [20](implementation-evidence/navigation-evidence/final-node20.log), [22](implementation-evidence/navigation-evidence/final-node22.log), [24](implementation-evidence/navigation-evidence/final-node24.log) |
| Final packed Node 22/24 consumers | PASS: actual init, repeat init, upgrade, Copilot coexistence, real OpenSpec and CLI smoke; 159 packed files | [22](implementation-evidence/navigation-evidence/final-package22.log), [24](implementation-evidence/navigation-evidence/final-package24.log) |
| Final retention regressions | PASS: 7 case/probe, 8 scoped-input, 10 reporting tests | [Cases](implementation-evidence/navigation-evidence/retention-cases-green.log), [inputs](implementation-evidence/navigation-evidence/retention-scopes-green.log), [reporting](implementation-evidence/navigation-evidence/retention-reporting-green.log) |
| Diff/generated consistency | `git diff --check` PASS; final build regenerated kit and hashes | Source and bundled evidence implementations match |

The full Node 22/24 suites preceded the final Python-only retention correction; their final packed consumers used the rebuilt correction. Node 20's final full gate tested the final tree. The designated package job runs the full packaged self-test; Node 22/24 package smoke deliberately does not duplicate that entire suite.

Red/green development is described per phase in PR1–PR5. Persisted failures were not hidden: [phase 3 initial full failure](implementation-evidence/navigation-evidence/phase3-full.log) exposed a missing selector boundary and was repaired; [dependency case red](implementation-evidence/navigation-evidence/dependency-cases-red.log) showed a skipped prerequisite incorrectly allowing downstream success, followed by [green](implementation-evidence/navigation-evidence/dependency-cases-green.log). A retention fixture used a symlink-alias temporary path and hit the existing export guard. Its path was corrected to the canonical root; no safety guard was weakened. An in-flight [earlier full run](implementation-evidence/navigation-evidence/final-acceptance.log) loaded that old fixture and failed; `final-confirmed.log` is the subsequent passing final run.

Limitations: eight Python and four Node native-platform cases were skipped, not passed. Windows junction/link privileges, npm `.cmd`, PowerShell/bootstrap and native launch contracts still need a Windows host. Linux execution was unavailable; Docker could not connect to `/Users/perfrico/.docker/run/docker.sock`. Only Python 3.14.3 ran here, not every supported Python release. Managed 0.3.x manifest/merge/recovery fixtures were exercised; actual historical-archive `test:upgrade` was not run because reviewed legacy and upgrade archives were not supplied. No live paid agent or authentication result is claimed. Test-only fixture approvals do not represent a human approval of this implementation.

## Measurements and impact

Raw samples and provenance: [measurements.json](implementation-evidence/navigation-evidence/measurements.json), extracted from the final full log. These are small same-host fixtures, not a controlled live-agent benchmark or model-token measurement.

| Measurement | Observed result |
| --- | --- |
| Source-mode ordinary consumer, n=3 | Zero indexer calls and zero extra graph commands. Adoption 0.0511/0.0488/0.0495 s; lifecycle excluding application checks 0.2823/0.2824/0.2844 s. |
| Legacy navigation comparison | Inspected baseline dispatched two providers at start, implemented and verify (six ensure dispatches, plus two queries). This is not six observed rebuilds. Real legacy graph wall time was not measured, so no numerical latency speedup is claimed. |
| Two real worktrees, one correctness scenario | Zero unrelated cross-tree invalidations/state changes; own-tree scope violation blocked; integration invalidated evidence and reran checks. Targeted run 1.240 s including checks. No live-agent parallel timing or approval-churn savings claim. |
| Two checks A/B, baseline plus three B changes | GLOBAL: A=4, B=4 executions. Opt-in SCOPED: A=1, B=4. Three unnecessary A reruns avoided; B rechecks retained. Shared/unknown mutations force execution in separate regressions. |
| Controller overhead excluding check runtime, n=3 | GLOBAL 0.1288/0.1311/0.1349 s; SCOPED 0.1686/0.1734/0.1762 s. The bounded reuse bookkeeping costs more in this tiny fixture. |
| Full inventory scan, n=3 | GLOBAL 0.00791/0.00760/0.00785 s; SCOPED 0.00779/0.00775/0.00782 s. Full scans remain; no hash-cache speedup is claimed. |
| Exit-zero with missing/skipped required case | Command PASS, criterion INSUFFICIENT and unsuccessful overall verification; required-case observations are not inferred from process success. |

Everyday tasks avoid graph setup; reviewed independent changes can avoid expensive unrelated checks. The accepted tradeoff is additional controller bookkeeping, not a guarantee of lower total runtime for cheap checks. No weakening of global scope enforcement or mandatory final integration checks was accepted.

## Compatibility, migration and rollback

- New installs receive source navigation. Existing installations lacking policy retain historical dual requirements across upgrade. Changing an existing project to source or a single provider is an explicit policy migration through its normal review/replan rules, not an automatic risk downgrade.
- Existing commands, tasks and v1 evidence remain readable. Legacy acceptance mappings remain check-only and do not retroactively invalidate historical DONE records. New extensions are optional and version-validated; unsupported future formats reject.
- Opt into case evidence by configuring the approved check's `report_format: "junit-v1"` and criterion `required_cases` mapping. Missing requested review/probe evidence blocks opted-in verification. Ordinary lint/build commands remain legitimate CHECK_ONLY checks.
- Opt into scoped reuse only after genuine review of the full dependency/independence declaration and its approval material. A hash binds that declaration; it cannot establish that its reasoning is correct or authenticate human intent. Any uncertainty should retain GLOBAL checks.
- Older strict readers may reject new optional fields. Preserve the compatible current reader with retained new receipts; do not strip evidence fields, rewrite history or pretend an older executable understands the extensions.
- Roll back reviewed implementation commits in reverse order on a clean dedicated branch after preserving consumer state and evidence. Compare against the preserved baseline and do not reset the user's working tree. Revert phase 5 to restore all-global execution first if the optimization is unwanted. Reverting newer evidence writers requires retaining a compatible reader/export for receipts already produced. Never delete artifacts or fabricate replacement approvals to make downgrade validation pass.

Remaining risks are bounded but real: a static independence review can be wrong; semantic review is an attestation; test observations cannot prove completeness; local hashes do not establish external-service freshness. Case/review/probe checks therefore remain fresh executions, unknown dependencies fall back globally, and external integrations still require their explicit checks. This iteration intentionally supports one bounded report format, Python assertion mapping and a narrow disposable fault fixture rather than a universal testing framework.

**Highest-value follow-up:** run the unchanged complete CI matrix on native Windows x64 and Linux (including required link privileges and supported Python/Node versions), retain the artifacts and resolve any failures before release acceptance. Until then the implementation is locally verified and reviewable, but the mandate's all-target acceptance is blocked.
