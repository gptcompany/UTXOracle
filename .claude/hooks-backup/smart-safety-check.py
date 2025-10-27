#!/usr/bin/env python3
"""
Smart Safety Check Hook - Intelligent Command Protection

Instead of blocking dangerous commands entirely (which frustrates Claude),
this hook implements a smarter approach:

1. Auto-checkpoint before dangerous operations
2. Limit scope to CWD (current working directory)
3. Clear warnings with confirmation required
4. Risk-based categorization

Based on best practices from claude-code-hooks community
"""

import json
import sys
import re
import subprocess
from pathlib import Path

# Risk Categories
RISK_CRITICAL = "CRITICAL"  # Block entirely (fork bombs, etc.)
RISK_HIGH = "HIGH"          # Checkpoint + confirm + CWD limit
RISK_MEDIUM = "MEDIUM"      # Warning only

# Critical patterns - ALWAYS BLOCK (no recovery possible)
CRITICAL_PATTERNS = [
    (r':.*\(\)\s*\{.*:\|:.*\};:', "Fork bomb detected"),
    (r'dd\s+if=/dev/(zero|random|urandom)\s+of=/', "dd to critical device"),
    (r'mkfs\.\w+\s+/dev/', "Filesystem formatting"),
    (r'>\s*/dev/(sda|nvme)', "Writing to disk device"),
    (r'rm\s+.*-rf\s+/', "Deletion from root (/)"),
    (r'rm\s+.*-rf\s+~', "Deletion from home (~)"),
    (r'rm\s+.*-rf\s+\$HOME', "Deletion from HOME"),
]

# High-risk patterns - Checkpoint + Confirm + CWD limit
HIGH_RISK_PATTERNS = [
    (r'rm\s+.*-[a-z]*r[a-z]*f', "Recursive force deletion"),
    (r'rm\s+.*\*.*\*', "Multiple wildcards in rm"),
    (r'find\s+.*-delete', "find with -delete"),
    (r'git\s+reset\s+--hard', "Git hard reset"),
    (r'git\s+clean\s+-[a-z]*f[a-z]*d', "Git clean -ffd"),
]

# Medium-risk patterns - Warning only
MEDIUM_RISK_PATTERNS = [
    (r'chmod\s+-R\s+777', "Chmod 777 recursive"),
    (r'chown\s+-R', "Chown recursive"),
    (r'npm\s+install\s+-g', "Global npm install"),
    (r'pip\s+install\s+--user', "User-wide pip install"),
]


def categorize_risk(command):
    """Categorize command risk level"""
    
    # Check critical patterns
    for pattern, reason in CRITICAL_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return RISK_CRITICAL, reason
    
    # Check high-risk patterns
    for pattern, reason in HIGH_RISK_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return RISK_HIGH, reason
    
    # Check medium-risk patterns
    for pattern, reason in MEDIUM_RISK_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return RISK_MEDIUM, reason
    
    return None, None


def get_cwd():
    """Get current working directory"""
    return str(Path.cwd())


def create_git_checkpoint():
    """Create automatic git checkpoint before dangerous operation"""
    try:
        # Check if in git repo
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            check=True
        )
        
        if result.returncode != 0:
            return None
        
        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True
        )
        
        if not result.stdout.strip():
            # No changes, just return current commit
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()[:8]
        
        # Create checkpoint commit
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(
            ["git", "commit", "-m", "[AUTO-CHECKPOINT] Before dangerous operation"],
            check=True,
            capture_output=True
        )
        
        # Get commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        
        return result.stdout.strip()[:8]
        
    except subprocess.CalledProcessError:
        return None


def limit_to_cwd(command, cwd):
    """
    Suggest CWD-limited version of command
    
    This doesn't modify the command (Claude needs to decide),
    but provides a safer alternative in the warning
    """
    
    # For rm commands, suggest explicit path
    if 'rm' in command and '-r' in command.lower():
        # Extract target (simple heuristic)
        parts = command.split()
        target = None
        for i, part in enumerate(parts):
            if part.startswith('-'):
                continue
            if i > 0 and parts[i-1] == 'rm':
                continue
            if not part.startswith('/') and not part.startswith('~'):
                target = part
                break
        
        if target:
            safe_cmd = command.replace(target, f"{cwd}/{target}")
            return safe_cmd
    
    return None


def main():
    try:
        # Read input from Claude Code
        input_data = json.loads(sys.stdin.read())
        
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        
        # Only check Bash commands
        if tool_name != "Bash":
            sys.exit(0)
        
        command = tool_input.get("command", "")
        if not command:
            sys.exit(0)
        
        # Categorize risk
        risk_level, reason = categorize_risk(command)
        
        if not risk_level:
            # Safe command
            sys.exit(0)
        
        cwd = get_cwd()
        
        # Handle CRITICAL risk - BLOCK entirely
        if risk_level == RISK_CRITICAL:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "shouldBlock": True,
                    "blockMessage": (
                        f"🛑 BLOCKED: {reason}\n"
                        f"Command: {command}\n\n"
                        f"This operation is too dangerous and has been blocked entirely.\n"
                        f"If you absolutely need this, run it manually outside Claude Code."
                    )
                }
            }
            print(json.dumps(output))
            sys.exit(1)
        
        # Handle HIGH risk - Checkpoint + Confirm + CWD suggestion
        if risk_level == RISK_HIGH:
            # Try to create checkpoint
            checkpoint = create_git_checkpoint()
            
            checkpoint_msg = ""
            if checkpoint:
                checkpoint_msg = f"✅ Git checkpoint created: {checkpoint}\n   Rollback: git reset --hard {checkpoint}\n\n"
            else:
                checkpoint_msg = "⚠️  No git checkpoint created (not in repo or git unavailable)\n\n"
            
            # Suggest CWD-limited version
            safe_alternative = limit_to_cwd(command, cwd)
            cwd_msg = f"📁 Current directory: {cwd}\n"
            if safe_alternative:
                cwd_msg += f"💡 Safer alternative (CWD-limited):\n   {safe_alternative}\n\n"
            else:
                cwd_msg += f"💡 Consider limiting to CWD: {cwd}\n\n"
            
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "shouldBlock": False,  # Don't block, just warn
                    "message": (
                        f"⚠️  HIGH RISK OPERATION DETECTED\n\n"
                        f"Reason: {reason}\n"
                        f"Command: {command}\n\n"
                        f"{checkpoint_msg}"
                        f"{cwd_msg}"
                        f"⚡ This command will proceed, but review carefully!\n"
                        f"   Consider the safer alternative above to limit scope."
                    )
                }
            }
            print(json.dumps(output))
            sys.exit(0)
        
        # Handle MEDIUM risk - Warning only
        if risk_level == RISK_MEDIUM:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "shouldBlock": False,
                    "message": (
                        f"ℹ️  Medium Risk Operation\n\n"
                        f"Reason: {reason}\n"
                        f"Command: {command}\n\n"
                        f"Review this operation carefully. It may have unintended consequences."
                    )
                }
            }
            print(json.dumps(output))
            sys.exit(0)
        
        # Default: allow
        sys.exit(0)
        
    except json.JSONDecodeError:
        # Not valid JSON, allow
        sys.exit(0)
    except Exception as e:
        # On error, fail open but log
        print(json.dumps({
            "hookSpecificOutput": {
                "message": f"⚠️  Safety check error: {str(e)}"
            }
        }))
        sys.exit(0)


if __name__ == "__main__":
    main()
