---
name: discovery
description: Investigate source and impact before planning or changing code.
---

# discovery

## Inputs and preconditions
Read [TECH_SPEC](../../../docs/TECH_SPEC.md), [ARCHITECTURE](../../../docs/ARCHITECTURE.md), [decisions](../../../docs/DECISION_QUEUE.md), and the active specs/<feature-id>/, using repository-root paths when resolving links. Requirements outrank code and graph. Application edits require approved inputs and explicit scope; generic harness setup can proceed while application documents remain DRAFT.

Use the relevant section of the [operating guide](../../../docs/HARNESS.md); applicable rules remain mandatory.

## Procedure and output contract
Run ./harness indexes ensure, then bounded CodeGraph and Graphify queries; inspect referenced source, contracts and tests against specifications. Use targeted rg searches for unsupported languages, dynamic behavior or unavailable graph. A graph is navigation, never proof or sole test selection.

For material story or implementation claims, inspect the active host's actual MCP tool inventory. Use relevant already-connected read-only tools only within the user's authorized investigation; a config entry is not availability or permission. Compare each useful MCP result with exact code locations and approved requirements. Record selected and rejected tool reasons, resource/revision, bounded sanitized summaries, agreement, contradictions and gaps in a task-scoped investigation report; submit it with `./harness investigation record TASK-ID --file FILE`, then run `./harness investigation check TASK-ID`. If no relevant tool is available, record NO_MCP or CODE_ONLY honestly. Required source denial, failed query, contradiction or stale revision blocks the dependent claim. Do not start a server, invoke write tools or treat agent-reported use as authenticated host proof. Output concrete file locations, confirmed facts, hypotheses, coverage gaps and proposed bounded scope.

## Verification and maintenance
Use actual command exit codes and content-bound evidence. Inspect .harness/state.json, .harness/events.jsonl and referenced artifacts. Evaluate ./harness checkpoint --if-needed after edit batches, check outcomes, decisions, blockers and handoffs. Record observable rationale using ./harness note; never log private reasoning or secrets. Before source discovery check graph freshness and update if needed, then inspect source; partial/unavailable graph requires source-search fallback. Read-only work with no meaningful changes needs no journal rewrite.

## Stop and permissions
Stop dependent work on missing approvals, conflicting requirements, uncertain effects or scope/architecture/dependency/access-policy changes; record a concrete blocker and continue independent authorized work. These instructions grant no tool permissions. Use existing runtime sandbox and approvals; no automatic installs, source transmission, deployment, destructive operations or production credentials. Roles may run sequentially. Delegate only when authorized and useful; serialize shared writes. Scripts and agent-writable records are bypassable, not tamper-proof enforcement.
