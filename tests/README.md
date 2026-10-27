# Test entry points in an adopted Python kit

Run `python3 -B tests/run_scoped.py --profile smoke` for a short contract check or `--profile changed --language python --dry-run` to inspect affected tests in a repository-root installation. Omit `--dry-run` to execute. On Windows use native `python` or `scripts/python.ps1` instead of `python3`. Select `--language python` when the kit has no npm/Node project; the Node/package baseline belongs to the SpecReceipt source repository.

`--base REF` includes committed changes since the Git merge base plus staged, unstaged and untracked paths. Missing Git history, malformed rules and unmapped test inventory fail visibly. Shared fixtures expand coverage. Unknown paths select the full baseline. `--suite py:test_protocol` explicitly selects a module with MANUAL coverage; it does not assert complete impact coverage.

`python3 -B harness self-test` remains the complete Python regression and the final required check when a task requires it. `SCOPED`/`MANUAL` PASS and `NO_RUNTIME_TESTS` do not replace final acceptance. Test runner summaries report actual case and skip counts. The selector does not change workflow gates, install tools or launch paid agents.
