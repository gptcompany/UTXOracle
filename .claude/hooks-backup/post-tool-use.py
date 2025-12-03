#!/usr/bin/env python3
"""
PostToolUse Hook: Log tool usage and detect error patterns (Multi-Project Template)

This hook is called after each Claude Code tool execution. It:
1. Calculates tool duration from PreToolUse start time
2. Logs tool usage to PostgreSQL database
3. Detects error patterns (tdd_block, timeout, etc.)
4. Records events for recurring pattern detection

Database:
    PostgreSQL claude_sessions (via session_manager.py)
    - tool_usage table: Individual tool invocations
    - events table: Error and block tracking

ENV VARIABLES:
    CLAUDE_PROJECT_NAME: Project identifier for multi-repo tracking

Returns:
    JSON response: {"success": True} to confirm logging completed
"""
import json
import sys
import re
import tempfile
import os
from datetime import datetime
from pathlib import Path

# Add scripts directory to path for session_manager import
# Uses relative path resolution to work in any repository
hook_file_path = Path(__file__).resolve()
scripts_dir = hook_file_path.parent.parent / 'scripts'
sys.path.insert(0, str(scripts_dir))

try:
    from session_manager import ClaudeSessionManager
except ImportError as e:
    print(json.dumps({"success": False, "error": f"Failed to import session_manager: {e}"}))
    sys.exit(1)

# Read hook input with error handling
try:
    hook_data = json.loads(sys.stdin.read())
except json.JSONDecodeError as e:
    print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
    sys.exit(1)

session_id = hook_data.get('session_id')
tool_name = hook_data.get('tool_name')
success = hook_data.get('success', True)
error = hook_data.get('error')

# Validate required fields
if not session_id or not tool_name:
    print(json.dumps({"success": False, "error": "Missing session_id or tool_name"}))
    sys.exit(1)

# Sanitize file path components (same as pre-tool-use.py)
safe_session = re.sub(r'[^a-zA-Z0-9\-_]', '_', str(session_id))
safe_tool = re.sub(r'[^a-zA-Z0-9\-_]', '_', str(tool_name))

# Calculate duration using cross-platform temp directory
temp_dir = tempfile.gettempdir()
start_file = Path(temp_dir) / f'claude_tool_start_{safe_session}_{safe_tool}'

if start_file.exists():
    try:
        start_time = datetime.fromisoformat(start_file.read_text().strip())
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        start_file.unlink()  # Cleanup
    except (ValueError, OSError) as e:
        # If temp file is corrupted or can't be read, default to 0 duration
        duration_ms = 0
else:
    # No start file found (PreToolUse may not have run)
    duration_ms = 0

# Log to database with error handling
try:
    manager = ClaudeSessionManager()
    manager.log_tool_use(session_id, tool_name, duration_ms, success, error)

    # Detect error events
    if not success and error:
        if 'tdd' in error.lower() or 'test' in error.lower():
            manager.log_event(session_id, 'tdd_block', tool_name, error)
        elif 'timeout' in error.lower():
            manager.log_event(session_id, 'timeout', tool_name, error)
        elif 'hook' in error.lower() or 'blocked' in error.lower():
            manager.log_event(session_id, 'hook_block', tool_name, error)
        else:
            manager.log_event(session_id, 'error', tool_name, error)

    manager.close()
    print(json.dumps({"success": True}))

except FileNotFoundError as e:
    # Database not initialized
    print(json.dumps({"success": False, "error": str(e)}))
    sys.exit(1)
except Exception as e:
    # Unexpected error during database operations
    print(json.dumps({"success": False, "error": f"Database error: {e}"}))
    sys.exit(1)
