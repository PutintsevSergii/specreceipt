---
name: spec-author
description: Draft or revise product and feature specifications when requirements need clarification.
---

# spec-author

## Inputs and preconditions
Read [TECH_SPEC](../../../docs/TECH_SPEC.md), [ARCHITECTURE](../../../docs/ARCHITECTURE.md), [decisions](../../../docs/DECISION_QUEUE.md), and the active specs/<feature-id>/, using repository-root paths when resolving links. Requirements outrank code and graph. Application edits require approved inputs and explicit scope; generic harness setup can proceed while application documents remain DRAFT.

Use the relevant section of the [operating guide](../../../docs/HARNESS.md); applicable rules remain mandatory.

## Procedure and output contract
Read developer requirements and identify stable requirement IDs, observable acceptance criteria, failure cases and unresolved assumptions. Edit canonical documents or templates/feature copies as DRAFT, pin canonical revisions, and record conflicts in docs/DECISION_QUEUE.md. Output the draft and only material questions; do not invent approvals or stack choices. Validate structure before handoff.

Give acceptance criteria stable AC identifiers and observable outcomes. Before approval, check ambiguous actors, permissions, failure behavior and scope boundaries; reuse supplied answers and ask only unresolved material questions. For UI work, describe user-visible loading, empty, error, denied and success states where applicable. Keep domain terms in the canonical specification rather than inventing another source of truth.

Resolve uncertainty in proportion to its effect. Investigate factual questions from available evidence; bring unresolved product, scope and acceptance choices to the developer with the affected criterion and consequence. For a deferred question, record who can resolve it, what evidence or decision is needed, the dependent work and the point before which it must be revisited. Deferral does not authorize implementing a guessed answer. Preserve the existing document language and approved terminology.

For a new project knowledge base or several missing canonical inputs, work under [project-onboarding](../project-onboarding/SKILL.md). Return source references, completed sections and remaining questions to that coordinator; it owns the interview flow and readiness handoff.

## Verification and maintenance
Use actual command exit codes and content-bound evidence. Inspect .harness/state.json, .harness/events.jsonl and referenced artifacts. Evaluate ./harness checkpoint --if-needed after edit batches, check outcomes, decisions, blockers and handoffs. Record observable rationale using ./harness note; never log private reasoning or secrets. Before source discovery check graph freshness and update if needed, then inspect source; partial/unavailable graph requires source-search fallback. Read-only work with no meaningful changes needs no journal rewrite.

## Stop and permissions
Stop dependent work on missing approvals, conflicting requirements, uncertain effects or scope/architecture/dependency/access-policy changes; record a concrete blocker and continue independent authorized work. These instructions grant no tool permissions. Use existing runtime sandbox and approvals; no automatic installs, source transmission, deployment, destructive operations or production credentials. Roles may run sequentially. Delegate only when authorized and useful; serialize shared writes. Scripts and agent-writable records are bypassable, not tamper-proof enforcement.

## Developer approval loop before implementation
For each new implementation request or materially changed scope, prepare the concrete implementation spec and plan before asking for approval. Investigate and draft documentation first; keep spec.md and plan.md DRAFT. When OpenSpec is configured, review its linked source together with the harness execution mapping and wrappers; structural validation does not approve implementation.

Present the outcome, included/excluded scope, affected boundaries, ordered implementation steps, acceptance criteria/checks, significant risks and unresolved decisions. Link the actual documents and identify their revisions. Then explicitly ask, in the developer's language: "Approve this specification and implementation plan and start implementation, or should we revise it?" Wait for the answer before task start or application edits. A request to build a feature, a clarification answer, silence, installation success or a readiness report is not approval of a later proposed plan.

If the developer requests changes, revise the documents, increment material revisions, update task/check mappings and keep the proposal DRAFT. Show the updated proposal and the relevant changes; ask for approval again. Repeat until the current version is explicitly approved. Record the real answer/reference and the approved document revisions; never invent a quote or approve on the developer's behalf. Then run readiness TASK-ID and start only the approved scope. For an active attempt, follow task replan with a reviewed reference when required.

An existing explicit approval of the same unchanged plan remains valid. It can cover several listed tasks: do not ask again for each implementation step, routine fix or resumed session within that approved scope. New requirements, changed acceptance, scope or material design decisions require a revised proposal and renewed approval before dependent implementation. This procedural dialogue complements executable gates; local agent-writable records cannot authenticate a human.
