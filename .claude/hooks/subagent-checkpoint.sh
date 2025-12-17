#!/bin/bash
# SubagentStop Hook - Auto-checkpoint after agent completes

# Read JSON input from stdin
input=$(cat)

# Extract agent info from JSON
agent_type=$(echo "$input" | jq -r '.agent_type // "unknown"')
session_id=$(echo "$input" | jq -r '.session_id // "unknown"')
success=$(echo "$input" | jq -r '.success // false')

# Get current timestamp
timestamp=$(date -Iseconds)

# Log to .claude/stats/subagent_completions.jsonl
mkdir -p .claude/stats
echo "{\"timestamp\":\"$timestamp\",\"agent\":\"$agent_type\",\"session\":\"$session_id\",\"success\":$success}" \
    >> .claude/stats/subagent_completions.jsonl

# Check if there are changes to commit
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git status --porcelain)" ]; then
    # Auto-commit with agent stats
    git add .
    
    # Count tasks from specs if available
    tasks_file="specs/002-mempool-live-oracle/tasks.md"
    if [ -f "$tasks_file" ]; then
        tasks_completed=$(grep -c "✅" "$tasks_file" 2>/dev/null || echo 0)
        tasks_total=$(grep -c "^\- \[" "$tasks_file" 2>/dev/null || echo 0)
    else
        tasks_completed="N/A"
        tasks_total="N/A"
    fi
    
    # Create commit message
    if [ "$success" = "true" ]; then
        status_emoji="✅"
        status_text="SUCCESS"
    else
        status_emoji="⚠️"
        status_text="PARTIAL"
    fi
    
    git commit -m "[$status_emoji Agent: $agent_type] $status_text

Tasks: $tasks_completed/$tasks_total
Session: $session_id
Timestamp: $timestamp

🤖 Generated with Claude Code (SubagentStop Auto-Checkpoint)
Co-Authored-By: Claude <noreply@anthropic.com>"

    echo "✅ Auto-checkpoint created for agent: $agent_type ($status_text)"
else
    echo "ℹ️  No changes to commit for agent: $agent_type"
fi

exit 0
