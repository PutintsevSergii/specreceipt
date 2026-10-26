# SpecReceipt

SpecReceipt is a repository-local engineering workflow toolkit for coding agents. It installs shared Skills, project instructions, templates and a Python lifecycle engine. A TypeScript CLI handles installation, diagnostics and upgrades. The Python engine owns task state, readiness, approvals, checks and evidence.

**Unpublished npm candidate:** `specreceipt@0.3.1` is prepared under the [Unlicense](LICENSE). The npm package remains marked private pending publication review. Public npm installation has not yet been verified.

## Requirements

- Node.js 20.19 through 24 and npm.
- Python 3.11 or newer.
- macOS or Linux; WSL is the supported route on Windows. Native Windows engine execution is unsupported.
- Git for merging user changes during upgrades.
- OpenSpec 1.14.3 for `init`; CodeGraph and Graphify are installed separately when navigation is needed.

## Install a local archive

The example uses the reviewed tarball, not a registry package:

```sh
npm install --prefix /path/to/tools --ignore-scripts /path/to/specreceipt-0.3.1.tgz
npm install --prefix /path/to/project/.harness/tools/openspec --ignore-scripts @fission-ai/openspec@1.14.3
cd /path/to/project
/path/to/tools/node_modules/.bin/specreceipt init --target /path/to/project --dry-run
/path/to/tools/node_modules/.bin/specreceipt init --target /path/to/project --agent codex --yes
/path/to/tools/node_modules/.bin/specreceipt doctor --target /path/to/project --json
```

`init` previews its changes with `--dry-run`. Noninteractive installation needs `--yes`. It stages official OpenSpec generation and refuses incompatible or conflicting project files. Select `copilot`, `copilot-ide`, `codex,copilot`, or `codex,copilot-ide` with `--agent` as needed. Copilot CLI authentication and tool permissions are configured separately. No agent is automatically authorized to change an application.

After installation, the CLI exposes the Python operations, including `resume`, `status`, `next`, `readiness`, `task`, `verify`, `review`, `skills`, and `tools`. For navigation tooling, run `specreceipt tools update --apply --only codegraph graphify` in the project, then `specreceipt indexes ensure`. These tools have their own runtime and network requirements.

## Workflow and limits

A developer approves a current specification and plan before implementation. Task readiness, configured verification, evidence, review and a separate final developer approval govern completion. `doctor` checks installation health; it does not prove application readiness, external agent authentication, protected CI, or a safe public release. Local files and scripts are editable by their owners.

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

This source is a release candidate. The [public repository](https://github.com/PutintsevSergii/specreceipt) is available; npm publication is pending a separate decision.
