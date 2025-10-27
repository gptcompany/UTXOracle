#!/usr/bin/env python3
"""
Auto-Format Hook - Ruff auto-format after Python edits

Automatically formats Python files with Ruff (format + check --fix)
after Write/Edit operations. Fast (<100ms) and silent on errors.
"""

import json
import sys
import subprocess
from pathlib import Path

def should_format(file_path):
    """Check if file should be formatted"""
    
    # Only Python files
    if not file_path.endswith('.py'):
        return False
    
    # Skip non-code directories
    skip_dirs = [
        'archive/',
        'historical_data/',
        '.venv/',
        'venv/',
        '__pycache__/',
        '.git/',
    ]
    
    for skip_dir in skip_dirs:
        if skip_dir in file_path:
            return False
    
    return True

def format_file(file_path):
    """Format file with Ruff"""
    
    if not Path(file_path).exists():
        return None
    
    try:
        # Format with Ruff (via uv)
        format_result = subprocess.run(
            ['uv', 'run', 'ruff', 'format', file_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Auto-fix linting issues (unused imports, etc.)
        check_result = subprocess.run(
            ['uv', 'run', 'ruff', 'check', '--fix', file_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # Check if any changes were made
        formatted = format_result.returncode == 0
        fixed = check_result.returncode == 0 or 'fixed' in check_result.stdout.lower()
        
        return {
            'formatted': formatted,
            'fixed': fixed,
            'filename': Path(file_path).name
        }
        
    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        # Ruff/uv not installed
        return None
    except Exception:
        return None

def main():
    try:
        # Read input from Claude Code
        input_data = json.loads(sys.stdin.read())
        
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        
        # Only trigger on Write/Edit
        if tool_name not in ["Write", "Edit", "MultiEdit"]:
            sys.exit(0)
        
        # Check if should format
        if not should_format(file_path):
            sys.exit(0)
        
        # Format the file
        result = format_file(file_path)
        
        if result:
            # Show success message to Claude
            message = f"✨ Auto-formatted {result['filename']}"
            if result['fixed']:
                message += " (+ auto-fixed linting)"
            
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "message": message
                }
            }
            print(json.dumps(output))
        
        # Always exit 0 (fail open)
        sys.exit(0)
        
    except json.JSONDecodeError:
        # Not valid JSON input, silent pass
        sys.exit(0)
    except Exception:
        # Any error, fail open
        sys.exit(0)

if __name__ == "__main__":
    main()
