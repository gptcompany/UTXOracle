# 🔍 TDD Guard vs Auto-Test - Analisi Complementarietà

## 📊 Cosa Fa Ciascuno

### **TDD Guard** (già installato)

**Scopo**: ENFORCEMENT (blocca violazioni TDD)

**Funzionamento**:
```
Claude tenta: Write production code
         ↓
TDD Guard: ❌ BLOCKED! Nessun test failing
         ↓
Claude: Scrive test RED first
         ↓
TDD Guard: ✅ OK, procedi
```

**Cosa BLOCCA**:
- ❌ Implementation senza test failing (RED first)
- ❌ Over-implementation (oltre test requirements)
- ❌ Multiple test additions (un test alla volta)

**Cosa NON FA**:
- ❌ Non esegue test
- ❌ Non verifica che test passino
- ❌ Non dà feedback su test failures

---

### **Auto-Test** (proposto, non installato)

**Scopo**: AUTOMATION (esegue test automaticamente)

**Funzionamento**:
```
Claude modifica: live/backend/zmq_listener.py
         ↓
Auto-Test: Rileva modifica Python
         ↓
Auto-Test: Esegue pytest tests/test_live/test_zmq_listener.py
         ↓
Output: ✅ 5 passed / ❌ 2 failed
         ↓
Claude: Vede failures, fixxa
```

**Cosa FA**:
- ✅ Esegue test automaticamente dopo edit
- ✅ Mostra output test a Claude
- ✅ Feedback immediato su failures

**Cosa NON FA**:
- ❌ Non blocca niente
- ❌ Non enforce TDD workflow
- ❌ Solo esecuzione, no enforcement

---

## 🤝 Sono Complementari!

| Aspetto | TDD Guard | Auto-Test | Complementari? |
|---------|-----------|-----------|----------------|
| **Enforce test-first** | ✅ | ❌ | Sì - TDD Guard forza, Auto-test aiuta |
| **Esegue test** | ❌ | ✅ | Sì - TDD Guard non esegue, Auto-test sì |
| **Blocca violazioni** | ✅ | ❌ | Sì - enforcement vs automation |
| **Feedback loop** | ❌ | ✅ | Sì - Auto-test chiude loop |

---

## 🎯 Workflow Completo (Con Entrambi)

### **Scenario: Aggiungere feature ZMQ listener**

```python
# Step 1: Claude tenta implementazione
Write: live/backend/zmq_listener.py
  def listen_transactions():
      # Implementation...

# TDD Guard:
❌ BLOCKED! No failing test found for zmq_listener.py
   Write test first (RED), then implementation (GREEN)

# Step 2: Claude scrive test
Write: tests/test_live/test_zmq_listener.py
  def test_listen_transactions():
      # Test implementation
      assert zmq_listener.listen_transactions() == expected

# TDD Guard:
✅ OK - Test file created

# Auto-Test (se attivo):
🧪 Running: pytest tests/test_live/test_zmq_listener.py
❌ FAILED - ImportError: No module 'zmq_listener'
   (Test RED - come previsto!)

# Step 3: Claude implementa (TDD Guard permette, test è RED)
Write: live/backend/zmq_listener.py
  def listen_transactions():
      return []  # Minimal implementation

# Auto-Test:
🧪 Running: pytest tests/test_live/test_zmq_listener.py
✅ PASSED - 1 test passed

# Step 4: Refactor (opzionale)
Edit: live/backend/zmq_listener.py
  # Improve implementation

# Auto-Test:
🧪 Running: pytest tests/test_live/test_zmq_listener.py
✅ PASSED - Still green!
```

**Risultato**:
- TDD Guard: Enforzò RED → GREEN workflow
- Auto-Test: Diede feedback immediato su ogni step

---

## ⚖️ UTXOracle: Serve Auto-Test?

### **Considerazioni KISS/YAGNI**

| Pro | Contro |
|-----|--------|
| ✅ Feedback automatico immediato | ❌ Token/tempo extra per ogni modifica |
| ✅ Scopre errori subito | ❌ pytest può essere lento (>2s) |
| ✅ Simula CI locale | ❌ Frontend JS non ha test setup |
| ✅ Claude vede failures senza chiedere | ❌ Agenti già testano manualmente quando serve |

### **Stato Attuale UTXOracle**

```
Backend Python:
  • TDD Guard: ✅ Attivo (enforcement)
  • Auto-test: ❌ Non configurato
  • Test command: uv run pytest
  • Test speed: ~2-3s (ok per manual, lento per auto)

Frontend JS:
  • TDD Guard: ❌ Disabilitato (frontend/**/*.js ignorato)
  • Auto-test: ❌ Non serve (no test setup, vanilla JS)
  • Test command: Nessuno (no Jest/Vitest)

Agenti:
  • Già eseguono pytest manualmente quando necessario
  • TDD Guard li forza a scrivere test first
```

---

## 💡 Raccomandazione

### **KISS Approach (Raccomandato per ora)**

**Mantieni solo TDD Guard** ✅

**Motivi**:
1. TDD Guard già enforce discipline (obiettivo principale)
2. Auto-test aggiunge overhead (2-3s × 10 modifiche = 30s)
3. Agenti già eseguono `uv run pytest` quando serve
4. Frontend non ha test (auto-test inutile)
5. YAGNI - no complessità prematura

**Workflow attuale (funziona bene)**:
```
1. TDD Guard blocca → Claude scrive test
2. Claude esegue: uv run pytest tests/test_module.py
3. Vede output, fixa se fallisce
4. Procede
```

---

### **Quando Aggiungere Auto-Test** (Futuro)

Aggiungi auto-test SOLO SE:

1. **Test diventano veloci** (<500ms)
   - Dopo refactor Rust/Cython
   - Con test paralleli
   
2. **Sviluppo frontend intenso**
   - Setup Jest/Vitest
   - Test component Canvas/Three.js
   
3. **CI/CD locale importante**
   - Pre-commit automation
   - Continuous feedback required

4. **Più di 100 test**
   - Feedback loop manuale troppo lento
   - Auto-test risparmia tempo

---

## 📝 Implementazione Auto-Test (Se Serve)

### **Versione Python per UTXOracle**

```python
#!/usr/bin/env python3
# .claude/hooks/auto-test.py

import os
import sys
import json
import subprocess
from pathlib import Path

def should_run_tests(file_path):
    """Check if file change should trigger tests"""
    
    # Only Python files
    if not file_path.endswith('.py'):
        return False
    
    # Skip non-test changes in specific dirs
    skip_dirs = ['archive/', 'historical_data/', '.venv/']
    if any(skip in file_path for skip in skip_dirs):
        return False
    
    return True

def find_test_file(file_path):
    """Find corresponding test file"""
    
    # If already a test file, run it
    if '/test_' in file_path or file_path.startswith('tests/'):
        return file_path
    
    # Map source file to test file
    # live/backend/zmq_listener.py → tests/test_live/test_zmq_listener.py
    path = Path(file_path)
    
    if 'live/backend/' in file_path:
        test_file = f"tests/test_live/test_{path.name}"
    elif 'core/' in file_path:
        test_file = f"tests/test_core/test_{path.name}"
    else:
        # Default: tests/test_<filename>
        test_file = f"tests/test_{path.name}"
    
    return test_file if Path(test_file).exists() else None

def main():
    try:
        input_data = json.loads(sys.stdin.read())
        
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        
        # Only trigger on Write/Edit
        if tool_name not in ["Write", "Edit", "MultiEdit"]:
            sys.exit(0)
        
        file_path = tool_input.get("file_path", "")
        
        if not should_run_tests(file_path):
            sys.exit(0)
        
        test_file = find_test_file(file_path)
        
        if not test_file:
            # No test file found, silent pass
            sys.exit(0)
        
        # Run tests
        result = subprocess.run(
            ["uv", "run", "pytest", test_file, "-v"],
            capture_output=True,
            text=True,
            timeout=10  # 10s max
        )
        
        # Show output to Claude
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "message": (
                    f"🧪 Auto-Test Results for {Path(file_path).name}:\n\n"
                    f"{result.stdout}\n"
                    f"{'✅ PASSED' if result.returncode == 0 else '❌ FAILED'}"
                )
            }
        }
        
        print(json.dumps(output))
        sys.exit(0)
        
    except subprocess.TimeoutExpired:
        print(json.dumps({
            "hookSpecificOutput": {
                "message": "⚠️  Tests timeout (>10s), skipped auto-run"
            }
        }))
        sys.exit(0)
    except Exception:
        # Fail open
        sys.exit(0)

if __name__ == "__main__":
    main()
```

**Configurazione**:
```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Write|Edit|MultiEdit",
      "hooks": [{
        "type": "command",
        "command": ".claude/hooks/auto-test.py"
      }]
    }]
  }
}
```

---

## 🎯 Conclusione

### **Per UTXOracle OGGI**

✅ **Mantieni TDD Guard** (enforcement)  
❌ **Defer Auto-Test** (YAGNI, overhead non giustificato)

**Motivo**: TDD Guard già garantisce test-first, auto-test aggiunge poco valore con overhead significativo.

### **Aggiungi Auto-Test QUANDO**

- Test diventano veloci (<500ms)
- Setup test frontend (Jest)
- CI/CD locale diventa priorità
- >100 test nel progetto

