# Independent task worktrees

Use a separate branch and Git worktree for each concurrent task. Commands below
work with native Git on Windows, macOS and Linux; choose distinct unused paths
and branch names. First inspect `git status --short`, `git branch --list` and
`git worktree list`. Commit or otherwise preserve work deliberately before
selecting a starting revision. Do not copy another workspace's `.harness`.

```text
git worktree add -b task/invoices ../project-invoices main
git worktree add -b task/catalog ../project-catalog main
specreceipt init --target ../project-invoices --yes
specreceipt init --target ../project-catalog --yes
```

Run each workspace's own intake, readiness and task approvals. Init requires the
normal supported Python/Node and OpenSpec prerequisites; it does not transfer
application readiness or create human approvals. A Python-kit alternative is
`python /absolute/kit/harness adopt ../project-invoices --apply` and the same for
the second target (use `python3` on systems with that interpreter name).

Task state, execution baselines, approvals, reports and receipts must be created
independently. Git's local exclude file may be shared between worktrees; this
is ignore configuration, not evidence or task state. Never force-add local state.
Project-owned specifications/configuration intended for version control require
deliberate review of the installed ignore policy.

Edits in B cannot invalidate A before integration because the inventories read
separate working directories. Edits outside A's authorized scope inside A still
block. After reviewed integration into A, rerun freshness and required checks:
worktrees do not establish semantic independence or substitute for integration
verification. Global binding remains unchanged in this phase.

For handoff, retain the review package before removing any temporary workspace.
Inspect both status and `git worktree list`; use ordinary `git worktree remove`
only after its work is safely retained. Never use force removal to bypass dirty
state. If setup stops partway, inspect the existing worktree and installer journal
and follow normal recovery; do not rerun creation onto a colliding path or copy
state from a different worktree. No workspace-management helper is introduced.

`tests/test_worktree_isolation.py` creates two actual Git worktrees, initializes
both independently, checks isolated evidence/state and unauthorized writes, then
integrates a branch and observes invalidation and a new real verification.
