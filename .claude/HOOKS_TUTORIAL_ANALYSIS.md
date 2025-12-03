# Hooks Tutorial vs UTXOracle - Analisi

## 📊 Confronto Hook Attuali

### **UTXOracle Hooks (già implementati)**

| Hook File | Tipo | Funzione | Status |
|-----------|------|----------|--------|
| `smart-safety-check.py` | PreToolUse | Dangerous command detection + auto-checkpoint | ✅ Ottimo |
| `git-safety-check.py` | PreToolUse | Git operations protection | ✅ Ottimo |
| `post-tool-use.py` | PostToolUse | Tool usage logging | ✅ Base |
| `notification.py` | Notification | Custom notifications | ✅ Base |
| `stop.py` | Stop | End-of-response actions | ✅ Base |
| `subagent-checkpoint.sh` | SubagentStop | Auto-commit agent work | ✅ Innovativo |

---

## 🆕 Hook dal Tutorial (potenzialmente utili)

### **1. ESLint Validator** (PreToolUse)
```python
# ~/scripts/eslint-validator.py
# Valida JS/TS prima di Write/Edit
```

**Per UTXOracle**:
- ❌ NON serve: Frontend vanilla JS (no build, no linter setup)
- ⏸️ Potenziale futuro: Se aggiungi Jest/Vitest

---

### **2. Auto-Format Hook** (PostToolUse)
```bash
# Ruff format Python dopo ogni edit
if [[ "$file_path" =~ \.py$ ]]; then
    ruff format "$file_path"
    ruff check --fix "$file_path"
fi
```

**Per UTXOracle**:
- ✅ **UTILE**: Mantiene code style consistente
- ✅ Ruff già installato (pyproject.toml)
- ✅ Zero overhead (fast formatter)

**Raccomandazione**: ✅ Implementa

---

### **3. Auto-Documentation Generator** (PostToolUse)
```python
# Genera docstring automatiche con AI
if file.endswith('.py') and 'service' in file:
    generate_docstrings(file)
```

**Per UTXOracle**:
- ⚠️ **MAYBE**: Utile ma...
- ❌ Token overhead per ogni modifica
- ❌ Complessità (AI call per docstring)
- ✅ KISS alternative: Manual docstrings (più controllo)

**Raccomandazione**: ⏸️ Defer (YAGNI)

---

### **4. Test Runner Hook** (PostToolUse)
```python
# Run pytest automaticamente dopo Python edit
if file_path.endswith('.py') and file in test_map:
    pytest test_file
```

**Per UTXOracle**:
- ❌ NON serve: TDD Guard + manual pytest meglio
- ❌ Overhead: 2-3s per modifica
- ✅ Già discusso (TDD Guard vs Auto-Test)

**Raccomandazione**: ❌ No (TDD Guard sufficiente)

---

## 💡 Raccomandazioni per UTXOracle

### **IMPLEMENTA SUBITO**

#### **1. Auto-Format Hook (PostToolUse)**

File: `.claude/hooks/auto-format.py`

```python
#!/usr/bin/env python3
"""Auto-format Python files with Ruff after edits"""
import json
import sys
import subprocess
from pathlib import Path

def main():
    try:
        input_data = json.loads(sys.stdin.read())
        
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        
        # Only Python files in live/ or core/ (not tests, not archive)
        if not file_path.endswith('.py'):
            sys.exit(0)
        
        skip_dirs = ['archive/', 'historical_data/', '.venv/', 'tests/']
        if any(skip in file_path for skip in skip_dirs):
            sys.exit(0)
        
        if not Path(file_path).exists():
            sys.exit(0)
        
        # Format with Ruff (fast!)
        subprocess.run(
            ['ruff', 'format', file_path],
            capture_output=True,
            timeout=5
        )
        
        # Auto-fix linting issues
        subprocess.run(
            ['ruff', 'check', '--fix', file_path],
            capture_output=True,
            timeout=5
        )
        
        # Success message
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "message": f"✨ Auto-formatted {Path(file_path).name} with Ruff"
            }
        }
        print(json.dumps(output))
        sys.exit(0)
        
    except subprocess.TimeoutExpired:
        # Fail silently on timeout
        sys.exit(0)
    except Exception:
        # Fail open
        sys.exit(0)

if __name__ == "__main__":
    main()
```

**Configuration** (add to settings.local.json):
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{
          "type": "command",
          "command": "/media/sam/1TB/UTXOracle/.claude/hooks/auto-format.py"
        }]
      }
    ]
  }
}
```

**Benefici**:
- ✅ Code style automatico (zero effort)
- ✅ Ruff è velocissimo (<100ms)
- ✅ Auto-fix linting (unused imports, etc.)
- ✅ Consistenza tra agent e manual edits

---

### **MIGLIORA ESISTENTI**

#### **2. Enhanced post-tool-use.py**

Attuale: Solo logging
Proposto: Logging + stats + insights

**Aggiungi**:
- File type tracking (`.py`, `.js`, `.md`)
- Edit vs Write ratio
- Files most edited (hotspots)

**Esempio output**:
```
📊 Session Stats:
  • 15 edits, 3 writes
  • Hotspots: zmq_listener.py (5x), config.py (3x)
  • Languages: Python 80%, Markdown 20%
```

---

## ❌ NON Implementare (YAGNI)

| Hook Tutorial | Perché NO |
|---------------|-----------|
| **ESLint validator** | Frontend vanilla JS (no linter) |
| **JSDoc generator** | No JS docs setup |
| **Auto-test runner** | TDD Guard già enforce + overhead |
| **Auto-deploy** | No deployment automation (local dev) |
| **Slack notifications** | No team (solo project) |

---

## 🎯 Piano Implementazione

### **Oggi** (15 min):
1. ✅ Crea `auto-format.py` hook
2. ✅ Configura PostToolUse in settings.local.json
3. ✅ Testa con edit di Python file

### **Opzionale** (30 min):
4. ⚠️ Enhance post-tool-use.py con stats

---

## 📊 Hook Architecture (Completo)

```
PreToolUse:
  • smart-safety-check.py     → Dangerous commands (checkpoint + warn)
  • git-safety-check.py       → Git protection (block force push)

PostToolUse:
  • post-tool-use.py          → Tool usage logging
  • auto-format.py            → Ruff auto-format ✨ NEW

Notification:
  • notification.py           → Custom notifications

Stop:
  • stop.py                   → End-of-response

SubagentStop:
  • subagent-checkpoint.sh    → Auto-commit agents
```

---

## 🎓 Best Practices dal Tutorial

### **Hook Design**:
1. ✅ **Fail open** (exit 0 on error, not 1)
2. ✅ **Fast execution** (<500ms per hook)
3. ✅ **Specific matchers** (`Write|Edit` not `.*`)
4. ✅ **JSON output** per comunicare con Claude
5. ✅ **Timeout protection** (5-10s max)

### **Security**:
1. ✅ Absolute paths per scripts
2. ✅ Quote shell variables (`"$VAR"`)
3. ✅ Validate inputs (file paths, commands)
4. ✅ Skip sensitive files (`.env`, `.git/`)

---

## 🔄 Workflow Completo (Con Auto-Format)

```
1. Claude: Write live/backend/zmq_listener.py
   ↓
2. PreToolUse: smart-safety-check → ✅ Pass
   ↓
3. Tool executes: File written
   ↓
4. PostToolUse: auto-format.py → Ruff format + check
   ↓
5. PostToolUse: post-tool-use.py → Log to stats
   ↓
6. Claude sees: "✨ Auto-formatted zmq_listener.py with Ruff"
```

**Result**: Codice sempre formattato, zero manual effort!

---

## 🎯 Conclusione

### **Implementa ORA**:
- ✅ Auto-format hook (Ruff) - 15 min setup, value immediato

### **Già Ottimo**:
- ✅ Smart safety check
- ✅ Git safety
- ✅ Subagent checkpoint

### **Defer**:
- ❌ ESLint (non applicabile)
- ❌ Auto-test (TDD Guard basta)
- ❌ Auto-docs (YAGNI)

**UTXOracle hook system è già molto avanzato!**
Solo auto-format manca per perfezione.

