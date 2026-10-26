# Native Windows and performance verification

Task: WIN-001. Required execution: PASS on stable final inputs.
Evidence: .harness/evidence/55bba3ba-ddf3-4390-9312-4ac203bf8591.json.
Approval: native revision 1 and follow-up approved in chat; performance plan explicitly approved: "Утверждаю, реализуй оптимизацию". Final developer acceptance was subsequently recorded in reviews/final-acceptance.md; WIN-001 is DONE.

## Required execution

| Check | Observed result |
| --- | --- |
| harness-tests | PASS: 246 discovered tests, zero failures/errors, 12 explicit skips; 1189.057 seconds including progress bookkeeping (about 19m49s). |
| harness-validate | PASS. Application readiness remains separately unconfigured; this is harness maintenance. |
| native-indexes | PASS with real pinned native CodeGraph and Graphify indexes. |
| native-node | PASS: 28 tests, 26 pass, 2 POSIX cancellation skips. |
| native-typecheck | PASS. |

All eleven mappings WIN-001 through WIN-007 and PERF-001 through PERF-004 PASS. No stable-inputs failure exists in the final run. Earlier failed/interrupted executions remain in the task history; they were not rewritten as PASS.

Python skips: eight real file-symlink cases lack Windows privilege 1314; two POSIX shell cases are inapplicable on Windows; two optional global-Graphify CLI fixtures lack that executable on PATH. Project-local real Graphify is independently required and passes native-indexes. Strict Windows CI sets HARNESS_REQUIRE_SYMLINK_TESTS=1, requiring real symlink execution. Real unprivileged junction tests run locally.

## Measured performance

Three samples before and after, direct library calls on the same adopted-kit fixture construction. The optimized kit has 121 source files versus 118 before because three service/test files were added. These are local medians, not CLI latency percentiles or guarantees for large repositories.

| Operation | Before median | After median | Full scans before/after |
| --- | --- | --- | --- |
| status | 0.7053s | 0.3455s | 2 / 1 |
| report before task start | 0.4083s | 0.2384s | 1 / 1 |
| next_action | 0.4935s | 0.2727s | 1 / 1 |
| transition to IN_PROGRESS | 2.2125s | 0.5589s | 8 / 3 |
| transition to IMPLEMENTED | 1.7185s | 0.5788s | 8 / 3 |

Evidence: .harness/reporting-performance-comparison.json and the three reporting-baseline/optimized sample JSON files. Transition targets (at least 2x faster and at most four scans) pass. No speedup ratio is claimed for the entire test suite: the old full baseline was interrupted. The final full integration suite still takes roughly twenty minutes on this host.

Reports share one immutable observation, discarded after use. Public operations coalesce final derived-report refreshes while durable state/events remain immediate. Transition/approval gates and before/after-check bindings still read fresh inputs. Negative regressions cover same-timestamp content edits, external check mutation, additions/deletions, real junctions, approval/reference changes and process exit after commit. Progress records counts, active test, elapsed time and slowest cases; it is last-observed diagnostic data, never execution evidence or liveness proof. Raw child output remains private until final redaction.

## Actual native entry points

- .harness/windows-full-install-proof-report.json: all nine native installation stages PASS from an empty private runtime with Python/Node/uv absent from PATH, into a fresh temporary project outside the kit. This preceded the performance-only changes.
- .harness/windows-clean-bootstrap-final.log: real verified uv/Python installation and execution using --no-bin --no-registry. The obsolete installer HTTP 403 was mitigated by fixed official release origins and pinned SHA-256.
- .harness/optimized-package-smoke.json: final immutable archive, offline cached consumer installation, real OpenSpec initialization and CLI validate PASS. The archive includes report_operation.py and test_progress.py. Full packaged self-test repetitions were not run.
- .harness/native-fast-command.log: the documented Windows focused-test argument-array invocation PASS. Focused checks remain partial diagnostics; final required verification executed the entire discovered suite.

## Review and limits

Reviewer: Codex, separate same-session final diff review; not independent proof. See reviews/WIN-001.md bound to the exact final execution. All recorded implementation findings are resolved.

Hosted Windows/Linux/macOS CI, interactive Windows wizard and a clean-OS virtual machine were not executed here. An isolated empty-runtime/PATH test is not a whole clean-OS attestation. No system-wide execution-policy change or WSL was used. The developer subsequently authorized completion and repository push. See docs/releases/0.4.0.md for the release-version verification boundary. No npm publication or deployment is claimed.
