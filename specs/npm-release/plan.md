# npm release plan

Status: APPROVED
Revision: 2
Approval: Developer approved revision 2 in chat on 2026-10-27; see .harness/evidence/npm-release/revision-2-approval.md. The earlier 0.4.1 plan is historical and was not released.
Tech-Spec-Revision: 0
Architecture-Revision: 0

1. Use package.json version, not another duplicate config. Add a stdlib Node release helper for synchronization, drift checks and read-only registry decisions. Update package scripts and lock metadata. Review malformed inputs/markers and API failures with tiny fixtures and injected HTTP responses; no real publish in tests.
2. Synchronize before TypeScript compilation and before the independent Python CI job. Preserve protocol/configuration versions, public runtime behavior and all existing checks.
3. Extend the existing verify.yml with a publication job depending on required. Restrict to push/main/own repository, pin checkout to github.sha, check that main still points to that SHA, serialize publication, skip existing versions, build and pack before a minimal OIDC publication step. Reuse the original trusted workflow, not a privileged workflow_run chain or PR-supplied artifact commands. Trusted publisher filename is verify.yml.
4. Inspect the implemented release contracts, impact rules, documentation and generated kit assets for the observed 0.4.2 version. Fix only a reproduced discrepancy under the approved scope; a material scope change requires revised approval.
5. Run the task's required checks (harness-validate, native-typecheck, native-node), version consistency, build, offline pack/install/version/contract smoke, and actual installed-package evidence where available. Read live npm dist-tags and the exact hosted CI run. A smoke without real OpenSpec is partial; a skipped publish step cannot prove publication by that run.
6. Perform separate current diff/contract review and obtain final developer approval after verification before DONE. Do not publish 0.4.1 or republish 0.4.2. A later code correction needs a separately reviewed delivery action.

Requirements map REL-001/004 to release contracts; REL-002 to type/native/protocol/packed checks; REL-003/005 to exact workflow guard inspection and contracts; REL-006 to recorded local checks and actual external evidence. Required executable checks are harness-validate, native-typecheck and native-node; manual package/protocol evidence supplements them. No optional live/paid agent tests are added.

The original implementation batch included package.json, package-lock.json, CHANGELOG.md, release helper, CI, tests, generated assets and guides. Revision 2 closes the release against current evidence and expects no new source edit unless inspection finds a concrete defect. Do not widen the runtime whitelist or hide any subsequent configuration changes from review.

Source basis: [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/) specifies job OIDC permissions, compatible CLI/runtime and package-owner setup; [npm publish](https://docs.npmjs.com/cli/commands/npm-publish/) defines immutable versions. Existing build-assets assertions already require synchronized TypeScript/Python/package versions. Current registry and CI observations must be recorded separately from the historical 0.4.1 plan.
