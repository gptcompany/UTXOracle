# Migration to claude-hooks-shared

**Date**: 2025-10-27
**Status**: ✅ Complete
**Objective**: Consolidate hooks and scripts to `/media/sam/1TB/claude-hooks-shared/` for multi-project consistency

---

## 🎯 UTXOracle-Specific Notes

This project shares the same PostgreSQL database and hook system with N8N_dev, but maintains **TDD guard functionality** as a unique feature.

---

## 🛡️ TDD Guard (Preserved)

**Purpose**: Enforces Test-Driven Development workflow

**Configuration** (maintained in `.claude/settings.local.json`):
```json
{
  "permissions": {
    "deny": [
      "Read(.claude/tdd-guard/**)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{"type": "command", "command": "tdd-guard"}]
      }
    ],
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "tdd-guard"}]}
    ],
    "SessionStart": [
      {
        "matcher": "startup|resume|clear",
        "hooks": [{"type": "command", "command": "tdd-guard"}]
      }
    ]
  }
}
```

**Behavior**:
- ❌ Blocks `Write` and `Edit` tools if tests are not written first
- ❌ Blocks new user prompts during TDD violations
- ❌ Enforces TDD workflow on session start/resume

**Why UTXOracle has this**: Trading systems require rigorous testing. TDD guard ensures code changes are test-driven.

---

## 📁 File Backups

**Backup Location**: `.claude/hooks-backup/`

**Files Backed Up**:
- `auto-format.py` → Now uses shared version
- `context_bundle_builder.py` → Now uses shared version
- `git-safety-check.py` → Now uses shared version
- `notification.py` → Now uses shared version
- `post-tool-use.py` → Now uses shared version
- `session-end.sh` → Now uses shared version
- `smart-safety-check.py` → Now uses shared version
- `stop.py` → Now uses shared version
- `subagent-checkpoint.sh` → Now uses shared version
- `update-claude-structure.py` → Project-specific (not migrated)

**Scripts Backup Location**: `.claude/scripts-backup/`

**Files Backed Up**:
- `session_manager.py` → Now uses shared version
- `context-monitor.py` → Now uses shared version
- `analyze_patterns.py` → Project-specific (preserved)
- `context-monitor2.py` → Legacy backup

---

## 🔧 settings.local.json Updates

**Key Changes**:

1. **StatusLine**: Now uses shared context-monitor.py with `CLAUDE_PROJECT_NAME="UTXOracle"`
2. **All hooks**: Updated to absolute paths in `/media/sam/1TB/claude-hooks-shared/`
3. **TDD guard**: ✅ **Maintained** as unique UTXOracle feature
4. **ENV vars**: Added `CLAUDE_PROJECT_NAME` and `DATABASE_URL` to relevant hooks

**Example Change**:
```json
// BEFORE
{"command": "/media/sam/1TB/UTXOracle/.claude/hooks/post-tool-use.py"}

// AFTER
{
  "command": "/media/sam/1TB/claude-hooks-shared/hooks/core/post-tool-use.py",
  "env": {
    "CLAUDE_PROJECT_NAME": "UTXOracle",
    "DATABASE_URL": "postgresql://n8n:n8n@localhost:5433/claude_sessions"
  }
}
```

---

## 🗄️ Database Integration

**Database**: Shared PostgreSQL `claude_sessions` (localhost:5433)

**Project Tracking**:
```sql
-- UTXOracle sessions are tracked with project_name
SELECT session_id, project_name, git_branch, outcome
FROM sessions
WHERE project_name = 'UTXOracle'
ORDER BY started_at DESC
LIMIT 5;
```

**Multi-Project Analytics**:
```sql
-- Compare productivity across projects
SELECT
  project_name,
  COUNT(*) as sessions,
  AVG(lines_added) as avg_lines,
  COUNT(CASE WHEN outcome = 'SUCCESS' THEN 1 END) as successful
FROM sessions
WHERE started_at >= NOW() - INTERVAL '7 days'
GROUP BY project_name;

-- Result:
-- project_name | sessions | avg_lines | successful
-- N8N_dev      | 15       | 120       | 12
-- UTXOracle    | 8        | 85        | 7
```

---

## 🔁 Differences from N8N_dev

| Feature | N8N_dev | UTXOracle |
|---------|---------|-----------|
| **TDD Guard** | ❌ No | ✅ Yes (enforced) |
| **N8N Enforcement** | ✅ Yes (n8n-enforce.py) | ❌ No |
| **Shared Hooks** | ✅ Yes | ✅ Yes |
| **Database Tracking** | ✅ project_name="N8N_dev" | ✅ project_name="UTXOracle" |
| **Safety Hooks** | ✅ smart-safety-check.py | ✅ smart-safety-check.py |
| **Auto-Format** | ✅ Ruff | ✅ Ruff |

---

## 🧪 Testing Checklist

### UTXOracle-Specific Tests

```bash
# 1. Verify TDD guard works
# Try to edit a file without test → Should block

# 2. Verify shared hooks load
# Check post-tool-use logs to database with project_name="UTXOracle"

# 3. Verify session tracking
# Complete a session and check the session notification

# 4. Database verification
psql -h localhost -p 5433 -U n8n -d claude_sessions -c \
  "SELECT project_name, COUNT(*) FROM sessions GROUP BY project_name;"
```

---

## 📊 Migration Benefits

**Before Migration**:
- ❌ Hooks duplicated between N8N_dev and UTXOracle
- ❌ No project_name tracking in database
- ❌ Inconsistent session_manager versions

**After Migration**:
- ✅ Single source of truth for hooks (claude-hooks-shared)
- ✅ Multi-project analytics possible
- ✅ Consistent behavior across all projects
- ✅ TDD guard unique to UTXOracle preserved

---

## 🚨 Rollback Instructions

If issues occur, restore from backups:

```bash
# Restore hooks
cp .claude/hooks-backup/* .claude/hooks/

# Restore scripts
cp .claude/scripts-backup/* .claude/scripts/

# Restore settings
git checkout .claude/settings.local.json
```

---

## 🔗 Related Files

- `/media/sam/1TB/claude-hooks-shared/` - Shared hooks repository
- `/media/sam/1TB/N8N_dev/.claude/MIGRATION-TO-SHARED-HOOKS.md` - N8N_dev migration doc
- `.claude/hooks-backup/` - Local hooks backup
- `.claude/scripts-backup/` - Local scripts backup

---

**Migration Completed by**: Claude Code (Sonnet 4.5)
**Migration Date**: 2025-10-27
**Database**: PostgreSQL claude_sessions (localhost:5433)
**Unique Feature**: TDD Guard (preserved)
