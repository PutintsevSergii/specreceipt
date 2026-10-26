---
name: test-designer
description: Design tests from requirements and known failure modes.
---

# test-designer

## Inputs and preconditions
Read [TECH_SPEC](../../../docs/TECH_SPEC.md), [ARCHITECTURE](../../../docs/ARCHITECTURE.md), [decisions](../../../docs/DECISION_QUEUE.md), and the active specs/<feature-id>/, using repository-root paths when resolving links. Requirements outrank code and graph. Application edits require approved inputs and explicit scope; generic harness setup can proceed while application documents remain DRAFT.

Use the relevant section of the [operating guide](../../../docs/HARNESS.md); applicable rules remain mandatory.

## Procedure and output contract
Map each requirement to positive, negative, boundary and dependency-failure scenarios. State expected observable behavior before inspecting implementation details. Choose isolated fixtures and meaningful assertions; include authorization, schema, timeout and rollback cases where applicable. Output requirement-to-test mapping and executable tests. Demonstrate that regressions fail where practical; never weaken acceptance to pass.

Use stable AC identifiers to connect the complete feature acceptance set to tests or concrete inspections. For regression tests, distinguish an assertion failing for the intended defect from broken test setup, unavailable infrastructure and a test that already passes. Investigate an unexpected pass; it may describe existing correct behavior rather than a missing implementation. Record evidence for the classification. Do not add tests that merely restate reversible copy edits.

## Verification and maintenance
Use actual command exit codes and content-bound evidence. Inspect .harness/state.json, .harness/events.jsonl and referenced artifacts. Evaluate ./harness checkpoint --if-needed after edit batches, check outcomes, decisions, blockers and handoffs. Record observable rationale using ./harness note; never log private reasoning or secrets. Before source discovery check graph freshness and update if needed, then inspect source; partial/unavailable graph requires source-search fallback. Read-only work with no meaningful changes needs no journal rewrite.

## Stop and permissions
Stop dependent work on missing approvals, conflicting requirements, uncertain effects or scope/architecture/dependency/access-policy changes; record a concrete blocker and continue independent authorized work. These instructions grant no tool permissions. Use existing runtime sandbox and approvals; no automatic installs, source transmission, deployment, destructive operations or production credentials. Roles may run sequentially. Delegate only when authorized and useful; serialize shared writes. Scripts and agent-writable records are bypassable, not tamper-proof enforcement.
