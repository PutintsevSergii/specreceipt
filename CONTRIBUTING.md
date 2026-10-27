# Contributing

Open an issue describing the behavior and a small reproducible case before a large change. Keep changes scoped and update affected documentation and tests. Use `python3 -B tests/run_scoped.py --profile changed --dry-run` to inspect the affected checks, then omit `--dry-run` to execute them. On Windows use native Python or `scripts/python.ps1 -B tests/run_scoped.py --profile changed`. Use `--base REF` to include committed changes relative to their merge base, in addition to staged, unstaged and untracked changes.

Do not run the entire integration suite after every edit. `--profile smoke` gives a short contract check; `--profile changed` selects affected suites and shared-fixture consumers. Unknown or foundational changes deliberately expand coverage. A scoped PASS is not complete acceptance. Run `python3 -B harness self-test` once for final acceptance when required by the approved task, and run package/upgrade checks for those boundaries. See [the testing guide](docs/TESTING.md) for selection rules, prerequisites and CI stages. No new dependency installation is needed for selection or Python tests; install the existing Node dependencies only for Node/build/package checks.

The project uses explicit requirements, plan approval, verification evidence, review and final approval for its own task lifecycle. A pull request does not by itself grant an agent permission to act in a downstream repository.

Contributions intended for inclusion must be your own work or material you have the right to release under the Unlicense. By submitting a contribution for inclusion, you agree to release your contribution under the project's [Unlicense](LICENSE). Do not submit secrets or material you cannot redistribute.
