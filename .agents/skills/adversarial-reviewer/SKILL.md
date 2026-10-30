---
name: adversarial-reviewer
description: Review the actual implementation diff separately from coding.
---

# adversarial-reviewer

## Effective task contract
For an eligible schema-version-2 compact task, use the canonical task record, concise approved project context, required check/case mapping and referenced evidence. Follow [the compact journey](../../../docs/HARNESS.md#compact-fast-journey). The formal document preparation, full-document prerequisites and repeated resume/status/next procedures below apply to formal records; they do not require compact tasks to create duplicate TECH_SPEC, ARCHITECTURE, spec, plan or verification prose. Stricter project instructions, existing linked requirements and policy floors remain authoritative.

The current IDE host prepares and displays one plan/context/check bundle, records the actual combined decision, then uses `run` and guarded `run --submit REQUEST_ID` role completion. Implementation stays in scope; verification uses approved application checks and current evidence; review is a separate pass identified honestly and writes only the requested review record. Show current results and limits, then obtain separate bound final acceptance. Never fabricate consent or make the developer operate lifecycle commands. Unchanged resume and in-scope repairs need no repeated initial approval. Load only the guidance needed for this role.

## Inputs and preconditions
Read [TECH_SPEC](../../../docs/TECH_SPEC.md), [ARCHITECTURE](../../../docs/ARCHITECTURE.md), [decisions](../../../docs/DECISION_QUEUE.md), and the active specs/<feature-id>/, using repository-root paths when resolving links. Requirements outrank code and graph. Application edits require approved inputs and explicit scope; generic harness setup can proceed while application documents remain DRAFT.

Use the relevant section of the [operating guide](../../../docs/HARNESS.md); applicable rules remain mandatory.

## Procedure and output contract
Inspect Git diff when available; otherwise compare a saved baseline and disclose that limitation. Trace changed behavior against requirements, caller contracts, error paths and tests. Attempt concrete counterexamples. Record Reviewer:, Findings:, Evidence: in the feature verification.md, with severity, file/line, behavior, violated requirement/risk and reproduction for each finding. Do not implement fixes during review. Recheck fixes and record review via task approve only when findings are resolved. A model review is not independent proof.

Review the complete approved acceptance set, not only criteria claimed by changed tasks. First assess requirement and contract coverage across the whole feature; then inspect implementation quality, security and failure handling. For UI criteria inspect the rendered user flow and relevant states; backend-only tests do not establish UI behavior. Re-read canonical inputs directly rather than relying on the implementer summary. Report same-session review honestly; use a separate context only when authorized, and never call an additional model independent proof.

## Executable hardening contracts

Write one structured harness-review JSON block per task under specs/<feature>/reviews/<TASK-ID>.md, using templates/feature/verification.md. Bind the exact latest execution evidence. PASS requires substantive fields and every finding RESOLVED; headings alone cannot approve completion. The review pass must not change implementation. Record severity, location, behavior, requirement, reproduction and resolution for each finding.

## Verification and maintenance
Use actual command exit codes and content-bound evidence. Inspect .harness/state.json, .harness/events.jsonl and referenced artifacts. Evaluate ./harness checkpoint --if-needed after edit batches, check outcomes, decisions, blockers and handoffs. Record observable rationale using ./harness note; never log private reasoning or secrets. Follow .harness/navigation.json: source mode uses targeted source search with no graph preparation; required mode checks only selected providers; missing policy retains legacy providers. Navigation never proves behavior. Read-only work with no meaningful changes needs no journal rewrite.

## Stop and permissions
Stop dependent work on missing approvals, conflicting requirements, uncertain effects or scope/architecture/dependency/access-policy changes; record a concrete blocker and continue independent authorized work. These instructions grant no tool permissions. Use existing runtime sandbox and approvals; no automatic installs, source transmission, deployment, destructive operations or production credentials. Roles may run sequentially. Delegate only when authorized and useful; serialize shared writes. Scripts and agent-writable records are bypassable, not tamper-proof enforcement.
