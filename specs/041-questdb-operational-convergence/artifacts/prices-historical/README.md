# prices-historical parity run

Run executed on 2026-03-31 against the live runtime exposed on `127.0.0.1:8011`.

## Inputs

- Candidate payload: [questdb_candidate_8011_days7.json](/media/sam/1TB/UTXOracle/specs/041-questdb-operational-convergence/artifacts/prices-historical/questdb_candidate_8011_days7.json)
- OpenAPI snapshot: [openapi_8011.json](/media/sam/1TB/UTXOracle/specs/041-questdb-operational-convergence/artifacts/prices-historical/openapi_8011.json)
- Parity report: [parity_report_days7.json](/media/sam/1TB/UTXOracle/specs/041-questdb-operational-convergence/artifacts/prices-historical/parity_report_days7.json)
- Dual-read event: [dual_read_days7.jsonl](/media/sam/1TB/UTXOracle/specs/041-questdb-operational-convergence/artifacts/prices-historical/dual_read_days7.jsonl)
- Offline baseline: `data/utxoracle.duckdb` table `price_analysis`

## Observations

- `GET /api/prices/historical?days=7` on `8011` returned `200` with `[]`
- `GET /api/prices/comparison?days=7` on `8011` returned `200` with `total_entries=0`
- `GET /api/prices/latest` on `8011` returned `500` with detail `404: No price data available`
- `openapi_8011.json` still advertises `/api/prices/latest`, `/api/prices/historical`, and `/api/prices/comparison`

## Result

Status: `fail`

Reason:
- the candidate side has no samples for the 7-day request window
- the DuckDB baseline helper anchors to the latest available historical day in `price_analysis`, which is 2025-12-27
- the report therefore records `key_mismatch` and `no_overlapping_samples`

## Interpretation

This is a real environment drift signal, not just a repo-state issue:
- the running `8011` service still exposes the `prices` family
- that family is not operationally ready for parity or cutover
- `prices-historical` should remain outside the retained production surface until a real QuestDB-backed candidate series exists with overlapping history
