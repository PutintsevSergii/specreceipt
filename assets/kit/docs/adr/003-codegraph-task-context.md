# ADR 003: Index-backed task context

Status: Accepted for harness maintenance, 2026-10-23
Authorization: User requested CodeGraph and Graphify installation/index checks, context collection before implementation, reindexing after substantial edits, and Git exclusions. The CodeGraph CLI choice is an explicit working assumption pending confirmation because the two supplied URLs refer to different products.

## Choice and evidence

Use [`colbymchenry/codegraph`](https://colbymchenry.github.io/codegraph/) as the CLI adapter because its documented `init`, `status`, `sync`, and `query` commands match the requested local index lifecycle. Version 1.6.2 is recorded in its [package manifest](https://github.com/colbymchenry/codegraph/blob/main/package.json). The other linked [`codegraph-ai/CodeGraph`](https://github.com/codegraph-ai/CodeGraph) is a separate MCP/server product with a different installation and indexing contract; it is not silently substituted.

For application tasks, task start now ensures both external indexes, runs bounded CodeGraph and Graphify queries using the task outcome and scope, and saves redacted navigation context in `.harness/graph/`. The IMPLEMENTED transition and verification refresh stale indexes. Agents also run `./harness indexes ensure` after substantial edit batches. Index files are excluded from Git, navigation inventory and verification inputs. Existing `.gitignore` rules are preserved during adoption.

## Limits

The CodeGraph CLI is not installed on this development host, so its command contract is exercised with a deterministic fake executable; the real CodeGraph CLI has not been validated here. Graphify has a live isolated-fixture test. Automatic CodeGraph installation requires npm and package access; Graphify requires uv. Context retrieval can miss behavior and never replaces reading source, approved requirements, tests, separate review, or verification. If either external index cannot be prepared, application implementation remains blocked. The kit's harness-only tasks can continue without them.
