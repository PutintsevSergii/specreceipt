# Validate independent Git worktrees before input-scope optimization

A real two-worktree fixture now demonstrates independent state and receipts,
unchanged A fingerprints after B edits, blocking for unauthorized writes inside
A, and invalidation plus fresh command execution after branch integration.
The portable workflow documents independent initialization and safe handoff.
No state copying, scope changes, fingerprint optimization or worktree manager.

Validation: targeted integration test; complete configured baseline PASS in 167.285 seconds, including real OpenSpec packed initialization and full packaged self-test. One targeted fixture run took 1.240 seconds (includes application checks); zero cross-worktree invalidations, one intentional same-tree scope block and one mandatory integration invalidation. This is a correctness fixture, not a speedup benchmark.
