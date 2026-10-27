# Release 0.4.1 and Actions repair verification

Status: PASS (local engineering checks; hosted CI pending)

Developer approved package.json-driven 0.4.1 publication and instructed investigation/repair of actual Actions failures without unnecessary test runs. No full local Python self-test was rerun for this slice.

## Local evidence

- Release helper/workflow contracts: 8 PASS; Windows alias protocol regression also PASS (9 focused cases together).
- Selector contracts: 35 PASS in 3.400 seconds, including UTF-8 subprocess configuration.
- Exact failing Skill-reader test with UTF-8 mode disabled: PASS in 0.586 seconds after explicit UTF-8 read.
- Fresh checkout without state: generic init followed by structural validate PASS; no self-tests in this smoke.
- Actual existing OpenSpec Windows scenario with lowercase TEMP aliases: 1 PASS in 62.590 seconds.
- Actual tarball/offline consumer smoke: 0.4.1, 147 curated files, CLI version and packaged Python contract PASS, protocol 1, zero external downloads.
- TypeScript and workflow script parsing PASS; read-only npm registry gate requests publication of new 0.4.1 above current latest 0.3.1.

Evidence logs are in .harness/npm-release-unit.log, ci-identity-release-tests.log, ci-selector-focused.log, ci-skill-reader.log, ci-fresh-checkout.log, ci-windows-openspec-focused.log and npm-release-package-smoke.json. These are local observations, not hosted CI or npm publication proof.

## Actual hosted failures

See docs/CI_FAILURES_2026-10-27.md and GitHub run 40462024172 (ee68c40). The Linux/macOS suites themselves passed all 280 cases; validation then failed on missing state. Windows Python had one locale decoding error; Windows Node had repeated staged-engine identity mismatches. New code initializes CI state, forces UTF-8 for scoped Python and compares native physical directory identities, while retaining version/status/content guards.

A first scoped native-node verification exposed one remaining test assertion using raw TEMP spelling after the production boundary was fixed (35 pass, 1 fail, 2 platform skips). The fixture now uses fs.realpathSync.native; its exact failing case PASS with lowercase TEMP (26.375 seconds). No assertions were removed: canonical directory identity is the intended contract, and a separate real Python regression still exercises both input casing aliases. Required scoped checks are being repeated on this corrected fixture.

## Review and external state

Separate same-session implementation/security review covers the combined distribution configuration batch and modeled consumers. Existing developer approval authorizes release configuration; the exact helper refinement is recognized with an explicitly agent-attested configuration review, not a claim of new human approval or widened runtime write scope. Runtime scope whitelist was not changed.

The publish job depends on required, limits execution to own push/main, checks the verified SHA against current main, serializes publication, rejects malformed/API-error/downgrade metadata, builds a validated tarball, and uses only job-scoped OIDC. Protocol 1 and configuration schema 2 are unchanged. No persistent npm token is introduced.

Developer chose to configure npm Trusted Publisher independently. Required settings: PutintsevSergii / specreceipt / verify.yml, no environment, allow direct npm publish. The browser was not signed in; no account security setting was changed by the agent. Hosted CI for the new patch and actual npm publication remain NOT_RUN until the commit is pushed and the services report results.

## Final scoped local result

Delivery-only documentation follow-up: README install examples now use the latest published package or a VERSION placeholder, so future releases only edit package.json. This wording changed after local scoped code verification; no runtime, test, build or CI code changed after that PASS. Local evidence is for the frozen implementation; the upcoming hosted workflow verifies the actual commit including README. Do not rerun engine tests just for this wording or claim the old local fingerprint covers it.

.harness/evidence/9c2bf02d-674f-489c-a51d-716d3fc1e8b7.json PASS: harness-validate, native-typecheck and native-node. Node: 38 cases, 36 PASS, 2 explicit platform skips, zero failures; 93.533 seconds. All six declared acceptance mappings PASS. The actual OpenSpec case and offline tarball smoke are additional evidence above. The prior failed scoped attempt f0f476f9 is retained, not rewritten as PASS.

Same-session separate implementation/security review completed after the fixture correction, with no open findings. Hosted cross-platform confirmation and registry publication are still pending the push; npm Trusted Publisher configuration is explicitly the developer's own action.
