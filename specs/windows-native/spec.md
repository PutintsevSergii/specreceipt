# Native Windows support

Status: APPROVED
Revision: 1
Approval: Developer approved revision 1 in this chat on 2026-10-26: "Approve this specification and implementation"
Tech-Spec-Revision: 0
Architecture-Revision: 0

## Outcome and proposed platform decision

Run SpecReceipt and the repository harness on Windows x64 using Windows PowerShell 5.1 or Command Prompt, without WSL, Bash, MSYS2, administrator privileges, or a machine-wide execution-policy change. Preserve Linux/macOS behavior. Python >=3.11 and the existing supported Node versions remain runtime dependencies; native setup should detect compatible installations or offer explicit user-local provisioning. This is harness maintenance, not application onboarding or approval of the placeholder application specifications.

Windows ARM64, network-filesystem locking guarantees, application implementation, publishing and paid agent runs are outside this revision. Support must not be declared complete using mocked Windows tests alone.

## Observed evidence and limitations

- `harnesslib/storage.py:4` unconditionally imports `fcntl`. Invoking the launcher with the desktop's existing native Python reproduced `ModuleNotFoundError: No module named 'fcntl'` before command dispatch.
- `resume`, `status`, `next`, `indexes ensure`, and fallback `graph update --if-needed` all exited 1 at this import. No `.harness/state.json`, `.harness/events.jsonl`, or active `specs/` directory exists in this checkout. These are not passing checks.
- `src/engine.ts:30` explicitly rejects win32; `src/doctor.ts` recommends WSL and defaults Codex source-mode shell discovery to `/bin/sh`.
- `harnesslib/runtime.py` installs uv through sh and selects only Linux/macOS Node tarballs. Storage also assumes directory fsync support.
- `harnesslib/core.py`, `assessment.py`, and `tool_updates.py` use POSIX process-group termination. Native process cleanup needs explicit implementation and tests.
- `.github/workflows/verify.yml` runs the engine suite on Linux/macOS; Windows currently receives installer-contract tests only. `scripts/test-wizard.py` uses a Unix PTY.
- The host has filesystem/command tools and connected GitHub tools, but no observed CodeGraph/Graphify MCP tools. Local code is the relevant source; no remote lookup or source transmission is needed for these findings. Evidence is CODE_ONLY and agent-attested.

The index and investigation gates cannot execute until the native import failure is repaired. After approval, the first bounded maintenance batch repairs the engine's platform primitives, then retries those gates before broader work. No application implementation or gate weakening is proposed. A formal task model and content-bound investigation report must be established and validated once the engine can run; this document does not claim those gates passed.

## Requirements and acceptance

| ID | Requirement and observable acceptance | Verification |
| --- | --- | --- |
| WIN-001 | Native launchers and npm entry point reach the Python engine with no WSL/Bash. Paths with spaces and Unicode work; missing/incompatible Python gives actionable native instructions. | Native launcher and packaged lifecycle tests, including restricted PATH and missing runtime cases. |
| WIN-002 | Concurrent writers remain excluded; successful writes produce valid recoverable state. Interrupted writes and lock cleanup retain existing recovery rules. | Separate-process contention, interrupted transaction, replacement failure and recovery tests on Windows and POSIX. |
| WIN-003 | Setup detects or explicitly provisions native prerequisites in a user-local location, preserving existing installations. Failed downloads, checksums or unsupported platforms fail clearly without reporting readiness. | Native setup tests with controlled downloads plus a real approved installation smoke test. |
| WIN-004 | Required CodeGraph, Graphify and OpenSpec commands execute natively with safe argument boundaries. Missing tools still block required gates. | Actual index ensure/query and OpenSpec integration runs; spaces/metacharacter arguments; unavailable-tool cases. |
| WIN-005 | Timed-out checks and tool invocations stop their child processes and record failure. | Native child/grandchild timeout test and POSIX regression tests. |
| WIN-006 | Install/init, doctor, lifecycle evidence, resume and upgrade work on Windows; Linux/macOS retain support. | Build/type checks, Node tests, package/upgrade tests, harness validate/self-test/task verification, and expanded OS CI. |
| WIN-007 | User-facing setup and generated instructions give native Windows commands and accurately describe prerequisites and limitations. | README, operating/version guides, diagnostics, generated assets and launcher inventory review. |

## Ordered implementation plan

1. Repair platform-specific storage imports, locking and atomic writes in `harnesslib/storage.py`, with focused native regression tests. Retain POSIX semantics and existing recovery barriers. Retry reconciliation, indexes and investigation recording; inspect any further blockers before expanding scope.
2. Add native repository launchers and PowerShell setup. Implement Windows runtime discovery and provisioning in `harnesslib/runtime.py`; handle Store aliases, native archive layout, executable suffixes and safe npm command resolution. Preserve existing shell launchers for POSIX.
3. Remove the npm Windows rejection after engine tests pass. Update `src/engine.ts`, `src/doctor.ts` and relevant command adapters. Audit Python process boundaries, tool paths and descendant cleanup; preserve argument arrays and authorization controls.
4. Exercise required navigation and OpenSpec dependencies on native Windows. If a dependency cannot satisfy the current required contract, report the precise blocker and request a revised decision; do not silently substitute or disable checks.
5. Update adoption/asset manifests, package tests, Windows wizard coverage, CI and documentation. Run the complete relevant suite and review the combined diff separately. Record evidence and limitations; request final developer approval after verification.

Likely scope: native launcher/setup files; `harnesslib/` platform, process, tool-path and adoption code; `src/` engine/diagnostic/integration boundaries; associated Python/Node tests and scripts; build asset inventory; `.github/workflows/verify.yml`; README and Windows-relevant documentation. Changes to workflow approval policy, application requirements or third-party tool selection require renewed review.

## Risks and pending decisions

Approval of this revision selects Windows x64 and the existing built-in shells as the initial baseline, retains Python/Node, and authorizes implementation of explicit native provisioning (not an unattended installation during this planning turn). Key risks are filesystem durability differences, child-process cleanup, command-shim quoting, third-party native tool availability and packaging drift. Compatibility of required external tools remains unverified. Installation/network approvals remain subject to host permissions. No global policy changes or automatic fallback to WSL are allowed.

## Approval

Approve this specification and implementation plan and start implementation, or revise it. Record the actual developer response before any implementation edit. The repository planner explicitly requires this approval; the initial feature request is not approval of a later plan.

## Authorized follow-up
Revision 2 implementation and verification corrections: see docs/WINDOWS_NATIVE_FOLLOWUP.md. Developer instruction: разработай план и делай. Original requirements remain applicable; capability-aware local symlink skips require strict Windows CI coverage.


## Approved performance follow-up
Developer approved docs/HARNESS_PERFORMANCE_PLAN.md in chat: "Утверждаю, реализуй оптимизацию". PERF-001: report-scoped snapshots. PERF-002: coalesced derived reports. PERF-003: safe visible progress. PERF-004: explicit fast/full developer loop, preserving complete final verification.
