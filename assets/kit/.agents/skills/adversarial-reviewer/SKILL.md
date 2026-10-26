---
name: adversarial-reviewer
description: Review the actual implementation diff separately from coding.
---

# adversarial-reviewer

## Inputs and preconditions
Read [TECH_SPEC](../../../docs/TECH_SPEC.md), [ARCHITECTURE](../../../docs/ARCHITECTURE.md), [decisions](../../../docs/DECISION_QUEUE.md), and the active specs/<feature-id>/, using repository-root paths when resolving links. Requirements outrank code and graph. Application edits require approved inputs and explicit scope; generic harness setup can proceed while application documents remain DRAFT.

Use the relevant section of the [operating guide](../../../docs/HARNESS.md); applicable rules remain mandatory.

## Procedure and output contract
Inspect Git diff when available; otherwise compare a saved baseline and disclose that limitation. Trace changed behavior against requirements, caller contracts, error paths and tests. Attempt concrete counterexamples. Record Reviewer:, Findings:, Evidence: in the feature verification.md, with severity, file/line, behavior, violated requirement/risk and reproduction for each finding. Do not implement fixes during review. Recheck fixes and record review via task approve only when findings are resolved. A model review is not independent proof.

Review the complete approved acceptance set, not only criteria claimed by changed tasks. First assess requirement and contract coverage across the whole feature; then inspect implementation quality, security and failure handling. For UI criteria inspect the rendered user flow and relevant states; backend-only tests do not establish UI behavior. Re-read canonical inputs directly rather than relying on the implementer summary. Report same-session review honestly; use a separate context only when authorized, and never call an additional model independent proof.

## Executable hardening contracts

Write one structured harness-review JSON block per task under specs/<feature>/reviews/<TASK-ID>.md, using templates/feature/verification.md. Bind the exact latest execution evidence. PASS requires substantive fields and every finding RESOLVED; headings alone cannot approve completion. The review pass must not change implementation. Record severity, location, behavior, requirement, reproduction and resolution for each finding.

## Verification and maintenance
Use actual command exit codes and content-bound evidence. Inspect .harness/state.json, .harness/events.jsonl and referenced artifacts. Evaluate ./harness checkpoint --if-needed after edit batches, check outcomes, decisions, blockers and handoffs. Record observable rationale using ./harness note; never log private reasoning or secrets. Before source discovery check graph freshness and update if needed, then inspect source; partial/unavailable graph requires source-search fallback. Read-only work with no meaningful changes needs no journal rewrite.

## Stop and permissions
Stop dependent work on missing approvals, conflicting requirements, uncertain effects or scope/architecture/dependency/access-policy changes; record a concrete blocker and continue independent authorized work. These instructions grant no tool permissions. Use existing runtime sandbox and approvals; no automatic installs, source transmission, deployment, destructive operations or production credentials. Roles may run sequentially. Delegate only when authorized and useful; serialize shared writes. Scripts and agent-writable records are bypassable, not tamper-proof enforcement.
