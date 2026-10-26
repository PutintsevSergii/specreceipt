---
name: bootstrap-project
description: Configure a newly adopted harness from approved project requirements.
---

# bootstrap-project

## Inputs and preconditions
Read [TECH_SPEC](../../../docs/TECH_SPEC.md), [ARCHITECTURE](../../../docs/ARCHITECTURE.md), [decisions](../../../docs/DECISION_QUEUE.md), and the active specs/<feature-id>/, using repository-root paths when resolving links. Requirements outrank code and graph. Application edits require approved inputs and explicit scope; generic harness setup can proceed while application documents remain DRAFT.

Use the relevant section of the [operating guide](../../../docs/HARNESS.md); applicable rules remain mandatory.

## Procedure and output contract
Inspect runtime availability with ./harness doctor. Map each approved stack and acceptance requirement to an executable check in .harness/checks.json; record versions in .harness/environment.json. Keep stack_revision null until the application inputs and check commands are approved. Run init idempotently, validate and self-test. Output a readiness report separating generic infrastructure, application configuration and feature readiness.

Establish the current host capabilities from available tools or observed results: file access, command execution, user interaction and any required browser/service access. Do not assume automatic skill discovery, an agent API, named model or slash command. The portable entry is AGENTS.md plus ./harness skills NAME. Optional orchestration can become sequential work; missing required execution or observation remains BLOCKED/NOT_RUN. Preserve existing host configuration and avoid duplicate instruction copies.

If canonical inputs are incomplete, route to [project-onboarding](../project-onboarding/SKILL.md) to gather answers and authorized evidence. Do not require the developer to author all documents manually. Configure application_checks in .harness/onboarding.json; run ./harness readiness after configuration. Configuration work does not authorize application scaffolding.

## Verification and maintenance
Use actual command exit codes and content-bound evidence. Inspect .harness/state.json, .harness/events.jsonl and referenced artifacts. Evaluate ./harness checkpoint --if-needed after edit batches, check outcomes, decisions, blockers and handoffs. Record observable rationale using ./harness note; never log private reasoning or secrets. Before source discovery check graph freshness and update if needed, then inspect source; partial/unavailable graph requires source-search fallback. Read-only work with no meaningful changes needs no journal rewrite.

## Stop and permissions
Stop dependent work on missing approvals, conflicting requirements, uncertain effects or scope/architecture/dependency/access-policy changes; record a concrete blocker and continue independent authorized work. These instructions grant no tool permissions. Use existing runtime sandbox and approvals; no automatic installs, source transmission, deployment, destructive operations or production credentials. Roles may run sequentially. Delegate only when authorized and useful; serialize shared writes. Scripts and agent-writable records are bypassable, not tamper-proof enforcement.
