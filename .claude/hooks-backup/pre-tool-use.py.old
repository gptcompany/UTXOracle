#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///

import json
import sys
import re

def is_dangerous_rm_command(command):
    """
    Comprehensive detection of dangerous rm commands.
    Matches various forms of rm -rf and similar destructive patterns.
    """
    # Normalize command by removing extra spaces and converting to lowercase
    normalized = ' '.join(command.lower().split())
    
    # Pattern 1: Standard rm -rf variations
    patterns = [
        r'\brm\s+.*-[a-z]*r[a-z]*f',  # rm -rf, rm -fr, rm -Rf, etc.
        r'\brm\s+.*-[a-z]*f[a-z]*r',  # rm -fr variations
        r'\brm\s+--recursive\s+--force',  # rm --recursive --force
        r'\brm\s+--force\s+--recursive',  # rm --force --recursive
        r'\brm\s+-r\s+.*-f',  # rm -r ... -f
        r'\brm\s+-f\s+.*-r',  # rm -f ... -r
    ]
    
    # Check for dangerous patterns
    for pattern in patterns:
        if re.search(pattern, normalized):
            return True
    
    # Pattern 2: Check for rm with recursive flag targeting dangerous paths
    dangerous_paths = [
        r'/',           # Root directory
        r'/\*',         # Root with wildcard
        r'~',           # Home directory
        r'~/',          # Home directory path
        r'\$HOME',      # Home environment variable
        r'\.\.',        # Parent directory references
        r'\*',          # Wildcards in general rm -rf context
        r'\.',          # Current directory
        r'\.\s*$',      # Current directory at end of command
    ]
    
    if re.search(r'\brm\s+.*-[a-z]*r', normalized):  # If rm has recursive flag
        for path in dangerous_paths:
            if re.search(path, normalized):
                return True
    
    return False

def is_env_file_access(tool_name, tool_input):
    """
    Check if any tool is trying to access .env files containing sensitive data.
    """
    if tool_name in ['Read', 'Edit', 'MultiEdit', 'Write', 'Bash']:
        # Check file paths for file-based tools
        if tool_name in ['Read', 'Edit', 'MultiEdit', 'Write']:
            file_path = tool_input.get('file_path', '')
            if '.env' in file_path and not file_path.endswith('.env.sample'):
                return True
        
        # Check bash commands for .env file access
        elif tool_name == 'Bash':
            command = tool_input.get('command', '')
            # Pattern to detect .env file access (but allow .env.sample)
            env_patterns = [
                r'\b\.env\b(?!\.sample)',  # .env but not .env.sample
                r'cat\s+.*\.env\b(?!\.sample)',  # cat .env
                r'echo\s+.*>\s*\.env\b(?!\.sample)',  # echo > .env
                r'touch\s+.*\.env\b(?!\.sample)',  # touch .env
                r'cp\s+.*\.env\b(?!\.sample)',  # cp .env
                r'mv\s+.*\.env\b(?!\.sample)',  # mv .env
            ]
            
            for pattern in env_patterns:
                if re.search(pattern, command):
                    return True
    
    return False

def is_safe_operation(tool_name, tool_input):
    """
    Check if this is a safe operation that should be automatically authorized.
    """
    # Safe tools that are always allowed
    safe_tools = {
        'Read', 'Glob', 'Grep', 'BashOutput', 'WebFetch', 'WebSearch', 
        'TodoWrite', 'Write', 'Edit', 'MultiEdit', 'NotebookEdit',
        'Task', 'ExitPlanMode'
    }
    
    if tool_name in safe_tools:
        # Additional check for file operations
        if tool_name in ['Write', 'Edit', 'MultiEdit']:
            file_path = tool_input.get('file_path', '')
            # Block system files
            system_paths = ['/etc/', '/usr/', '/bin/', '/sbin/', '/var/']
            if any(file_path.startswith(path) for path in system_paths):
                return False
        return True
    
    # Safe bash commands
    if tool_name == 'Bash':
        command = tool_input.get('command', '')
        
        # Check for dangerous rm commands
        if is_dangerous_rm_command(command):
            return False
            
        # Allow safe read-only commands
        safe_commands = ['ls', 'pwd', 'whoami', 'date', 'echo', 'cat', 'head', 'tail', 'grep', 'find', 'which', 'git status', 'git log', 'git diff']
        command_start = command.strip().split()[0] if command.strip() else ''
        if command_start in safe_commands:
            return True

    return False

def main():
    try:
        # Read JSON input from stdin
        input_data = json.loads(sys.stdin.read())
        
        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})
        
        # Check for env file access
        if is_env_file_access(tool_name, tool_input):
            output = {
                "decision": "block",
                "reason": "Access to .env files is restricted for security. Use .env.sample for templates."
            }
            print(json.dumps(output))
            sys.exit(0)
        
        # Check if operation is safe
        if not is_safe_operation(tool_name, tool_input):
            # For dangerous operations, block by default
            if tool_name == 'Bash':
                command = tool_input.get('command', '')
                if is_dangerous_rm_command(command):
                    output = {
                        "decision": "block", 
                        "reason": "Dangerous rm command detected. This could delete important files."
                    }
                    print(json.dumps(output))
                    sys.exit(0)
        
        # Allow operation to proceed
        sys.exit(0)
        
    except json.JSONDecodeError:
        sys.exit(0)
    except Exception:
        sys.exit(0)

if __name__ == '__main__':
    main()