#!/bin/bash
# Trigger n8n webhook for session analysis with git metrics

SESSION_ID="$1"
TRIGGER_TYPE="${2:-auto}"  # auto or manual

# Calculate git statistics
if git rev-parse --git-dir > /dev/null 2>&1; then
  # Get lines changed (unstaged + staged combined)
  LINES_ADDED=$(git diff HEAD --stat | grep -oP '\d+(?= insertion)' | awk '{sum+=$1} END {print sum+0}')
  LINES_REMOVED=$(git diff HEAD --stat | grep -oP '\d+(?= deletion)' | awk '{sum+=$1} END {print sum+0}')
  FILES_MODIFIED=$(git diff HEAD --name-only | wc -l)
  GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
else
  LINES_ADDED=0
  LINES_REMOVED=0
  FILES_MODIFIED=0
  GIT_BRANCH="unknown"
fi

# Send to n8n webhook with git metrics (background, non-blocking)
nohup curl -X POST https://n8nubuntu.princyx.xyz/webhook/claude-session-end \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SESSION_ID\",
    \"trigger\": \"$TRIGGER_TYPE\",
    \"git_metrics\": {
      \"branch\": \"$GIT_BRANCH\",
      \"lines_added\": $LINES_ADDED,
      \"lines_removed\": $LINES_REMOVED,
      \"files_modified\": $FILES_MODIFIED
    }
  }" \
  --max-time 20 \
  --silent \
  --show-error >/dev/null 2>&1 &

# Exit immediately without waiting for curl (non-blocking for Claude)
exit 0
