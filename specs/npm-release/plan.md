# npm release plan

Status: APPROVED
Revision: 1
Approval: Developer approved the prior concrete publication flow and confirmed version-file behavior and release 0.4.1 in chat on 2026-10-27.
Tech-Spec-Revision: 0
Architecture-Revision: 0

1. Use package.json version, not another duplicate config. Add a stdlib Node release helper for synchronization, drift checks and read-only registry decisions. Update package scripts and lock metadata. Review malformed inputs/markers and API failures with tiny fixtures and injected HTTP responses; no real publish in tests.
2. Synchronize before TypeScript compilation and before the independent Python CI job. Preserve protocol/configuration versions, public runtime behavior and all existing checks.
3. Extend the existing verify.yml with a publication job depending on required. Restrict to push/main/own repository, pin checkout to github.sha, check that main still points to that SHA, serialize publication, skip existing versions, build and pack before a minimal OIDC publication step. Reuse the original trusted workflow, not a privileged workflow_run chain or PR-supplied artifact commands. Trusted publisher filename is verify.yml.
4. Add release contracts to the existing engine-upgrade Node suite (already covered by native-node), update impact rules for release tooling, document exact npm owner setup and update changelog. Build 0.4.1 and refresh generated kit/hash assets.
5. Run targeted checks appropriate to this release: native-typecheck, native-node (including new release contracts), harness-validate, three Python protocol tests, version consistency, actual pack/install/version/contract smoke. The prior complete 280-case integration run remains historical; do not rerun it for version-only engine constants or claim it is current evidence for this release.
6. Perform separate implementation/security review; record real local check evidence and account/hosted CI limitations. Commit and push the ready release configuration. Observe the resulting workflow if accessible; report publishing success only from actual registry/CI evidence.

Requirements map REL-001/004 to release contracts; REL-002 to type/native/protocol/packed checks; REL-003/005 to exact workflow guard inspection and contracts; REL-006 to recorded local checks and actual external evidence. Required executable checks are harness-validate, native-typecheck and native-node; manual package/protocol evidence supplements them. No optional live/paid agent tests are added.

The runtime's narrow harness scope excludes package.json, package-lock.json, CHANGELOG.md and new release-helper paths. Prepare these explicitly authorized distribution configuration files as a separate recorded pre-start batch. REL-001 models synchronization consumers, build scripts, CI, tests, generated assets and guides; the combined review covers both batches. Do not widen the runtime whitelist or hide the configuration changes from review.

Source basis: [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/) specifies job OIDC permissions, compatible CLI/runtime and package-owner setup; [npm publish](https://docs.npmjs.com/cli/commands/npm-publish/) defines immutable versions. Existing build-assets assertions already require synchronized TypeScript/Python/package versions. Public web documentation is external contract evidence; local source investigation is agent-attested CODE_ONLY. No repository source was sent to research services.
