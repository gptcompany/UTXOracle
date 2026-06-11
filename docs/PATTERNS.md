# UTXOracle Engineering Patterns — Index

This file is an **index**, not a documentation repository. Each entry below cross-links to the spec that owns the canonical pattern document. Do NOT copy pattern content into this file; that creates drift between the index and the source of truth.

## Strangler-fig migration (legacy store → QuestDB)

When and how to migrate a read helper off a legacy data store (DuckDB) onto QuestDB without breaking existing callers.

→ **Canonical pattern**: [spec-062 plan, Appendix A](../specs/062-aggregator-zero-duckdb/plan.md#appendix-a--strangler-fig-migration-pattern-canonical-per-fr-010)
