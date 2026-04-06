# Decision Log: spec-052 BTC Consumer Bundles and Signal Snapshots

This file records the binding outputs of `Freeze` and `Decide` tasks from [tasks.md](/media/sam/1TB/UTXOracle/specs/052-btc-consumer-bundles-and-signal-snapshots/tasks.md).

Usage:

- fill one row when the referenced task is actually resolved
- keep `Decision` short and final; do not paste discussion transcripts
- use `Binding For` to name the downstream tasks, phases, or artifacts that must follow this decision
- use `Source Ref` to point to the spec section, commit, or implementation file that made the decision effective

Expected coverage: 18 binding decision rows.

| Phase | Task | Topic | Decision | Binding For | Source Ref |
|-------|------|-------|----------|-------------|------------|
| Phase 1 | T001 | bundle-plane boundary |  | T006-T011, T015-T016, T033-T040, T050-T054 |  |
| Phase 1 | T002 | signal-plane boundary |  | T016, T042-T049, T050-T054 |  |
| Phase 2 | T007 | common bundle metadata |  | T031-T041, T055-T058 |  |
| Phase 2 | T008 | `btc_core_live.v1` payload shape |  | T031-T034, T041, T050-T055 |  |
| Phase 2 | T009 | `btc_flow.v1` payload shape |  | T031-T036, T041, T050-T056 |  |
| Phase 2 | T010 | `btc_macro.v1` payload shape |  | T027-T029, T031-T038, T041, T050-T057 |  |
| Phase 2 | T011 | `btc_cohort.v1` payload shape |  | T018-T023, T031-T041, T050-T058 |  |
| Phase 2 | T012 | fields intentionally left outside v1 |  | T050-T054, consumer docs, non-goal enforcement |  |
| Phase 3 | T013 | `sequence_id` generation and persistence |  | T015-T017, T031-T032, T045, T055-T056 |  |
| Phase 3 | T014 | per-bundle vs cross-bundle `sequence_id` model |  | T015-T017, T031-T032, T045, T055-T056 |  |
| Phase 3 | T017 | history ordering semantics |  | T032, T034, T036, T038, T040, T048, T055-T056 |  |
| Phase 4 | T018 | admitted `cost_basis` subset |  | T019-T023, `btc_cohort.v1`, contract registry updates |  |
| Phase 4 | T021 | `cost_basis` serving path |  | T022-T023, `btc_cohort.v1`, degraded semantics, consumer docs |  |
| Phase 5 | T024 | curated `BRK` macro subset |  | T027-T029, T037-T038, `btc_macro.v1`, T057, T059 |  |
| Phase 6 | T030 | uniform failure vocabulary |  | T031-T041, T045-T049, T055-T060 |  |
| Phase 7 | T042 | `btc_signal_snapshot.v1` payload schema |  | T045-T049, T050-T054 |  |
| Phase 7 | T043 | signal formulas and normalization rules |  | T045-T049, signal writer, consumer docs |  |
| Phase 7 | T044 | signal `service_status` vocabulary |  | T045-T049, T055-T060 |  |
