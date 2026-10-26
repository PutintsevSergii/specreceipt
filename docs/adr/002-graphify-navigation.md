# ADR 002: Optional Graphify navigation

Status: Accepted for harness maintenance, 2026-10-23
Authorization: User requested CodeGraph/Graphify-first tool navigation and automatic install/index checks on adoption. This does not authorize LLM semantic extraction or source transmission.

## Decision

The host has Graphify CLI 0.9.27 from the `graphifyy` package, with an observed `update <path> --force --no-cluster` command that builds a local graph without LLM calls and a `query --budget N` command. Adoption checks for the CLI and installs the pinned package through `uv` when absent. It then indexes the target project. A repo-local state file binds the index to the input snapshot and CLI version; stale input triggers a rebuild. Query output is capped and remains navigation evidence only. The existing `local-python-ast` provider and targeted source search remain fallbacks.

The package metadata in the installed environment identifies [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) as the upstream repository. The installed CLI interface and isolated-fixture behavior were checked locally. CodeGraph integration was subsequently added under ADR 003 after its CLI variant was identified.

## Limits and recovery

Automatic installation requires `uv` and package-network access. If it fails, adoption reports BLOCKED and preserves any files already copied. `./harness graphify ensure` retries. The index lives in `graphify-out/` and is excluded from Git and the harness's own input inventory. Graphify's source selection can differ from the harness inventory, so a fresh index is still a navigation aid, not complete coverage or verification proof. No hook is installed and no Graphify semantic extraction is run.
