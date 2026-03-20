# UTXOracle

UTXOracle is a Bitcoin-native, exchange-free price oracle that calculates the market price of Bitcoin directly from the blockchain.

Unlike traditional oracles that rely on exchange APIs, UTXOracle estimates a BTC/USD price directly from confirmed on-chain activity. The repository now also contains a large DuckDB-backed analytics surface and is being repositioned as a live production service that integrates `BRK`, `mempool-api`, `electrs`, and `Hyperliquid`.

## Current 2026 Status

The current live-first direction is:
- `UTXOracle` remains the canonical oracle and the future consumer-facing live API
- `BRK` is the main upstream feature provider for broad on-chain metrics and query ergonomics
- `mempool-api` remains the live mempool and exchange-price context source
- `electrs` remains low-level confirmed-chain infrastructure
- `Hyperliquid` remains the external oracle and derivatives comparison source

Current host runtime verified on 2026-03-20:
- `UTXOracle API`: `127.0.0.1:8001`
- `BRK`: `127.0.0.1:7070`
- `electrs`: `127.0.0.1:3002`
- `mempool-api`: `127.0.0.1:8999`
- `mempool-web`: `127.0.0.1:8080`

## How It Works

UTXOracle analyzes confirmed Bitcoin transactions and isolates a canonical price point from on-chain economic activity:
- filters coinbase, spam, and low-signal outputs
- focuses on economically meaningful transaction outputs
- derives a Bitcoin price directly from chain behavior rather than exchange APIs

The result is a reproducible on-chain oracle that remains the conceptual center of this repository.

## Repository Roles

This repository now serves three distinct purposes:
- canonical oracle engine via `UTXOracle.py` and `UTXOracle_library.py`
- DuckDB-backed analytics and research workspace with many custom metrics
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

Some older repo documents still reflect an earlier runtime model and may contain stale ports such as:
- `electrs` on `3001`
- `BRK` on `3110`
- FastAPI on `8000`

Treat the documents listed in `Current Documentation` as the current source of truth for the live migration.

## License

UTXOracle is licensed under the [Blue Oak Model License 1.0.0](./LICENSE).

## Credits

Created by [@Unbesteveable](https://github.com/Unbesteveable).
