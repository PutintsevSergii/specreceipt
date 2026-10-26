---
name: status-reporter
description: Report actual task progress from persisted state and evidence.
---

# status-reporter

## Inputs and preconditions
Read [TECH_SPEC](../../../docs/TECH_SPEC.md), [ARCHITECTURE](../../../docs/ARCHITECTURE.md), [decisions](../../../docs/DECISION_QUEUE.md), and the active specs/<feature-id>/, using repository-root paths when resolving links. Requirements outrank code and graph. Application edits require approved inputs and explicit scope; generic harness setup can proceed while application documents remain DRAFT.

Use the relevant section of the [operating guide](../../../docs/HARNESS.md); applicable rules remain mandatory.

## Procedure and output contract
Run ./harness status and inspect referenced artifacts, observed changes, pending transactions and graph freshness. Use effective status; IMPLEMENTED is untested and stale completion is rework. Report completed scope, current failures/blockers, application readiness and concrete next action. Do not infer completion from chat or mistake NOT_RUN for PASS. Reconcile before claiming current completion when files differ.

## Executable hardening contracts

Report historical task completion separately from evidence_current and regression_required. A DONE task can need current regression; finished dispatcher output requires all historical completions and current evidence. Distinguish deterministic fixture-adapter verification from actual live-provider operation.

## Verification and maintenance
Use actual command exit codes and content-bound evidence. Inspect .harness/state.json, .harness/events.jsonl and referenced artifacts. Evaluate ./harness checkpoint --if-needed after edit batches, check outcomes, decisions, blockers and handoffs. Record observable rationale using ./harness note; never log private reasoning or secrets. Before source discovery check graph freshness and update if needed, then inspect source; partial/unavailable graph requires source-search fallback. Read-only work with no meaningful changes needs no journal rewrite.

## Stop and permissions
Stop dependent work on missing approvals, conflicting requirements, uncertain effects or scope/architecture/dependency/access-policy changes; record a concrete blocker and continue independent authorized work. These instructions grant no tool permissions. Use existing runtime sandbox and approvals; no automatic installs, source transmission, deployment, destructive operations or production credentials. Roles may run sequentially. Delegate only when authorized and useful; serialize shared writes. Scripts and agent-writable records are bypassable, not tamper-proof enforcement.

For adaptive tasks, consult the Adaptive task workflow section of docs/HARNESS.md. FAST combines workflow and brief-plan confirmation when project policy permits; keep final approval separate. Use `status TASK-ID --format terminal` for concise evidence-backed reporting.
