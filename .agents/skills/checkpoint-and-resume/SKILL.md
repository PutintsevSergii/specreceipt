---
name: checkpoint-and-resume
description: Reconcile interrupted work and persist a safe handoff.
---

# checkpoint-and-resume

## Inputs and preconditions
Read [TECH_SPEC](../../../docs/TECH_SPEC.md), [ARCHITECTURE](../../../docs/ARCHITECTURE.md), [decisions](../../../docs/DECISION_QUEUE.md), and the active specs/<feature-id>/, using repository-root paths when resolving links. Requirements outrank code and graph. Application edits require approved inputs and explicit scope; generic harness setup can proceed while application documents remain DRAFT.

Use the relevant section of the [operating guide](../../../docs/HARNESS.md); applicable rules remain mandatory.

## Procedure and output contract
Run ./harness resume then status; inspect .harness/state.json, events.jsonl and referenced evidence. For uncertain operations inspect visible processes and filesystem effects without replaying commands. Acknowledge recovery only after effects are understood. Evaluate checkpoint --if-needed after meaningful changes and confirm a repeated unchanged checkpoint is a no-op. Output last confirmed checkpoint, uncertainties and exact next action.

Make a handoff usable in any host: include the project path, feature/task IDs when present, current canonical revisions, evidence references, unresolved decisions or uncertain effects, and one concrete next action. A new agent should load the files itself. No host-specific session-reset command is required, and silence from an asynchronous worker is not a completed report.

## Executable hardening contracts

Inspect next and any runner-state budget when resuming bounded dispatch. Repeated run invocations preserve step/time/failure budgets; --new-run is an explicit new budget. Interrupted adapter intents remain uncertain and must not be replayed until inspected and acknowledged. Do not treat a subprocess exit as acceptance evidence.

## Verification and maintenance
Use actual command exit codes and content-bound evidence. Inspect .harness/state.json, .harness/events.jsonl and referenced artifacts. Evaluate ./harness checkpoint --if-needed after edit batches, check outcomes, decisions, blockers and handoffs. Record observable rationale using ./harness note; never log private reasoning or secrets. Before source discovery check graph freshness and update if needed, then inspect source; partial/unavailable graph requires source-search fallback. Read-only work with no meaningful changes needs no journal rewrite.

## Stop and permissions
Stop dependent work on missing approvals, conflicting requirements, uncertain effects or scope/architecture/dependency/access-policy changes; record a concrete blocker and continue independent authorized work. These instructions grant no tool permissions. Use existing runtime sandbox and approvals; no automatic installs, source transmission, deployment, destructive operations or production credentials. Roles may run sequentially. Delegate only when authorized and useful; serialize shared writes. Scripts and agent-writable records are bypassable, not tamper-proof enforcement.
