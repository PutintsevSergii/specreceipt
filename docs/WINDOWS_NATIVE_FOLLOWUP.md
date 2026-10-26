# Windows verification and bootstrap follow-up

Status: APPROVED
Revision: 2
Approval: Developer instructed in chat: "разработай план и делай", after the four recommendations on timeout, capability-aware link tests, bootstrap fallback and cross-platform verification.
Tech-Spec-Revision: 0
Architecture-Revision: 0

This supplements approved revision 1 in docs/WINDOWS_NATIVE_PLAN.md. WIN-001 through WIN-007 and the no-admin/no-WSL contract remain applicable.

1. Keep all 232 currently discovered Python tests and their assertions. Increase the full-suite budget to 1800 seconds in this checkout and packaged installation seeds; record actual elapsed time. This changes only execution budget, never a passing threshold.
2. Make real file-symlink tests capability-aware: skip only Windows privilege error 1314 and explicitly label the reason. Propagate all other errors. Windows CI sets HARNESS_REQUIRE_SYMLINK_TESTS=1 so the same missing privilege fails instead of skipping. Retain unprivileged real-junction boundary tests and add regressions proving the capability helper cannot silently hide other failures.
3. Use a shared native PowerShell uv downloader from Python and the no-Python launcher. Pin uv 0.13.5, Windows x64, and the official archive SHA-256. Try fixed official GitHub and Astral release origins; never execute an unverified archive, arbitrary project URL or installer script. Refuse overwriting existing managed binaries. Include helper in adoption and package assets.
4. Test checksum failure, unsafe archive paths, fallback behavior, missing-Python read-only behavior, and real fresh user-local bootstrap with Python/uv removed from child PATH. Report this as an isolated bootstrap test, not a whole clean-OS attestation.
5. Rebuild assets; run full self-test, native Node regressions, type checking, real indexes, package smoke and required task verification. Inspect the final diff separately, bind the exact verification evidence and checkpoint. Existing CI matrix covers Windows/Linux/macOS; executing hosted CI requires an authorized remote change and available runner. Do not claim it ran locally.

Scope additionally includes scripts/uv.ps1 and tests/platform_support.py. No system policy changes, privilege elevation requirement, dependency-family change, commit, push or publication is authorized by this follow-up.
