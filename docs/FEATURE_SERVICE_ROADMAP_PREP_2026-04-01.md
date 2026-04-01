# UTXOracle Feature Service Roadmap Prep

Date: 2026-04-01

Status: Working handoff document for roadmap drafting

Supersedes for roadmap work: [docs/FEATURE_AUDIT_2026.md](/media/sam/1TB/UTXOracle/docs/FEATURE_AUDIT_2026.md)

## 1. Purpose

This document is the current baseline for drafting a real roadmap for `UTXOracle` as an upstream data and feature service for `nautilus_dev`.

It is intentionally strict about evidence. Every capability is classified using only four labels:

- `runtime verified`
- `code implemented`
- `calculator only`
- `placeholder`

This document does not treat `UTXOracle` as a live trading engine. The correct scope is:

- `UTXOracle`: feature extraction, normalization, serving, provenance, health
- `nautilus_dev`: strategy, backtesting, live trading, execution

## 2. Verification Basis

### Runtime verified in this session

Verified directly against the live app on `127.0.0.1:8011`:

- `GET /health`
- `GET /api/v1/live/snapshot`
- `GET /api/v1/live/history`
- `GET /api/v1/live/comparison/latest`
- `GET /api/v1/live/ready`
- `GET /api/v1/charts/catalog`
- `GET /api/v1/charts/live-price-comparison/latest`
- `GET /api/v1/charts/live-price-comparison/history`
- `GET /api/v1/charts/realized-price-reference/compare`
- `GET /charts/live-price-comparison`

Runtime facts observed:

- live service status was `healthy`
- source health was `healthy` for `brk`, `electrs`, `mempool_api`, `hyperliquid`, `utxoracle`
- `BRK` realized price matched the realized-price comparison chart exactly

### Source/client layer verified by tests

Verified with:

```bash
pytest -q tests/test_live_source_clients.py tests/test_live_runtime.py -k "brk or mempool or electrs or hyperliquid or live_runtime"
```

Covered components:

- `ElectrsClient`
- `MempoolApiClient`
- `BrkClient`
- `HyperliquidSnapshotClient`
- `ElectrsBlockOracleResolver`
- live runtime composition

### BRK direct verification

Verified directly against `127.0.0.1:7070`:

- `GET /health` returned `healthy`
- `GET /api/metrics` returned a large metric catalog

Important constraint:

- `BRK` universe exists and is healthy upstream
- `UTXOracle` does not currently republish the entire `BRK` universe end-to-end
- the live feature plane currently republishes only a curated subset:
  - `realized_price_usd`
  - `liveliness`
  - `reserve_risk`

### Main app verification limit

The main FastAPI app route table was verified at import time, but the full lifespan-backed runtime verification was not completed in this session because startup depends on the configured QuestDB connection and full environment bootstrap.

Implication:

- `runtime verified` is only claimed where the route was actually exercised
- many main-app routes are correctly classified as `code implemented`, not `runtime verified`
- availability of many main-app routes still depends on QuestDB, DuckDB, Bitcoin Core RPC, or external upstream services being present and populated

### Main app live router duplication

The main FastAPI app includes the live router via `app.include_router(live_router, prefix="/api/v1")` in [api/main.py](/media/sam/1TB/UTXOracle/api/main.py), which means `/api/v1/live/*` is exposed on both:

- `:8001` via the main app
- `:8011` via the dedicated live app

This is important for roadmap work:

- `:8011` is the intentionally scoped live surface that was runtime verified in this session
- `:8001` shares the route code but not necessarily the same worker lifecycle assumptions

The roadmap should either remove the main-app duplicate exposure or document it explicitly as a secondary alias with caveats.

## 3. Architectural Scope

### Correct role of this repository

`UTXOracle` should be treated as:

- canonical oracle and feature gateway
- on-chain analytics and normalization layer
- whale, wallet, exchange-flow, and feature-serving platform
- curated upstream consumer of `BRK`, `mempool`, `electrs`, and Hyperliquid context

### What this repository should not be judged on

It should not be judged on:

- live order routing
- broker execution
- trading engine logic
- position management

Those belong to `nautilus_dev`.

## 4. Endpoint Inventory

The route inventory below was derived from the registered route tables in:

- [api/main.py](/media/sam/1TB/UTXOracle/api/main.py)
- [api/apps/live.py](/media/sam/1TB/UTXOracle/api/apps/live.py)
- [api/routes/live.py](/media/sam/1TB/UTXOracle/api/routes/live.py)
- [api/routes/charts.py](/media/sam/1TB/UTXOracle/api/routes/charts.py)
- [api/mempool_whale_endpoints.py](/media/sam/1TB/UTXOracle/api/mempool_whale_endpoints.py)

### 4.1 Runtime Verified

#### Live app

- `GET /health`
- `GET /api/v1/live/snapshot`
- `GET /api/v1/live/history`
- `GET /api/v1/live/comparison/latest`
- `GET /api/v1/live/ready`
- `GET /api/v1/charts/catalog`
- `GET /api/v1/charts/{chart_id}/latest`
  - verified with `chart_id=live-price-comparison`
- `GET /api/v1/charts/{chart_id}/history`
  - verified with `chart_id=live-price-comparison`
- `GET /api/v1/charts/{chart_id}/compare`
  - verified with `chart_id=realized-price-reference`
- `GET /charts/{chart_id}`
  - verified with `chart_id=live-price-comparison`

### 4.2 Code Implemented

#### Prices

- `GET /api/prices/latest`
- `GET /api/prices/historical`
- `GET /api/prices/comparison`

#### Whale query surface

- `GET /api/whale/transactions`
- `GET /api/whale/summary`
- `GET /api/whale/transaction/{txid}`

#### Main metrics currently wired

- `GET /api/metrics/latest`
- `GET /api/metrics/exchange-netflow`
- `GET /api/metrics/exchange-netflow/history`
- `GET /api/exchange-addresses/stats`
- `GET /api/metrics/binary-cdd`
- `GET /api/metrics/net-realized-pnl`
- `GET /api/metrics/net-realized-pnl/history`
- `GET /api/metrics/pl-ratio`
- `GET /api/metrics/pl-ratio/history`
- `GET /api/metrics/sopr`
- `GET /api/metrics/nvt`
- `GET /api/metrics/volatility`
- `GET /api/metrics/puell-multiple`
  - route is implemented, but the 365-day baseline uses a hardcoded historical average price rather than real issuance history
- `GET /api/metrics/mining-pulse`
- `GET /api/metrics/hash-ribbons`
- `GET /api/metrics/mining-economics`
- `GET /api/metrics/mining-economics/history`

#### Risk, model, and validation surface

- `GET /api/risk/pro`
  - route is implemented, but component inputs are currently hardcoded placeholders rather than live metric values
- `GET /api/risk/pro/zones`
  - static zone definitions; usable as-is
- `GET /api/risk/pro/history`
  - route is implemented, but the history provider currently returns an empty list
- `GET /api/v1/models`
- `GET /api/v1/models/{name}/predict`
- `GET /api/v1/models/backtest/{name}`
- `GET /api/v1/models/compare`
- `POST /api/v1/models/ensemble`
- `GET /api/v1/models/power-law`
- `GET /api/v1/models/power-law/predict`
- `GET /api/v1/models/power-law/history`
- `POST /api/v1/models/power-law/recalibrate`
- `GET /api/v1/validation/rbn/metrics`
- `GET /api/v1/validation/rbn/quota`
- `GET /api/v1/validation/rbn/{metric_id}`
- `GET /api/v1/validation/rbn/report`
- `DELETE /api/v1/validation/rbn/cache`

Important routing caveat:

- `/api/v1/models/power-law/predict` is currently shadowed by the earlier `/api/v1/models/{name}/predict` registration in the main app route order, so it should be treated as a routing conflict to resolve before it is relied on as a distinct contract

#### Main app operational pages

- `GET /`
- `GET /health`
- `GET /metrics`
- `GET /whale`
- `GET /dashboard`
- `GET /monitor`
- `GET /power-law`
- `GET /power_law`

### 4.3 Calculator Only (registered as 501 today)

These routes are registered in the main app and currently return HTTP `501 Not Implemented`. They are not consumable via API today. However, real analytical logic exists behind them in `scripts/metrics` or related modules, so the missing layer is API wiring and, in some cases, historical materialization.

#### Advanced and regime analytics

- `GET /api/metrics/advanced`
- `GET /api/metrics/wasserstein`
- `GET /api/metrics/wasserstein/history`
- `GET /api/metrics/wasserstein/regime`
- `GET /api/metrics/cointime`
- `GET /api/metrics/cointime/history`
- `GET /api/metrics/cointime/signal`

#### Advanced on-chain metrics

- `GET /api/metrics/urpd`
- `GET /api/metrics/supply-profit-loss`
- `GET /api/metrics/reserve-risk`
- `GET /api/metrics/sell-side-risk`
- `GET /api/metrics/cdd-vdd`
- `GET /api/metrics/nupl`
- `GET /api/metrics/revived-supply`
- `GET /api/metrics/cost-basis`

#### Wallet and cohort analytics

- `GET /api/metrics/address-cohorts`
- `GET /api/metrics/wallet-waves`
- `GET /api/metrics/absorption-rates`

### 4.4 Placeholder (501 without ready backend)

These routes are registered and return HTTP `501 Not Implemented`, but unlike section 4.3 they do not currently have a ready calculator-backed serving path behind them.

- `GET /api/whale/latest`
- `GET /api/whale/historical`
- `GET /api/whale/history`
- `GET /api/metrics/wallet-waves/history`

## 5. Upstream and Data Source Roles

### UTXOracle native

Primary native strengths:

- canonical on-chain oracle price
- UTXO lifecycle analytics
- custom exchange-flow analytics
- clustering and cost-basis logic
- whale monitoring and mempool analytics

Primary source files:

- [UTXOracle.py](/media/sam/1TB/UTXOracle/UTXOracle.py)
- [UTXOracle_library.py](/media/sam/1TB/UTXOracle/UTXOracle_library.py)
- [scripts/metrics](/media/sam/1TB/UTXOracle/scripts/metrics)
- [scripts/clustering](/media/sam/1TB/UTXOracle/scripts/clustering)

### BRK

Current role:

- upstream macro/on-chain feature source with a much broader universe than what `UTXOracle` currently republishes

Verified current usage in `UTXOracle` live path:

- `realized_price_usd`
- `liveliness`
- `reserve_risk`

Primary files:

- [scripts/live/source_clients.py](/media/sam/1TB/UTXOracle/scripts/live/source_clients.py)
- [scripts/validate_brk_integration.py](/media/sam/1TB/UTXOracle/scripts/validate_brk_integration.py)
- [scripts/compare_brk_utxoracle.py](/media/sam/1TB/UTXOracle/scripts/compare_brk_utxoracle.py)

### Mempool

Current role:

- exchange BTC/USD reference in live path
- real-time mempool whale monitoring foundation

Primary files:

- [scripts/live/source_clients.py](/media/sam/1TB/UTXOracle/scripts/live/source_clients.py)
- [scripts/mempool_whale_monitor.py](/media/sam/1TB/UTXOracle/scripts/mempool_whale_monitor.py)
- [api/mempool_whale_endpoints.py](/media/sam/1TB/UTXOracle/api/mempool_whale_endpoints.py)

### Electrs

Current role:

- confirmed-chain block/tip support for live resolver and chain-aware calculations

Primary files:

- [scripts/live/runtime.py](/media/sam/1TB/UTXOracle/scripts/live/runtime.py)
- [scripts/live/source_clients.py](/media/sam/1TB/UTXOracle/scripts/live/source_clients.py)

### Hyperliquid

Current role:

- derivative and oracle comparison reference in the live fast plane

Primary files:

- [scripts/live/source_clients.py](/media/sam/1TB/UTXOracle/scripts/live/source_clients.py)
- [docker-compose.live.yml](/media/sam/1TB/UTXOracle/docker-compose.live.yml)

## 6. What `nautilus_dev` Can Consume Today

### Immediately consumable with strongest confidence

- live snapshot bundle from `/api/v1/live/*` on the dedicated live app `:8011`
- live chart comparison surfaces from `/api/v1/charts/*` on the dedicated live app `:8011`
- price comparison APIs
- whale transaction query APIs backed by `mempool_predictions`
- exchange netflow APIs
- latest metrics bundle
- binary CDD
- net realized PnL
- P/L ratio
- mining metrics
- SOPR
- NVT
- volatility
- power-law APIs, with the route-order caveat on `/api/v1/models/power-law/predict`
- RBN validation APIs

### Consumable only with explicit caveats

- PRO Risk zone definitions only (`/api/risk/pro/zones`)
- `/api/risk/pro` currently returns composite output built from hardcoded component inputs
- `/api/risk/pro/history` currently returns an empty list
- Puell Multiple currently computes against a hardcoded historical average price rather than real issuance history
- mining economics history currently hardcodes `pulse_zone="NORMAL"` for historical entries

### Consumable only if `nautilus_dev` links code or reuses calculators directly

- Wasserstein calculations
- cointime calculations
- URPD
- supply profit/loss
- reserve risk
- sell-side risk
- CDD/VDD
- NUPL
- revived supply
- cost basis
- address cohorts
- wallet waves
- absorption rates

### Not consumable as stable API today

- legacy whale snapshot/history routes
- wallet-waves historical endpoint

## 7. Gold Mine Capabilities Already Present But Not Productized

### Wallet and cluster intelligence

Existing internal capabilities:

- address clustering
- CoinJoin filtering
- change detection
- wallet-level cost basis
- entity-like cohort analysis

Primary files:

- [scripts/clustering/address_clustering.py](/media/sam/1TB/UTXOracle/scripts/clustering/address_clustering.py)
- [scripts/clustering/coinjoin_detector.py](/media/sam/1TB/UTXOracle/scripts/clustering/coinjoin_detector.py)
- [scripts/clustering/change_detector.py](/media/sam/1TB/UTXOracle/scripts/clustering/change_detector.py)
- [scripts/clustering/cost_basis.py](/media/sam/1TB/UTXOracle/scripts/clustering/cost_basis.py)
- [scripts/clustering/migrate_cost_basis.py](/media/sam/1TB/UTXOracle/scripts/clustering/migrate_cost_basis.py)

Roadmap implication:

- there is enough analytical substrate to build entity-aware features
- what is missing is stable serving, provenance, confidence, and historical materialization

### Whale and mempool intelligence

Existing capabilities:

- `mempool_predictions` query surface
- realtime mempool whale monitoring
- block-aware whale flow detector

Roadmap implication:

- whale intelligence exists in two overlapping pipelines
- it should be unified into one canonical product surface

### BRK underutilization

Current reality:

- `BRK` offers a broad metric universe
- `UTXOracle` currently republishes only three BRK metrics in the live path

Roadmap implication:

- a curated BRK feature manifest is needed
- the roadmap should decide which BRK families are promoted into first-class `UTXOracle` feature bundles

## 8. Major Gaps To Review Before Writing the Roadmap

### Gap A: API surface drift

There is a large difference between:

- what the repository can compute
- what the main API currently exposes
- what the live app intentionally keeps minimal

This drift is the main reason roadmap work must start from this document instead of from specs alone.

### Gap B: Missing productization for calculator-backed features

These are the most obvious candidates for roadmap conversion from `calculator only` to `code implemented` and then `runtime verified`:

- `address-cohorts`
- `wallet-waves`
- `absorption-rates`
- `urpd`
- `nupl`
- `reserve-risk`
- `sell-side-risk`
- `cdd-vdd`
- `cost-basis`
- `revived-supply`
- `cointime`
- `wasserstein`

### Gap C: No canonical entity registry

If the product direction includes institutional wallet movement reconstruction or more forensic use cases, the repo is still missing:

- canonical `entity_id`
- provenance model for labels
- confidence model for attribution
- cluster-to-entity registry
- entity movement APIs

### Gap D: No curated feature bundle contract for `nautilus_dev`

Current surfaces are fragmented across:

- main app metrics
- live fast plane
- calculators
- BRK upstream

The roadmap should define canonical bundle surfaces such as:

- `core`
- `forensics`
- `macro`
- `entities`

### Gap E: Data dependency map is still implicit

Current `code implemented` routes do not share one backend. They depend on different infrastructure layers:

- QuestDB:
  - `/api/prices/*`
  - `/api/metrics/latest`
  - `/api/whale/transactions`
  - `/api/whale/summary`
  - `/api/whale/transaction/{txid}`
- DuckDB / `utxo_lifecycle[_full]`:
  - `/api/metrics/exchange-netflow*`
  - `/api/metrics/binary-cdd`
  - `/api/metrics/net-realized-pnl*`
  - `/api/metrics/pl-ratio*`
  - `/api/metrics/sopr`
  - `/api/metrics/nvt` (also uses `block_heights`)
- DuckDB / `daily_prices`:
  - `/api/metrics/volatility`
- No persistent backend for core calculation:
  - `/api/metrics/puell-multiple` (current calculation relies on hardcoded constants; DuckDB is used only opportunistically for block height)
- Bitcoin Core RPC:
  - `/api/metrics/mining-pulse`
  - `/api/metrics/mining-economics`
- External upstream APIs:
  - `/api/metrics/hash-ribbons`
  - `/api/metrics/mining-economics/history`
- External credentials / service configuration:
  - `/api/v1/validation/rbn/*`

The roadmap should turn this into an explicit dependency matrix so each feature tier has a defined infrastructure requirement and failure mode.

## 9. Recommended Roadmap Framing

The roadmap should not be framed as:

- "make everything live"
- "expose every BRK metric"
- "turn UTXOracle into a trading engine"

It should be framed as:

### Track 1: Core Feature Gateway

Deliverables:

- stable live snapshot contract
- price and comparison reliability
- curated BRK subset
- source health and provenance

### Track 2: Productize Existing Calculators

Deliverables:

- wire calculator-backed APIs
- add historical snapshot storage where required
- add contract tests and runtime smoke tests

### Track 3: Forensic and Entity Feature Plane

Deliverables:

- unify whale pipelines
- add entity registry
- expose cluster and institutional movement surfaces
- add provenance and confidence

### Track 4: ML-Ready Feature Bundles

Deliverables:

- curated BRK manifest
- canonical feature bundles for `nautilus_dev`
- export and replay friendly schemas

## 10. Questions The Roadmap Must Answer

- Which features are mandatory for `nautilus_dev` in the first production-ready contract?
- Which `BRK` families should be promoted, ignored, or treated as validation-only?
- Should `UTXOracle` expose entity-aware forensic surfaces in the main API, in a separate app, or through periodic bundles?
- Which current `code implemented` routes are actually strategic versus just historically accumulated?
- Which placeholder routes should be removed instead of completed?
- How much historical snapshotting is required to unlock wallet waves history and absorption rates in production form?

## 11. Immediate Roadmap Input Set

When roadmap drafting starts, the minimum input set should be:

- this document
- [docs/FEATURE_AUDIT_2026.md](/media/sam/1TB/UTXOracle/docs/FEATURE_AUDIT_2026.md)
- [docs/LIVE_STACK_ROLE_MATRIX.md](/media/sam/1TB/UTXOracle/docs/LIVE_STACK_ROLE_MATRIX.md)
- [docs/HANDOFF_UTXORACLE_LIVE_2026-03-20.md](/media/sam/1TB/UTXOracle/docs/HANDOFF_UTXORACLE_LIVE_2026-03-20.md)
- [specs/021-advanced-onchain-metrics/spec.md](/media/sam/1TB/UTXOracle/specs/021-advanced-onchain-metrics/spec.md)
- [specs/025-wallet-waves/spec.md](/media/sam/1TB/UTXOracle/specs/025-wallet-waves/spec.md)
- [specs/039-address-balance-cohorts/spec.md](/media/sam/1TB/UTXOracle/specs/039-address-balance-cohorts/spec.md)
- [specs/043-nautilus-live-trading-integration/spec.md](/media/sam/1TB/UTXOracle/specs/043-nautilus-live-trading-integration/spec.md)

## 12. Recommended Next Step

The next concrete step should be a roadmap matrix with these columns:

- `surface`
- `current label`
- `consumer`
- `source of truth`
- `blocking gap`
- `target contract`
- `priority`
- `estimated effort`

That roadmap should begin from this verified inventory, not from assumptions.
