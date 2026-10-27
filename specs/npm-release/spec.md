# Version-file-driven npm publication

Status: APPROVED
Revision: 1
Approval: Developer accepted the proposed main/green-CI/OIDC publication flow, instructed implementation and version increase, then explicitly confirmed "Да: версия из файла, сейчас 0.4.1" in chat on 2026-10-27.
Tech-Spec-Revision: 0
Architecture-Revision: 0

This is distribution maintenance, not application implementation. package.json version is the single human-edited release value. Prepare 0.4.1; ordinary commits never automatically increment it. Derived CLI/Python constants and lockfile root metadata are synchronized from that field. Protocol 1 and configuration schema 2 remain unchanged.

| Criterion | Observable contract |
| --- | --- |
| REL-001 | One source version, 0.4.1 now; synchronization is deterministic/idempotent, rejects invalid stable versions and malformed/missing markers before writes; --check detects drift. |
| REL-002 | Build, type checking and each Python CI job synchronize derived versions before tests; built and packaged CLI/Python versions agree. |
| REL-003 | Only a successful same-workflow required job on a push to this repository's main can authorize publishing. Publish checkout uses exactly github.sha; superseded main revisions are skipped. PR/release/manual events cannot publish. |
| REL-004 | Registry lookup skips an already existing version; network/auth/server/malformed responses fail. Missing package/invalid metadata and stable-version downgrade fail. Checks do not publish or install anything. |
| REL-005 | Publication uses GitHub-hosted Node 24, npm >=11.5.1, job-scoped OIDC, public registry and a built tarball. No npm token, auto-bump commit, runtime/schema change or branch-protection change. Concurrent publications are serialized. |
| REL-006 | Focused release-unit, native engine/version, Python protocol, build, pack and package smoke checks establish the release. Record actual publication/CI/account-setup outcomes separately; no local mock or dry-run can claim registry publication. |

Public registry read during discovery: specreceipt exists, latest 0.3.1, maintainer perfrico. Trusted publisher configuration requires npm package-owner access; local GitHub/source access does not establish that permission. Actual external account setup remains an explicit deployment prerequisite, not a fake local PASS.
