---
name: discovery
description: Investigate source and impact before planning or changing code.
---

# discovery

## Effective task contract
For an eligible schema-version-2 compact task, use the canonical task record, concise approved project context, required check/case mapping and referenced evidence. Follow [the compact journey](../../../docs/HARNESS.md#compact-fast-journey). The formal document preparation, full-document prerequisites and repeated resume/status/next procedures below apply to formal records; they do not require compact tasks to create duplicate TECH_SPEC, ARCHITECTURE, spec, plan or verification prose. Stricter project instructions, existing linked requirements and policy floors remain authoritative.

The current IDE host prepares and displays one plan/context/check bundle, records the actual combined decision, then uses `run` and guarded `run --submit REQUEST_ID` role completion. Implementation stays in scope; verification uses approved application checks and current evidence; review is a separate pass identified honestly and writes only the requested review record. Show current results and limits, then obtain separate bound final acceptance. Never fabricate consent or make the developer operate lifecycle commands. Unchanged resume and in-scope repairs need no repeated initial approval. Load only the guidance needed for this role.

## Inputs and preconditions
Read [TECH_SPEC](../../../docs/TECH_SPEC.md), [ARCHITECTURE](../../../docs/ARCHITECTURE.md), [decisions](../../../docs/DECISION_QUEUE.md), and the active specs/<feature-id>/, using repository-root paths when resolving links. Requirements outrank code and graph. Application edits require approved inputs and explicit scope; generic harness setup can proceed while application documents remain DRAFT.

Use the relevant section of the [operating guide](../../../docs/HARNESS.md); applicable rules remain mandatory.

## Procedure and output contract
Follow .harness/navigation.json: source mode uses targeted source search without graph setup; required mode runs ./harness indexes ensure and bounded queries for the selected providers; absent policy retains both legacy providers; inspect referenced source, contracts and tests against specifications. Use targeted rg searches for unsupported languages, dynamic behavior or unavailable graph. A graph is navigation, never proof or sole test selection.

For material story or implementation claims, inspect the active host's actual MCP tool inventory. Use relevant already-connected read-only tools only within the user's authorized investigation; a config entry is not availability or permission. Compare each useful MCP result with exact code locations and approved requirements. Record selected and rejected tool reasons, resource/revision, bounded sanitized summaries, agreement, contradictions and gaps in a task-scoped investigation report; submit it with `./harness investigation record TASK-ID --file FILE`, then run `./harness investigation check TASK-ID`. If no relevant tool is available, record NO_MCP or CODE_ONLY honestly. Required source denial, failed query, contradiction or stale revision blocks the dependent claim. Do not start a server, invoke write tools or treat agent-reported use as authenticated host proof. Output concrete file locations, confirmed facts, hypotheses, coverage gaps and proposed bounded scope.

## Verification and maintenance
Use actual command exit codes and content-bound evidence. Inspect .harness/state.json, .harness/events.jsonl and referenced artifacts. Evaluate ./harness checkpoint --if-needed after edit batches, check outcomes, decisions, blockers and handoffs. Record observable rationale using ./harness note; never log private reasoning or secrets. Follow .harness/navigation.json: source mode uses targeted source search with no graph preparation; required mode checks only selected providers; missing policy retains legacy providers. Navigation never proves behavior. Read-only work with no meaningful changes needs no journal rewrite.

## Stop and permissions
Stop dependent work on missing approvals, conflicting requirements, uncertain effects or scope/architecture/dependency/access-policy changes; record a concrete blocker and continue independent authorized work. These instructions grant no tool permissions. Use existing runtime sandbox and approvals; no automatic installs, source transmission, deployment, destructive operations or production credentials. Roles may run sequentially. Delegate only when authorized and useful; serialize shared writes. Scripts and agent-writable records are bypassable, not tamper-proof enforcement.
