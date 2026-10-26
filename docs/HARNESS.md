# Engineering harness: working guide

For npm installations, use `specreceipt` for init, doctor, lifecycle operations, review and upgrade. The `./harness` commands below remain backward-compatible Python entry points. Public command arguments match Python, with `--target DIR` selecting the project. See [v0.3 guide](V03.md) for the installed-engine contract and upgrades.

This setup helps a developer and an agent carry a change from an agreed requirement to tested, reviewed code. It keeps the plan, task status, decisions and evidence in the project so another session can continue without the original conversation.

The developer owns product choices and approvals. The agent investigates, proposes bounded work, implements authorized changes, runs checks and keeps the records current. The harness supplies instructions and executable checks around that collaboration. It can dispatch explicitly configured implementation/review command adapters through a bounded local loop. No model, credentials or provider is installed or selected; application onboarding and actual approvals remain required.

## Reference navigation

This guide is a reference, not a required full-document read on every task. Select Skills by their metadata (or `harness skills`), load the relevant role, then read the sections needed for its procedure. Reuse unchanged instructions already in context; refresh them when inputs change or context is missing. Selecting fewer references never waives applicable requirements, approvals, verification, security rules or Strict policy.

| Current work | Required procedure when applicable |
| --- | --- |
| New implementation or material replanning | [Implementation approval](#required-implementation-approval-conversation) |
| Incomplete project | [Onboarding](#automatic-onboarding-after-adoption), plus the project-onboarding Skill |
| Task execution, verification or review | [Working cycle](#the-normal-working-cycle), [completion contracts](#verification-and-completion-contracts-hardening-revision) |
| OpenSpec feature | [OpenSpec workflow](#openspec-workflow-enabled-by-default) |
| Skill selection or host capabilities | [Skill catalog](#all-skills-when-and-how-to-use-them), [portable access](#use-with-different-agents-and-hosts) |
| Installation, package upgrade or Strict policy | [v0.2 guide](V02.md) and the project's .harness/quality.json |
| Managed tool update | [Tool updates](#managed-tool-updates) |
| Authorized command dispatch | [Bounded continuation](#bounded-continuation-and-command-adapters) |

## Start here

For a new project, adopt the kit. Adoption initializes its state and installs host instructions that route the installing agent, or the first ordinary task in a new agent session, through assessment and onboarding. For an existing harness project, run `resume` and `status`, then follow the recorded next action.

```sh
# From the downloaded kit (Python does not need to be preinstalled):
sh install.sh /absolute/path/to/project

# Optional read-only preview when Python is already available:
./harness adopt /absolute/path/to/project

# From the target project:
./harness doctor
./harness validate
./harness self-test
./harness graph update --if-needed
./harness graphify status
./harness graphify query "entry point" --budget 800
./harness indexes ensure
```

Adoption preserves existing files. Identical files are left alone; different files are reported as conflicts, and apply stops before copying when a conflict is found. Merge those conflicts deliberately and rerun. A concurrent filesystem change can leave a partial additive copy; rerunning is safe because target files are created exclusively rather than overwritten. Project tasks, state, journal and evidence are not copied from the kit. A fresh project state is initialized automatically; existing state is preserved.

On `adopt --apply`, the CLI checks for CodeGraph and Graphify and fresh indexes. It prepares missing uv and compatible Node/npm in a user-local runtime, installs missing or incompatible tool versions locally, enables OpenSpec by default, then initializes or synchronizes CodeGraph and updates Graphify locally without Graphify LLM extraction. This creates `.codegraph/` (or `.codegraph-wsl/`) and `graphify-out/` in the target project. In an existing Git repository, adoption adds rules both to Git’s local `info/exclude` and to the target project’s `.gitignore`, preserving existing rules. A tracked `.gitignore` will appear as modified; its rule changes can be committed, while kit files remain ignored. The rules exclude the exact kit files (including skills), `.harness/`, index directories and harness Python caches, while keeping unrelated files in shared directories visible. Without a Git repository, adoption appends these rules to `.gitignore`; a newly created ignore file also excludes itself. Neither mechanism prevents forced `git add -f`. Already tracked kit files block adoption because ignore rules cannot hide tracked files; adoption never removes files from the Git index. New application source files remain visible to Git. If setup fails, adoption reports BLOCKED; files already copied remain in place, so rerun after fixing the dependency. Use `./harness indexes ensure` after a substantial code edit batch. The application task start transition collects bounded graph context before implementation; the IMPLEMENTED transition and verification refresh both indexes. Graph findings guide source inspection, not acceptance proof.

The shell installer prepares Python 3.12 when Python 3.11+ is unavailable. A POSIX environment is required: macOS, Linux, or Windows through WSL. The runtime uses the Python standard library. Git is optional; without a repository, Git revision fields are empty. Native Windows locking is not supported. Application languages and frameworks are chosen separately in the project specification.

## What the setup provides

| Feature | What it does |
| --- | --- |
| Coordinated onboarding | Interviews the developer, consults authorized sources and reuses the existing roles to prepare a reviewed documentation base. |
| Documentation readiness gate | Blocks application transitions until required topics, documents, decisions, check configuration and developer sign-off are complete and current. |
| Project specification | Holds product goals, requirements, stack, contracts, security and acceptance criteria. |
| Architecture and decisions | Records module boundaries, allowed dependencies, recovery choices and unresolved decisions. |
| Feature templates | Provides a spec, plan, task list and verification report for each feature. |
| Acceptance traceability | Connects stable acceptance IDs to tasks, planned checks and observed evidence for review. |
| Proportionate planning | Keeps simple work brief and adds detail where contracts, data, UI or risk need it. |
| 18 agent skills | Gives each kind of engineering work a focused procedure and output contract. |
| Portable skill access | Lists and reads role instructions through the CLI even when the agent host does not discover skills automatically. |
| Task lifecycle | Controls transitions from TODO through implementation, verification and completion, with blocking and rework paths. |
| Approval and review records | Requires review and any task-specific approvals before DONE; binds records to current content. |
| Executable verification | Runs approved checks and records actual outcomes, commands and exit codes. |
| Stale-evidence detection | Detects changes to repository content, requirements, check configuration or declared environment. |
| Checkpoints | Saves meaningful progress; an unchanged checkpoint does not rewrite state. |
| Interruption recovery | Reconciles persisted operations without automatically replaying an uncertain command. |
| Implementation journal | Appends observable project actions, decisions, results and next steps. |
| Evidence storage | Keeps redacted check summaries and fingerprints for inspection and resumption. |
| Incremental code navigation | Indexes eligible files and supported Python relationships, refreshing changed paths. |
| Safe graph fallback | Makes partial or unavailable coverage visible and directs discovery back to source search. |
| Check adapters | Lets a project configure its own build, lint, test, security or migration commands. |
| Non-overwriting adoption | Reuses the kit in other projects without importing another project's history. |
| Isolated self-tests | Exercises lifecycle, recovery, evidence, graph and adoption behavior in temporary fixtures. |
| Engineering walkthrough | Uses real project evidence to explain decisions and help the developer identify understanding gaps. |

Some features are executable safeguards; others are agent procedures. In particular, each task must map its acceptance criteria to required checks through `acceptance_checks`. Execution records this declared coverage; prose tables still support semantic review and are not a proof that the checks are adequate. A passing schema does not establish that a specification is complete or correct.

## OpenSpec workflow (enabled by default)

New installations enable OpenSpec automatically; `--no-openspec` explicitly opts out. Use OpenSpec as the source of feature requirements while harness records execution scope, approvals, tests and review. Native harness features remain supported. This adapter is pinned to OpenSpec 1.14.3 and requires Node >=20.19 plus npm for installation.

```sh
# During adoption (also retains the existing navigation-index setup):
sh install.sh /path/to/project

# Or enable it in an already adopted project:
./harness openspec init --install --tools codex,claude,github-copilot
./harness openspec status
./harness openspec new add-greeting
./harness openspec instructions proposal --change add-greeting
./harness openspec list
```

The CLI is installed under `.harness/tools/openspec`, without modifying application dependencies or requiring a global install. A matching CLI already on PATH can be used without installation. Standalone `openspec init` defaults to `--tools none`. Adoption detects agent executables and existing provider configuration and selects their OpenSpec instructions; if none are detected it uses `none`. Harness startup bridges are still installed for all three supported hosts. `--openspec-tools` can explicitly override detection. Existing OpenSpec config is preserved; divergent agent files produce a conflict. Both Git ignore layers cover newly owned files. Existing corporate OpenSpec data is not silently hidden or untracked. Telemetry and update checks are disabled for adapter invocations.

Have the available agent prepare the OpenSpec change following its generated skills/instructions. Include stable requirement identifiers in the requirements, for example `### Requirement: GREET-001 Greeting`. Keep project onboarding complete and its baseline application checks configured. Then prepare an execution mapping using `templates/feature/tasks.json`: supply a new feature ID, current revisions, unique TODO task IDs, OpenSpec requirement IDs, explicit scope, acceptance-to-check mappings and the actual application check names. Do not invent test commands or approvals. Save the mapping to `.harness/openspec-mapping.json` and run:

```sh
./harness openspec validate add-greeting
./harness openspec import add-greeting --mapping .harness/openspec-mapping.json
./harness openspec context add-greeting
```

Import creates DRAFT spec/plan wrappers pointing to the OpenSpec source, retains execution metadata in tasks.json, and adds `openspec-<change>` as a required structural check. No feature requirement text is copied. Review the mapping and actual source before approving the wrappers. Adding the check changes project configuration, so renew onboarding approval after its normal review. Continue with `readiness`, task start/transition, verify and review as usual. Structural validation never replaces application tests. A checked OpenSpec checkbox does not complete a harness task.

Changes to the bound OpenSpec documents invalidate approval/execution inputs. For TODO, REWORK or BLOCKED features, `./harness openspec refresh FEATURE-ID` rebinds the source and resets wrapper approval to DRAFT. Review and approve again; unfinished attempts also need the existing `task replan` process. It never silently restarts completed work.

Scope for this adapter is active repository-local changes using the standard spec-driven layout. External stores, custom artifact layouts and automatic archive/sync are not supported. Do not move/archive linked sources without a reviewed migration of their harness records. The adapter does not claim a live model connection or remove required CodeGraph/Graphify gates. See [ADR 004](adr/004-openspec-integration.md).

## Installation-time environment assessment

Adoption previews a bounded inventory of existing project instructions, skills, package script names, local script paths, MCP configuration locations and discoverable agent executables. Applying adoption writes `.harness/assessment.json`, `.harness/assessment-context.json` and `.harness/ASSESSMENT.md`. File contents containing MCP credentials and script command bodies are not copied into the inventory. Nothing discovered is executed or connected automatically. Missing, malformed or unsupported sources remain gaps; this is not an exhaustive inventory of an IDE or corporate machine.

An already available agent (including an IDE Copilot) reads the handoff, inspects the relevant skills and its actual tool inventory, then produces a response. Apply it with:

```sh
./harness assess --response .harness/assessment-response.json
```

For unattended assessment, explicitly supply a command adapter during installation or afterward. The adapter receives the context path through `{context}` and returns JSON on stdout:

```sh
./harness adopt /path/to/project --apply --agent-command '["/path/to/company-assessor", "{context}"]'
./harness assess --agent-command '["/path/to/company-assessor", "{context}"]'
```

These paths are examples of a company-provided adapter, not installed programs. No vendor CLI syntax, model or credentials are assumed. Supplying the command authorizes its invocation in the target project under host permissions; the harness does not sandbox that process. It receives a minimal environment, has a 60-second timeout, and must not edit the project, run project checks or install/connect anything. A failing adapter leaves assessment pending. Its subprocess is real, but fixture tests do not establish live Copilot or MCP access.

The response contract is:

```json
{
  "inventory_hash": "copy from assessment-context.json",
  "role_skills": {"verifier": [".github/skills/company-tests/SKILL.md"]},
  "capabilities": [{"name": "company-search", "status": "available", "evidence": "Describe the observed host tool and its actual availability"}],
  "summary": "Explain which project capabilities should be used and which remain unavailable."
}
```

Paths must come from the current inventory. Capability status is `available`, `unavailable` or `unverified`, and remains explicitly agent-reported evidence. A CLI on PATH or an MCP config does not prove authentication or tool access. Global and IDE-only skills/tools must be assessed by the host agent; only inventoried project skill paths can currently be bound automatically.

`./harness skills ROLE` returns the canonical role plus the assessed project skill supplements. Command-adapter dispatch includes the current assessment. Changed inventoried inputs invalidate the bindings; reassess to use them again. Assessment does not authorize commands, replace acceptance checks, approve documentation or remove the current CodeGraph/Graphify prerequisites. Project command candidates still need the normal approved check configuration.

Differing project `AGENTS.md` and colliding `.agents/skills` files are preserved. Harness copies go to `.harness/AGENTS.md` and `.harness/skills` respectively; the role reader prefers the latter. The installed host bridges route to `.harness/BOOTSTRAP.md`, which loads the assessment handoff and onboarding automatically. Existing company instruction files are not edited. Other conflicting kit files still require deliberate resolution. Both ignore mechanisms cover harness copies and reports without hiding the preserved corporate instruction files.

## Where information belongs

| File or directory | Purpose |
| --- | --- |
| `AGENTS.md` | Short entry point for the agent. |
| `docs/HARNESS.md` | This complete operating guide. |
| `docs/TECH_SPEC.md` | Authoritative application requirements and stack. |
| `docs/ARCHITECTURE.md` | Authoritative application architecture. |
| `docs/DECISION_QUEUE.md` | Decisions that need developer input and the work they affect. |
| `docs/adr/` | Meaningful architectural decisions; start from `templates/adr.md`. |
| `specs/<feature-id>/spec.md` | Feature scope, requirements, acceptance and assumptions. |
| `specs/<feature-id>/plan.md` | Bounded slices, dependencies and acceptance-to-check mapping. |
| `specs/<feature-id>/tasks.json` | Task definitions, statuses, history and evidence references. |
| `specs/<feature-id>/verification.md` | Acceptance readback, findings and separate review. |
| `.agents/skills/` | Detailed instructions for each role listed below. |
| `.harness/onboarding.json` | Project mode, source references, topic coverage, baseline application checks and bound documentation approval. |
| `.harness/checks.json` | Approved executable checks and their purposes/timeouts. |
| `.harness/environment.json` | Significant application toolchain, container and database versions. |
| `.harness/graph-config.json` | Navigation provider, size limit and exclusions. |
| `.harness/state.json` | Last confirmed workflow state and next action. |
| `.harness/events.jsonl` | Append-only project journal. |
| `.harness/evidence/` | Verification summaries; optional large artifacts belong in `raw/`. |
| `.harness/graph/` | Rebuildable navigation cache. |
| `docs/ENGINEERING_LOG.md` | Optional summary generated from the project's journal. |

The specification outranks code, graph results and conversation assumptions. Feature plans record the specification and architecture revisions they use. If these disagree, resolve the conflict before dependent implementation. Keep constraints in their canonical documents and reference them elsewhere.

## All skills: when and how to use them

A skill is a role the agent can perform, not a separate process that must always run. One session can perform roles sequentially. Ask for a role in ordinary language or point the agent to its file. Hosts with native skill discovery can use their own invocation syntax; this setup does not require that support. The table below links the same instructions used by the CLI.

| Skill | Use it when | Example request and expected result |
| --- | --- | --- |
| [project-onboarding](../.agents/skills/project-onboarding/SKILL.md) | A new or existing project lacks a sufficient documentation base. | “Onboard this project; ask me questions and use only the sources I authorize.” Coordinates discovery, specifications, planning, testing, review and bootstrap until the first slice is ready; does not implement the application. |
| [bootstrap-project](../.agents/skills/bootstrap-project/SKILL.md) | A project needs its harness connected to approved requirements. | “Configure the harness for this project's approved stack.” Maps requirements to checks, records environment needs and reports readiness. |
| [spec-author](../.agents/skills/spec-author/SKILL.md) | An idea or requested change needs clear requirements. | “Turn this feature request into a draft specification.” Produces scope, stable acceptance IDs, failure cases and material open questions without inventing approval. |
| [discovery](../.agents/skills/discovery/SKILL.md) | You need to understand existing code before deciding what to change. | “Find the code and tests affected by this requirement.” Uses a fresh graph plus source inspection and reports facts, gaps and relevant locations. |
| [planner](../.agents/skills/planner/SKILL.md) | Approved requirements need a practical implementation sequence. | “Plan the smallest usable slices for this feature.” Produces dependencies, scopes, acceptance coverage and check/approval points. |
| [test-designer](../.agents/skills/test-designer/SKILL.md) | You need tests that establish required behavior. | “Derive positive, negative and boundary tests from these criteria.” Produces a test mapping and meaningful assertions, including relevant failure paths. |
| [implementer](../.agents/skills/implementer/SKILL.md) | A bounded task is approved and ready to build. | “Implement TASK-001 within its approved scope.” Changes code, runs targeted checks and leaves evidence for verification. |
| [verifier](../.agents/skills/verifier/SKILL.md) | An implemented task needs execution-based validation. | “Verify TASK-001 against every acceptance criterion.” Runs required checks, inspects results and records gaps; does not edit implementation during the pass. |
| [adversarial-reviewer](../.agents/skills/adversarial-reviewer/SKILL.md) | A complete change needs a separate challenge before completion. | “Review this feature against the full approved spec.” Checks omitted requirements, contracts and failure paths, then records located, reproducible findings. |
| [security-reviewer](../.agents/skills/security-reviewer/SKILL.md) | The change touches relevant security or trust boundaries. | “Review authorization and sensitive-data handling in this change.” Inspects applicable risks and negative cases rather than adding an unrelated checklist. |
| [debugger](../.agents/skills/debugger/SKILL.md) | A defect or failing check needs a root-cause fix. | “Reproduce this failure and repair the cause.” Produces a minimal reproduction, regression coverage, correction and re-verification. |
| [tool-updater](../.agents/skills/tool-updater/SKILL.md) | Managed tools need updates. | Checks supported versions, updates local installations and records verification. |
| [graph-maintainer](../.agents/skills/graph-maintainer/SKILL.md) | Navigation is stale, partial or failing. | “Refresh the graph and explain its coverage gaps.” Updates the index, checks results against source and records fallback needs. |
| [checkpoint-and-resume](../.agents/skills/checkpoint-and-resume/SKILL.md) | Work resumes after a pause or interruption. | “Resume this project from persisted evidence.” Reconciles files, task state and uncertain operations, then identifies the safe next action. |
| [status-reporter](../.agents/skills/status-reporter/SKILL.md) | You need an accurate progress report. | “What is complete, blocked or awaiting verification?” Reports persisted status and current evidence, including stale completion. |
| [harness-maintainer](../.agents/skills/harness-maintainer/SKILL.md) | The workflow itself has a concrete defect or recurring source of friction. | “Improve the harness to prevent this repeated failure.” Makes a targeted change and validates it with isolated evidence. |
| [engineering-walkthrough](../.agents/skills/engineering-walkthrough/SKILL.md) | You want to understand and explain completed project work. | “Walk me through this decision and its evidence.” Uses actual code and incidents, asks you to explain key choices and identifies gaps. |
| [llm-boundary-verifier](../.agents/skills/llm-boundary-verifier/SKILL.md) | The application itself includes LLM behavior. | “Verify this model-backed feature's failure boundaries.” Checks output schemas and meaning, tool authorization, injection risks, timeouts, bounded retries, cost limits, fallbacks and evaluation cases. Otherwise it is not applicable. |

Use roles according to the task, not as a compulsory sequence of every role. Delegation requires authorization and useful independent work. Inspect shared files and contracts as well as task dependencies; serialize shared writes. A separate pass by the same agent is not independent attestation, and another model's opinion is not proof of behavior.

## Use with different agents and hosts

The portable interface is ordinary Markdown plus the local CLI. Give an agent access to the project and ask it to read `AGENTS.md`. If the host does not load that file automatically, reference it explicitly in the first request. Keep `.agents/skills/` as the single role source; do not copy instructions into several competing host configurations.

```sh
./harness skills                 # List available role names and paths.
./harness skills planner         # Read the selected role, with its instructions.
```

These commands return JSON and work before state initialization. They only read files: they do not execute skills, call a model, modify configuration or grant permissions. The kit uses the portable subset of skill metadata (`name` and `description`); it has no model-tier or host-tool directives.

A host-neutral request can be: “Read AGENTS.md, use the planner role in .agents/skills/planner/SKILL.md, and prepare a bounded plan for this requirement.” Follow the actual host's instruction hierarchy and approval system. An entry file cannot override them.

| Capability | If available | If absent |
| --- | --- | --- |
| Native skill discovery | Select the relevant role through the host. | Read the role file directly or use `harness skills NAME`. |
| Structured user questions | Use the supported question interface. | Ask clearly in ordinary conversation; required answers remain pending. |
| Subagents or isolated contexts | Use only when authorized and useful. | Execute roles sequentially and disclose the review arrangement. |
| Graph indexing | Use fresh supported relationships for navigation. | Search source directly; keep verification unchanged. |
| Shell or command execution | Run approved harness and project checks. | Prepare instructions for an authorized runner; execution remains NOT_RUN/BLOCKED until evidence is available. |
| Browser or service access | Observe required behavior through supported tools. | Use an equivalent method only if it establishes the same requirement; otherwise record the missing coverage. |

Optional convenience features may have simpler equivalents. A missing capability required to verify behavior cannot be replaced with a claim of success. Portability here means agent-independent files and commands, not a guarantee that every host has been tested or can access every required environment.

## The normal working cycle

1. **Reconcile:** run `resume`, then `status`; read current state and evidence.
2. **Check inputs:** confirm the requirement, canonical revisions, approved scope and unresolved decisions.
3. **Discover:** check graph freshness, update if needed, retrieve relevant locations and inspect source/tests directly.
4. **Plan:** choose a small usable slice and connect every in-scope acceptance criterion to a task and a check or concrete inspection.
5. **Define verification:** decide what observable behavior would establish success and failure before writing implementation.
6. **Implement:** make authorized changes and use targeted checks while iterating.
7. **Verify:** execute all required checks and inspect actual behavior across the affected boundaries.
8. **Review:** assess the combined feature against the complete acceptance set, then code quality, security and error paths.
9. **Resolve:** fix findings and repeat affected verification. Change scope or acceptance only through explicit decision review.
10. **Checkpoint and hand off:** record evidence, current status, remaining limits and the exact next action.

For small wording changes, a short plan and direct readback may suffice. Changed interfaces need contract and caller analysis; storage changes need consistency and recovery analysis. UI work needs the relevant loading, empty, success, error and permission states, plus rendered checks where acceptance requires them. Add diagrams and separate documents only when they clarify a real decision.

For requests spanning multiple features, sketch deliverable increments against canonical requirements, explain real prerequisites and detail only the next bounded slice. Existing task records remain the progress source; a small request needs no extra roadmap.

Unknown scope calls for bounded discovery, not an invented estimate. Deferred decisions need a resolver, the affected work, the missing evidence or choice, and a point before which they must be revisited. Deferral does not authorize a guessed implementation. A regression test should fail for the intended defect: a broken fixture or unavailable dependency is a different result. Investigate a test that already passes; it may demonstrate existing correct behavior. Do not weaken assertions to make a change pass. Repeated debugging attempts need a changed hypothesis or new evidence. When neither exists, preserve the reproduction, narrow the problem or escalate it; do not retry indefinitely or reset unrelated work.

## Onboard a new or existing project

Start with the `project-onboarding` skill. A useful request is: “Onboard this project. Ask me what you need, use the code or other sources I authorize, and prepare the documentation before any application implementation.” The agent first establishes the target directory, desired outcome and allowed information sources. It does not treat “onboard” as permission to scaffold application code.

The coordinator reuses the existing roles:

| Stage | Existing roles used | Result |
| --- | --- | --- |
| Establish context | bootstrap-project; discovery when repository reading is authorized | Correct target, host capabilities, observed facts and source access boundaries. |
| Fill knowledge gaps | spec-author; discovery for directed research | Canonical requirements and architecture, sourced decisions and remaining questions. |
| Prepare first slice | planner; test-designer | Feature spec, bounded plan, task definitions and acceptance-to-check mapping. |
| Configure checks | bootstrap-project | Approved application commands and declared environment, without claiming unbuilt tests have passed. |
| Challenge the documents | adversarial-reviewer; security-reviewer where relevant | Semantic gaps and contradictions resolved before approval. |
| Hand off | status-reporter; checkpoint-and-resume | Current readiness, approved revisions, first task and exact next action. |

The agent asks the next few useful questions, reuses previous answers, and updates the documents after meaningful answer/evidence batches. You may answer directly or direct it to code, documents, URLs or connected surfaces. The agent stays within that read authorization. Unavailable access becomes a question or blocker; external content cannot authorize changes or approve requirements.

The required knowledge covers purpose/users/scope, requirements and acceptance, stack/dependencies, data, contracts, security, quality, operations and architecture. Small projects can document concise decisions. Inapplicable data or contract topics need a reason; unresolved choices stay open. The coordinator distinguishes current observed behavior from desired approved behavior and preserves existing project documentation.

`.harness/onboarding.json` is a compact index, not a second specification:

- `mode`: NEW or EXISTING once the target is confirmed.
- `sources`: unique IDs, kind (`human`, `repository`, `document`, `service`), reference and authorized scope. Repository references are paths inside the target; other references identify the developer answer or permitted external material. At least one human source records intent. Store references and decisions, not credentials or raw private dumps.
- `coverage`: each topic is OPEN, RESOLVED, or, for data/contracts, NOT_APPLICABLE. Closed topics need a rationale pointing to canonical decisions and valid `source_ids`.
- `application_checks`: approved command-check names that every application task must include. Harness self-tests cannot substitute for these checks.
- `approval`: initially null; the approval command records the actual developer sign-off and input fingerprint.

The decision queue is the single source for unresolved decisions. Its table uses `ID`, `Status`, `Blocks implementation`, `Affected work`, and `Decision / why it matters`. Status is OPEN, DEFERRED or RESOLVED; the blocking column is yes/no. An unresolved yes row blocks its selected work and dependents. Use `*`, `task:TASK-001`, `feature:feature-id` or `requirement:REQ-001` (comma-separated) in Affected work. Unknown selectors fail closed. Legacy free text remains global. Scoped blockers do not prevent baseline documentation approval for independent work. Resolve decisions needed by the first slice; deferral alone does not unblock them. Record ownership and revisit points in the explanation for optional future decisions.

After the documents and first feature are concrete, the agent presents them for your review and approval. It records an accurate approval reference in a project file, marks only actually approved documents APPROVED, resolves completed decisions, and runs:

```sh
./harness validate
./harness onboarding approve --by 'developer name' --reference docs/approvals/onboarding.md
./harness readiness
./harness readiness TASK-001
```

`readiness` is read-only and returns BLOCKED with actionable gaps until the prerequisites are satisfied. With a task ID it additionally checks the feature approvals/revision pins, task completeness, baseline checks, dependency completion and workflow blockers. It does not execute application checks. `onboarding approve` refuses incomplete project inputs; never call it until the developer has actually approved the presented documentation.

Approval binds the intake record, canonical documents, decision queue, check/environment configuration and approval-reference text. Changes require renewed review and approval even without a revision bump. Repository sources must exist when documentation approval is recorded; the source registry then serves as intake provenance. Ordinary application code edits or refactors do not by themselves revoke documentation approval, though they still stale execution evidence. Adoption uses the blank `templates/onboarding.json` and never copies another project's answers or sign-off.

Application start, the transition to IMPLEMENTED, verification and completion enforce readiness. Agents must also run `readiness TASK-ID` before every application edit batch. Existing projects without the intake record are blocked until onboarded; structural `validate` may pass while application readiness is blocked. Structural checks and recorded approval support a human/agent semantic review; they cannot prove document quality, authenticate the developer or prohibit direct filesystem edits outside the harness.

## Prepare and execute a feature

Fill in and approve `docs/TECH_SPEC.md` and `docs/ARCHITECTURE.md`; resolve relevant decisions and configure stack checks. Draft documents do not authorize application implementation. Application readiness also requires completed onboarding coverage, a reviewed decision queue with no blocking rows applicable to the selected work, declared application checks, the current technical revision in `stack_revision`, and a current developer documentation approval. Use the onboarding workflow below instead of filling metadata alone.

Copy `templates/feature/` to `specs/<feature-id>/`. Complete the spec and plan, pin their canonical revisions, and fill `tasks.json` with stable task IDs, requirement references, scope, dependencies, acceptance, failure scenarios, risk, required checks and approvals. Set feature kind to `application`. Keep documents DRAFT until actual approval is available.

```sh
./harness resume
./harness status
./harness validate
./harness readiness TASK-001
./harness task start TASK-001

# After implementing the approved slice:
./harness task transition TASK-001 IMPLEMENTED --reason 'Approved behavior implemented; verification pending'
./harness verify TASK-001
./harness task transition TASK-001 VERIFIED --reason 'Required checks have current PASS evidence'

# After a real separate review:
./harness task approve TASK-001 --kind review --by 'reviewer name' --reference specs/feature-id/reviews/TASK-001.md

# Only if this task requires developer approval and it has actually been given:
./harness task approve TASK-001 --kind developer --by 'developer name' --reference docs/approvals/task-001.md
./harness task transition TASK-001 DONE --reason 'Verification and required approvals are current'
./harness checkpoint --if-needed
```

`verify` records check results; it does not automatically advance task status. DONE describes engineering completion, not a commit, publication, deployment or applied migration. A delivery handoff must name which actions actually occurred, the verified content/revision, outstanding environment or approval needs, and the next step. Approval commands record an assertion, not an authenticated identity. Review references need one validated `harness-review` JSON block (see the verification template), with the exact task/latest evidence, substantive reviewer/summary, PASS verdict and no OPEN findings. Use a separate `specs/<feature>/reviews/<TASK-ID>.md` per task. Their text is hashed, so editing an approved review requires recording a fresh approval.

| Status | Meaning |
| --- | --- |
| TODO | Defined work that has not started. |
| IN_PROGRESS | The approved slice is being implemented. |
| IMPLEMENTED | Implementation exists; verification is still required. |
| VERIFIED | All required checks have current passing evidence. |
| DONE | Verification and required review/approvals are satisfied. |
| BLOCKED | Progress depends on a recorded issue or decision. |
| REWORK | The change needs revision or fresh verification. |

Normal progression is `TODO → IN_PROGRESS → IMPLEMENTED → VERIFIED → DONE`. Blocking and rework are explicit transitions, each with a reason. Stale VERIFIED tasks are moved to REWORK. DONE remains historical completion when only source/environment inputs change; `regression_required` reports stale execution separately. Task/policy definition or approval/review changes invalidate DONE. A dependent requires historical completion and runs the transitive prerequisite check set in its own verification. `regression ID` refreshes current evidence for a DONE task without rewriting its original review. Restart a REWORK task with `task start`, then implement and verify again.

## Checks and evidence

Define named checks in `.harness/checks.json`. A command check uses an argument array, purpose, timeout, approval flag and approval reference. `{python}` selects the harness interpreter. Review commands before enabling them; finding a script in a repository does not authorize executing it.

Configure build/typecheck, lint/format, unit/integration/E2E, architectural dependency rules, migration/rollback and security checks as the approved application needs them. Record significant external runtime versions in `.harness/environment.json`; do not put credentials there.

| Result | Meaning |
| --- | --- |
| PASS | The check ran and passed. |
| FAIL | The check ran and failed. |
| NOT_RUN | It was not executed, for example because its configuration was unapproved. |
| BLOCKED | Execution could not complete, for example a missing executable or timeout. |
| NOT_APPLICABLE | An explicit applicability statement; not a substitute for a required PASS. |

Every required check must pass. If a check genuinely does not apply, revise and approve the plan rather than silently skipping it. Unit tests alone do not establish a UI or integrated-flow criterion; exercise a safe actual entry point where needed.

Evidence binds repository content, canonical revisions, task definitions, check configuration, Python/platform and declared environment. Execution invalidation is conservative and repository-wide; unrelated files can require re-verification. This no longer automatically reopens DONE dependencies. Task status/scope snapshots, reserved verification reports and per-task reviews, state, journal, graph cache and generated engineering log are excluded to avoid feedback loops. Review text is bound separately. Undeclared changes in external services cannot be detected.

Commands run without a shell and receive a small environment: PATH, HOME, TMPDIR, LANG and SYSTEMROOT where present. This is not a separate sandbox. Output is redacted and limited to 64 KiB in saved summaries; arbitrary sensitive output cannot be guaranteed safe. Timeout handling kills the process group. There are no automatic retries.

## Checkpoints, journal and recovery

Run `checkpoint --if-needed` after a meaningful edit batch, finished check, changed task/phase, decision, blocker, next action or handoff. Unchanged read-only exploration does not need a new journal entry. Checkpoints describe confirmed state, not guaranteed live progress after a crash. A cross-session or cross-host handoff should identify the project path, active task, canonical revisions, evidence references, uncertainties and one concrete next action. The receiving agent reads those files directly; no particular reset command or conversation history is required.

Use the journal for observable project work:

```sh
./harness note blocker 'Test database unavailable' --next-action 'Restore the approved test environment'
./harness note resolve 'Test database unavailable'
./harness note decision 'Contract choice requires review' --next-action 'Resolve the recorded decision'
./harness note observation 'Describe the observed result and evidence'
./harness note correction 'Correct an earlier factual record'
./harness engineering-log
```

Do not record secrets, sensitive fixtures, environment dumps or private reasoning. Correct ordinary journal errors with new events. `engineering-log` generates an optional readable summary from the current project's events; it does not invent a development history.

State updates use one advisory writer lock, a recoverable pending transaction and atomic JSON replacements. Resume can replay an interrupted state transaction without duplicating its event. A recognized torn final journal append can be repaired; unknown corruption stops for inspection. Concurrent readers can observe a pending update, so reconcile before trusting completion.

```sh
./harness resume
./harness status
# Inspect uncertain effects, visible processes and partial evidence first.
./harness recovery acknowledge --note 'Describe inspected effects and the safe next action'
```

An interrupted verification command is not automatically rerun. Process IDs can be reused and descendants may remain; inspect what is observable before acknowledging uncertainty. Keep referenced evidence summaries, state and journal with the project. Graph cache, lock files, pending transactions, temporary files and large `evidence/raw/` artifacts are ignored by Git. Retention of large artifacts is manual; preserve summaries and fingerprints before removing them.

## Graph-backed discovery

```sh
./harness graph status
./harness graph update --if-needed
./harness graph query authentication --limit 30
```

The `local-python-ast` provider indexes eligible files, Python definition locations and static import syntax. Test-to-source links are naming heuristics. Relationships carry provenance and confidence. Imports may remain unresolved; there is no reliable call graph, route analysis or persistence-entity analysis. Other languages receive file nodes only. Coverage is explicitly partial.

The external navigation tools are `colbymchenry/codegraph` and Graphify. `./harness indexes status` reports both; `./harness indexes ensure` installs missing CLIs and updates stale indexes. CodeGraph's CLI `init/status/sync/query` is distinct from the unrelated `codegraph-ai/CodeGraph` MCP server. Application tasks require fresh indexes and saved task context before implementation. `./harness codegraph query TERM --limit 10` and `./harness graphify query "question" --budget 800` bound the context returned to an agent. The local graph and targeted source search remain useful for diagnosing an external tool failure, but do not satisfy the application index prerequisite. Neither graph is a verification gate or proof of behavior.

### Repository investigation with host MCP tools

For a story or plan claim about existing code or an external contract, inspect the active host's actual MCP tool inventory and query relevant already-connected read-only tools within the authorized task. A configured server is only a candidate. Compare bounded MCP results with exact repository locations, tests and approved requirements. Record agreement, contradiction, missing evidence or optional code-only coverage; a graph or MCP answer alone does not establish behavior. Never connect an arbitrary server, invoke a mutation tool, persist credentials/raw dumps, or claim that an agent-authored report authenticates tool execution.

`./harness investigation record TASK-ID --file .harness/candidate-investigation.json` validates and atomically stores `.harness/investigations/TASK-ID.json`; `./harness investigation check TASK-ID` rechecks the current task definition, policy and repository file hashes. The JSON report has `schema_version: 1`, `task_id`, `question` equal to the task outcome, `definition` equal to the engine task-definition digest, `repository_fingerprint` equal to `digest(h.fingerprints())`, `policy_hash` equal to the digest of the effective investigation policy, nullable `host_trace`, `tools`, and `claims`. Each tool has `name`, `status` (`available`, `configured_only`, `unavailable`, `denied`, `failed`, `irrelevant`), `read_only` and a bounded relevance `reason`. Each claim has an `id`, exact task `criterion`, bounded `summary`, nullable source `category`, `result` (`AGREE`, `CODE_ONLY`, `NO_MCP`, `CONFLICT`, `UNVERIFIED`), `code` references (`path`, one-based `line`, full-file `sha256`), and `mcp` references (`tool`, `resource`, `revision`, `observed_at`, bounded `summary`, `status`); failed or denied results use `revision: null`. Use Python's `Harness.definition(task)`, `investigation.policy(h)` and `storage.digest(...)` to populate the three content pins; they are not approvals. A failed record leaves the preceding report intact, but `check` still detects stale inputs.

Projects may add `.harness/investigation-policy.json` with `{"schema_version":1,"required_sources":[{"category":"api-contract","tasks":["STORY-001"]}]}`; `*` targets all tasks. Without this file, no MCP category is required by default. For required categories, a matching AGREE claim is mandatory. Every successful MCP claim, required or optional, needs a current source revision before `check` can PASS. The host may submit a fresh `.harness/investigations/TASK-ID.current.json` or pass `--current FILE` to `check`; its fields are `schema_version`, `task_id`, UTC-aware `observed_at`, and `sources` entries with `resource` and `revision`. Current observations expire after 24 hours and must not predate the claim. Their contents are still host/agent reported. Missing, denied, failed, contradictory or changed required sources block the dependent claim and application readiness; unrelated work may continue. Optional absence remains visible as NO_MCP or CODE_ONLY. The engine does not call MCP itself.

Freshness uses working-tree hashes and provider configuration. Updates reuse unchanged parsed records, index new/changed files and remove deleted paths, including renames. Untracked files and lockfiles are considered. Configuration changes require re-indexing the eligible inventory. Interrupted updates remain visibly stale until a successful update. The default per-file limit is 1 MiB; secrets, symlinks, dependencies, generated files and binaries are excluded from navigation.

Always inspect retrieved source and the applicable specification. On unavailable or insufficient coverage, use targeted text search such as `rg`; required verification still applies. The graph is neither a specification nor behavioral evidence, and must not be the sole test selector.

Additional graph providers require a demonstrated retrieval gap, an identified upstream tool/version/interface and a data-handling review. Compare them with the local fallback, record the decision and rollback plan, then test on isolated fixtures. An adapter must retain the manifest, status, query, provenance and failure contracts. Providers without incremental support must disclose bounded full rebuilds.

## Command reference

| Command | Purpose |
| --- | --- |
| `./harness adopt PATH` | Preview files and conflicts in a target project. |
| `./harness adopt PATH --apply` | Apply a conflict-free, non-overwriting adoption. |
| `./harness init` | Initialize missing state; preserve existing state. |
| `./harness readiness [TASK-ID]` | Report project or selected-task documentation readiness; exit nonzero when blocked. |
| `./harness onboarding approve --by NAME --reference FILE` | Record actual developer approval of complete project documentation and configuration. |
| `./harness skills [NAME]` | List roles, or read one role without invoking an agent or changing state. |
| `./harness doctor` | Report runtime, skills, Git information and structural validation. |
| `./harness validate` | Check document structure, schemas, references, history and evidence consistency. |
| `./harness self-test` | Run isolated harness regression tests; fail if no tests are found. |
| `./harness task start ID` | Start or restart a task through its lifecycle gates. |
| `./harness task transition ID STATUS --reason TEXT` | Record an allowed status transition. |
| `./harness task approve ID --kind KIND --by NAME --reference FILE` | Record an already-given approval or completed review. |
| `./harness verify ID` | Run required checks for an IMPLEMENTED task and save evidence. |
| `./harness next` | Read the next deterministic action without executing it. |
| `./harness run --max-steps N --max-seconds N` | Continue within persisted budgets and explicit adapter authorization. |
| `./harness regression ID` | Refresh current checks for historically completed work. |
| `./harness task replan ID --reference FILE` | Record actual reviewed scope/policy changes without absorbing source edits. |
| `./harness status` | Read current recorded state and observed evidence freshness. |
| `./harness resume` | Reconcile state, interruptions and stale evidence, then report status. |
| `./harness checkpoint --if-needed` | Save a checkpoint only when meaningful state differs. |
| `./harness note KIND TEXT --next-action TEXT` | Record observation, decision, blocker, resolution or correction. |
| `./harness recovery acknowledge --note TEXT` | Clear uncertainty after inspecting interrupted-operation effects. |
| `./harness graph status` | Report freshness and coverage. |
| `./harness graph update --if-needed` | Refresh the eligible navigation index when stale. |
| `./harness graph query TERM --limit 30` | Retrieve a bounded neighborhood, refreshing first if needed. |
| `./harness engineering-log` | Generate a readable summary of project journal events. |

The global `--root PATH` option, placed before the subcommand, selects another harness root. Ordinary project use should run the project's own `./harness` from its root so commands, checks and files stay together.

## Extension and enforcement boundaries

The Python modules have focused responsibilities: `storage.py` handles schemas, redaction, locking and transactions; `core.py` handles lifecycle and evidence; `verification.py` handles input inventory, scope, acceptance and review; `runner.py` handles bounded dispatch; `graph.py` handles navigation; `cli.py` exposes commands; `skills.py` reads the role catalog; `readiness.py` checks onboarding prerequisites and approval freshness; `adopt.py` copies reusable files. Add isolated regressions when changing these mechanisms.

Schema validation implements a deliberate subset: type, properties, required, additionalProperties, items, enum, minLength, minItems, pattern and minimum, plus descriptive metadata. Unsupported keywords fail closed. Do not assume full JSON Schema support.

Markdown guides agent behavior. Scripts detect invalid records and enforce their own transitions. The host's permissions restrict actual actions. Protected CI, restricted credentials and branch rules provide separate enforcement outside editable local files. Configure those for the target repository; the harness does not enable them.

The setup does not automatically install dependencies, change model settings, apply migrations, commit, merge or deploy. Agent subprocesses run only through explicitly configured and authorized adapters. Such actions follow the user's authorization and the project's approved workflow. Local approvals are not identity attestations, and editable scripts can be bypassed by their editors.


## Verification and completion contracts (hardening revision)

Design and primary-source rationale: [ADR 001](adr/001-harness-hardening.md).

- Add `acceptance_checks` to each task: an array of `{"criterion": "exact acceptance_criteria string", "checks": ["required-check-name"]}`. Every criterion appears exactly once; every named check must be required. This binds declared coverage to real execution, without proving test semantics.
- Scope accepts normalized repository-relative files or explicit `directory/` prefixes, not glob patterns. Start snapshots current inputs, including existing user changes. Later changes outside scope block implementation, verification and completion. Retries of unfinished work preserve the snapshot. Reopening a previously completed task begins a new attempt with a new observed snapshot, so later completed work is not falsely attributed to the old task. For an approved scope/policy change, move to REWORK or BLOCKED, update the approved inputs, then `task replan ID --reference docs/approvals/replan.md`. This records actual reviewed replanning and preserves the original source snapshot. Missing legacy baselines require a reviewed replacement task.
- `.env*`, binary assets and executable bits participate in verification hashes without recording contents. `.DS_Store` is ignored. Symlinks fail closed. Navigation exclusions do not determine verification inputs. Build/dependency directories listed in `verification.py` remain excluded; declare relevant versions in environment.json. Remote services and mutable installed packages are not automatically fingerprinted.
- `./harness regression ID` reruns a completed task and its prerequisite checks against current inputs. It does not replace historical completion or authorize deployment. A failed regression is visible as stale/nonpassing evidence and blocks the dispatcher's finished result.
- Reserved `specs/<feature>/verification.md` and `specs/<feature>/reviews/` contain records only, never runtime code. Reviews bind their own text independently. Prepare any external developer approval reference before the final verification when it lies outside these reserved record paths.

## Bounded continuation and command adapters

`./harness next` returns a deterministic read-only next action: start, implement, verify, review, approval, complete, regression, finished, or a concrete blocker. Selection keeps the active task first and otherwise uses stable task-ID ordering among ready tasks. BLOCKED tasks are never silently restarted.

`./harness run --max-steps 20 --max-seconds 600` advances mechanical steps and optionally invokes configured adapters. Without adapters it stops at implementation/review so the current agent session can do that role. Each dispatcher step consumes a persisted step budget; elapsed execution time and failures are also recorded. Repeating the command resumes the same budget. Only explicit `--new-run` creates a new budget after inspection. These are local wall-time/step/failure controls, not a model-token or monetary budget. Command bundles are admitted only when their configured timeouts fit the remaining budget; filesystem overhead may exceed the nominal time boundary.

To opt in, copy `templates/runner.json` to `.harness/runner.json`, fill the allowlisted task IDs, exact implementation/review command arrays, timeout and failure limit. Present the actual configuration and access implications for developer approval. Record that actual authorization in `approval_reference`. Set enabled to true only within that authorization, then calculate approval_hash with the following local Python expression (the hash binds the full configuration and the reference text):

```python
from pathlib import Path
from harnesslib.runner import authorization_hash
from harnesslib.storage import read, atomic
root = Path.cwd()
p = root / '.harness/runner.json'
cfg = read(p)
cfg['approval_hash'] = authorization_hash(cfg, (root / cfg['approval_reference']).read_text())
atomic(p, cfg)
```

A hash records an assertion; it is not authenticated human identity. The default template is disabled. The harness never chooses a vendor, installs a CLI, passes production credentials or changes host sandbox permissions.

Adapters receive a JSON context-file path through `{context}` and may use `{task_id}` in argv. `{python}` selects the harness interpreter. Context contains task/feature, action, scope, required checks, acceptance mapping, latest evidence and review output path. The adapter must read repository instructions and canonical documents. Implementation edits only approved scope and exits zero when ready for checks. Review is a separate invocation and writes only the provided review path with the structured review block; it must inspect actual behavior/evidence. Adapters must not call lifecycle/approval commands or mutate task/configuration records. The parent holds the advisory writer lock, validates effects and performs transitions itself.

Intent is persisted before a subprocess starts. Timeouts or interrupted intent produce uncertainty, never automatic replay. Inspect effects/processes and use `recovery acknowledge` only when justified. Failed verification or a substantive review requesting changes routes back to implementation within the remaining budget. A nonzero adapter result stops the invocation and consumes failure budget. A successful subprocess does not imply successful verification. Required developer approvals stop the loop at `approval`; they are never generated by the runner.

The dispatcher uses existing command environment restrictions. Adapter credentials and isolation must be supplied by the authorized host; there is no new sandbox. Review process separation is not independent attestation. No live provider has been validated by this kit's deterministic adapter tests.

## Upgrading existing projects

Use adoption preview and explicitly merge conflicts; do not overwrite project-owned records. Add acceptance maps, migrate reviews and rerun checks. Legacy evidence without definition/coverage fields cannot establish current completion. Old tasks without a scope snapshot cannot claim retrospective scope verification: archive their records as history and define reviewed replacement tasks. A default DRAFT application remains blocked after upgrading.


## Managed tool updates

Use the [tool-updater skill](../.agents/skills/tool-updater/SKILL.md), or run:

```sh
python3 scripts/update-tools.py                    # read-only plan
python3 scripts/update-tools.py --check-latest     # compare public upstream releases
python3 scripts/update-tools.py --apply            # install/update supported versions
python3 scripts/update-tools.py --apply --include-optional --only openspec
```

Equivalent CLI: `./harness tools update`. The managed set is CodeGraph, Graphify and optional OpenSpec. Versions come from their adapter contracts; newer upstream releases require compatibility review and tests before changing those pins. Newer installed versions are blocked rather than downgraded. Missing optional OpenSpec is skipped unless explicitly included or already configured.

Installations live under `.harness/tools/` and take precedence over PATH tools. The updater refreshes changed navigation indexes and runs `validate` and `self-test`. `.harness/tool-updates.json` records per-tool outcomes and partial failures. Interrupted updates retain an active-tool marker: inspect processes and installation files before clearing it and retrying. Host Python/Node/npm/uv, agent CLIs, corporate MCP and application dependencies are not automatically upgraded. Existing adoption exclusions cover local installations and reports; adoption also excludes the installed script and skill by exact owned paths.


## Automatic onboarding after adoption

`./harness adopt /path/to/project --apply` installs these exact, Git-excluded startup bridges by default:

| Host | Installed entry point |
| --- | --- |
| Codex | `AGENTS.override.md`, explicitly directing the agent to read existing `AGENTS.md` first |
| Claude Code | `.claude/rules/harness-bootstrap.md`, an unconditional project rule |
| Copilot in supported local hosts | `.github/instructions/harness-bootstrap.instructions.md`, with `applyTo: "**"` |

All bridges route to `.harness/BOOTSTRAP.md`. The installing agent should continue there immediately in the target project. If adoption runs in a plain shell, open a new agent session and give the actual task, for example “Add CSV export for orders.” No setup prompt or manual `init` step is needed. Already-open hosts may need a new session to load instructions. Host policies must permit custom instructions; unsupported/disabled hosts and remote agents without these ignored local files are not covered.

The agent preserves the request, reconciles state, evaluates available corporate skills/MCP capabilities, prepares missing project documentation with project-onboarding, and asks only for unresolved decisions and concrete approvals. Once readiness passes it continues the requested task. It skips completed onboarding and preserves existing approvals; it never invents approval. A shell installer does not run a model or prove semantic readiness. Its `agent_bootstrap.status=instructions_installed` means routing files exist, not that onboarding or authentication has completed.

Bridge conflicts and tracked bridge files block installation before copying, just like other owned kit files. Corporate `AGENTS.md`, `CLAUDE.md`, Copilot instructions and skills remain preserved. Codex selects an override instead of the same-directory AGENTS.md, which is why our bridge explicitly loads the original; this is an agent instruction, not enforcement against a disobedient model.

Host contracts: [Codex discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Claude project rules](https://code.claude.com/docs/en/memory), [VS Code custom instructions](https://code.visualstudio.com/docs/agent-customization/custom-instructions). Actual authenticated host consumption still needs a live host check; file tests do not establish that.


## One-command runtime bootstrap

Run `sh install.sh /path/to/project` from a cloned or unpacked kit. The target may be new or existing. This wraps `adopt --apply`; OpenSpec is enabled without extra flags. `./harness adopt PATH --apply` also bootstraps missing Python through its shell launcher. `python3 harness ...` remains supported when Python is already installed. Read-only commands never bootstrap missing Python.

The installer detects usable Python, uv, Node/npm and exact adapter-supported tool versions. It reuses compatible programs. If Python is absent/too old, the shell downloads uv from its official installer and installs managed Python 3.12. A compatible Node/npm is reused; otherwise the installer downloads the matching official Node 22 distribution for macOS/Linux x64/arm64 and verifies its SHA-256 against the official checksum manifest before extraction. CodeGraph, Graphify and OpenSpec installs use project-local prefixes. No sudo, system package replacement, shell profile edits or agent login is performed.

Managed prerequisites live under `${XDG_DATA_HOME:-$HOME/.local/share}/harness/runtime`, overridable with `HARNESS_RUNTIME_DIR`. Keep that override when invoking the kit, or export it in the host environment. The harness launcher activates this directory for its own processes. Downloads require network access and a trusted HTTPS chain; initial Python bootstrap needs system `sh`, basic POSIX utilities and curl or wget. Native Windows is unsupported; use WSL. Unsupported architectures, unavailable native libraries/build dependencies, corporate download restrictions and missing host permissions produce failure, not a false ready result.

`.harness/runtime.json` records runtime versions; `.harness/install.json` records each provisioning/index/validation stage and the failing stage. For a new project with no eligible code, the pinned Graphify CLI explicitly reports that absence; harness records an empty graph with `coverage: empty`. This is not an extraction failure or evidence of application correctness. Adding source makes the index stale and triggers extraction. Other Graphify errors still block installation.

An interrupted RUNNING report blocks replay: inspect remaining processes and partial effects before removing the report and retrying deliberately. BLOCKED failures may be retried after fixing their cause. Files already installed remain; there is no automatic rollback. A failed tool version probe is reported rather than silently overwritten.

The installer provisions the harness toolchain, not arbitrary application stacks or authenticated agent accounts. Application dependencies are determined during automatic onboarding from project requirements and corporate instructions. Inventory discovers candidate agents and project configuration; it does not prove host login or MCP access. Runtime bootstrap and agent onboarding are separate recorded outcomes.

References: [uv unmanaged installation](https://docs.astral.sh/uv/reference/installer/), [uv managed Python](https://docs.astral.sh/uv/guides/install-python/), [official Node distributions](https://nodejs.org/dist/).


## Required implementation approval conversation

For every new implementation request, the agent first investigates and prepares a concrete spec and implementation plan. It presents their current revisions, scope, expected behavior, steps, acceptance checks, relevant risks and open decisions, then asks explicitly: “Approve this specification and implementation plan and start implementation, or should we revise it?” The initial feature request does not automatically approve the later proposal.

The developer can approve or request changes. Changes keep the proposal DRAFT; the agent revises the documents and task mapping, shows the updated version and asks again. Repeat until the current version is explicitly approved. Record the real approval reference and revisions, run `readiness TASK-ID`, then start implementation. For OpenSpec features, approval covers the actual linked source plus execution mapping, not just wrapper headings. Material changes during execution require reviewed replanning and renewed approval before dependent edits.

Existing explicit approval of an unchanged plan remains valid across its listed tasks and resumed sessions. Routine implementation steps and fixes within that scope do not require repeated confirmation. Setup success, project onboarding approval, schema validation, silence and clarification answers do not approve a new implementation plan. Read-only investigation and drafting may proceed before approval. Existing readiness/start gates reject DRAFT inputs; the agent procedure supplies the user-facing approval dialogue. Agent-writable metadata cannot independently prove a human answer.


## npm distribution facade

The public CLI delegates lifecycle commands through a versioned JSON adapter to the verified project-installed Python engine. Python owns initial state, transitions, approvals and evidence. Doctor validates that same engine without running application checks. Use dedicated `upgrade --dry-run` and `upgrade` for package changes; init refuses version changes. See [v0.2 guide](V02.md) for safe conflicts, migrations, recovery and isolated package/E2E procedures.

## Adaptive task workflow

For npm initialization, `--workflow openspec` selects the specification integration and `--quality strict` selects the engineering quality baseline. Neither selects the execution profile of an adaptive task; `--workflow adaptive` is not an initialization option. The Python Engine owns profile selection and enforcement. An absent `.harness/workflow-policy.json` defaults to a FAST minimum with no blanket OpenSpec requirement, while task risk, linked requirements and explicit policy may require more. Existing legacy task requirements remain unchanged. Installing OpenSpec scaffolding does not require creating an OpenSpec change for every task.

For a new task in an already onboarded project, first prepare a brief plan and bounded facts (at most 12 relevant files, 128 KiB total) and use `./harness workflow assess TASK-ID --facts FILE`. This preliminary assessment does not require index rebuilding, loading all Skills, or creating OpenSpec artifacts. Keep onboarding `assess` separate. Resolve cheap unknowns locally; critical unknowns block confirmation until investigated.

Present recommendation, policy minimum, reasons and the brief plan together. In FAST, request one explicit workflow-plus-plan confirmation, then record it with `./harness workflow confirm TASK-ID --profile FAST --by NAME --reference FILE`; terminal users can use `specreceipt workflow select TASK-ID --by NAME`. A recommendation is never authorization. Record approved document metadata from the actual answer before binding confirmation. Project policy may require separate approvals. Preserve existing readiness, required tests, scope, review and evidence gates. Request final `developer` approval only after VERIFIED and review, before DONE.

FAST uses targeted investigation/tests and compact evidence; STANDARD uses structured investigation, integration checks appropriate to affected boundaries and separate review; STRICT retains formal specification/OpenSpec and all existing gates. Do not drop configured checks. Use OpenSpec for FAST/STANDARD when project policy, linked requirements or scope demands it; no automatic initialization merely to assess. Reassess only on material scope, policy, risk or requirements changes.

Finish meaningful outcomes with `./harness status TASK-ID --format terminal` (or `markdown`/`json`). Show real project/files, evidence, approval freshness and next command. For disposable runs use `--retain-dir /persistent/review-location` when authorized; `--retain` stays inside the target and does not survive deletion of that target. Local records cannot authenticate consent or prevent direct filesystem edits.

### Assessment facts and project policy

Example facts file (repository-relative references actually inspected by the agent):

```json
{"critical_risk":false,"critical_unknowns":[],"unknowns":[],"public_api":false,"architecture_change":false,"components":1,"inspected":["src/parser.py"],"agent":"codex"}
```

Python validates sizes and references, scans bounded evidence and task metadata for sensitive signals, and enforces the project floor independently of the recommendation. This conservative signal check is not a complete semantic security analysis. Record uncovered critical questions explicitly; ordinary unknowns can be resolved by targeted inspection or an explicitly selected policy-permitted workflow. No recurring assessment after minor edits is required.

`public_api` means that the task changes an externally consumed contract or introduces a contract intended for external consumption/public distribution (for example a published package export or service endpoint). A new local CommonJS export used only by local tests is not automatically public. Cite actual consumers, distribution intent or integration evidence; unknown exposure belongs in the unknowns requiring investigation, not an invented `false`. The engine validates the boolean and enforces its STANDARD floor; it cannot discover consumers outside the inspected project or authenticate an agent's factual assertion. Keep task risk independent: a recorded medium risk may recommend STANDARD even when the policy minimum is FAST.

Risk detection uses token/identifier families, so `author` does not match `auth`, while `authorize_user` and `authenticateUser` remain sensitive source signals. Assessment, confirmation and lifecycle guards share the same bounded classifier. In narrative text, applicable sensitive changes establish a STRICT signal; narrowly recognized complete statements of non-applicability such as “No authentication” or “No production impact” do not. Mixed statements retain their positive clauses. Sensitive requirements such as “No authentication bypass is allowed” are not scope exclusions. Uncertain wording, bare unresolved mentions and unrecognized negations require deeper assessment. STRICT selection can proceed only after the bounded review below; FAST and STANDARD remain blocked. This is a conservative deterministic classifier, not general natural-language understanding; source/config content remains conservative and only full-line comments receive narrative treatment.

Known task records are scanned for substantive requirement/outcome/acceptance/failure fields, not their previously generated workflow conclusions, approval records or history. Onboarding coverage rationales and check purposes/commands remain inspected; provenance labels are not risk evidence. These narrow structural projections do not apply to arbitrary JSON, and full file hashes remain bound as evidence. Section labels alone do not establish scope. Explicit `critical_risk`, high task risk, `minimum`, `strict_paths`, required checks, approvals and applicable OpenSpec requirements retain precedence; a negative document cannot waive sensitive code or policy. The classifier version is bound into the material fingerprint, so an engine classification change requires reassessment rather than reusing an older decision. Evidence beyond the bounded inspection limit requires investigation instead of being silently skipped.

For ambiguous or oversized findings, inspect every flagged source and write a JSON review inside `.harness/` with `task_id`, the assessment `material` and `assessment_revision`, and one `items` entry per exact finding. Each item needs `source`, the file raw SHA-256 in `sha256`, up to eight one-based `locations`, a sanitized 40–1000 character `finding`, and `risk` of `HIGH` or `NOT_APPLICABLE`. The `task scope/requirements` finding binds to a stable hash of the substantive task definition rather than the mutable workflow envelope in `tasks.json`. Run `./harness workflow resolve TASK-ID --review .harness/path/to/review.json`, then `./harness workflow confirm TASK-ID --profile STRICT --by NAME --reference FILE`. Confirmation and task guards recheck completeness, source hashes, assessment revision and review content. Missing sources, critical unknowns and absent inspected evidence remain blocked. This review is an agent-authored attestation, not independent proof of the analysis.

Optional `.harness/workflow-policy.json` fields are `minimum` (FAST/STANDARD/STRICT), `strict_paths` (glob patterns), `required_checks`, `approval_requirements`, `openspec_required` and `separate_plan_approval`. Policy edits need developer decision review and invalidate existing adaptive confirmation/evidence. New task templates set `workflow_required: true`, so task start requires assessment and explicit confirmation. Legacy tasks without this marker or adaptive metadata retain existing strict gates. A policy change does not retroactively fabricate workflow selections.

The official confirmation record kind is `workflow-plan`; when separate plan confirmation is mandatory, record `plan` through `task approve`. Final consent uses `developer`. Required checks and approvals cannot be removed by choosing FAST. Standard/Strict depth is reflected in the approved task plan and check selection; engine minimums, current evidence and protected transitions remain mandatory. Assessment does not automatically approve DRAFT documents.

Terminal selection: `specreceipt workflow select TASK-ID --by NAME`. Noninteractive/IDE: present the recorded plan and recommendation, obtain an actual answer, then `./harness workflow confirm TASK-ID --profile FAST --by NAME --reference FILE`. Never generate a fictitious approval reference.

Use `specreceipt status TASK-ID --json` for the versioned protocol envelope; `./harness status TASK-ID --format json` returns report data directly. Raw `./harness status` remains backward-compatible. Check summaries are compact; complete redacted subprocess logs are retained with content hashes in evidence. Recognized TAP counts are shown per check; unknown counts remain unknown.

### Agent execution preflight and current reports

Before a repository-owned paid Codex/Copilot launch, execution preflight reuses doctor diagnostics. Inspect it without a model call:

```sh
specreceipt doctor --execution --agent codex --target /absolute/project --task TASK-001 --ignore-user-config --json
specreceipt doctor --execution --agent copilot --target /absolute/project --json
```

Use the same environment, working directory and ignore-user-config setting as the launch. The programmatic `executionPreflight` / `checkedAgentLaunch` exports in `dist/doctor.js` accept the exact launch environment; `runCopilot` sanitizes permissions before both probes and spawn. Codex probes its selected login shell (the default is `$SHELL`, then `/bin/sh`); a host with another shell must supply that shell explicitly. Unknown Codex shell environment policies fail closed rather than claiming the outer PATH is authoritative. Probes are bounded, deterministic version/capability checks; they do not install tools, authenticate through a model or rebuild indexes.

Diagnostics separate REQUIRED, OPTIONAL and NOT_APPLICABLE from PASS/WARN/FAIL. Python resolves existing navigation requirements from the selected application task and explicit repository index instructions. Required CodeGraph/Graphify CLI capabilities remain mandatory. Without such a requirement, a missing CodeGraph CLI warns and available repository search is a fallback. `copilot-ide` requires no CLI. A configured MCP server is not necessarily available: an already-connected host can supply a read-only capability probe identifying server `codegraph` and a supported query/search tool, or a generic `mcpInventory` of server names and observed read-only tool names. A required generic server passes preflight only with an observed read-only capability; a task claim still needs investigation evidence. Preflight never activates a server or contacts an endpoint itself. MCP availability never replaces a CLI-only engine contract. Copilot's disabled built-in MCP flag does not disable explicitly configured custom servers.

The guard covers the repository's Codex E2E spawn and Copilot transport, including continuation paths. External/direct agent launches and arbitrary runner adapters must use the guard themselves. Version/help and shell probes cannot prove model authentication, account quota, sandbox-specific access restrictions or future filesystem stability. Run preflight immediately at the launch boundary; it does not grant lifecycle or permission approval.

Python `status TASK-ID --format terminal` renders live lifecycle state, evidence freshness, review and approvals. Historical implementation notes are explicitly labeled with their recorded state and time. New retained reports include snapshot timestamps; existing evidence and snapshots are never rewritten. Valid historical DONE completion and current regression evidence are displayed separately.

After lifecycle transitions, verification, approvals, reconciliation and checkpoints, derived current reports are refreshed at `.harness/reports/current.json` and `.harness/reports/current.md`. These files are excluded from verification fingerprints and are not immutable evidence. Their `state_updated_at` / generation time identifies the observation; external edits require a fresh status query or checkpoint. Bounded workflow assessment marks the cached report explicitly stale without triggering a full reporting inventory. If refresh fails after a committed transition, a warning and `.harness/reports/refresh-error.json` identify the stale cache; the committed state is preserved. Use live `status` rather than a failed cache. Final developer approval remains a separate gate.

## Task baseline reconciliation

When approved work from another task intervenes, do not enlarge the current task's write scope or reset its baseline. Use `./harness task baseline propose TASK-ID` to produce an exact JSON manifest, retain it under `.harness/evidence/`, and obtain explicit developer approval of its digest (`harnesslib.storage.digest` over parsed JSON). Record that digest in the approval reference. Then use `./harness task baseline accept TASK-ID --manifest FILE --reference APPROVAL --by NAME`.

Recognition records exact created/modified/deleted paths, inventory identities (including executable mode), raw SHA-256, original baseline, task definition and prior record digest. It grants no write permission. Additional changes require a new explicitly approved manifest; changed recognized content, symlinks, unsafe paths and stale references block progress. Task-policy changes use approved `task replan`; replan preserves the original baseline, archives prior execution, and keeps policy adjustments separate. A changed definition requires fresh recognition approval before restart. Other tasks' lifecycle-only JSON fields use the existing semantic inventory after acceptance; substantive changes remain detected.

Reports label recognized pre-existing files separately from task-scope changes. Full repository test evidence remains content-bound: recognition never makes old tests or reviews current. Run required verification and review again, then obtain separate final developer approval. Recognition is a local authorization record, not authenticated identity or protection against malicious local writers.
