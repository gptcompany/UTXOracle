# CLAUDE.md

## Project Overview
**UTXOracle** - Bitcoin-native, exchange-free price oracle. Calculates BTC/USD directly from blockchain data using statistical clustering.

**Key Principles**: Pure Python | Single-file reference | Bitcoin Core RPC only | Privacy-first (no external feeds)

**Philosophy**: KISS + YAGNI

**Skills Framework**: See `.claude/SKILLS_FRAMEWORK_BLUEPRINT.md`

---

## Quick Start

```bash
python3 UTXOracle.py              # Yesterday's price
python3 UTXOracle.py -d 2025/10/15  # Specific date
python3 UTXOracle.py -rb           # Recent 144 blocks
```

**Requirements**: Python 3.8+, Bitcoin Core (synced, RPC enabled)

---

## Long-Running Processes

**ALWAYS use `setsid` for long processes:**
```bash
setsid uv run python script.py >> /tmp/script.log 2>&1 &
```

---

## Architecture (4-Layer)

| Layer | Component | Purpose |
|-------|-----------|---------|
| 1 | `UTXOracle.py` | Reference (IMMUTABLE) |
| 2 | `UTXOracle_library.py` | Reusable library |
| 3 | mempool.space + electrs | Self-hosted infra |
| 4 | `api/main.py` + `frontend/` | FastAPI + Dashboard |

**Full docs**: `docs/ARCHITECTURE.md` (auto-validated on commit)

---

## Critical Paths

| Component | Path |
|-----------|------|
| Bitcoin Core | `/media/sam/3TB-WDC/Bitcoin` |
| BRK binary | `~/.local/bin/brk` (v0.0.111) |
| BRK data | `/media/sam/1TB/brk-data` (286GB) |
| Docker stack | `/media/sam/2TB-NVMe/prod/apps/mempool-stack/` |
| UTXOracle | `/media/sam/1TB/UTXOracle` |
| DuckDB | `data/utxoracle.duckdb` |
| Live DuckDB | `data/utxoracle_live.duckdb` |

**Service URLs**: Bitcoin RPC `:8332` | electrs `:3002` | mempool `:8999/:8080` | API `:8001` | Live API `:8011`

---

## Start Commands

```bash
setsid ~/.local/bin/brk >> ~/.brk/log 2>&1 &                    # BRK
setsid uv run uvicorn api.main:app --port 8001 >> /tmp/api.log 2>&1 &  # API (legacy systemd)
docker start mempool-electrs                                     # electrs
docker compose -f docker-compose.live.yml up -d                 # Live stack (worker + API :8011)
```

---

## BRK (Bitcoin Research Kit)

**Problema noto**: BRK causa system freeze durante fase "Flushing" per I/O intensivo.

**Soluzione**: Ridurre priorità I/O prima del sync:
```bash
# Avvia BRK
setsid ~/.local/bin/brk >> ~/.brk/log 2>&1 &

# Applica ionice (IMPORTANTE per evitare freeze)
BRK_PID=$(pgrep brk)
sudo ionice -c3 -p $BRK_PID      # I/O class "idle"
sudo renice -n 10 -p $BRK_PID    # CPU priority ridotta
```

**Monitoraggio**:
```bash
tail -f ~/.brk/log                           # Progress
curl -s http://localhost:3110/api/v1/status  # API (disponibile dopo sync)
```

---

## Agents & Skills

> **Context Optimization**: Delegate to agents early. Main context = orchestration only.

| Agent | Use For | Model |
|-------|---------|-------|
| bitcoin-onchain-expert | ZMQ, Bitcoin Core | opus |
| mempool-analyzer | Histogram, clustering, price est. | opus |
| alpha-debug | Bug hunting (auto-triggered) | opus |
| alpha-evolve | Multi-implementation | opus |
| alpha-visual | Visual validation | opus |
| transaction-processor | Binary parsing, filtering | sonnet |
| data-streamer | WebSocket server | sonnet |
| visualization-renderer | Canvas/WebGL | sonnet |
| tdd-guard | TDD enforcement | sonnet |

| Skill | Savings |
|-------|---------|
| pytest-test-generator | 83% |
| github-workflow | 79% |
| pydantic-model-generator | 75% |

---

## Repository Structure

```
UTXOracle/
├── UTXOracle.py          # Reference (IMMUTABLE)
├── api/, frontend/       # Backend + Dashboard
├── scripts/{metrics/, derivatives/, alerts/, backtest/, clustering/}
├── tests/, specs/, docs/
└── .claude/{agents/, skills/}
```

---

## Development Rules

### NEVER
- `--no-verify` | Disable tests | Commit without testing | Hardcode secrets

### ALWAYS
- `uv run pytest` before commit | `ruff check . && ruff format .` | Use `uv` (not pip)
- Update `docs/ARCHITECTURE.md` for architecture changes

### SpecKit Markers
- **[P]**: Only for tasks editing DIFFERENT files
- **[E]**: Complex algorithmic tasks (alpha-evolve)

---

## TDD Workflow

```bash
uv run pytest tests/test_x.py::test_new -v  # RED
# implement
uv run pytest tests/test_x.py::test_new -v  # GREEN
```

**When Stuck**: Max 3 attempts, then document and ask.

---

## Specs Status

| Spec | Status | Spec | Status |
|------|--------|------|--------|
| 007-010 | Complete | 011-015 | Complete |
| 016-018 | Complete | 020, 033 | Complete |
| 040 | Complete | | |

---

## WIP (Liveliness Backfill)

```bash
cat data/backfill_checkpoint.json  # Check status
nohup uv run python -m scripts.bootstrap.historical_spent_backfill --resume > backfill.log 2>&1 &
```

When complete (~927966), run: `uv run python -m scripts.integrations.validation_batch --days 30`

---

## Testing Requirements (MANDATORY)

**Ogni implementazione deve includere test:**

1. **Unit Tests**: Test per funzioni/classi individuali
2. **Integration Tests**: Test per componenti che interagiscono
3. **E2E Tests (quando applicabile)**:
   - Testa il flusso completo end-to-end
   - Usa dati reali quando possibile (non solo mock)
   - Verifica comportamento in condizioni realistiche

**Prima di considerare un task completato:**
- [ ] Unit tests passano
- [ ] Integration tests passano
- [ ] E2E tests con dati reali (se applicabile)
- [ ] Coverage adeguata per codice critico
