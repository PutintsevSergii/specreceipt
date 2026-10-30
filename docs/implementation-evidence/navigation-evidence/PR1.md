# Source-first navigation with explicit provider requirements

New npm installations and Python adoptions receive project-owned navigation
policy version 1. Source mode performs no graph setup or query. Required mode
uses exactly the selected providers; policy absence preserves legacy dual-provider
requirements. Application lifecycle and CLI navigation now use the same resolver.
Diagnostics, provisioning and agent instructions follow that policy.

Navigation changes invalidate active task definitions and input freshness.
Legacy absent-policy fingerprint/definition shape is preserved. Risk profiles,
checks, source write scope and human approval semantics remain independent.

Validation: initial source/provider tests failed against baseline; seven focused
policy/adoption/lifecycle tests now pass. Existing graph tests (2), installer tests
(7), execution preflight tests (16), Node suite (74 pass/6 skip), Python self-test
(296 cases/8 skip), typecheck, build and packed smoke passed on macOS with Node
20.20.0 and Python 3.14.3. Full configured baseline passed in 164.549 seconds, including complete packaged self-test and wizard; the final Node run had 77 pass/4 skip (81 cases).
Real OpenSpec 1.14.3 is used for packed initialization. Native Windows execution
and Node 22/24 are not claimed from this host.

No automatic legacy migration, navigation plugin system or risk-profile changes.
