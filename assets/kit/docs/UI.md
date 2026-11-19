# SpecReceipt local UI

A small, offline browser workspace: task board, inbox, and task detail. The Node
HTTP server is bundled with the CLI; no Electron, frontend package installation,
account, CDN or external hosting is needed. Node >=22.20 and <25 is required to launch the UI. Setup prepares a missing
Python runtime using the existing platform bootstrap. The server binds only to `127.0.0.1`.

```sh
specreceipt ui
# Optional: --port 4318 or --target /path/to/project
```

Open the complete URL printed in the terminal. Its fragment is a session secret;
do not share it. The UI exchanges it for a tab-scoped sessionStorage entry and
removes it from the address bar. Stop with Ctrl+C. Restarting invalidates the old
session. This is a single-user local interface, not an authenticated team service.

From the source checkout, build first and run `node dist/cli.js ui`. The launcher
opens a repository chooser without adopting the current working directory. An
explicit `--target DIR` remains an optional shortcut. A source checkout is not
automatically a consumer project.

## Multiple repositories

The home screen lists remembered repositories; the sidebar switches between
workspaces. Choose **Добавить репозиторий**, enter an absolute directory path,
and choose **Выбрать репозиторий**. A configured repository opens directly. A new
folder automatically enters setup and shows a preview of the installation.
Damaged or older installations report their actual error rather than being
silently overwritten.

Configured repositories persist under `~/.specreceipt/ui/repositories/` (override
with `SPECRECEIPT_UI_HOME`). This user-local registry contains only directory
bookmarks, up to 50 entries; tasks, evidence, answers and approvals remain inside
each repository. Discovery does not execute repository code. Missing directories
stay in the list and report an error when opened. Unreadable bookmarks produce a
visible warning. Successful connection/setup writes bookmarks atomically.

Each tab selects its own repository. Approval previews are bound to that repo,
even when task IDs match. Switching clears the task detail and review preview.
This is not an aggregated cross-repository task board.

## First-time repository setup

1. Run `specreceipt ui`, open the session URL, and add your project directory.
2. New folders automatically show setup. The default integration is Codex; choose
   another supported agent if needed and refresh the preview.
3. Review the target and planned changes, confirm, then select **Установить
   SpecReceipt**. Setup prepares missing Python and OpenSpec automatically, showing
   progress in the UI. Python uses the existing platform bootstrap and user-local
   runtime (`HARNESS_RUNTIME_DIR` overrides its location); OpenSpec uses the pinned
   npm package under `.harness/tools/openspec`, with lifecycle scripts disabled.
   Downloads require internet access. An explicit invalid `HARNESS_PYTHON` override
   reports an error rather than being silently replaced.
4. The background worker stages official OpenSpec files, checks conflicts, and
   uses the existing transactional installer. Changes since preview block setup.
   Only one installation runs per UI server at a time.
5. Review installation diagnostics and open the workspace. It is now remembered
   across server restarts. Reloading the tab during setup resumes job observation
   while the server is running. Installation grants no onboarding/task approvals.

The advanced setup mode still permits reconfiguration and an existing-OpenSpec
choice. Setup errors remain visible; fix the cause and obtain a fresh preview
before retrying. Downloaded dependencies may remain after failure. Version
migrations and pending-transaction recovery retain the CLI's explicit `upgrade`
and `init --recover` workflows. Optional navigation tools, application-specific
dependencies, agent login and provider permissions retain their existing flows.
Native Python bootstrap supports the platforms supported by the bundled scripts;
this UI does not broaden their platform support.

## Per-repository navigation settings

Open a repository, then **Настройки навигации**. Radio buttons select:

- **Только исходники / Source only:** no graph tools.
- **Автоматически / Auto:** a bounded single-file task uses source navigation;
  broader scopes select at most one enabled, installed provider, preferring a
  fresh index. Missing tools, indexing failures or query failures fall back to
  source navigation with the reason recorded in task context.
- **Свой выбор / Custom:** every enabled provider is required. Missing or stale
  indexes block the existing task gates. Each provider has Enabled/Disabled radio
  buttons; Auto and Custom need at least one enabled provider.

The CLI reads and changes the same `.harness/navigation.json`:

```sh
specreceipt navigation show --target /path/to/repo
specreceipt navigation set --mode source --target /path/to/repo
specreceipt navigation set --mode auto --providers codegraph graphify --target /path/to/repo
specreceipt navigation set --mode custom --providers codegraph --target /path/to/repo
```

Inside the repository, `--target` can be omitted. `--expected REVISION` optionally
binds a CLI update to the revision from `navigation show`; the UI always supplies
it and rejects stale edits. Changes are serialized and journaled by the Python
engine. They can invalidate task readiness/evidence; saving never grants approvals.

Settings do not install or uninstall tools. Use the existing managed installation
command for the providers you choose:

```sh
specreceipt tools update --apply --only codegraph graphify --target /path/to/repo
```

Auto is a conservative scope-based policy, not the full benchmark-tuned retrieval
system proposed in research. It does not claim measured token savings, language
coverage guarantees, or automatic tool downloads. New installs retain Source only;
legacy required-provider policies are preserved until explicitly changed. Version
1 source/required policies remain readable; settings writes use schema version 2.

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
