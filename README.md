# SpecReceipt

SpecReceipt is a repository-local engineering workflow toolkit for coding agents. It installs shared Skills, project instructions, templates and a Python lifecycle engine. A TypeScript CLI handles installation, diagnostics and upgrades. The Python engine owns task state, readiness, approvals, checks and evidence.

`specreceipt` is distributed under the [Unlicense](LICENSE). Check the [npm package page](https://www.npmjs.com/package/specreceipt) for published versions. The release version is defined in `package.json`; see [npm automation](docs/NPM_RELEASE.md).

## Requirements

- Node.js 20.19 through 24 and npm.
- Python 3.11 or newer.
- Windows x64 (Windows PowerShell 5.1 or Command Prompt), macOS, or Linux. WSL and Bash are not required on Windows.
- Git for merging user changes during upgrades.
- OpenSpec 1.14.3 for `init`; new projects use source navigation without CodeGraph or Graphify. Explicitly required providers remain mandatory.

## Native Windows setup

From a source checkout, use existing native Python 3.11+ or set `HARNESS_PYTHON` to its executable path, then run `.\harness.cmd validate`. The launcher also recognizes `py` and previously provisioned user-local Python. Microsoft Store execution aliases are not treated as installed runtimes.

To adopt the kit into another project and explicitly provision missing prerequisites:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 C:\projects\my-project
```

The execution-policy setting applies only to that process. No WSL, Bash, administrator access, or machine-wide policy change is required. Downloads need network access. Native prerequisites live under `%LOCALAPPDATA%\harness\runtime`, overridden by `HARNESS_RUNTIME_DIR`. Python, Node/npm and required navigation tools remain dependencies; unavailable downloads or incompatible tools report failure. Existing npm installations use `specreceipt.cmd` from either shell. See [native verification](specs/windows-native/verification.md) for current validation limits.

## Fast feedback and full verification

For a focused Windows development check, forward an explicit argument array to the native Python launcher:

```powershell
& .\scripts\python.ps1 -CommandArgs @('-B', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_performance.py', '-v')
```

On Linux/macOS use `python3 -B -m unittest discover -s tests -p test_performance.py -v`. Focused checks provide partial feedback. Final acceptance still requires `harness verify TASK-ID` and the complete self-test; no quick subset replaces those gates.

During a self-test, `.harness/progress/self-test.json` exposes completed/total counts, the active test, elapsed time and the slowest cases. Live status includes this last observation. It is not process-liveness proof or execution evidence. Raw child output stays private until the final redacted log is recorded. Lifecycle operations update derived reports once at their final boundary; their durable state/events and fresh gate checks remain immediate.

Windows bootstrap pins uv 0.13.5 and verifies the official archive SHA-256 before installing its executable. It tries GitHub Releases and the official Astral release mirror. Managed Python installation disables user-bin shortcuts and registry registration. If both sources are inaccessible, setup reports failure and supports retrying with an existing native uv/Python installation.

The complete Python self-test has a 30-minute budget. On Windows without symlink privilege, real symlink fixtures explicitly report skips for error 1314; other errors still fail. Windows CI sets `HARNESS_REQUIRE_SYMLINK_TESTS=1`, which requires those tests to execute. Unprivileged junction-boundary regressions run locally.

## Install

After publication, install the latest published version in a separate tools directory:

```sh
npm install --prefix /path/to/tools --ignore-scripts specreceipt
```

Before npm publication, use the reviewed local archive instead (replace `VERSION` with the version from `package.json`):

```sh
npm install --prefix /path/to/tools --ignore-scripts /path/to/specreceipt-VERSION.tgz
npm install --prefix /path/to/project/.harness/tools/openspec --ignore-scripts @fission-ai/openspec@1.14.3
cd /path/to/project
/path/to/tools/node_modules/.bin/specreceipt init --target /path/to/project --dry-run
/path/to/tools/node_modules/.bin/specreceipt init --target /path/to/project --agent codex --yes
/path/to/tools/node_modules/.bin/specreceipt doctor --target /path/to/project --json
```

`init` previews its changes with `--dry-run`. Noninteractive installation needs `--yes`. It stages official OpenSpec generation and refuses incompatible or conflicting project files. Select `copilot`, `copilot-ide`, `codex,copilot`, or `codex,copilot-ide` with `--agent` as needed. Copilot CLI authentication and tool permissions are configured separately. No agent is automatically authorized to change an application.

After installation, the CLI exposes the Python operations, including `resume`, `status`, `next`, `readiness`, `task`, `verify`, `review`, `skills`, and `tools`. For navigation tooling, run `specreceipt tools update --apply --only codegraph graphify` in the project, then `specreceipt indexes ensure`. These tools have their own runtime and network requirements.

## Workflow and limits

A developer approves a current specification and plan before implementation. Task readiness, configured verification, evidence, review and a separate final developer approval govern completion. Before asking for final `DONE`, run `specreceipt approval-package TASK-ID --format markdown` and present its linked files, result, limits and exact approval effect. A blocked package means the decision is not ready. `doctor` checks installation health; it does not prove application readiness, external agent authentication, protected CI, or a safe public release. Local files and scripts are editable by their owners.

For an approved task, an optional Codex CLI adapter can let the bounded Python runner perform implementation and a separate review, then stop at the final developer decision. After reviewing the exact task IDs, local tool access and a substantive approval reference, run `specreceipt codex-runner-preview --task TASK-001 --reference docs/approvals/runner.md --target /path/to/project`. Review the emitted configuration and save it as `<project>/.harness/runner.json`; the preview does not enable execution. Run `specreceipt run --max-steps 20 --max-seconds 3600 --target /path/to/project` only in the approved project. The adapter requires the local Codex CLI, performs an execution preflight, uses a workspace-write sandbox and cannot grant its own approvals. See [bounded continuation](docs/HARNESS.md#bounded-continuation-and-command-adapters).

The project keeps its own instructions and OpenSpec material. The package uses a managed section in `AGENTS.md` and includes 18 optional role Skills. The section's legacy `my-ai-harness` comment markers remain for safe upgrades; the command is `specreceipt`. See the [operating guide](assets/kit/docs/HARNESS.md) and [v0.3 contract](assets/kit/docs/V03.md).

## Upgrade an existing installation

Install the new tarball in a separate tools directory. Run `specreceipt upgrade --target /path/to/project --dry-run`, inspect the changes, then run without `--dry-run`. Existing 0.3.0 installations use their recorded baselines. For customized v0.1.0 or v0.2.0 installations, provide `--baseline /path/to/original/node_modules/my-ai-harness`. The package checks the baseline identity and preserves nonoverlapping user edits; conflicts block the upgrade. See [v0.3 contract](assets/kit/docs/V03.md). Keep a backup before changing an important repository.

## Build and verify

```sh
npm ci
npm run check
npm run build
npm test
python3 -B harness self-test
npm run test:package
```

The package test installs a packed archive in a temporary consumer. Integration coverage with the real OpenSpec CLI requires `HARNESS_REAL_OPENSPEC` to name the installed 1.14.3 executable. Check the [GitHub Actions runs](https://github.com/PutintsevSergii/specreceipt/actions) for hosted verification results.

## Project information

- [Release notes](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)
- [Security reports](SECURITY.md)
- [License](LICENSE)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

The [public repository](https://github.com/PutintsevSergii/specreceipt) contains the source. Check the [npm package page](https://www.npmjs.com/package/specreceipt) for published versions.
