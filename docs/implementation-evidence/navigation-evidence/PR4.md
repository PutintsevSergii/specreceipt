# Observe named cases, qualify semantic reviews and detect a targeted fault

A bounded stamped JUnit adapter and real stdlib unittest reporter produce fresh
case receipts through the existing approved command runner. Opted-in task mappings
require all named cases to pass. Exit-zero commands with missing/skipped/stale/
ambiguous observations remain command PASS but fail criterion support and overall
verification. Content hashes and invocation/check/command/input bindings are
revalidated before use. Raw XML is not retained.

Optional semantic artifacts map every required case to exact current Python
assertions and explicitly identify the reviewer as human/agent, without claiming
authentication or proof. Optional exact replacement probes use disposable bounded
fixtures and distinguish the intended assertion failure from setup/syntax errors.
All three evidence domains remain separately inspectable.

Red: adapter regression initially failed because the implementation was absent.
Green: parser negatives, actual consumer CLI, missing required case, skip/xfail,
receipt tampering, semantic review, behavioral fault and syntax-fault rejection.
Full configured verification PASS in 178.864 seconds: 306 Python cases (8 skips), Node tests and complete packed self-test with real OpenSpec. Intentional limits: one JUnit subset,
Python assertion mapping and one-module stdlib fault fixture; no universal parser,
mutation framework, automatic probes or new default approval steps.
