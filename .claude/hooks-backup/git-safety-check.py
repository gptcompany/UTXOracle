#!/usr/bin/env python3
"""
Git Safety Check Hook for Claude Code
Prevents dangerous Git operations and sensitive file commits

Protects UTXOracle from:
- Force push to main/master
- Deletion of protected branches
- Committing sensitive files (.env, bitcoin.conf, etc.)
- Large file commits (>50MB)
- Sensitive keywords in commit messages
"""

import sys
import json
import re
import subprocess
from pathlib import Path

# Configuration
PROTECTED_BRANCHES = ["main", "master", "production"]
LARGE_FILE_THRESHOLD = 50_000_000  # 50MB

# Sensitive file patterns (UTXOracle specific)
SENSITIVE_PATTERNS = [
    r'\.env$',                      # Environment variables
    r'\.env\..*',                   # .env.local, .env.production
    r'bitcoin\.conf$',              # Bitcoin RPC credentials
    r'\.cookie$',                   # Bitcoin auth cookie
    r'.*\.pem$',                    # SSH keys
    r'.*\.key$',                    # Private keys
    r'id_rsa',                      # SSH private key
    r'\.aws/credentials',           # AWS credentials (future)
    r'\.pypirc$',                   # PyPI credentials
]

# Sensitive keywords in content/messages
SENSITIVE_KEYWORDS = [
    'BROWSERBASE_API_KEY',
    'BROWSERBASE_PROJECT_ID',
    'rpcuser',
    'rpcpassword',
    'private_key',
    'secret_key',
    'api_key',
    'password',
    'token',
]


def get_current_branch():
    """Get current Git branch name"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def is_protected_branch(branch):
    """Check if branch is protected"""
    return branch in PROTECTED_BRANCHES


def check_force_push(command):
    """Detect force push attempts"""
    if "--force" in command or "-f" in command:
        if "push" in command:
            return True
    return False


def check_branch_deletion(command):
    """Detect branch deletion attempts"""
    if "branch" in command and ("-D" in command or "-d" in command):
        # Extract branch name
        for protected in PROTECTED_BRANCHES:
            if protected in command:
                return protected
    return None


def check_sensitive_files(command):
    """Check if commit includes sensitive files"""
    sensitive_files = []
    
    # Get list of files to be committed
    if "commit" in command or "add" in command:
        try:
            # Check staged files
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                check=True
            )
            staged_files = result.stdout.strip().split('\n')
            
            for file_path in staged_files:
                if not file_path:
                    continue
                    
                # Check against sensitive patterns
                for pattern in SENSITIVE_PATTERNS:
                    if re.search(pattern, file_path, re.IGNORECASE):
                        sensitive_files.append(file_path)
                        break
                        
        except subprocess.CalledProcessError:
            pass
    
    return sensitive_files


def check_large_files():
    """Check for large files in staging area"""
    large_files = []
    
    try:
        # Get staged files with sizes
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True
        )
        staged_files = result.stdout.strip().split('\n')
        
        for file_path in staged_files:
            if not file_path or not Path(file_path).exists():
                continue
                
            file_size = Path(file_path).stat().st_size
            if file_size > LARGE_FILE_THRESHOLD:
                large_files.append({
                    "file": file_path,
                    "size": file_size,
                    "size_mb": file_size / 1_000_000
                })
                
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    return large_files


def check_commit_message(command):
    """Check commit message for sensitive keywords"""
    found_keywords = []
    
    if "commit" in command and "-m" in command:
        # Extract message from command
        message_match = re.search(r'-m\s+["\']([^"\']+)["\']', command)
        if message_match:
            message = message_match.group(1).lower()
            
            for keyword in SENSITIVE_KEYWORDS:
                if keyword.lower() in message:
                    found_keywords.append(keyword)
    
    return found_keywords


def main():
    """Main hook logic"""
    try:
        # Read input from Claude Code
        input_data = json.loads(sys.stdin.read())
        
        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command", "")
        
        if not command or "git" not in command:
            # Not a git command, allow
            sys.exit(0)
        
        current_branch = get_current_branch()
        warnings = []
        errors = []
        
        # Check 1: Force push to protected branch
        if check_force_push(command):
            if current_branch and is_protected_branch(current_branch):
                errors.append(
                    f"❌ BLOCKED: Force push to protected branch '{current_branch}' is not allowed.\n"
                    f"   Use 'git push' without --force, or create a feature branch first."
                )
            else:
                warnings.append(
                    f"⚠️  WARNING: Force push detected on branch '{current_branch}'.\n"
                    f"   This may overwrite remote history. Proceed with caution."
                )
        
        # Check 2: Branch deletion
        deleted_branch = check_branch_deletion(command)
        if deleted_branch:
            errors.append(
                f"❌ BLOCKED: Cannot delete protected branch '{deleted_branch}'.\n"
                f"   Protected branches: {', '.join(PROTECTED_BRANCHES)}"
            )
        
        # Check 3: Sensitive files
        sensitive_files = check_sensitive_files(command)
        if sensitive_files:
            warnings.append(
                f"⚠️  WARNING: Attempting to commit sensitive files:\n"
                + "\n".join(f"   - {f}" for f in sensitive_files) +
                f"\n   Review carefully before proceeding. Consider adding to .gitignore."
            )
        
        # Check 4: Large files
        large_files = check_large_files()
        if large_files:
            warnings.append(
                f"⚠️  WARNING: Large files detected in commit:\n"
                + "\n".join(f"   - {f['file']} ({f['size_mb']:.1f} MB)" for f in large_files) +
                f"\n   Consider using Git LFS for files >{LARGE_FILE_THRESHOLD/1_000_000:.0f}MB."
            )
        
        # Check 5: Sensitive keywords in commit message
        sensitive_keywords = check_commit_message(command)
        if sensitive_keywords:
            warnings.append(
                f"⚠️  WARNING: Sensitive keywords in commit message:\n"
                + "\n".join(f"   - {k}" for k in sensitive_keywords) +
                f"\n   Avoid committing secrets in messages."
            )
        
        # If errors, block the operation
        if errors:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "shouldBlock": True,
                    "blockMessage": "\n\n".join(errors)
                }
            }
            print(json.dumps(output))
            sys.exit(1)
        
        # If warnings, show but allow
        if warnings:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "shouldBlock": False,
                    "message": "\n\n".join(warnings)
                }
            }
            print(json.dumps(output))
            sys.exit(0)
        
        # All clear
        sys.exit(0)
        
    except json.JSONDecodeError:
        # Not valid JSON input, allow operation
        sys.exit(0)
    except Exception as e:
        # On error, fail open (allow operation but log)
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "message": f"⚠️  Git safety check error: {str(e)}"
            }
        }))
        sys.exit(0)


if __name__ == "__main__":
    main()
