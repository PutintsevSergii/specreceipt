# Scoped test execution verification

Status: NOT_RUN

Planning only. spec.md and plan.md revision 1 are DRAFT. Runtime, tests and CI have not been changed; no implementation or test PASS is claimed.

Historical baseline: Python verification 55bba3ba-ddf3-4390-9312-4ac203bf8591, 246 cases / 12 skips / 1189.057 seconds. Do not reuse it as evidence for the proposed selector.

Discovery: resume/status/next read; WIN-001 remains historically DONE with regression_required. Both external indexes ensured fresh, CodeGraph query self_test and Graphify query within 800 tokens PASS. Graphify truncates and contains generated copies, so source files were inspected directly. Initial launcher lookup failed because native Python was not on PATH; the observed bundled native executable was explicitly selected, without installs or runtime changes.

Before declaring completion, record acceptance coverage TST-001 through TST-006, actual selected commands/counts/timings, zero-selection/failure/rename/base tests, CI review, full discovery audit, one complete final regression, structural validation and separate diff review. Hosted CI behavior remains unverified until actually executed by GitHub.

Research sources and their application are recorded in plan.md. No repository code was sent to external services. Next action: developer approval of the concrete test-only plan and CI execution-frequency decision.

Planning structural validation: `harness validate` PASS with two task records, including DRAFT TST-001. This validates record structure, not implementation or plan approval. Existing required check names are retained for the one final migration verification; targeted development commands will be documented separately.
