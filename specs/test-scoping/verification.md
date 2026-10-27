# Scoped test execution verification

Status: PASS

Developer approved spec/plan revision 1 on 2026-10-27: "Утверждаю план, реализуй". Developer also requested push to the primary branch when ready. Local required verification is complete; hosted CI execution is not claimed.

## Acceptance evidence

| Criterion | Evidence and current result |
| --- | --- |
| TST-001 | Required explicit profile; smoke/manual/scoped/full labels and no-profile error covered. Smoke: 5 executed / 0 skips / PASS, 10.922 seconds including process startup. |
| TST-002 | Tiny Git repositories cover staged/unstaged/untracked paths, Unicode/spaces, rename/delete, committed changes, diverged target merge base, missing base and option rejection. Unit suite PASS. |
| TST-003 | Manifest audits every current Python/TypeScript source boundary. Narrow, union, transitive fixture, unknown/foundation fallback, missing/new test and malformed rules PASS. Manual/smoke lists stay exact. |
| TST-004 | Dry-run executes nothing; CI plan commands are recomputed; nonzero exits propagate; zero-case/all-skipped selections cannot claim coverage. Actual changed-profile protocol run: 3 executed / 0 skips / PASS in 2.968 seconds. |
| TST-005 | YAML and four embedded Python blocks parse. CI retains Node 20/22/24 and strict Windows symlinks, moves Python to one job per OS, always starts planning/aggregate jobs and rejects failed/cancelled prerequisites. Hosted execution NOT_RUN locally. |
| TST-006 | Complete required migration regression PASS: 280 cases / 12 skips / zero failures or errors / 1157.380 seconds. Original 246 cases retained, plus 34 selector cases. Structural validation PASS. Utility source and generated assets unchanged. |

Local scratch evidence: .harness/test-selection-unit.log, test-selection-smoke.log, test-selection-protocol-run.log, test-selection-live-plan.json and test-selection-adopted-fixture.log. A real adopted-kit fixture test passed with an external writable temporary directory. These logs are not CI attestation.

## Separate diff review before final regression

Reviewer: Codex, separate same-session pass; not independent attestation.

Resolved findings:

- R1 / medium / tests/run_scoped.py changed_paths: a nested directory can inherit its parent's Git repository and select unrelated paths (TST-002). Reproduced by the new missing-repository test with TEMP under the source checkout. Require exact repository-root identity; regression PASS.
- R2 / medium / tests/run_scoped.py Python command: unittest returns zero for an empty or all-skipped suite (TST-004). Reject zero loaded/executed cases and report discovered/skipped/executed counts; both negative regressions PASS.
- R3 / low / tests/run_scoped.py select: manual/smoke selections unnecessarily expanded fixture consumers (TST-001). Restrict expansion to automatic changed selection; exact-selection regression PASS.

Reviewed mappings, argument arrays, native applicability, CI merge base, artifact command rejection, fallback labels, retained assertions and the combined diff including CONTRIBUTING.md. Actual two-archive upgrades remain explicit with reviewed input archives; the ordinary baseline does not claim this optional integration ran. Paid/live agent checks are never launched.

## Execution mapping and limitations

The runtime harness-scope whitelist excludes CONTRIBUTING.md and specs/ implementation scope. The approved contributor edit was a separate pre-start documentation batch included in the combined review. TST-001 tracks tests/, CI and guides; feature records remain metadata. No runtime whitelist or verification rule changed. Application readiness remains blocked for placeholder application documents; this is approved test-infrastructure maintenance.

Research sources are in plan.md; no repository source was sent externally. Investigation is CODE_ONLY and agent-attested with no required-source gaps. Both external indexes worked; Graphify navigation was truncated and included generated copies, so source inspection supports the actual claims. Sandbox defaults made TEMP inaccessible; initial checks used the other writable workspace root outside the source kit, without utility or OS policy changes.

Historical baseline 55bba3ba-ddf3-4390-9312-4ac203bf8591: 246 cases / 12 skips / 1189.057 seconds. This is not current evidence. Full-suite acceleration was not the goal; routine edits now have explicit scoped entry points.

## Final required execution

Evidence: .harness/evidence/fe3f280e-871f-45fc-a4b2-07e3a419a93f.json. Every required check (harness-tests and harness-validate) PASS; all six acceptance mappings PASS. Full self-test progress completed 280/280 with 12 explicit skips. Detailed redacted logs are linked from the evidence record. No source/assertion/timeout changes were made between the partial attempts and the final successful run.

Two partial attempts remain FAIL evidence: 1cf73157-8725-41a9-9a9b-0afac86ceb0c was stopped after restricted-context slowdown (same adopted fixture 4.215 seconds restricted versus 1.170 native); d128464f-be74-4da8-a9d6-7bc21b0e39f0 was stopped after the long TEMP prefix caused a Windows MAX_PATH error in replan archive creation. The same isolated replan case PASS with ordinary shorter LOCALAPPDATA/Temp/harness-tests in 15.979 seconds. The final complete run uses that corrected native environment. Neither partial attempt is treated as PASS.

The actual extracted CI planning step also executed locally with no tests: it generated Python/Node job flags and a conservative full plan for this selector-policy change. Hosted multi-OS execution and external branch protection remain unverified locally. No package publication, version bump or paid agent run is included.
