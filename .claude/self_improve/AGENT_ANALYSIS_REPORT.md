# Claude-Flow Repository Analysis Report

**Date**: 2025-10-20
**Analyzed by**: Subagent (general-purpose)
**Repository**: https://github.com/ruvnet/claude-flow
**Version**: v2.7.0-alpha.10
**Local Path**: `/media/sam/1TB/UTXOracle/CLAUDE_FLOW/`

---

## Executive Summary

The claude-flow repository is an enterprise-grade AI orchestration platform with sophisticated **session management**, **workflow automation**, **SQLite-based persistence**, and **hook-based event systems**.

**Key patterns relevant to UTXOracle's self-improvement system**:
1. ✅ Session tracking with SQLite (3 core tables)
2. ✅ Hook-based workflow automation (8 hook types)
3. ✅ Checkpoint/resume system
4. ✅ JSON export/import for portability
5. ✅ Analytics & session summary generation

**Recommendation**: Use **20% of claude-flow patterns** (session manager, hooks, SQLite basics), discard 80% (swarm coordination, neural patterns, consensus algorithms).

---

## 🎯 Key Findings

### 1. Session Management Pattern

**File**: `session-manager.js` (1,187 lines)
**Copied to**: `.claude/self_improve/reference/session-manager.js`

#### Data Structure
```javascript
{
  id: 'session-xxxxx',
  swarm_id: 'swarm-id',
  swarm_name: 'project-name',
  objective: 'task description',
  status: 'active' | 'paused' | 'stopped' | 'completed',
  created_at: DateTime,
  updated_at: DateTime,
  completion_percentage: 0-100,
  checkpoint_data: JSON,
  metadata: JSON,
  parent_pid: process.pid,
  child_pids: [pid1, pid2]
}
```

#### Key Methods (Adaptable)
- `createSession(swarmId, name, objective, metadata)` → Initialize
- `saveCheckpoint(sessionId, name, data)` → Progress snapshots
- `getActiveSessions()` → List running sessions
- `resumeSession(sessionId)` → Restore from checkpoint
- `stopSession(sessionId)` → Cleanup + terminate
- `logSessionEvent(sessionId, level, message, data)` → Structured logging
- `generateSessionSummary(sessionId)` → Analytics

#### Adaptation for UTXOracle
```python
# Simplified for Claude Code sessions
createSession() → track session_id, timestamp, git_branch
saveCheckpoint() → save after N tool invocations
logSessionEvent() → log tool usage, errors, blocks
generateSessionSummary() → cost, tokens, tools used, outcome
```

---

### 2. Hook System Pattern

**File**: `hook-manager.ts` (300+ lines)
**Copied to**: `.claude/self_improve/reference/hook-manager.ts`

#### Hook Types (8 total, we need 3)
```typescript
// Relevant for UTXOracle:
'workflow-start'      // Session initialization
'workflow-step'       // Before/after each tool
'workflow-complete'   // Session end

// Not needed (swarm-specific):
'workflow-error', 'performance-metric', 'memory-operation',
'llm-request', 'neural-training'
```

#### Registration Pattern
```typescript
agenticHookManager.register({
  id: 'tool-usage-tracker',
  type: 'workflow-step',
  priority: 8,
  enabled: true,
  handler: async (payload, context) => {
    const startTime = Date.now();

    // Track tool usage
    await storeToolUsage({
      tool: payload.tool,
      timestamp: startTime,
      sessionId: context.sessionId
    });

    return {
      success: true,
      continue: true,
      sideEffects: [
        { type: 'memory-store', data: {...} }
      ]
    };
  }
});
```

#### Adaptation for UTXOracle
```python
# Pre-tool hook (.claude/hooks/pre-tool-use.py)
- Log tool invocation + timestamp
- Increment tool counter

# Post-tool hook (.claude/hooks/post-tool-use.py)
- Store results + duration
- Update session metrics
- Detect errors/blocks

# Session-end hook (NEW)
- Trigger webhook to n8n
- Generate summary
- Archive data
```

---

### 3. Database Schema

**File**: `hive-mind-schema.sql` (150 lines)
**Copied to**: `.claude/self_improve/reference/schema.sql`

#### Core Tables (Adaptable)
```sql
-- Sessions table (PRIMARY)
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  swarm_id TEXT NOT NULL,
  swarm_name TEXT NOT NULL,
  objective TEXT,
  status TEXT DEFAULT 'active',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  completion_percentage REAL DEFAULT 0,
  checkpoint_data TEXT,
  metadata TEXT
);

-- Session logs (SECONDARY)
CREATE TABLE session_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  log_level TEXT DEFAULT 'info',
  message TEXT,
  agent_id TEXT,
  data TEXT
);

-- Checkpoints (OPTIONAL)
CREATE TABLE session_checkpoints (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  checkpoint_name TEXT NOT NULL,
  checkpoint_data TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### Simplified Schema for UTXOracle
```sql
-- Core sessions table
CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  ended_at DATETIME,
  git_branch TEXT,
  task_description TEXT,
  total_tools INTEGER DEFAULT 0,
  total_tokens INTEGER DEFAULT 0,
  total_cost REAL DEFAULT 0,
  outcome TEXT,  -- SUCCESS/PARTIAL/BLOCKED/FAILED
  summary TEXT
);

-- Tool usage log
CREATE TABLE tool_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  duration_ms INTEGER,
  success BOOLEAN DEFAULT 1,
  error TEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- Events (errors, blocks)
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  event_type TEXT NOT NULL,  -- 'tdd_block', 'test_failure', etc
  tool_name TEXT,
  error_message TEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
```

---

### 4. Serialization Pattern

**File**: `enhanced-session-serializer.js` (200+ lines)
**Copied to**: `.claude/self_improve/reference/session-serializer.js`

#### Complex Type Handling
```javascript
class SessionSerializer {
  serializeSessionData(data) {
    return JSON.stringify(data, (key, value) => {
      if (value instanceof Map)
        return { __type: 'Map', data: [...value] };
      if (value instanceof Date)
        return { __type: 'Date', iso: value.toISOString() };
      if (value instanceof Set)
        return { __type: 'Set', data: [...value] };
      return value;
    });
  }

  deserializeSessionData(json) {
    return JSON.parse(json, (key, value) => {
      if (value?.__type === 'Map')
        return new Map(value.data);
      if (value?.__type === 'Date')
        return new Date(value.iso);
      if (value?.__type === 'Set')
        return new Set(value.data);
      return value;
    });
  }
}
```

#### Adaptation for UTXOracle
```python
# For checkpoint data (if needed)
import json
from datetime import datetime

def serialize_checkpoint(data):
    """Handle datetime objects in checkpoint data"""
    def default(obj):
        if isinstance(obj, datetime):
            return {'__type': 'datetime', 'iso': obj.isoformat()}
        raise TypeError(f"Type {type(obj)} not serializable")

    return json.dumps(data, default=default)

def deserialize_checkpoint(json_str):
    """Restore datetime objects"""
    def object_hook(obj):
        if obj.get('__type') == 'datetime':
            return datetime.fromisoformat(obj['iso'])
        return obj

    return json.loads(json_str, object_hook=object_hook)
```

---

## 📁 Reference Files Copied

| File | Original Path | Copied To | Size | Purpose |
|------|---------------|-----------|------|---------|
| session-manager.js | `src/cli/simple-commands/hive-mind/` | `reference/session-manager.js` | 1,187 lines | Session lifecycle management |
| hook-manager.ts | `src/services/agentic-flow-hooks/` | `reference/hook-manager.ts` | 300+ lines | Hook registration & execution |
| schema.sql | `src/db/` | `reference/schema.sql` | 150 lines | SQLite database schema |
| session-serializer.js | `src/memory/` | `reference/session-serializer.js` | 200+ lines | Complex type serialization |

**Total**: ~1,837 lines of reference code

---

## 🎯 Recommended Adaptations

### Phase 1: Session Tracking (Week 1)
**From**: `session-manager.js`
**Adapt**:
- `createSession()` → Initialize Claude session with `session_id`
- `logSessionEvent()` → Log tool usage to SQLite
- `generateSessionSummary()` → Cost/token/outcome summary

**Implementation**:
```python
# .claude/scripts/session_manager.py
import sqlite3
from datetime import datetime

class ClaudeSessionManager:
    def __init__(self, db_path='.claude/logs/sessions.db'):
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def create_session(self, git_branch=None, task=None):
        session_id = f"session-{int(datetime.now().timestamp())}"
        self.conn.execute("""
            INSERT INTO sessions (session_id, started_at, git_branch, task_description)
            VALUES (?, ?, ?, ?)
        """, (session_id, datetime.now(), git_branch, task))
        self.conn.commit()
        return session_id

    def log_tool_use(self, session_id, tool_name, duration_ms, success, error=None):
        self.conn.execute("""
            INSERT INTO tool_usage
            (session_id, tool_name, timestamp, duration_ms, success, error)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, tool_name, datetime.now(), duration_ms, success, error))
        self.conn.commit()

    def generate_summary(self, session_id):
        # Query tool_usage stats
        stats = self.conn.execute("""
            SELECT tool_name, COUNT(*) as count, AVG(duration_ms) as avg_duration
            FROM tool_usage WHERE session_id = ?
            GROUP BY tool_name
        """, (session_id,)).fetchall()

        return {
            'session_id': session_id,
            'tool_stats': [
                {'tool': row[0], 'count': row[1], 'avg_duration': row[2]}
                for row in stats
            ]
        }
```

### Phase 2: Hook Integration (Week 1-2)
**From**: `hook-manager.ts`
**Adapt**:
- Register pre/post tool hooks
- Execute hooks on tool invocation
- Store side effects (metrics, logs)

**Implementation**:
```python
# .claude/hooks/post-tool-use-enhanced.py
import json
import sys
from datetime import datetime
from session_manager import ClaudeSessionManager

def on_tool_use():
    input_data = json.loads(sys.stdin.read())

    session_id = input_data.get('session_id')
    tool_name = input_data.get('tool_name')
    success = input_data.get('tool_response', {}).get('success', True)
    error = input_data.get('tool_response', {}).get('error')

    # Track in database
    manager = ClaudeSessionManager()
    manager.log_tool_use(session_id, tool_name, 0, success, error)

    # Detect events (blocks, errors)
    if not success and 'tdd' in str(error).lower():
        manager.log_event(session_id, 'tdd_block', tool_name, error)

if __name__ == '__main__':
    on_tool_use()
```

### Phase 3: Database Setup (Week 1)
**From**: `schema.sql`
**Use**: Simplified 3-table schema (see above)

**Setup**:
```bash
# Create database
sqlite3 .claude/logs/sessions.db < .claude/self_improve/simplified_schema.sql

# Verify
sqlite3 .claude/logs/sessions.db "SELECT name FROM sqlite_master WHERE type='table';"
# Expected: sessions, tool_usage, events
```

---

## 🚫 What NOT to Adapt

| Pattern | Reason | Complexity |
|---------|--------|------------|
| Swarm coordination | Not multi-agent | High |
| Consensus algorithms | Single session only | Very High |
| Neural training | Over-engineered for our use case | Extreme |
| Agent spawning | N/A for Claude Code | Medium |
| Task queues | Sequential tool execution | Medium |

**Rule of Thumb**: If it mentions "swarm", "agent", "consensus", "neural" → Skip it

---

## 📊 Comparison: Claude-Flow vs UTXOracle Needs

| Feature | Claude-Flow | UTXOracle | Adaptation |
|---------|-------------|-----------|------------|
| Session tracking | ✅ Multi-agent | ✅ Single session | Simplify (remove swarm_id) |
| Database | ✅ SQLite | ✅ SQLite | Use 3 tables (not 8) |
| Hooks | ✅ 8 types | ✅ 3 types | Use workflow-start/step/complete |
| Checkpoints | ✅ Every N tasks | ⚠️ Optional | Maybe skip initially |
| Serialization | ✅ Complex types | ✅ Simple JSON | Use for datetime only |
| Analytics | ✅ Per-agent stats | ✅ Per-session stats | Adapt queries |
| Export/Import | ✅ Full session | ✅ Daily summaries | Simplify (JSON only) |

---

## 🎯 Key Takeaways

### ✅ What Works for Us
1. **Session lifecycle pattern** (create → track → summarize)
2. **SQLite for persistence** (fast, local, zero-config)
3. **Hook-based event tracking** (pre/post tool use)
4. **Structured logging** (session_id as foreign key)
5. **Summary generation** (analytics queries)

### ❌ What's Overkill
1. Multi-agent coordination (we're single-session)
2. Neural pattern learning (too complex for MVP)
3. Consensus algorithms (no distributed system)
4. Complex serialization (we don't need Maps/Sets)

### 💡 Clever Ideas to Steal
1. **Checkpoint system** → Resume analysis if interrupted
2. **Dual storage** → SQLite (primary) + JSON (backup)
3. **Process tracking** → Store parent/child PIDs for cleanup
4. **Prepared statements** → Performance optimization
5. **In-memory fallback** → If SQLite fails, continue in-memory

---

## 📂 Next Actions

### Immediate (This Session)
- [x] Copy reference files to `.claude/self_improve/reference/`
- [x] Save this analysis report
- [x] Update SELF_IMPROVE.md with findings
- [ ] Create simplified schema SQL file

### Next Session
- [ ] Implement `ClaudeSessionManager` class
- [ ] Adapt hooks to use session manager
- [ ] Test SQLite setup
- [ ] Generate first session summary

### Future
- [ ] n8n workflow integration
- [ ] Gemini analysis integration
- [ ] Discord notifications
- [ ] Dashboard/visualization

---

## 📚 Additional Resources

### Claude-Flow Documentation
- Memory System: `docs/MEMORY-SYSTEM.md`
- Hooks Refactoring: `docs/maestro/specs/hooks-refactoring-plan.md`
- Session Commands: `src/cli/commands/session.ts`

### External References
- [SQLite Documentation](https://www.sqlite.org/docs.html)
- [Python sqlite3 Module](https://docs.python.org/3/library/sqlite3.html)
- [n8n SQLite Node](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.sqlite/)

---

**Analysis Date**: 2025-10-20
**Analyst**: General-purpose subagent
**Status**: ✅ Complete - Ready for implementation

**Recommendation**: Start with Phase 1 (Session Tracking) using reference files. 80% of value comes from 20% of the patterns.
