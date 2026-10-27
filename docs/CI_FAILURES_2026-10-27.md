# Actions failure investigation: 2026-10-27

Observed run: [40462024172](https://github.com/PutintsevSergii/specreceipt/actions/runs/40462024172), commit ee68c40. Primary evidence is actual GitHub Actions job logs, not local test assumptions. The earlier bb626e3 run also failed in Windows engine installation.

## Three independent root causes

1. **Fresh checkout state missing.** Linux job 122048658089 completed all 280 Python tests in 89.477 seconds with zero failures (10 explicit skips), then `harness validate` failed because `.harness/state.json` does not exist in a checkout. macOS job 122048658056 likewise passed all 280 cases in 59.803 seconds before the same missing-state error. Fix: initialize repository-local generic state before the selected Python checks. Do not commit machine state or remove structural validation.
2. **Windows locale-sensitive test input.** Windows Python job 122048658130 reached all 280 cases and reported one error: test_skill_links_resolve used default-code-page `Path.read_text()` on UTF-8 skills (UnicodeDecodeError, byte 0x9d). Fix: explicit UTF-8 for that reader; scoped Python subprocesses use -X utf8 plus PYTHONUTF8/PYTHONIOENCODING, preserving the original Windows self-test launch contract.
3. **Windows physical directory identity compared as raw text.** Windows Node job 122048658147 failed repeatedly with Engine/protocol/target mismatch while installing a staged engine. Node fs.realpathSync can preserve input drive/directory case, whereas Python Path.resolve returns native canonical case. Local minimal reproduction: lowercase drive and uppercase directory aliases both failed before the fix, although Python reported the same physical directory. fs.realpathSync.native exposes the difference. Fix: compare canonical native directory identities for response target/cwd/engineRoot; protocol/version/exit-code and installed-content guards remain unchanged. Regression invokes the real Python protocol through both aliases.

## Bounded verification

Do not repeat a full local regression simply to rediscover the known failures. Use: one real Windows alias protocol regression, the exact UTF-8 Skill-reader case with UTF-8 mode disabled, a fresh-checkout initialization/validation smoke, selector contracts and relevant native engine checks. The release guard unit tests remain part of the ongoing 0.4.1 slice. Hosted CI after the fix is the cross-platform confirmation; record its real result and do not claim it has passed from local tests alone.
