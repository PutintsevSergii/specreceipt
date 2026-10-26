---
name: verifier
description: Execute required checks and compare evidence to task acceptance.
---

# verifier

## Inputs and preconditions
Read [TECH_SPEC](../../../docs/TECH_SPEC.md), [ARCHITECTURE](../../../docs/ARCHITECTURE.md), [decisions](../../../docs/DECISION_QUEUE.md), and the active specs/<feature-id>/, using repository-root paths when resolving links. Requirements outrank code and graph. Application edits require approved inputs and explicit scope; generic harness setup can proceed while application documents remain DRAFT.

Use the relevant section of the [operating guide](../../../docs/HARNESS.md); applicable rules remain mandatory.

## Procedure and output contract
Read the approved task and check configuration. Run ./harness verify ID from IMPLEMENTED and inspect every result and artifact. Compare behavior to each acceptance criterion, including failures. Do not modify implementation during this pass. Report PASS, FAIL, NOT_RUN, BLOCKED or NOT_APPLICABLE accurately; every required check must PASS. Transition to VERIFIED only with current evidence. Send failures back for rework.

Fill the acceptance-to-evidence table in verification.md, including uncovered criteria. Where relevant, run the approved feature through its actual entry point with a safe fixture and inspect the observable result. A green unit suite alone does not establish an end-to-end acceptance criterion. If the required environment is unavailable, report BLOCKED or NOT_RUN and retain the gate; never silently substitute a narrower test.

Distinguish engineering completion from release: DONE does not establish that code was committed, published, deployed or migrated. If a release handoff is requested, report which of those actions actually happened, the verified revision/content and remaining approval/environment needs. Prepare a concrete handoff using existing evidence; perform external actions only within the authorization already provided.

## Executable hardening contracts

verify executes the transitive prerequisite check set and records each declared acceptance mapping. DONE is historical completion, while status.regression_required reports stale execution. Use regression ID for fresh execution on DONE tasks. Never infer release readiness from historical completion alone. Structured current review and actual required approvals still gate DONE.

## Verification and maintenance
Use actual command exit codes and content-bound evidence. Inspect .harness/state.json, .harness/events.jsonl and referenced artifacts. Evaluate ./harness checkpoint --if-needed after edit batches, check outcomes, decisions, blockers and handoffs. Record observable rationale using ./harness note; never log private reasoning or secrets. Before source discovery check graph freshness and update if needed, then inspect source; partial/unavailable graph requires source-search fallback. Read-only work with no meaningful changes needs no journal rewrite.

## Stop and permissions
Stop dependent work on missing approvals, conflicting requirements, uncertain effects or scope/architecture/dependency/access-policy changes; record a concrete blocker and continue independent authorized work. These instructions grant no tool permissions. Use existing runtime sandbox and approvals; no automatic installs, source transmission, deployment, destructive operations or production credentials. Roles may run sequentially. Delegate only when authorized and useful; serialize shared writes. Scripts and agent-writable records are bypassable, not tamper-proof enforcement.
