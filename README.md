# UTXOracle

UTXOracle is a Bitcoin-native, exchange-free price oracle that calculates the market price of Bitcoin directly from the blockchain.

Unlike traditional oracles that rely on exchange APIs, UTXOracle estimates a BTC/USD price directly from confirmed on-chain activity. The repository now also contains a large QuestDB-backed analytics surface and is being repositioned as a live production service that integrates `BRK`, `mempool-api`, `electrs`, and `Hyperliquid`.

## Current 2026 Status

The current live-first direction is:
- `UTXOracle` remains the canonical oracle and the future consumer-facing live API
- `QuestDB` is the primary time-series database for all on-chain analytics
- `BRK` is the main upstream feature provider for broad on-chain metrics and query ergonomics
- `mempool-api` remains the live mempool and exchange-price context source
- `electrs` remains low-level confirmed-chain infrastructure
- `Hyperliquid` remains the external oracle and derivatives comparison source, surfaced locally through `hyperliquid-node` and its filtered oracle-update dataset

Current host runtime verified on 2026-03-31:
- `UTXOracle Live API`: `127.0.0.1:8011` — canonical production API via `api.apps.live:app`
- `UTXOracle API`: `127.0.0.1:8001` — explicit legacy surface via `api.apps.legacy:app`
- `QuestDB Web Console`: `127.0.0.1:9000`
- `BRK`: `127.0.0.1:7070`
- `electrs`: `127.0.0.1:3002`
- `mempool-api`: `127.0.0.1:8999`
- `mempool-web`: `127.0.0.1:8080`
- `hyperliquid-node /info`: `127.0.0.1:3001` via `POST /info`
- `hyperliquid-node metrics`: `127.0.0.1:9101/metrics`
- `hyperliquid filtered oracle updates`: `/media/sam/4TB-NVMe/hyperliquid/filtered/hip3_oracle_updates_by_block`

## How It Works

UTXOracle analyzes confirmed Bitcoin transactions and isolates a canonical price point from on-chain economic activity:
- filters coinbase, spam, and low-signal outputs
- focuses on economically meaningful transaction outputs
- derives a Bitcoin price directly from chain behavior rather than exchange APIs

The result is a reproducible on-chain oracle that remains the conceptual center of this repository.

## Repository Roles

This repository now serves three distinct purposes:
- canonical oracle engine via `UTXOracle.py` and `UTXOracle_library.py`
- QuestDB-backed analytics and research workspace with many custom metrics
- foundation for a live production service with a normalized downstream API

## Core Components

- `UTXOracle.py`: immutable reference implementation of the oracle logic
- `UTXOracle_library.py`: reusable oracle engine extracted from the reference implementation
- `api/`: FastAPI backend with historical metrics and dashboards
- `scripts/`: batch jobs, sync utilities, whale pipeline, and integration tooling
- `scripts/metrics/`: custom analytics modules built on top of the local data model
- `docs/`: architecture, integration notes, and operational references
- `specs/`: implementation specs, including the new live-service direction

## What Is Unique to UTXOracle

These remain first-class responsibilities of this repository even when BRK is present:
- canonical on-chain Bitcoin price oracle methodology
- DuckDB-backed local research datasets and custom analytics
- UTXO lifecycle based metrics and experimental features
- whale-flow, exchange-netflow, and fusion logic specific to this repo
- normalized live API contract for Nautilus Trader and backtest engines

## Current Documentation

Start here before following older setup or deployment instructions:
- [Live Stack Role Matrix](docs/LIVE_STACK_ROLE_MATRIX.md)
- [Feature Audit 2026](docs/FEATURE_AUDIT_2026.md)
- [UTXOracle Live Service Spec](specs/040-utxoracle-live-service/spec.md)
- [BRK Integration Analysis](docs/BRK_INTEGRATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Mempool + electrs Architecture](MEMPOOL_ELECTRS_ARCHITECTURE.md)

## Production Direction

The intended production topology is:
1. `bitcoind` as root truth
2. `electrs` as confirmed-chain raw index
3. `mempool-api` as live mempool and exchange-price context
4. `BRK` as the primary on-chain feature provider and validation surface
5. `Hyperliquid` as external oracle and derivatives comparator
6. `UTXOracle Live API` as the only downstream consumer contract

Current production boundary:
- `8011` exposes multiple execution and operator route families
- `8001` is legacy/research-only and must not be treated as the canonical consumer contract
- the retained live family on `8011` is now served directly from QuestDB `live_snapshots`

### Service Boundary

The explicit NT execution contract is strictly limited to `tier_1_execution` surfaces:
- `/health`
- `/api/v1/live/*`
- `/api/features/btc/*`
- `/api/signals/btc/*`

For the complete service boundary and tier assignments, refer to [docs/contracts/surface_boundary.yaml](docs/contracts/surface_boundary.yaml) as the canonical source of truth.

## Canonical Chart Surface

The current chart entry point is on the live production app at `8011`.

Canonical routes:
- `GET /charts/live-price-comparison`
- `GET /api/v1/charts/catalog`
- `GET /api/v1/charts/live-price-comparison/latest`
- `GET /api/v1/charts/live-price-comparison/history`
- `GET /api/v1/charts/live-price-comparison/compare`
- `GET /api/v1/charts/realized-price-reference/latest`
- `GET /api/v1/charts/realized-price-reference/history`
- `GET /api/v1/charts/realized-price-reference/compare`

Current semantics:
- `live-price-comparison` is the canonical market-reference chart family
- `realized-price-reference` is the first admitted BRK-linked external validation family
- chart history and latest payloads are served from QuestDB-backed `live_snapshots`
- long-window `history` reads may be downsampled server-side with `downsampling_strategy=uniform_stride`; use `downsample=false` for raw operator/debug reads
- the compare path for `realized-price-reference` uses the latest local `brk_realized_price` and one live BRK curated fetch with a hard timeout of `2s`
- older scattered chart pages and legacy API families are not the canonical validation surface
- `frontend/comparison.html` and `/static/comparison.html` remain legacy/research-only on `8001` and should not be used as the canonical chart entry point

## Current Validation Workflow

The first frozen validation workflow for `spec-042` is:

1. fetch `realized-price-reference/latest`
2. fetch `realized-price-reference/history`
3. fetch `realized-price-reference/compare`
4. treat `compare.summary.status` as the first parity gate

Operational notes:
- a good run returns HTTP `200` on all three endpoints
- `compare.summary.status` may be `match`, `minor_diff`, `major_diff`, or `no_overlap`
- BRK unavailability must degrade the compare payload to `no_overlap`, not fail the chart API
- the current external compare is point-in-time only; it is not yet a historical BRK overlay parity claim

Recorded example run:
- [realized-price-reference validation run](specs/042-questdb-charting-validation/artifacts/realized-price-reference/README.md)
- [spec-042 operator notes](specs/042-questdb-charting-validation/operator-notes.md)

## Getting Started

For the reference oracle only:

```bash
git clone https://github.com/Unbesteveable/UTXOracle.git
cd UTXOracle
python3 UTXOracle.py
```

This requires a local `bitcoind` node with RPC enabled.

For the current live migration, do not rely on older step-by-step commands blindly. Read the documents listed in `Current Documentation` first.

## Notes on Older Documentation

Some older repo documents still reflect an earlier runtime model and may contain stale ports or stale Hyperliquid assumptions such as:
- `electrs` on `3001`
- `BRK` on `3110`
- FastAPI on `8000`
- `127.0.0.1:12345` as if it were the canonical Hyperliquid comparison source

Treat the documents listed in `Current Documentation` as the current source of truth for the live migration.

## License

UTXOracle is licensed under the [Blue Oak Model License 1.0.0](./LICENSE).

## Credits

Created by [@Unbesteveable](https://github.com/Unbesteveable).

## Monitoring
Check service status and version:
`curl -s http://localhost:8011/health | jq .`
