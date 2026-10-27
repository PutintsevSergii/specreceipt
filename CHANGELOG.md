# Changelog

## 0.4.1

- Select scoped developer tests and separate Python regressions from Node-version CI jobs.
- Derive CLI, Python engine and lockfile versions from package.json.
- Publish new versions from verified main commits using npm Trusted Publishing; ordinary commits do not increment the version.

## 0.4.0

- Run natively on Windows x64 through PowerShell or Command Prompt without WSL, with user-local runtime provisioning and verified uv downloads.
- Support native file locking, safe command-shim resolution, managed tool paths and descendant process cleanup.
- Share read-only report snapshots and coalesce derived report refreshes while preserving fresh lifecycle gates and immediate durable state/events.
- Expose structured self-test progress and slowest-case timings; document focused development checks alongside complete final verification.
- Extend native Windows coverage and retain managed upgrades from 0.3.1 and earlier supported releases.

## 0.3.1

- Add host-mediated, read-only MCP investigation evidence alongside repository findings, with required-source and freshness checks.
- Resolve content-bound STRICT deeper reviews for ambiguous or oversized sources.
- Keep 0.3.0 installations eligible for the managed upgrade path.

## 0.3.0 — release candidate

- Rename the npm package and CLI to `specreceipt`.
- Prepare public documentation and curated source packaging under the Unlicense.
- Preserve the Python lifecycle and protocol 1 while advancing the package and engine inventory version to 0.3.0.
- Accept existing v0.1.0 and v0.2.0 installation manifests for safe upgrade.
