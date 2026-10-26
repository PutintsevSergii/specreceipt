---
name: debugger
description: Reproduce and repair a defect or failed verification.
---

# debugger

## Inputs and preconditions
Read [TECH_SPEC](../../../docs/TECH_SPEC.md), [ARCHITECTURE](../../../docs/ARCHITECTURE.md), [decisions](../../../docs/DECISION_QUEUE.md), and the active specs/<feature-id>/, using repository-root paths when resolving links. Requirements outrank code and graph. Application edits require approved inputs and explicit scope; generic harness setup can proceed while application documents remain DRAFT.

Use the relevant section of the [operating guide](../../../docs/HARNESS.md); applicable rules remain mandatory.

## Procedure and output contract
Preserve failing evidence and minimize an isolated reproduction. List falsifiable hypotheses and inspect source plus graph coverage. Run discriminating checks, record the observed root cause, add regression coverage and implement the smallest in-scope correction. Rerun affected required checks. Output reproduction, root cause, fix and evidence; escalate requirement or architecture changes.

Before retrying, identify what changed in the hypothesis, input or environment and what observation will distinguish the next attempt. If attempts stop producing new evidence, stop the repeated action, preserve the reproduction and narrow or escalate the unresolved cause. Set any retry budget from task risk and approved constraints; do not introduce automatic model escalation, dependency installs or destructive rollback. Keep unrelated user edits intact.

## Verification and maintenance
Use actual command exit codes and content-bound evidence. Inspect .harness/state.json, .harness/events.jsonl and referenced artifacts. Evaluate ./harness checkpoint --if-needed after edit batches, check outcomes, decisions, blockers and handoffs. Record observable rationale using ./harness note; never log private reasoning or secrets. Before source discovery check graph freshness and update if needed, then inspect source; partial/unavailable graph requires source-search fallback. Read-only work with no meaningful changes needs no journal rewrite.

## Stop and permissions
Stop dependent work on missing approvals, conflicting requirements, uncertain effects or scope/architecture/dependency/access-policy changes; record a concrete blocker and continue independent authorized work. These instructions grant no tool permissions. Use existing runtime sandbox and approvals; no automatic installs, source transmission, deployment, destructive operations or production credentials. Roles may run sequentially. Delegate only when authorized and useful; serialize shared writes. Scripts and agent-writable records are bypassable, not tamper-proof enforcement.
