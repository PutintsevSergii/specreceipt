# Feature plan

Status: DRAFT
Revision: 0
Approval: TBD
Tech-Spec-Revision: 0
Architecture-Revision: 0

## Conformance and bounded outcome
TBD: approved requirement references, intended observable result, scope and non-goals.

## Planning depth and unknowns
TBD: explain the affected boundaries and risk. Keep a small change inline; add separate artifacts only when they improve a concrete decision. Name unresolved facts and the bounded discovery needed. Documentation depth never waives required checks or approvals.

## Acceptance coverage
Include every in-scope criterion from spec.md, including failure cases, not just the easiest implementation paths. Keep IDs stable; reference rather than duplicate criterion text.

| AC ID | Task ID | Surface or boundary | Planned test or inspection | Required check / evidence method |
| --- | --- | --- | --- | --- |
| TBD | TBD | TBD | TBD | TBD |

## Slices and dependencies
TBD: small usable slices, dependencies with concrete reasons, affected files and integration order. For multi-feature scope, outline requirement-backed increments and detail only the next slice; retain existing task records as the progress source. Inspect overlapping writes as well as logical dependencies. Keep compile-coupled contract/caller changes together where needed; no delegation is implied.

## Applicable design details
TBD: record only affected API/event/CLI contracts, data consistency/migration recovery, authorization boundaries, UI flows/states, or external failure behavior. Omit inapplicable detail with a concise reason. A new document or ADR is justified by a decision, not a fixed document quota.

## Verification and recovery
TBD: approved commands, positive/negative/boundary cases, significant environment, safe entry-point smoke check where relevant, and recovery. For a regression, establish whether the initial failure actually reproduces the defect; broken setup or unavailable dependencies are not successful reproduction.

## Review and handoff
TBD: review the entire acceptance set and combined change. Record evidence, unresolved findings, exact next action and approval points. Use persisted state; no session-reset command is required.


## Developer approval of this revision
Keep this proposal DRAFT until the developer reviews the concrete spec and implementation plan. Present the documents/revisions and ask whether to approve and start or revise. On requested changes, update the proposal and ask again; clarification alone is not approval. Record the actual approval reference and approved revisions in Approval metadata before starting. Reuse valid approval for unchanged work; material changes require renewed approval. Local metadata is not authenticated human consent.
