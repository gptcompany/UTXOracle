# 🔍 Analisi Hook EvanL1/claude-code-hooks per UTXOracle

## 📊 Hook Disponibili vs Necessità UTXOracle

| Hook | Utilità | Priorità | Motivo |
|------|---------|----------|--------|
| **git-safety-check.py** | ✅✅✅ ALTA | 🔴 P1 | Previeni git push --force, delete main, commit .env |
| **file-stats.py** | ✅✅ MEDIA | 🟡 P2 | Track code complexity (utile con 6 agenti) |
| **terminal-ui.sh** | ✅ BASSA | 🟢 P3 | Estetica (nice-to-have) |
| **cargo-auto-format.py** | ⏰ FUTURA | ⏸️ Defer | Solo quando aggiungi Rust (non ora) |
| **docker-validator.py** | ❌ NO | - | No Docker deployment attualmente |
| **npm-safety-check.py** | ❌ NO | - | Frontend vanilla JS (no npm) |
| **java-build-check.py** | ❌ NO | - | Progetto Python/JS |
| **aws-safety-check.py** | ❌ NO | - | No cloud deployment ora |

---

## ✅ RACCOMANDATI (3 hook)

### **P1: git-safety-check.py** ⭐⭐⭐

**Cosa fa**:
- ❌ Blocca `git push --force` su main/master
- ❌ Blocca delete di branch main
- ⚠️ Warn su commit di file sensibili (.env, secrets)
- ⚠️ Alert su force push in generale

**Perché serve a UTXOracle**:
```bash
# Scenari protetti:
1. Agent prova push --force dopo rebase → BLOCCATO
2. Commit accidentale .env con BROWSERBASE_API_KEY → WARNING
3. Delete main branch → BLOCCATO
4. Commit large files (>50MB) → WARNING
```

**Integrazione**:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "/media/sam/1TB/UTXOracle/.claude/hooks/git-safety-check.py"
        }]
      }
    ]
  }
}
```

**ROI**: 🔴 CRITICO - Previene disasters (1 errore risparmiato > 10h recovery)

---

### **P2: file-stats.py** ⭐⭐

**Cosa fa**:
- 📊 Line count dopo ogni modifica
- 📈 Function/class count
- 📉 Complexity tracking

**Perché serve a UTXOracle**:
```python
# Aiuta a monitorare:
- Agent genera file troppo complesso (>500 LOC) → Refactor
- Module cresce (100→500 LOC) → Consider split
- Too many functions (>20) → Module doing too much
```

**Output esempio**:
```
📊 File Stats: live/backend/zmq_listener.py
  Lines: 342 (+45 from last edit)
  Functions: 12
  Classes: 3
  Complexity: MEDIUM (suggest review if >500 LOC)
```

**ROI**: 🟡 MEDIO - Mantiene qualità code (prevent bloat)

---

### **P3: terminal-ui.sh** ⭐

**Cosa fa**:
- 🎨 Beautiful terminal UI
- ⏰ Time display
- 📁 Current path
- 🔧 Mode indicator (plan/code)

**Perché utile** (ma non critico):
- Developer experience migliorata
- Facile vedere working directory
- Mode awareness (plan vs code)

**ROI**: 🟢 BASSO - Nice-to-have (estetica)

---

## ⏸️ DEFER (per futuro Rust)

### **cargo-auto-format.py**

**Quando serve**: Quando refactori algoritmo core in Rust

**Setup futuro**:
```bash
# Quando aggiungi Rust:
.claude/hooks/cargo-auto-format.py

# Ricorda:
cargo fmt         # Format Rust code
cargo clippy      # Lint Rust code
```

**Status**: ⏸️ Non implementare ora (YAGNI)

---

## ❌ NON NECESSARI

| Hook | Perché NO |
|------|-----------|
| **docker-validator.py** | No Docker deployment (solo locale) |
| **npm-safety-check.py** | Frontend vanilla JS (zero build, no package.json) |
| **java-build-check.py** | Progetto Python/JS |
| **aws-safety-check.py** | No cloud (local Bitcoin node) |

---

## 🎯 Setup Raccomandato

### **Implementa SUBITO** (P1):

```bash
# 1. Download git-safety-check.py
curl -o .claude/hooks/git-safety-check.py \
  https://raw.githubusercontent.com/EvanL1/claude-code-hooks/main/hooks/git-safety-check.py

chmod +x .claude/hooks/git-safety-check.py

# 2. Configura in settings.local.json
# (già fatto nel template sotto)
```

### **Implementa PRESTO** (P2):

```bash
# Download file-stats.py
curl -o .claude/hooks/file-stats.py \
  https://raw.githubusercontent.com/EvanL1/claude-code-hooks/main/hooks/file-stats.py

chmod +x .claude/hooks/file-stats.py
```

### **Opzionale** (P3):

```bash
# Download terminal-ui.sh
curl -o .claude/hooks/terminal-ui.sh \
  https://raw.githubusercontent.com/EvanL1/claude-code-hooks/main/hooks/terminal-ui.sh
```

---

## 📝 Configurazione Proposta

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit|TodoWrite",
        "hooks": [{
          "type": "command",
          "command": ".claude/scripts/tdd_guard_v2.py"
        }]
      },
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command", 
          "command": ".claude/hooks/git-safety-check.py",
          "description": "Prevent dangerous Git operations"
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": ".claude/hooks/post-tool-use.py"
        }]
      },
      {
        "matcher": "Write|Edit",
        "hooks": [{
          "type": "command",
          "command": ".claude/hooks/file-stats.py",
          "description": "Track file complexity"
        }]
      }
    ],
    "SubagentStop": [
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": ".claude/hooks/subagent-checkpoint.sh"
        }]
      }
    ]
  }
}
```

---

## 🔒 Sicurezza Aggiuntiva Specifica UTXOracle

### **File Sensibili da Proteggere**:

```python
# In git-safety-check.py, aggiungi pattern UTXOracle:
SENSITIVE_PATTERNS = [
    r'\.env$',                    # Environment variables
    r'bitcoin\.conf$',            # Bitcoin RPC credentials
    r'\.cookie$',                 # Bitcoin auth cookie
    r'BROWSERBASE_API_KEY',       # In any file
    r'BROWSERBASE_PROJECT_ID',    # In any file
    r'rpcuser.*password',         # In config files
]

LARGE_FILE_THRESHOLD = 50_000_000  # 50MB (historical HTML ok, but warn)
```

### **Git Operations Protette**:

```bash
# BLOCKED:
git push --force origin main
git branch -D main
git reset --hard HEAD~10  # On main

# WARNED:
git commit .env
git add bitcoin.conf
git commit -m "Added API keys"  # Scans message for "key", "password", "secret"
```

---

## 📊 ROI Totale

| Hook | Setup Time | Token Cost | Disaster Prevention | Value |
|------|------------|------------|---------------------|-------|
| git-safety-check.py | 10 min | ~100 tokens/use | 🔴 CRITICAL | +++++ |
| file-stats.py | 5 min | ~50 tokens/use | 🟡 MEDIUM | +++ |
| terminal-ui.sh | 2 min | ~20 tokens/use | 🟢 LOW | + |

**Total Setup**: 17 minuti
**Total Prevention Value**: >10 hours recovery time risparmiato

---

## 🚀 Prossimi Passi

1. ✅ **Implementa git-safety-check.py** (SUBITO)
2. ✅ **Testa con**: `git push --force` → Should block
3. ✅ **Aggiungi file-stats.py** (questa settimana)
4. ⏸️ **Defer cargo-auto-format.py** (quando aggiungi Rust)

