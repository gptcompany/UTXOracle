# Schema Evolution and Deprecation Policy (spec-058)

This document defines how UTXOracle contract surfaces (API payloads and DB schemas) evolve. These rules ensure that execution-grade consumers (like Nautilus Trader) can rely on stable and predictable data shapes and semantics.

## Change Classes

All changes to execution-grade surfaces must be classified into one of the following:

- **docs_only**: No consumer impact. Changes to documentation, metadata, or internal comments only.
- **additive_non_breaking**: New optional fields or metadata only. Existing consumers can safely ignore these.
- **behavioral_tightening**: Stricter semantics without shape breakage. Requires explicit review and compatibility signoff.
- **breaking**: Removal, rename, incompatible semantic change, or contract split. Requires a new major version and a deprecation window.

## Versioning Rules

- **v1 surfaces** are additive-only by default.
- Breaking changes **require a new major version** (e.g., v1 -> v2).
- Breaking replacements require a **minimum 30-day deprecation window** unless an emergency override is recorded.
- Parallel overlap of old and new versions is expected for breaking replacements where practical.

## Promotion Gates

Before promoting a `behavioral_tightening` or `breaking` change to an execution-grade surface, the following must be verified:

1. **Route Contract Validation**: Ensure the implementation matches the declared contract.
2. **Replay Compatibility**: Verify that historical replay remains valid.
3. **NT Adapter Compatibility**: Verify that the Nautilus Trader adapter can handle the change.
4. **Explicit Signoff**: Compatibility evidence must be recorded in the decision log.

## Review Checklist

When reviewing a PR that modifies an execution-grade surface, verify:

- [ ] Is the change class explicitly stated (`docs_only`, `additive_non_breaking`, `behavioral_tightening`, `breaking`)?
- [ ] For `additive_non_breaking`: Are the new fields strictly optional?
- [ ] For `behavioral_tightening`: Has compatibility signoff been recorded in the spec decision log?
- [ ] For `breaking`: Has a new major version been created and a deprecation plan established?
- [ ] Have the `feature_contract_registry.yaml` and `feature_provenance_manifest.yaml` been updated?
- [ ] Has NT adapter compatibility been verified?
