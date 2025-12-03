# MCP Tools Optimization per Agent

## Problema
Ogni agent carica tutti gli MCP tools disponibili, sprecando token per tools non necessari.

**Esempio**: `github` MCP (80+ tools) non serve a `bitcoin-onchain-expert`, ma viene comunque caricato nel contesto.

---

## MCP Servers Disponibili

| Server | Tools Count | Token Cost | Purpose |
|--------|-------------|------------|---------|
| github | ~80 tools | ~12,000 | GitHub operations (PR, issues, commits) |
| context7 | 2 tools | ~800 | Library documentation fetch |
| claude-self-reflect | 15 tools | ~3,000 | Conversation memory search |
| serena | 20 tools | ~4,500 | Code navigation (symbols, files) |
| gemini-cli | 4 tools | ~1,200 | Second opinion AI |
| ide | 2 tools | ~600 | VS Code diagnostics |

**Total MCP Load**: ~22,100 tokens/agent

---

## Matrice MCP per Agent

| Agent | context7 | reflect | serena | github | gemini | ide | Total |
|-------|----------|---------|--------|--------|--------|-----|-------|
| **Main Orchestrator** | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | 21,100 |
| bitcoin-onchain-expert | ✅ | ✅ | ✅ | ❌ | ⚠️ | ✅ | 10,100 |
| transaction-processor | ✅ | ✅ | ✅ | ❌ | ⚠️ | ✅ | 10,100 |
| mempool-analyzer | ✅ | ✅ | ✅ | ❌ | ⚠️ | ✅ | 10,100 |
| data-streamer | ✅ | ✅ | ✅ | ❌ | ⚠️ | ✅ | 10,100 |
| visualization-renderer | ✅ | ✅ | ✅ | ❌ | ⚠️ | ✅ | 10,100 |
| tdd-guard | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ | 8,100 |

✅ = Required
⚠️ = Optional (solo se esplicitamente richiesto)
❌ = Not needed

**Token Savings per Agent**: ~12,000 tokens (rimozione github)
**Additional Savings (tdd-guard)**: +800 tokens (rimozione context7)

---

## Breakdown per Agent

### Main Orchestrator (Claude principale)
**MCP Required**: ALL (github, context7, reflect, serena, ide)
**Reason**: Coordina tutto il workflow, gestisce PR/commits, accede a docs e naviga codice

**Token Load**: 21,100 (massimo)

---

### bitcoin-onchain-expert (Task 01)
**MCP Required**: context7, reflect, serena, ide
**MCP Excluded**: github, gemini

**Reason**:
- ✅ context7: Docs PyZMQ, Bitcoin Core RPC
- ✅ reflect: Memoria conversazioni su ZMQ patterns
- ✅ serena: Navigazione codice per integration points
- ✅ ide: Diagnostics Python
- ❌ github: Non crea PR/issues
- ❌ gemini: Non serve second opinion per task standard

**Token Load**: 9,900 (vs 21,100 = **-53%**)

---

### transaction-processor (Task 02)
**MCP Required**: context7, reflect, serena, ide
**MCP Excluded**: github, gemini

**Reason**:
- ✅ context7: Docs binary parsing, struct module
- ✅ reflect: Memoria su Bitcoin transaction format
- ✅ serena: Code navigation
- ✅ ide: Diagnostics
- ❌ github: Non crea PR/issues
- ❌ gemini: Parsing è task deterministico

**Token Load**: 9,900 (vs 21,100 = **-53%**)

---

### mempool-analyzer (Task 03)
**MCP Required**: context7, reflect, serena, ide
**MCP Excluded**: github, gemini

**Reason**:
- ✅ context7: Docs algoritmi statistici (se serve numpy)
- ✅ reflect: Memoria su algoritmo UTXOracle
- ✅ serena: Navigazione core algorithm
- ✅ ide: Diagnostics
- ❌ github: Non crea PR/issues
- ⚠️ gemini: Utile SOLO se algoritmo convergenza non funziona (debugging complesso)

**Token Load**: 9,900 base, +1,200 se serve gemini

---

### data-streamer (Task 04)
**MCP Required**: context7, reflect, serena, ide
**MCP Excluded**: github, gemini

**Reason**:
- ✅ context7: Docs FastAPI, WebSocket, Uvicorn
- ✅ reflect: Memoria su API patterns
- ✅ serena: Navigazione backend modules
- ✅ ide: Diagnostics
- ❌ github: Non crea PR/issues
- ❌ gemini: FastAPI è ben documentato

**Token Load**: 9,900 (vs 21,100 = **-53%**)

---

### visualization-renderer (Task 05)
**MCP Required**: context7, reflect, serena, ide
**MCP Excluded**: github, gemini

**Reason**:
- ✅ context7: Docs Three.js, Canvas API, WebGL
- ✅ reflect: Memoria su rendering patterns
- ✅ serena: Navigazione frontend code
- ✅ ide: Diagnostics (se TypeScript)
- ❌ github: Non crea PR/issues
- ⚠️ gemini: Utile SOLO per debugging WebGL shader complessi

**Token Load**: 9,900 base, +1,200 se serve gemini

---

### tdd-guard (TDD enforcement)
**MCP Required**: reflect, serena, ide
**MCP Excluded**: github, context7, gemini

**Reason**:
- ✅ reflect: Memoria su test patterns
- ✅ serena: Lettura test files, coverage report
- ✅ ide: pytest diagnostics
- ❌ github: Non gestisce workflow
- ❌ context7: Non serve docs (conosce pytest)
- ❌ gemini: Enforcement è rule-based

**Token Load**: 8,100 (vs 21,100 = **-62%**)

---

## Implementazione

### Opzione 1: Agent-Specific MCP Config (IDEALE)
Ogni agent ha il suo `.mcp.json` con solo i server necessari.

**Problema**: Claude Code attualmente non supporta MCP config per agent.

**Status**: ⏳ Feature request

---

### Opzione 2: Agent Instructions (ATTUALE)
Specificare in ogni agent prompt quali MCP tools usare/ignorare.

**Implementazione**:
```markdown
## MCP Tools Available

**Use These**:
- context7: Library documentation (PyZMQ, Bitcoin Core)
- claude-self-reflect: Conversation memory
- serena: Code navigation
- ide: Python diagnostics

**Ignore These** (not relevant for this task):
- github: GitHub operations (not needed for implementation)
- gemini-cli: Second opinion (use only if explicitly stuck)
```

**Savings**: ⚠️ Istruzioni occupano ~200 tokens, ma risparmiano ~12,000 in tool definitions = **net +11,800 tokens**

---

### Opzione 3: Lazy MCP Loading (FUTURO)
MCP tools caricati on-demand solo quando invocati.

**Status**: ⏳ Non disponibile in Claude Code

---

## Token Economics Finale

| Scenario | Tokens/Agent | Full Pipeline (6 agents) |
|----------|--------------|--------------------------|
| **Current** (all MCP) | 21,100 | 126,600 |
| **Optimized** (selective MCP) | 9,900 avg | 59,400 |
| **Savings** | -53% | **-67,200 tokens** ✅ |

---

## Raccomandazione

✅ **Implementare Opzione 2** (Agent Instructions) OGGI
⏳ **Monitorare Opzione 1** (Agent-Specific Config) per futuro

**Azione immediata**: Aggiungere sezione "MCP Tools Available" in ogni agent prompt.
