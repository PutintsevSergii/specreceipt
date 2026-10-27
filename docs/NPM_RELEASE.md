# npm releases from main

Edit only `package.json` → `version` when preparing a stable release. Ordinary commits do not increment it. Run `npm run version:sync`, then commit the canonical file and derived `package-lock.json`, `src/core.ts`, `src/engine.ts` and `harnesslib/protocol.py` together. `npm run check` and `npm run build` synchronize automatically; `npm run version:check` is read-only and rejects drift. Protocol and configuration schema versions are separate compatibility contracts.

## Automatic publication

The existing `Verify SpecReceipt` workflow verifies each main commit. Its `publish` job depends on the final `required` gate, accepts only this repository's push/main event, checks out exactly the verified SHA and skips it if main has advanced. It reads the version from package.json and the public npm registry. An existing version is skipped; a new version must exceed npm latest. Network, permissions, malformed metadata and server failures stop the job rather than permitting a publish.

The job uses GitHub-hosted Node 24 and checks npm >=11.5.1. It builds and validates a tarball, then publishes that tarball through OIDC with public access/provenance. Write OIDC permission exists only on the publication job. There is no npm token, auto-version commit or PR publication. Publications are serialized. A cancelled/failed publish can be retried by rerunning the original main push workflow; the registry lookup makes an already completed publication a no-op. Source files changing during CI synchronization are derived version outputs, not commits made by the pipeline.

## One-time npm package-owner configuration

For `specreceipt`, open npm package Settings → Trusted publishing and add GitHub Actions:

- Organization/user: `PutintsevSergii`
- Repository: `specreceipt`
- Workflow filename: `verify.yml` (filename only)
- Environment: leave empty; this workflow uses no GitHub Environment
- Allowed actions: explicitly enable direct `npm publish` (the default stage-only permission is insufficient)

This requires an npm package owner. The public registry currently lists `perfrico`; GitHub repository access alone cannot configure npm. Never paste an npm token into this repository or chat. npm does not validate a saved publisher until publication; the first successful publish must occur before the new publisher configuration expires. See [npm's current trusted-publishing instructions](https://docs.npmjs.com/trusted-publishers/).

The configured package must already exist; `specreceipt` does. After setup, rerun the original successful main workflow if its first publish failed authentication. Do not use `npm whoami` as an OIDC readiness check; use the actual publish result. Inspect npm's package version page and the GitHub publish job before claiming deployment succeeded.

## Local verification

Use the release contracts in `tests-node/engine-upgrade.test.mjs`, type checking, the native engine tests, Python protocol tests and actual packed installation smoke. No registry write is performed by local release tests. The earlier complete Python regression remains historical when only version constants/distribution configuration change; record scoped checks for the release rather than calling that old run fresh verification.
