#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///

import json
import sys
from datetime import datetime
from pathlib import Path

def get_session_log_dir():
    """Get or create session log directory"""
    log_dir = Path.cwd() / ".claude" / "logs" 
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir

def log_tool_usage():
    """Simple logging of tool usage"""
    try:
        # Read JSON input from stdin
        input_data = json.loads(sys.stdin.read())
        
        # Extract basic info
        tool_name = input_data.get('tool_name', 'unknown')
        session_id = input_data.get('session_id', 'unknown')
        
        # Create simple log entry
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "session_id": session_id,
            "success": input_data.get('tool_response', {}).get('success', True)
        }
        
        # Save to session log
        log_dir = get_session_log_dir()
        log_file = log_dir / f"{session_id}_tool_usage.json"
        
        # Read existing logs
        if log_file.exists():
            try:
                with open(log_file, 'r') as f:
                    logs = json.load(f)
            except:
                logs = []
        else:
            logs = []
        
        # Append new log
        logs.append(log_entry)
        
        # Keep only last 100 entries
        if len(logs) > 100:
            logs = logs[-100:]
        
        # Save updated logs
        with open(log_file, 'w') as f:
            json.dump(logs, f, indent=2)
            
    except Exception:
        # Fail silently
        pass

def main():
    log_tool_usage()
    sys.exit(0)

if __name__ == '__main__':
    main()