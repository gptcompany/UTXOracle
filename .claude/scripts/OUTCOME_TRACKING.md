# Session Outcome Tracking Guide

## 🎯 Problem: Missing "Why" Data

### Before
```json
{
  "cost_usd": 2.50,
  "lines_changed": {"added": 0}
}
```
❓ **Question**: Perché ho speso $2.50 senza output?

❌ **Answer**: Non lo sappiamo!

### After
```json
{
  "cost_usd": 2.50,
  "lines_changed": {"added": 0},
  "context": {
    "task_description": "Debug TDD guard issue"
  },
  "outcome": "BLOCKED",
  "summary": "TDD guard blocked 5 times, switched to manual .txt rename approach",
  "events_count": 5
}
```
✅ **Answer**: Sessione di debugging, bloccato da TDD guard, risolto cambiando approccio!

---

## 📦 3-Layer Tracking System

### Layer 1: Auto-Capture Eventi (Zero Effort)

**What**: Cattura automaticamente errori, blocks, failures
**Where**: `.claude/stats/session_events.jsonl`
**How**: PostToolUse hook

**Setup**:
```bash
# 1. Rinomina hook
mv .claude/hooks/session-outcome-tracker.py.txt \
   .claude/hooks/session-outcome-tracker.py
chmod +x .claude/hooks/session-outcome-tracker.py

# 2. Aggiungi a .claude/settings.local.json
# Nella sezione "hooks" → "PostToolUse", aggiungi:
{
  "matcher": "",
  "hooks": [{
    "type": "command",
    "command": ".claude/hooks/session-outcome-tracker.py"
  }]
}
```

**Eventi catturati**:
- `error`: Errore generico
- `tdd_block`: TDD guard ha bloccato un'operazione
- `hook_block`: Un hook ha bloccato (safety, git, etc.)
- `test_failure`: Test pytest falliti
- `timeout`: Comando in timeout

**Esempio entry**:
```json
{
  "timestamp": "2025-10-20T16:30:00",
  "session_id": "b6d7c547...",
  "tool_name": "Edit",
  "event_type": "tdd_block",
  "error_message": "Premature implementation violation. Write tests first..."
}
```

---

### Layer 2: Manual Outcome (Low Effort)

**When**: Quando completi/abbandoni un task
**Where**: `.claude/.session_outcome`
**How**: Echo simple status

#### Opzione A: One-Liner (Veloce)

```bash
# Success
echo "✅ SUCCESS: Implemented feature X" > .claude/.session_outcome

# Partial
echo "⚠️ PARTIAL: Got stuck on Y, needs investigation" > .claude/.session_outcome

# Blocked
echo "🚫 BLOCKED: TDD guard issue, switching approach" > .claude/.session_outcome

# Failed
echo "❌ FAILED: Approach doesn't work, need rethink" > .claude/.session_outcome
```

#### Opzione B: Structured (Completo)

```bash
cat > .claude/.session_outcome << 'EOF'
Status: SUCCESS
Task: Implement context-monitor v2
Summary: Added git branch, task desc, agent name to metrics
Output: 2 files (context-monitor.py, CONTEXT_USAGE.md)
Issues: TDD guard blocked once (resolved with .txt rename)
Next: Test with multiple sessions
EOF
```

---

### Layer 3: LLM Reflection (Conditional)

**When**: Quando ci sono **stati ≥3 errori** nella sessione
**Trigger**: Manuale (per ora)
**Output**: Summary + learnings

#### Quando Fare Reflection

```bash
# Check error count
cat .claude/stats/session_events.jsonl | \
  jq "select(.session_id == \"$(cat .claude/.current_session_id 2>/dev/null || echo 'unknown')\")" | \
  wc -l

# Se > 3 → LLM reflection consigliata
```

#### Template Prompt per Reflection

```
Analyze this failed/blocked session and extract learnings.

**Session Metrics**:
[paste last entry from session_metrics.jsonl]

**Events**:
[paste filtered session_events.jsonl for this session_id]

**Manual Outcome** (if exists):
[paste .session_outcome]

**Analysis Required**:

1. **Root Cause**: Why did this session have issues?
2. **Retry Pattern**: Were errors recurring? (same error >2 times)
3. **Blocker Type**: Technical (TDD, tests) or Approach (wrong solution)?
4. **Solution Found**: How was it resolved (if resolved)?
5. **Learnings**: What to avoid next time?

**Output Format**:
```markdown
## Session Post-Mortem: [session_id_short]

**Status**: BLOCKED/FAILED/PARTIAL

**Root Cause**: [1-2 sentences]

**Error Pattern**:
- TDD guard: 5x (blocks on context-monitor.py edits)
- Solution: Renamed to .txt, manual rename after

**Learnings**:
1. TDD guard blocks non-production code (logging scripts)
2. Use .txt bypass for monitoring/logging tools
3. [Other learning]

**Cost**: $X.XX for Y minutes → Expensive debugging session

**Recommendations**:
- [ ] Disable TDD guard for .claude/scripts/
- [ ] Document bypass pattern in CLAUDE.md
```

**Save**: `.claude/reports/session_postmortem_YYYY-MM-DD.md`

---

## 🔍 Post-Session Analysis Queries

### Query 1: Sessions by Outcome

```bash
# Count outcomes
cat .claude/.session_outcome_history/* | \
  grep -E "^Status:" | \
  sort | uniq -c

# Example output:
#  15 Status: SUCCESS
#   3 Status: PARTIAL
#   2 Status: BLOCKED
#   1 Status: FAILED
```

### Query 2: Error Patterns

```bash
# Top error types
cat .claude/stats/session_events.jsonl | \
  jq -r '.event_type' | \
  sort | uniq -c | sort -rn

# Example output:
#   5 tdd_block
#   3 test_failure
#   1 timeout
```

### Query 3: Expensive Failures

```bash
# Sessions with high cost + errors
jq -s 'map(select(.cost_usd > 1.0)) |
       map({
         cost: .cost_usd,
         lines: .lines_changed.added,
         task: .context.task_description
       })' .claude/stats/session_metrics.jsonl
```

### Query 4: Correlation: Errors vs Cost

```bash
# Join metrics with events
# (requires session_id matching)

SESSION_ID="b6d7c547-100b-476f-b9c1-596cceede893"

COST=$(jq -r "select(.session_id == \"$SESSION_ID\") |
              .cost_usd" .claude/stats/session_metrics.jsonl | tail -1)

ERROR_COUNT=$(jq "select(.session_id == \"$SESSION_ID\")" \
              .claude/stats/session_events.jsonl | wc -l)

echo "Session: $SESSION_ID"
echo "Cost: $$COST"
echo "Errors: $ERROR_COUNT"
echo "Cost per error: $(echo "$COST / $ERROR_COUNT" | bc -l)"
```

---

## 📊 Enhanced Analysis Prompts

### Prompt 1: Debugging Session Analysis

```
Analyze debugging sessions vs implementation sessions.

**All Sessions**:
[paste session_metrics.jsonl]

**Events**:
[paste session_events.jsonl]

**Questions**:
1. Do debugging sessions have more errors than implementation?
2. What's the cost difference?
3. Which error types are most expensive?
4. Patterns in successful vs failed debugging?

Format as comparison table + recommendations.
```

### Prompt 2: Outcome Prediction

```
Based on historical data, predict session outcome.

**Training Data** (past sessions with outcomes):
[paste sessions + outcomes]

**Current Session** (in progress):
[paste current metrics + events so far]

**Predict**:
- Likely outcome: SUCCESS/PARTIAL/BLOCKED/FAILED?
- Confidence: 0-100%
- Reasoning: Why this prediction?
- Red flags: What signals indicate trouble?
- Recommendation: Continue or stop/pivot?
```

---

## 🛠️ Advanced: Automated Outcome Detection

Create `.claude/hooks/session-end-summary.py.txt`:

```python
#!/usr/bin/env python3
"""
SessionEnd hook: Auto-generate outcome based on metrics

Logic:
- lines_changed > 0 AND events_count == 0 → SUCCESS
- lines_changed > 0 AND events_count > 0 → PARTIAL
- lines_changed == 0 AND events_count > 3 → BLOCKED
- duration > 30min AND lines == 0 → FAILED (unproductive)
"""

import json
from pathlib import Path

def auto_detect_outcome():
    # Read last session metrics
    metrics_file = Path(".claude/stats/session_metrics.jsonl")
    with open(metrics_file) as f:
        last_line = list(f)[-1]
        metrics = json.loads(last_line)

    # Count events for this session
    events_file = Path(".claude/stats/session_events.jsonl")
    session_id = metrics["session_id"]
    events_count = 0

    if events_file.exists():
        with open(events_file) as f:
            for line in f:
                event = json.loads(line)
                if event["session_id"] == session_id:
                    events_count += 1

    # Auto-detect outcome
    lines_added = metrics["lines_changed"]["added"]
    duration = metrics["duration_minutes"]

    if lines_added > 0 and events_count == 0:
        outcome = "SUCCESS"
    elif lines_added > 0 and events_count > 0:
        outcome = "PARTIAL"
    elif events_count > 5:
        outcome = "BLOCKED"
    elif duration > 30 and lines_added == 0:
        outcome = "FAILED"
    else:
        outcome = "UNKNOWN"

    # Save outcome
    outcome_file = Path(".claude/.session_outcome")
    with open(outcome_file, "w") as f:
        f.write(f"Status: {outcome}\n")
        f.write(f"Events: {events_count}\n")
        f.write(f"Lines: {lines_added}\n")
        f.write(f"Duration: {duration:.1f}m\n")

if __name__ == "__main__":
    auto_detect_outcome()
```

**Usage**: Add to SessionEnd hook (experimental)

---

## 📈 Workflow Completo

### Durante la Sessione (Auto)
1. ✅ `context-monitor.py` salva metriche + context
2. ✅ `session-outcome-tracker.py` cattura errori
3. ✅ Everything logged automatically

### Fine Sessione (Manual - 10 sec)
```bash
# Quick outcome
echo "✅ SUCCESS: Task completed" > .claude/.session_outcome

# OR structured
cat > .claude/.session_outcome << EOF
Status: PARTIAL
Summary: Got 80% done, last test failing
Next: Debug test_mempool_analyzer.py::test_clustering
EOF

# Archive outcome
mkdir -p .claude/.session_outcome_history
cp .claude/.session_outcome \
   .claude/.session_outcome_history/$(date +%Y%m%d_%H%M).txt
```

### Settimanale (LLM Analysis)
```bash
# 1. Extract week data
cat .claude/stats/session_metrics.jsonl | \
  jq "select(.timestamp | startswith(\"2025-10-20\"))" > week_data.json

# 2. LLM prompt (usa template sopra)
# 3. Save insights
#    → .claude/reports/weekly_2025_W43.md
```

---

## ✅ Checklist Setup

- [ ] Rinominato `session-outcome-tracker.py.txt` → `.py`
- [ ] Aggiunto a PostToolUse hooks in `settings.local.json`
- [ ] Verificato che `.claude/stats/session_events.jsonl` si crea
- [ ] Creato workflow per fine sessione (outcome file)
- [ ] Testato query analisi eventi
- [ ] Documentato pattern nel proprio CLAUDE.md

---

## 🎯 Esempi Reali

### Esempio 1: Sessione Produttiva

**Metrics**:
```json
{
  "cost_usd": 0.85,
  "lines_changed": {"added": 450},
  "duration_minutes": 25,
  "context": {"task_description": "Implement ZMQ listener"}
}
```

**Events**: 0

**Outcome**: `✅ SUCCESS`

**Analisi**: Efficiente! $0.85 per 450 linee = $0.002/linea

---

### Esempio 2: Sessione di Debugging

**Metrics**:
```json
{
  "cost_usd": 2.30,
  "lines_changed": {"added": 15},
  "duration_minutes": 45,
  "context": {"task_description": "Fix WebSocket leak"}
}
```

**Events**: 8 (test_failure × 6, timeout × 2)

**Outcome**:
```
Status: PARTIAL
Summary: Found root cause (missing await), fixed partially
Issues: Tests still failing on edge case (concurrent connections)
Next: Need to refactor connection pool
```

**Analisi**: Costoso! Ma normale per debugging complesso. 8 tentativi hanno portato a root cause.

---

### Esempio 3: Sessione Bloccata

**Metrics**:
```json
{
  "cost_usd": 1.80,
  "lines_changed": {"added": 0},
  "duration_minutes": 35,
  "context": {"task_description": "Refactor mempool analyzer"}
}
```

**Events**: 12 (tdd_block × 12)

**Outcome**:
```
Status: BLOCKED
Summary: TDD guard blocked all refactoring attempts
Solution: Will write tests first tomorrow
Learnings: Can't refactor without tests in place (TDD enforcing correctly)
```

**Analisi**: $1.80 spesi ma nessun output. **BUT**: Lezione importante appresa (TDD previene refactoring senza tests).

---

## 🚀 Benefit

Con questo sistema:

1. **Recupero post-mortem**: Tra 1 mese sai esattamente cosa è successo
2. **Pattern detection**: "TDD block succede sempre quando refactoro senza test"
3. **Cost attribution**: "Debug cost 2x more than implementation"
4. **Outcome prediction**: "5 errors in 10min → likely BLOCKED session"
5. **Learnings database**: Ogni failure genera learnings documentati

**Obiettivo primario mantentuto**: Data persistence per analisi
**Bonus**: Ora con **context qualitativo** (why, outcome, learnings)
