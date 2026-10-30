# Reuse reviewed independent check inputs while retaining global write guards

Opt-in per-check contracts pin the reviewed non-independent inventory, command,
environment and executable. Only explicitly independent regions can change
without invalidating a scoped binding. Unknown/shared changes fall back to global
execution until the declaration is reviewed again. Full safe inventory scanning,
write-scope classification, input-change detection, approvals and legacy checks
remain independent and conservative. Strong case/review/probe checks continue to
execute fresh; no receipt reuse protocol is invented for them.

Receipts and reports distinguish GLOBAL/SCOPED/MIXED and identify actual reuse.
Original receipt/log integrity and task/worktree/branch identity are enforced.
Final integration review also corrected new-project detection when only a tool
bootstrap directory exists, preserving legacy engines without auto-migration.

Red: new input-binding regression initially failed without the implementation.
Green: independent reuse, shared/unknown/environment fallback, write-scope blocks,
inventory/path/mode/config changes, branch identity and missing original receipts.
Three-change fixture: A executions 4 -> 1, B remains 4. Full scans retained;
controller overhead slightly increased in the tiny fixture. No universal speedup
claim. Final complete baseline PASS in 203.261 seconds: 317 Python tests (8 skips), type/build, full Node and packed self-test, real OpenSpec and wizard. Final Node 20/22/24 suites each passed 79 tests with 4 skips (83 total); packed consumer smoke also passed on 22/24. Native Windows/Linux execution remains blocked by unavailable hosts/daemon. Final review additionally fixed dependency case re-evaluation (red/green evidence retained), effective-environment binding during global fallback and pre-operation contract validation.

Final retention review: retained exports now include original reused receipts/logs, case observations, semantic assertion sources and bounded baseline/mutant probe observations. Approval packages expose support and scope qualifications in all report formats. Focused checks passed (7 case/probe, 8 scoped-input, 10 reporting); the complete final baseline and final Node 22/24 package smoke passed afterward. An initial export-fixture path hit the existing symlink guard; only its temporary path was corrected, with no guard weakening. See `final-confirmed.log` and `retention-*-green.log`.
