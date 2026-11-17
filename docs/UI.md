# SpecReceipt local UI

A small, offline browser workspace: task board, inbox, and task detail. The Node
HTTP server is bundled with the CLI; no Electron, frontend package installation,
account, CDN or external hosting is needed. Node and Python requirements remain
the same as the CLI. The server binds only to `127.0.0.1`.

```sh
specreceipt ui --target /path/to/installed-project
# Optional: --port 4318
```

Open the complete URL printed in the terminal. Its fragment is a session secret;
do not share it. The UI exchanges it for a tab-scoped sessionStorage entry and
removes it from the address bar. Stop with Ctrl+C. Restarting invalidates the old
session. This is a single-user local interface, not an authenticated team service.

From the source checkout, build first and run `node dist/cli.js ui --target DIR`.
The target must be a compatible installed SpecReceipt project, just as for the
other CLI commands. A source checkout is not automatically a consumer project.

## Three views

- **Tasks:** current effective statuses, search, attention filter, four columns.
  The board refreshes every 15 seconds while you are not typing. Moving cards does
  not change lifecycle; transitions remain the engine's responsibility.
- **Inbox:** agent questions, saved answers, and tasks waiting for approvals.
- **Task:** checks, failures and warnings, changed-file inventory, next action,
  current approval package, readable spec/plan/evidence/review artifacts, and an
  explicit acceptance form. This first version does not include a code diff editor
  or streaming agent terminal. Use the existing local tools for code inspection.

Detail and inbox views stay still while reviewing or answering; use Refresh for
new data. The approval endpoint always rechecks the exact result on submission.
Unreadable/legacy/incompatible state produces a visible error rather than demo
content or a fabricated status.

## Agent questions

```sh
specreceipt ui ask --target DIR --task TASK-001 --question "Which behavior should we implement?"
specreceipt ui questions --target DIR
```

The second command returns JSON with the question ID and either `answer: null`
or the developer's answer, name and timestamp. Questions and answers persist in
`.harness/ui/questions/` and `.harness/ui/answers/`, one immutable JSON file per
record. Agents must explicitly use this interface and poll/read their answers;
existing agent conversations are not intercepted and submitting an answer does
not automatically resume an agent. The UI never converts an answer into approval.

## Approval semantics

The UI displays the existing `approval-package`, not a new lifecycle model.
Only fresh, verified results with the required current review can be accepted.
The developer supplies a name and checks an explicit acceptance checkbox. The
record retains the displayed package and result binding under `.harness/approvals/`.
Python rechecks `--expected` inside its serialized approval operation, including
for formal tasks, so stale browser previews cannot authorize a newer result.
Compact acceptance uses `workflow accept` and reaches DONE. Formal acceptance
records `task approve --kind developer`; the ordinary engine workflow performs
its separate final transition. Acceptance does not authorize commit/push/deploy.
Names are self-declared, consistent with the CLI; this is not authenticated proof.

## Design preview

```sh
npm run build
node scripts/preview-ui.mjs
```

This isolated preview uses clearly labeled synthetic data. Answers live in a
throwaway directory removed on Ctrl+C; approvals are disabled. No project state
is changed. It is for design review only, not execution evidence.

Visual references: [Plane](https://plane.so/) for restrained workspace navigation
and [Vibe Kanban](https://www.vibekanban.com/) for the task → agent → review flow.
The implementation uses original markup/styles and no copied product assets.
