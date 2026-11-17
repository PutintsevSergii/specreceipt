# GitHub Copilot

Install the package, then select an agent:

```sh
specreceipt init --agent copilot
specreceipt init --agent copilot-ide
specreceipt init --agent codex,copilot
specreceipt init --agent codex,copilot-ide
```

Copilot IDE mode (including Rider) does not require the CLI. The wizard offers these same choices. OpenSpec, Strict and Engineering Pack are shared. Repeating init without selection flags retains the saved selection. To add a second agent, explicitly select the combined mode. Existing instructions and OpenSpec customization are preserved; conflicting managed content stops installation.

The short `.github/copilot-instructions.md` bridge points to shared `AGENTS.md` and task-specific guide sections. All 18 Engineering Skills remain in `.agents/skills`; none are copied into `.github/skills`. OpenSpec 2.1 installs the six official workflows into shared `.agents/skills/` for both Codex and Copilot; use `/openspec-propose` and other skill names instead of the removed `/opsx-*` prompts. Existing user files and legacy prompts are preserved. OpenSpec init runs with explicit `--scope project` in an empty staging directory with cloud generation disabled; no global skills, Actions workflows or cloud agent are installed. Installation needs Git and access to the official GitHub release skills.

In Rider, enable the GitHub Copilot plugin and sign in with an account authorized for this device. Check the response References for `.github/copilot-instructions.md`. Ask Copilot to load the relevant Engineering Skill explicitly if automatic `.agents/skills` discovery is unavailable in your plugin version. Restart the IDE after installing OpenSpec skills. Doctor validates files, not actual IDE loading.

For CLI use, install official stable GitHub Copilot CLI independently (`brew install --cask copilot-cli` on macOS, or an official supported alternative), then run `copilot login`. Complete the official OAuth flow yourself; never paste credentials into Harness configuration. Doctor does not spend model credits or inspect credential files. Successful login alone does not prove entitlement, available quota, or organization permission.

## Optional Python runner adapter

`specreceipt copilot-exec --context /absolute/project/.harness/dispatch/context.json --allow-tool 'write(/absolute/project/parser.mjs)' --timeout 120` is a thin role transport for the existing authorized Python runner. Configure the installed CLI's absolute path in `implement_argv` / `review_argv` only after reviewing the runner authorization and explicit per-role permission rules. Do not enable runner configuration automatically. Python creates the context, enforces readiness, checks effects, performs transitions and requires genuine developer approvals. The adapter calls the same versioned engine for readiness and never writes lifecycle state or grants approvals.

The transport probes the installed CLI, requires JSONL output and supported permission flags, preserves process exit codes, detects structured authentication/account errors, and terminates the process group on timeout/cancellation. It requires a successful final result record; assistant prose alone is not success. On unstructured startup errors, it reports process failure with bounded stderr rather than guessing an authentication diagnosis. CLI execution success is not task verification.

Only named command/file permission grants are accepted; no allow-all, yolo or automatic project-configuration trust flags are generated. CLI tool permissions are not an operating-system sandbox. Review local Copilot settings and commands before execution, use disposable projects for tests, and do not approve general interpreters as a substitute for a narrow command. Native Windows execution is not supported by the POSIX Python engine; use WSL.

## Sources and validation limits

- [GitHub CLI Skills locations](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)
- [JetBrains repository instructions](https://docs.github.com/en/copilot/how-tos/copilot-in-your-ide/customize-copilot/configure-custom-instructions/add-repository-instructions-in-your-ide)
- [GitHub CLI reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)
- [OpenSpec 2.1 release](https://github.com/Fission-AI/OpenSpec/releases/tag/v2.1.0); inspected official installed `dist/core/init.js` and `dist/core/skill-installer.js`.

Live consumer E2E must stop at planning and final developer approval until actual consent is provided. No cross-provider token equivalence is assumed.

Structured error categories follow [the official event schema](https://docs.github.com/en/copilot/how-tos/copilot-sdk/use-copilot-sdk/streaming-events); HTTP 401, 403 and 429 also produce actionable blocked results.
