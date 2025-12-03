# UTXOracle Skills - Analisi Estesa

## Skills Esistenti (2)

| Skill | Tokens Saved | Use Case |
|-------|--------------|----------|
| pytest-test-generator | 83% (3,000→500) | Test boilerplate automation |
| github-workflow | 79% (18,900→4,000) | PR/Issue/Commit templates |

**Total Savings**: 17,400 tokens/task

---

## Skills Proposte (5)

### 1. bitcoin-rpc-connector
**Pattern**: Connessione ripetitiva a Bitcoin Core RPC

**Template include**:
- Cookie authentication (.cookie file reading)
- bitcoin.conf parsing (user/password)
- RPC call wrapper (error handling)
- Auto-detection OS paths (Linux/macOS/Windows)

**Token Savings**: ~60% (2,500 → 1,000)

**Trigger Keywords**: "connect to bitcoin", "bitcoin rpc", "bitcoin core"

**Agenti che ne beneficiano**: bitcoin-onchain-expert, transaction-processor

---

### 2. histogram-plotter
**Pattern**: Generazione visualizzazioni HTML con Canvas

**Template include**:
- Canvas setup boilerplate
- Histogram rendering (bar chart)
- Intraday price points (line chart)
- Interactive hover tooltips
- HTML template base

**Token Savings**: ~70% (4,000 → 1,200)

**Trigger Keywords**: "plot histogram", "generate visualization", "create chart"

**Agenti che ne beneficiano**: mempool-analyzer, visualization-renderer

---

### 3. zmq-subscriber-template
**Pattern**: ZMQ subscriber setup per Bitcoin Core

**Template include**:
- ZMQ socket initialization
- Multi-topic subscription (rawtx, rawblock, hashtx)
- Binary message parsing
- Reconnection logic
- Error handling

**Token Savings**: ~65% (3,000 → 1,050)

**Trigger Keywords**: "zmq subscribe", "zmq listen", "bitcoin zmq"

**Agenti che ne beneficiano**: bitcoin-onchain-expert

---

### 4. pydantic-model-generator
**Pattern**: Auto-generazione Pydantic models da schema

**Template include**:
- Type hints generation
- Field validation rules
- Default values
- JSON schema export
- Example data

**Token Savings**: ~75% (2,000 → 500)

**Trigger Keywords**: "create model", "pydantic schema", "data validation"

**Agenti che ne beneficiano**: transaction-processor, data-streamer

---

### 5. fastapi-websocket-endpoint
**Pattern**: WebSocket endpoint setup per FastAPI

**Template include**:
- WebSocket route boilerplate
- Connection manager class
- CORS configuration
- Broadcast helper
- Error handling

**Token Savings**: ~70% (3,500 → 1,050)

**Trigger Keywords**: "websocket endpoint", "fastapi ws", "broadcast data"

**Agenti che ne beneficiano**: data-streamer, visualization-renderer

---

## Token Economics (Con 5 Nuove Skills)

| Component | Current | With New Skills | Savings |
|-----------|---------|-----------------|---------|
| Test generation | 500 | 500 | 0 |
| GitHub workflow | 4,000 | 4,000 | 0 |
| Bitcoin RPC | 2,500 | 1,000 | 1,500 ✅ |
| Histogram plot | 4,000 | 1,200 | 2,800 ✅ |
| ZMQ subscriber | 3,000 | 1,050 | 1,950 ✅ |
| Pydantic models | 2,000 | 500 | 1,500 ✅ |
| FastAPI WebSocket | 3,500 | 1,050 | 2,450 ✅ |

**New Total Savings**: 10,200 tokens/task aggiuntivi

**Grand Total**: 27,600 tokens saved per task (vs 17,400 attuali = +58%)

---

## Priorità Implementazione

1. **HIGH**: pydantic-model-generator (usato da 3+ agenti)
2. **HIGH**: bitcoin-rpc-connector (Task 01, 02)
3. **MEDIUM**: zmq-subscriber-template (Task 01)
4. **MEDIUM**: fastapi-websocket-endpoint (Task 04)
5. **LOW**: histogram-plotter (già gestito da visualization-renderer)

---

## Skill vs Subagent Decision Tree

```
Domanda: "È un pattern ripetitivo?"
├─ SÌ → "Template-driven?"
│   ├─ SÌ → SKILL (70-80% token savings)
│   └─ NO → SUBAGENT (complex reasoning)
└─ NO → SUBAGENT (one-off task)
```

**Esempi**:
- ✅ Skill: "Genera test per funzione X" (pattern ripetitivo)
- ❌ Subagent: "Implementa algoritmo convergenza" (logica complessa)
- ✅ Skill: "Crea PR template" (pattern ripetitivo)
- ❌ Subagent: "Ottimizza performance WebGL" (reasoning profondo)
