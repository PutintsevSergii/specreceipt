# Choosing test runs

Use scoped feedback while editing. Do not run the full regression after each file change.

| Situation | Command | Meaning |
| --- | --- | --- |
| Inspect local changes | `python3 -B tests/run_scoped.py --profile changed --dry-run` | Explain paths, selected checks, reasons and commands; execute nothing. |
| Check local changes | `python3 -B tests/run_scoped.py --profile changed` | Staged, unstaged and untracked files; a scoped result. |
| Check a branch | `python3 -B tests/run_scoped.py --profile changed --base origin/main` | Changes since the actual merge base, plus local changes. Fetch the target ref first. |
| Short contract check | `python3 -B tests/run_scoped.py --profile smoke` | Five Python cases covering protocol, atomic replacement and bounded index context; not complete acceptance. |
| Selector implementation | `python3 -B -m unittest discover -s tests -p test_test_selection.py -v` | Small isolated fixtures and Git repositories, no full-kit adoption. |
| Investigate a module | `python3 -B tests/run_scoped.py --profile changed --suite py:test_reporting --language python` | Explicit manual coverage; not a claim of complete automatic selection. |
| Complete Python acceptance | `python3 -B tests/run_scoped.py --profile full --language python` | Existing complete `harness self-test` plus structural validation. |
| Complete configured baseline | `python3 -B tests/run_scoped.py --profile full` | Python, native Node compatibility, type/build, real package and applicable wizard checks. |

On Windows replace `python3` with your native `python` command, or invoke `scripts/python.ps1 -B tests/run_scoped.py ...`. No WSL is needed. Set `HARNESS_PYTHON` when using the existing launcher with a runtime outside PATH. The selector's subprocesses use the same interpreter as the selector.

Run from the repository checkout; the script resolves its root independently of the shell working directory. An adopted kit inside a larger repository cannot safely infer repository-relative changes and fails explicitly rather than testing the wrong root. No profile means usage/error, not an accidental full run. `--language python` and `--language node` split CI responsibilities; neither is complete cross-language acceptance alone.

## How impact selection works

`tests/test_scopes.json` contains an explicit inventory and reviewed boundary-to-check mappings. Test-to-test static imports expand the selection transitively, including shared fixture consumers. Dynamic imports, subprocess calls, generated files and cross-language relationships require explicit manifest edges. Graph names alone do not select tests.

Examples: a change to `tests/test_protocol.py` selects its module; a change to the shared `tests/test_harness.py` fixture selects the complete baseline. A reporting change includes reporting, performance, recovery and lifecycle consumers. Unknown paths deliberately select the full baseline. Invalid configuration, new/unmapped or deleted test modules, unresolved test names and missing Git bases fail visibly instead of becoming a green zero-test run.

Update the manifest whenever tests or production boundaries change. New Python tests must match the existing `test_*.py` discovery convention; Node tests use `*.test.mjs`. `--dry-run` is advisory and checks no runtime prerequisites. The maintained map is conservative impact selection, not a complete dynamic call/coverage graph. It can select more tests than necessary. Do not narrow it merely to make a run quick.

`EMPTY_DIFF`, `PROSE_ONLY`, `MANUAL` and `SCOPED` are distinct labels. A no-command run reports `NO_RUNTIME_TESTS`. Read actual unittest/Node summaries for skipped counts. Scoped PASS never establishes complete acceptance. Windows retains the prior native Node compatibility set; POSIX-only Node/wizard fixtures are listed as not applicable there, not counted as executed.

## Prerequisites and final acceptance

Selection and Python tests require only the existing Python and Git runtimes. Node/build/package checks require the project's existing dependencies (`npm ci`) and supported Node. They build before executing selected Node modules. Real OpenSpec package checks require the reviewed `HARNESS_REAL_OPENSPEC` executable, as in CI. The runner does not install prerequisites itself.

Actual archived-version upgrades are an explicit additional check: `--profile changed --suite upgrade --language node`. Supply reviewed `HARNESS_LEGACY_PACKAGE` and `HARNESS_UPGRADE_PACKAGE` archives and the offline dependency cache expected by `scripts/test-upgrade.mjs`. Changes to the upgrade implementation select this check automatically. The ordinary full baseline includes `engine-upgrade.test.mjs` and packaged lifecycle checks; it does not invent archived inputs or claim a real two-version upgrade without them. Live/paid agent end-to-end checks remain separately authorized and are never launched by this selector.

Existing task-required checks and final acceptance gates remain mandatory. For this selection-policy migration, run small selector contracts and smoke first, then one complete Python regression after edits and review fixes settle. Keep the full self-test unchanged. Do not use a fast subset as the evidence for a check named `harness-tests`.

## CI stages

PRs and non-main branch pushes calculate a plan from the merge base, then execute selected checks. Main, tag, release and manual runs use the full baseline. Python runs once on each of Linux, macOS and Windows, rather than once for each Node version (three complete Python jobs instead of nine). Native Node compatibility still covers Node 20/22/24 on applicable platforms. Windows symlink coverage remains mandatory in CI.

The workflow always starts, including prose-only changes. The final `required` job rejects failed/cancelled prerequisites and permits intentionally unselected jobs. Configure protected branches to require this aggregate check; local files cannot change GitHub branch protection. Superseded runs for the same PR/ref are cancelled. A plan artifact records selection; commands are recomputed from local rules on each OS, never executed from artifact-supplied command text.

The previous full Python run took 1189.057 seconds for 246 cases (12 skips). This is a historical baseline. See `specs/test-scoping/verification.md` for measured selector/smoke/migration timings; no universal duration is promised for foundational changes or large integration suites.
