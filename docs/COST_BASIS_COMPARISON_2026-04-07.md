# Cost Basis vs BRK Comparison Outcome

Date: 2026-04-07
Spec: 052
Phase: 5
Task: T025, T026

## Comparison
We verified whether `BRK` exposes an exact `cost_basis` equivalent, specifically focusing on our STH (Short-Term Holder) and LTH (Long-Term Holder) cohorts and their respective MVRV ratios.

## Outcome
`BRK` does not expose an exact equivalent for our specific 155-day threshold STH/LTH cost basis calculations in a single API response that meets our latency and schema requirements.

## Decision (T026)
Because there is no exact upstream equivalent, `cost_basis` remains strictly `local_canonical`. UTXOracle retains local ownership of the metric, and it is computed from the DuckDB `utxo_lifecycle` dataset and materialized to QuestDB. The Feature Contract Registry already reflects this `local_canonical` ownership.