# spec-042 Operator Notes

## Current Validation Workflow

The first production validation path is `realized-price-reference`.

Use these runtime checks on `8011`:

1. fetch latest:
   - `curl -fsS 'http://127.0.0.1:8011/api/v1/charts/realized-price-reference/latest' | jq .`
2. fetch history:
   - `curl -fsS 'http://127.0.0.1:8011/api/v1/charts/realized-price-reference/history?minutes=60' | jq .`
3. fetch compare:
   - `curl -fsS 'http://127.0.0.1:8011/api/v1/charts/realized-price-reference/compare?minutes=60' | jq .`

## Expected Semantics

- `latest` and `history` are local QuestDB-backed reads from `live_snapshots`
- long-window `history` reads may return `is_downsampled=true` with `downsampling_strategy=uniform_stride`
- use `downsample=false` on `history` routes only when a raw operator/debug read is explicitly needed
- `compare` uses the latest local `features.brk_realized_price` and one live BRK curated fetch of `realized_price_usd`
- the BRK path is allowed to degrade after a hard timeout of `2s`
- a degraded BRK fetch must return a compare payload with `status=no_overlap`, not a route failure

## What Counts As A Good Run

- HTTP `200` on all three endpoints
- `compare.summary.status` is one of `match`, `minor_diff`, `major_diff`, or `no_overlap`
- `compare.summary.comparison_count=1`
- `compare.comparisons[0].reference_series_id=brk_api_realized_price`

Preferred healthy case:

- `compare.summary.status=match`
- `overlap_points=1`
- `mean_abs_diff=0`
- `mean_relative_diff_pct=0`

## Known Limitation

This is a point-in-time external compare only.

It does not yet prove historical parity against a time-aligned BRK overlay. If historical BRK parity is needed, add a materialized or cached overlay path before widening the claim beyond the current-point gate.
