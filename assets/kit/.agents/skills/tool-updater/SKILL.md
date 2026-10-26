---
name: tool-updater
description: Check and update the harness-managed CodeGraph, Graphify and optional OpenSpec toolchain, with compatibility checks and a persisted update report.
---

# Tool updater

For command details, consult [Managed tool updates](../../../docs/HARNESS.md). Use this skill when asked to check or update tools used by harness.

1. Run `python3 scripts/update-tools.py` from the project root for a read-only plan. Add `--check-latest` when network access is authorized to compare public registry releases with adapter-supported versions. No project content is sent to registries.
2. Explain blocked tools and missing prerequisites. The managed set is CodeGraph, Graphify and OpenSpec. Python, Node, npm, uv, agent CLIs, corporate MCP servers and project dependencies remain under their owner's management; never infer authorization to upgrade those.
3. For an authorized update, run `python3 scripts/update-tools.py --apply`. Add `--include-optional` only when installing optional OpenSpec is intended; use `--only codegraph graphify openspec` to select tools. The [script](../../../scripts/update-tools.py) installs pinned adapter-supported versions under `.harness/tools/`; it does not silently downgrade newer installations.
4. If a newer upstream release exists, report that it requires compatibility work. To support it, inspect official release documentation, update the adapter contract and version pin, test the real new CLI in isolation and run harness checks before applying. Merely checking the registry does not establish compatibility. Never claim that the newest upstream version was installed when a supported pin was used.
5. Inspect `.harness/tool-updates.json`, per-tool results, refreshed indexes and both validation checks. A partial failure is not success. An interrupted `active_tool` requires checking remaining processes and partial installation effects before clearing the marker and explicitly retrying. Do not blindly rerun failed installs.
6. Report installed versions, failures, skipped optional tools and verification limitations. Record an observable note and evaluate `./harness checkpoint --if-needed` after changes.

Preserve corporate instructions and skills. Respect host execution and network permissions. Harness source upgrades are reviewed source changes, not package-manager updates. An update report is evidence of executed checks, not independent attestation.
