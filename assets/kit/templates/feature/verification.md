# Verification and separate review

Reviewer: TBD
Findings: TBD
Evidence: TBD

## Acceptance readback
Compare the complete approved spec against observed behavior, not only the task's claimed coverage.

| AC ID | Test or inspection performed | Evidence reference | Result | Remaining gap |
| --- | --- | --- | --- | --- |
| TBD | TBD | TBD | NOT_RUN | No execution yet |

Use PASS, FAIL, NOT_RUN, BLOCKED or NOT_APPLICABLE precisely. This table aids review; it does not waive required CLI checks or mechanically prove semantic coverage.

## Runtime and affected surfaces
Record the actual entry point, safe fixture, significant environment and observable outcome where applicable. A backend check does not by itself verify UI states. Explain inapplicable smoke/visual checks; unavailable required checks remain blocked.

## Findings and resolution
Record severity, file/line, behavior, violated requirement/risk, reproduction, disposition and limitations. Review requirement coverage first, then quality and failure paths. A sequential review pass is not an independent attestation. No check has run yet.

## Delivery handoff, when requested
Name the verified content/revision, actual commit/publication/deployment/migration actions, outstanding environment or approval needs, and next action. DONE alone does not mean released. Do not perform an external action merely to fill this section.

## Machine-readable review

Use a separate `specs/<feature>/reviews/<TASK-ID>.md` for each task, preserving other tasks' reviews. After a separate review, replace the placeholders below with the actual task ID, latest evidence reference, reviewer and substantive result. An unexecuted template is never approval. Every finding must include `id`, `severity` (P0–P3), `status` (OPEN or RESOLVED), `location`, `behavior`, `requirement`, `reproduction`, and `resolution`. All findings must be resolved before PASS.

```harness-review
{
  "task_id": "TASK-001",
  "reviewer": "TBD",
  "evidence": ".harness/evidence/REPLACE-WITH-ACTUAL-ID.json",
  "verdict": "CHANGES_REQUESTED",
  "summary": "TBD",
  "findings": []
}
```
