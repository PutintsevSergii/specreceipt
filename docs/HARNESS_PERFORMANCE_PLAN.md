# Harness reporting and verification performance

Status: APPROVED
Revision: 1
Approval: Developer approved in chat on 2026-10-26: "Утверждаю, реализуй оптимизацию".
Tech-Spec-Revision: 0
Architecture-Revision: 0

## Problem and observed evidence

The Windows portability work exposed a performance problem in the harness itself, amplified by integration fixtures. Extending timeouts does not fix it.

- .harness/reporting-performance-baseline.json records one isolated adopted-kit fixture with 118 source files. Direct library status: 1.6893 seconds / 2 full fingerprint scans; report before task start: 0.7739 seconds / 1 scan; next_action: 1.2179 seconds / 1 scan; transition to IN_PROGRESS: 10.1012 seconds / 8 scans; transition to IMPLEMENTED: 5.6963 seconds / 8 scans. These are single observations, exclude CLI startup, and are not latency percentiles.
- A separately profiled complex lifecycle scenario made 206 fingerprint calls. cProfile increases execution cost, so its 145-second duration is diagnostic, not a normal latency estimate.
- The interrupted required full-suite run completed 194 cases before interruption, with portability failures. It is neither a complete baseline nor PASS. Two concurrent full runs added load and will not be repeated.
- Native end-to-end installation from an empty private runtime with Python/Node/uv absent from PATH passed all nine installation stages. Evidence: .harness/windows-full-install-proof-report.json. The performance issue does not imply WSL is necessary.

## Bounded design

### PERF-001: One immutable snapshot for each read-only report

Introduce an explicit report snapshot containing the current source fingerprints, environment binding and observation timestamp. Pass it through report-only evidence freshness and reconciliation calculations. Share it across all tasks and output formats in that report. Discard it when the report finishes.

The default authoritative APIs must continue to compute fresh inputs. Do not add a process-wide, persistent or modification-time-based cache. Report snapshots must never be passed into transition eligibility, approval or final verification decisions.

### PERF-002: Coalesce derived report work

Keep durable state, events, transaction recovery and evidence writes immediate. Coalesce duplicate derived-report refreshes performed by a transition and its checkpoint, so one public operation refreshes the derived current report at most once after its final durable change.

Retain direct Python-library callers as well as CLI/protocol callers. An exception after a committed transaction must leave a truthful stale-report marker, not old output presented as current. Standalone checkpoint and recovery operations must retain their report behavior.

Reuse the final operation snapshot only for rendering derived reports after source-affecting work ends. Fresh content scans remain mandatory before critical gates and after external commands. File changes between separate operations must always be observed.

### PERF-003: Visible bounded progress

Publish check name, start time, elapsed time and test progress while a full check runs. Preserve final result, command, content-bound logs and hashes.

Do not persist unredacted child output. Keep the current private raw-output handling until bounded streaming redaction is explicitly implemented and tested. A safe first slice may publish only structured test identifiers/counts and timing, with the existing final redacted log.

Show the slowest test cases and report interrupted execution honestly. Preserve timeout descendant cleanup and failures on missing verification.

### PERF-004: Improve the developer loop without reducing final coverage

Profile fixture preparation and separate fast unit checks from full integration checks in explicit commands. Keep the existing default full self-test and required final verification complete. Do not silently replace full verification with a quick subset.

Only minimize fixtures after identifying a measured repeated cost. Keep actual-kit adoption, recovery, symlink/junction and real process integration tests. Avoid hard links or shared mutable fixture state that could modify source files.

## Implementation sequence

1. Capture three isolated baseline samples of the benchmark before changing performance mechanisms; count full scans and report refreshes.
2. Implement PERF-001 and regression tests for identical reporting semantics, source changes between calls and no snapshot reuse by authoritative gates.
3. Implement PERF-002; test nested transition/checkpoint calls, direct library callers, failures after commit, and recovery/stale-report behavior.
4. Implement structured progress/timing and benchmark again. Investigate remaining fixture costs only if the measured acceptance targets are not achieved.
5. Run bounded affected regressions and compare the counters. After they pass, perform one sequential complete verification run, review the diff separately and checkpoint. Do not launch duplicate full suites concurrently.

## Acceptance

- A read-only report uses at most one source inventory snapshot, shared across its tasks; repeated separate reports detect intervening content changes.
- Each public mutation produces at most one final derived-report refresh.
- On the same 118-file harness fixture, the two measured task transitions reduce full inventory calls from eight to at most four, without changing decisions or evidence semantics. Application transitions may need additional fresh scans around external index work; do not remove those to meet a counter.
- Median transition time improves by at least 2x versus the fresh three-sample baseline on the same host and fixture. Report actual full-suite time; do not promise an unmeasured two-minute suite.
- Tests prove fresh rejection of content edits preserving timestamps, additions/deletions, symlink/junction changes, approval/config changes and source mutation by a check.
- State/event/evidence durability and crash recovery remain unchanged. Derived report failures cannot silently approve work.
- Progress exposes active check and elapsed time; test execution exposes counts/timing without leaking secret fixture values.
- Every existing required check remains mandatory. Interrupted, skipped and unexecuted checks stay distinguishable from PASS. Platform-specific capability rules from the approved Windows follow-up remain in force.

## Scope and limits

Likely implementation: harnesslib/core.py, reporting.py, reconciliation.py, CLI/protocol operation boundaries only if needed, associated tests, benchmark/progress helper scripts, docs and generated kit assets. No dependency installs, background watcher, global content cache, OS policy change, source transmission, commit, push or publication is included.

Implement the snapshot and report-refresh slice first. Any change to gate semantics, persistent state schemas, approval policy or mandatory coverage requires a renewed concrete decision. Implementation is authorized by the developer approval recorded above.
