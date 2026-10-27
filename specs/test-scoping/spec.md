# Scoped test execution

Status: DRAFT
Revision: 1
Approval: Pending developer review of this concrete proposal.
Tech-Spec-Revision: 0
Architecture-Revision: 0

## Outcome and boundary

Give contributors an explainable, change-based test run instead of requiring the entire integration suite after every edit. This is test infrastructure maintenance, not application implementation. The canonical application documents remain DRAFT and do not authorize application work.

Only tests, test execution infrastructure, CI and contributor documentation may change. No changes to harnesslib/, src/, production launchers/installers, schemas, runtime gate behavior, version, dependencies or historical WIN-001 records. Generated assets must not be rebuilt in this slice; packaging integration remains a separately tested boundary. No installs, paid agent runs, publishing or push are included.

## Acceptance

| ID | Observable criterion |
| --- | --- |
| TST-001 | Explicit smoke, changed and full profiles exist. Running without a profile prints usage and does not silently execute the full suite. A scoped PASS is labelled as scoped, never as complete acceptance. |
| TST-002 | Changed selection includes staged, unstaged and untracked paths locally; an explicit Git base includes committed changes too. PR selection uses the actual merge base with the target branch. Renames inspect both paths; deletions, spaces and Unicode are supported using NUL-delimited Git output. Missing bases and Git errors fail visibly. |
| TST-003 | A reviewed impact manifest maps source boundaries and shared test fixtures to suites. Every selected check has a reason. Unknown paths, malformed rules, missing mapped tests and changes to foundational boundaries widen selection or fail visibly; they never silently select zero tests. |
| TST-004 | A dry run lists changed paths, selected suites and exact commands without executing tests. Execution propagates nonzero exits, reports elapsed time and does not count skips/unexecuted checks as coverage. Empty diffs and approved prose-only diffs have explicit distinct reports. |
| TST-005 | PR/development runs use affected suites. Full Python regression remains available through the unchanged harness self-test and runs once per OS, separately from Node-version compatibility jobs, on main/release/manual full CI. Package, upgrade and real-tool integration stay explicit checks for their affected boundaries and final acceptance. |
| TST-006 | Existing assertions and negative/recovery/process/platform tests remain discoverable. Selector tests cover selection failures and dependency relationships. Runtime source remains byte-for-byte unchanged. The migration receives one complete final Python regression, after scoped checks pass, rather than a full run after each edit. |

## Risk decision for approval

This changes when CI executes broad regression: scoped PR checks give earlier feedback; complete regression still runs on main and for release/manual acceptance. Selection is a maintained conservative impact map, not proof of complete dynamic coverage. Changes to core/storage/verification/CLI/protocol, common fixtures, schemas, dependencies, packaging and selection policy trigger broader checks. A later coverage-derived selector or fixture rewrite requires its own measured proposal.
