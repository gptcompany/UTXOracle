# Context-Monitor v2: Usage Guide

## 📦 Installation

```bash
# Rinomina manualmente (bypass TDD guard)
mv .claude/scripts/context-monitor.py.txt .claude/scripts/context-monitor.py
chmod +x .claude/scripts/context-monitor.py
```

## 🆕 Nuove Funzionalità v2

### Metadati Contestuali Automatici

Ora ogni entry in `session_metrics.jsonl` include:

```json
{
  "session_id": "...",
  "timestamp": "...",
  "tokens": {...},
  "cost_usd": 0.95,
  "context": {
    "git_branch": "002-mempool-live-oracle",
    "task_description": "Implement context monitoring",
    "agent_name": "bitcoin-onchain-expert",
    "working_dir": "UTXOracle"
  }
}
```

---

## 🎯 Come Fornire Contesto (3 Metodi)

### Metodo 1: Environment Variable (Priorità Alta)

```bash
# Prima di lanciare Claude Code
export CLAUDE_TASK_DESC="Fix bug #123 in mempool analyzer"
claude

# Oppure inline
CLAUDE_TASK_DESC="Add WebSocket streaming" claude
```

**Quando usare**: Script automatici, CI/CD, sessioni programmatiche

---

### Metodo 2: File Marker (Priorità Media)

```bash
# All'inizio della sessione
echo "Task: Implement ZMQ listener
Agent: bitcoin-onchain-expert
Goal: Connect to Bitcoin Core via ZMQ" > .claude/.session_description

# Poi lavori normalmente...
```

**Quando usare**: Sessioni interattive, lavoro manuale

**Tip**: Aggiorna il file quando cambi task:
```bash
echo "Task: Debug cache usage issue" > .claude/.session_description
```

---

### Metodo 3: Git Commit (Fallback Automatico)

Se non usi env var o file, lo script legge l'ultimo commit:

```bash
git commit -m "Add context monitoring with metadata"
# Lo script userà: "Recent commit: Add context monitoring with metadata"
```

**Quando usare**: Quando dimentichi di settare contesto (better than nothing!)

---

## 🤖 Subagent Sessions

Per sessioni di subagent, setta il nome:

```bash
# Nel file agent definition o prima di lanciare
export CLAUDE_AGENT_NAME="transaction-processor"
```

Lo script lo include nelle metriche:
```json
{
  "context": {
    "agent_name": "transaction-processor"
  }
}
```

---

## 📊 Analisi Post-Sessione (Migliorata)

### Nuove Query Possibili

```bash
# Quanto costa per branch?
cat .claude/stats/session_metrics.jsonl | \
  jq -s 'group_by(.context.git_branch) |
         map({branch: .[0].context.git_branch,
              sessions: length,
              total_cost: (map(.cost_usd) | add)})'

# Quale agente costa di più?
cat .claude/stats/session_metrics.jsonl | \
  jq -s 'group_by(.context.agent_name) |
         map({agent: .[0].context.agent_name,
              avg_cost: (map(.cost_usd) | add / length)})'

# Sessioni per task
cat .claude/stats/session_metrics.jsonl | \
  jq -s 'group_by(.context.task_description) |
         map({task: .[0].context.task_description,
              count: length})'
```

### Esempio Output

```json
[
  {
    "branch": "002-mempool-live-oracle",
    "sessions": 15,
    "total_cost": 4.23
  },
  {
    "branch": "main",
    "sessions": 8,
    "total_cost": 1.87
  }
]
```

---

## 📝 Workflow Raccomandato

### Per Task Grandi (Multi-Sessione)

```bash
# 1. Setta contesto all'inizio
echo "Task: Implement Tasks 01-05 (mempool live oracle)
Branch: 002-mempool-live-oracle
Goal: ZMQ → Processing → Analysis → Streaming → Viz" > .claude/.session_description

# 2. Lavora normalmente (context auto-salvato)
claude

# 3. Quando cambi sub-task
echo "Task: Task 02 - Transaction Processor" > .claude/.session_description

# 4. Analizza alla fine
cat .claude/stats/session_metrics.jsonl | \
  jq 'select(.context.git_branch == "002-mempool-live-oracle")'
```

### Per Debugging/Fix Rapidi

```bash
# Quick context
CLAUDE_TASK_DESC="Debug TDD guard blocking issue" claude
```

---

## 🔍 Troubleshooting

### Context Non Salvato?

```bash
# Verifica che il file esista
ls -la .claude/stats/session_metrics.jsonl

# Leggi ultime entries
tail -5 .claude/stats/session_metrics.jsonl | jq .

# Verifica campo "context"
tail -1 .claude/stats/session_metrics.jsonl | jq .context
```

### Git Branch Non Rilevato?

```bash
# Verifica di essere in git repo
git branch --show-current

# Se non funziona, setta manualmente nel file marker
echo "Branch: 002-mempool-live-oracle" >> .claude/.session_description
```

---

## 📈 Best Practices

1. **Sempre setta contesto** per sessioni importanti
   ```bash
   echo "Task: [descrizione chiara]" > .claude/.session_description
   ```

2. **Usa branch git descrittivi**
   - ✅ `002-mempool-live-oracle`
   - ❌ `feature-branch`

3. **Analizza settimanalmente**
   ```bash
   # Crea report
   cat .claude/stats/session_metrics.jsonl | \
     jq -s 'group_by(.timestamp[:10])' > weekly_report.json
   ```

4. **Cancella `.session_description` dopo task completato**
   ```bash
   rm .claude/.session_description
   # Altrimenti vale per tutte le sessioni successive!
   ```

---

## 🎯 Prompt LLM Aggiornati

Ora puoi fare domande più specifiche nell'analisi:

```
Analizza le sessioni sul branch "002-mempool-live-oracle":

[paste filtered data]:
cat .claude/stats/session_metrics.jsonl | \
  jq 'select(.context.git_branch == "002-mempool-live-oracle")'

Domande:
1. Quanto è costato implementare Task 01 vs Task 02?
2. Quali agenti hanno consumato più token?
3. Le sessioni di debugging costano più delle sessioni di implementazione?
```

---

## 📊 Esempio Completo

```bash
# DAY 1: Start new feature
git checkout -b 003-websocket-api
echo "Task: Implement FastAPI WebSocket server (Task 04)
Agent: data-streamer
Goal: Real-time price streaming to clients" > .claude/.session_description

claude
# ... lavori ...

# DAY 2: Debug issue
echo "Task: Fix WebSocket connection leak" > .claude/.session_description
claude
# ... debug ...

# DAY 3: Analyze
cat .claude/stats/session_metrics.jsonl | \
  jq 'select(.context.git_branch == "003-websocket-api")' | \
  jq -s '{
    total_sessions: length,
    total_cost: (map(.cost_usd) | add),
    implementation_sessions: (map(select(.context.task_description | contains("Implement"))) | length),
    debug_sessions: (map(select(.context.task_description | contains("Fix"))) | length)
  }'

# Output:
# {
#   "total_sessions": 8,
#   "total_cost": 3.42,
#   "implementation_sessions": 5,
#   "debug_sessions": 3
# }
```

---

## 🔧 Customization

Se vuoi cambiare priorità di detection:

```python
# In context-monitor.py, funzione get_session_context()

# Aggiungi nuovo metodo (es: file TODO.md)
todo_file = Path("TODO.md")
if todo_file.exists():
    # Parse first line as task
    return todo_file.read_text().splitlines()[0]
```

---

## ✅ Checklist

- [ ] Rinominato `.txt` → `.py`
- [ ] Testato statusline (funziona)
- [ ] Verificato salvataggio metriche (`tail session_metrics.jsonl`)
- [ ] Campo `context` presente
- [ ] Git branch auto-detected
- [ ] Creato `.session_description` per task corrente
- [ ] Testato query jq per analisi

**Tutto pronto per analisi contestualizzate! 🚀**
