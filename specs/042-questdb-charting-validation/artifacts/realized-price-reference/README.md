# realized-price-reference validation run

Run executed on 2026-03-31 against the live runtime exposed on `127.0.0.1:8011`.

## Inputs

- Latest payload: [latest_8011.json](/media/sam/1TB/UTXOracle/specs/042-questdb-charting-validation/artifacts/realized-price-reference/latest_8011.json)
- History payload: [history_60m_8011.json](/media/sam/1TB/UTXOracle/specs/042-questdb-charting-validation/artifacts/realized-price-reference/history_60m_8011.json)
- Compare payload: [compare_60m_8011.json](/media/sam/1TB/UTXOracle/specs/042-questdb-charting-validation/artifacts/realized-price-reference/compare_60m_8011.json)

## Observations

- `GET /api/v1/charts/realized-price-reference/latest` returned `200` with `status=degraded`, `freshness_seconds=0.6`, and `latest_value=54133.13`
- `GET /api/v1/charts/realized-price-reference/history?minutes=60` returned `200` with `534` samples spanning `2026-03-31T15:49:28.808410+00:00` to `2026-03-31T16:49:25.618594+00:00`
- the local QuestDB-backed series stayed in a narrow range over the observed hour: `min=54133.13`, `max=54136.82`
- `GET /api/v1/charts/realized-price-reference/compare?minutes=60` returned `200` with `summary.status=match`

## Result

Status: `pass`

Numeric output:

- `comparison_count=1`
- `reference_series_id=brk_api_realized_price`
- `overlap_points=1`
- `mean_abs_diff=0.0`
- `max_abs_diff=0.0`
- `mean_relative_diff_pct=0.0`

## Interpretation

This validates the first admitted external compare path for `spec-042`:

- local data is served from QuestDB-backed `live_snapshots`
- the compare branch can resolve the live BRK curated metric without breaking the chart API
- the runtime degrades at the chart metadata level because `hyperliquid` is stale, but the realized-price compare itself still produced a clean `match`

The remaining limitation is explicit:

- the current external compare is a point-in-time parity gate with `overlap_points=1`
- it is not yet a historical BRK overlay or a time-aligned multi-sample parity run
