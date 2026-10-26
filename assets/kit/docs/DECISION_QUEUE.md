# Decision queue

| ID | Status | Blocks implementation | Affected work | Decision / why it matters |
| --- | --- | --- | --- | --- |
| APP-001 | OPEN | yes | All application tasks | Developer supplies and approves product specification, architecture and stack checks. Application implementation is blocked until then. |
| GRAPH-001 | RESOLVED | no | Code navigation tools | User authorized task-first CodeGraph and Graphify indexes. ADR 002 records Graphify; ADR 003 records the CodeGraph CLI selection, index lifecycle and limits. |
| CI-001 | OPEN | no | Merge enforcement | Select repository host and protected CI/branch rules when adopting this kit. Local checks are bypassable. |


Use OPEN, DEFERRED or RESOLVED. Blocks implementation is yes or no; unresolved yes rows block selected work and its dependents. Use *, task:TASK-001, feature:feature-id or requirement:REQ-001; unknown selectors fail closed and legacy prose remains global. Keep decisions needed for the initial slice blocking until resolved. For deferred work, record the resolver and revisit point in the explanation.
