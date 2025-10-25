# UTXOracle Hook Configuration for Multi-Project Tracking

## ⚠️ Manual Configuration Required

Add the following to `.claude/settings.local.json` in the `hooks` section:

### Fix PreToolUse (move context_bundle_builder here)

```json
"PreToolUse": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "/media/sam/1TB/UTXOracle/.claude/hooks/context_bundle_builder.py",
        "env": {
          "CLAUDE_PROJECT_NAME": "UTXOracle",
          "DATABASE_URL": "postgresql://n8n:n8n@localhost:5433/claude_sessions"
        }
      }
    ]
  },
  // ... keep existing PreToolUse hooks (smart-safety-check, git-safety-check, etc.)
]
```

### Update PostToolUse (add ENV to existing hook)

```json
"PostToolUse": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "/media/sam/1TB/UTXOracle/.claude/hooks/post-tool-use.py",
        "env": {
          "CLAUDE_PROJECT_NAME": "UTXOracle",
          "DATABASE_URL": "postgresql://n8n:n8n@localhost:5433/claude_sessions"
        }
      }
      // Remove context_bundle_builder.py from here (it's now in PreToolUse)
    ]
  },
  // ... keep other PostToolUse hooks (auto-format, notifications, etc.)
]
```

## Verification After Config

Test hook execution:
```bash
cd /media/sam/1TB/UTXOracle

# Run a simple operation to trigger hooks
# Then check database:
docker exec n8n-postgres-1 psql -U n8n -d claude_sessions -c \
  "SELECT session_id, project_name FROM sessions WHERE project_name = 'UTXOracle' ORDER BY started_at DESC LIMIT 5;"
```
