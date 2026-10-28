# Version-file-driven npm publication

Status: APPROVED
Revision: 2
Approval: Developer approved revision 2 in chat on 2026-10-27; see .harness/evidence/npm-release/revision-2-approval.md. Revision 1 targeted 0.4.1, which was never published.
Tech-Spec-Revision: 0
Architecture-Revision: 0

This is distribution maintenance, not application implementation. package.json version is the single human-edited release value. The current release outcome is 0.4.2; ordinary commits never automatically increment it. Derived CLI/Python constants and lockfile root metadata are synchronized from that field. Protocol 1 and configuration schema 2 remain unchanged. The live npm latest dist-tag was 0.4.2 and main CI run 40557196890 succeeded across Linux, macOS and Windows when inspected on 2026-10-27. That run skipped publishing an already existing version; it does not prove which earlier run published it. Do not publish 0.4.1 or republish 0.4.2.

| Criterion | Observable contract |
| --- | --- |
| REL-001 | One source version, 0.4.2 now; synchronization is deterministic/idempotent, rejects invalid stable versions and malformed/missing markers before writes; --check detects drift. |
| REL-002 | Build, type checking and each Python CI job synchronize derived versions before tests; built and packaged CLI/Python versions agree. |
| REL-003 | Only a successful same-workflow required job on a push to this repository's main can authorize publishing. Publish checkout uses exactly github.sha; superseded main revisions are skipped. PR/release/manual events cannot publish. |
| REL-004 | Registry lookup skips an already existing version; network/auth/server/malformed responses fail. Missing package/invalid metadata and stable-version downgrade fail. Checks do not publish or install anything. |
| REL-005 | Publication uses GitHub-hosted Node 24, npm >=11.5.1, job-scoped OIDC, public registry and a built tarball. No npm token, auto-bump commit, runtime/schema change or branch-protection change. Concurrent publications are serialized. |
| REL-006 | Focused release-unit, native engine/version, Python protocol, build, pack and package smoke checks establish the release. Record actual publication/CI/account-setup outcomes separately; no local mock or dry-run can claim registry publication. |

The prior registry read recorded latest 0.3.1 before the 0.4.2 release. Current registry and hosted CI facts require fresh external evidence; a local smoke without real OpenSpec is partial evidence. Trusted publisher configuration requires npm package-owner access; local GitHub/source access does not establish that permission.
