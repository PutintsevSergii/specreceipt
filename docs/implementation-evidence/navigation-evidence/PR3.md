# Distinguish command checks from criterion support

Receipts add versioned `acceptance_support` while preserving command result and
legacy criterion-mapping field semantics. JSON, terminal and Markdown expose
CHECK_ONLY/INSUFFICIENT/FAILED without claiming individual test execution,
semantic correctness or coverage-based proof. Historical receipts remain readable
and unchanged on disk. Unknown support versions and unsupported claims reject.

Red: two new report/receipt tests failed with missing support fields. Green:
three focused regressions passed, including exit-zero command and unchanged
legacy receipt bytes. Full configured verification PASS in 170.014 seconds. The first full run correctly failed the missing production-boundary selector entry; the mapping was repaired, not bypassed. Review also added navigation policy to Adaptive approval material (only when explicit policy exists), with a focused regression. No case parser or
new required approval is introduced in this change set.
