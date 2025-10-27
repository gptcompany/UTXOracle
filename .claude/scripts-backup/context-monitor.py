#!/usr/bin/env python3
"""
Claude Code Context Monitor - Enhanced with Contextual Metadata + Token Display
Real-time context usage monitoring + post-session analysis support

DUAL PURPOSE:
1. StatusLine display (real-time, eye-candy) - SECONDARY GOAL
2. Data persistence with context (analysis, metrics) - PRIMARY GOAL

CHANGELOG:
- Original: n8n repository (basic token tracking)
- Enhanced v1: Added persist_metrics() for JSONL logging
- Enhanced v2: Added contextual metadata (git branch, task desc, agent name)
- Enhanced v3: Added token count display in status line

NEW FEATURES IN v3:
- Token count visualization in status line (45k, 1.2M format)
- Color-coded based on context usage percentage
- Smart formatting (k/M suffixes)

USAGE:
1. StatusLine (automatic): configured in .claude/settings.local.json
2. Manual context: echo "Task: Fix bug #123" > .claude/.session_description
3. Agent context: export CLAUDE_AGENT_NAME="bitcoin-onchain-expert"
"""

import json
import sys
import os
import re
from pathlib import Path
from datetime import datetime

def parse_context_from_transcript(transcript_path):
    """Parse context usage from transcript file."""
    if not transcript_path or not os.path.exists(transcript_path):
        return None

    try:
        with open(transcript_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        # Track totals for persistence (PRIMARY GOAL)
        total_input = 0
        total_output = 0
        total_cache_creation = 0
        total_cache_read = 0
        message_count = 0

        # Check last 15 lines for context information
        recent_lines = lines[-15:] if len(lines) > 15 else lines

        for line in reversed(recent_lines):
            try:
                data = json.loads(line.strip())

                # Method 1: Parse usage tokens from assistant messages
                if data.get('type') == 'assistant':
                    message = data.get('message', {})
                    usage = message.get('usage', {})

                    if usage:
                        input_tokens = usage.get('input_tokens', 0)
                        cache_read = usage.get('cache_read_input_tokens', 0)
                        cache_creation = usage.get('cache_creation_input_tokens', 0)
                        output_tokens = usage.get('output_tokens', 0)

                        # Estimate context usage (assume 200k context for Claude Sonnet)
                        total_tokens = input_tokens + cache_read + cache_creation
                        if total_tokens > 0:
                            percent_used = min(100, (total_tokens / 200000) * 100)
                            return {
                                'percent': percent_used,
                                'tokens': total_tokens,
                                'input_tokens': input_tokens,
                                'output_tokens': output_tokens,
                                'cache_creation': cache_creation,
                                'cache_read': cache_read,
                                'method': 'usage'
                            }

                # Method 2: Parse system context warnings
                elif data.get('type') == 'system_message':
                    content = data.get('content', '')

                    # "Context left until auto-compact: X%"
                    match = re.search(r'Context left until auto-compact: (\d+)%', content)
                    if match:
                        percent_left = int(match.group(1))
                        return {
                            'percent': 100 - percent_left,
                            'warning': 'auto-compact',
                            'method': 'system'
                        }

                    # "Context low (X% remaining)"
                    match = re.search(r'Context low \((\d+)% remaining\)', content)
                    if match:
                        percent_left = int(match.group(1))
                        return {
                            'percent': 100 - percent_left,
                            'warning': 'low',
                            'method': 'system'
                        }

            except (json.JSONDecodeError, KeyError, ValueError):
                continue

        return None

    except (FileNotFoundError, PermissionError):
        return None

def get_git_branch():
    """
    Get current git branch for context

    Returns:
        str: Branch name or None if not in git repo
    """
    import subprocess
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=os.getcwd()
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            return branch if branch else None
    except:
        pass
    return None

def get_session_context():
    """
    Extract contextual metadata for session analysis

    Priority order:
    1. Environment variable CLAUDE_TASK_DESC (highest priority)
    2. File marker .claude/.session_description
    3. Last commit message (as fallback)

    Returns:
        str: Task description or None
    """
    # 1. Environment variable (highest priority)
    task_desc = os.environ.get('CLAUDE_TASK_DESC')
    if task_desc:
        return task_desc.strip()

    # 2. Session description file
    desc_file = Path(".claude/.session_description")
    if desc_file.exists():
        try:
            content = desc_file.read_text().strip()
            if content:
                return content
        except:
            pass

    # 3. Fallback: last commit message (if in git repo)
    import subprocess
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%s"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=os.getcwd()
        )
        if result.returncode == 0 and result.stdout.strip():
            commit_msg = result.stdout.strip()[:100]
            return f"Recent commit: {commit_msg}"
    except:
        pass

    return None

def get_agent_name(workspace_data=None):
    """
    Detect agent name from environment or workspace context

    Priority:
    1. Environment variable CLAUDE_AGENT_NAME
    2. Workspace directory analysis (for subagents)

    Returns:
        str: Agent name or None
    """
    # 1. Explicit environment variable
    agent_name = os.environ.get('CLAUDE_AGENT_NAME')
    if agent_name:
        return agent_name.strip()

    # 2. Detect from workspace (subagent sessions)
    if workspace_data:
        project_dir = workspace_data.get('project_dir', '')
        # Check if in .claude/agents/ subdirectory
        if '.claude/agents/' in project_dir or '/agents/' in project_dir:
            # Extract agent name from path
            agent_name = os.path.basename(project_dir)
            if agent_name:
                return agent_name

    return None

def persist_metrics(session_id, context_info, cost_data, model_name, workspace_data=None):
    """
    PRIMARY GOAL: Save structured metrics for post-session analysis

    Saves to: .claude/stats/session_metrics.jsonl
    Format: One JSON object per line (easy parsing with jq, pandas, etc.)

    NEW in v2: Includes contextual metadata for better analysis
    - Git branch (auto-detected)
    - Task description (from env, file, or commit)
    - Agent name (for subagent sessions)
    - Working directory

    Args:
        session_id: Claude session ID
        context_info: Token/context usage data
        cost_data: Cost and duration data from stdin
        model_name: Model display name
        workspace_data: Workspace info from stdin

    Returns:
        bool: True if metrics saved successfully
    """
    try:
        stats_dir = Path(".claude/stats")
        stats_dir.mkdir(parents=True, exist_ok=True)

        metrics_file = stats_dir / "session_metrics.jsonl"

        # Extract token data
        input_tokens = context_info.get('input_tokens', 0)
        output_tokens = context_info.get('output_tokens', 0)
        cache_creation = context_info.get('cache_creation', 0)
        cache_read = context_info.get('cache_read', 0)
        total_tokens = context_info.get('tokens', 0)

        # Calculate cost (Claude 4.5 Sonnet pricing)
        # Use cost_data from stdin if available (more accurate)
        if cost_data and cost_data.get('total_cost_usd'):
            total_cost = cost_data.get('total_cost_usd', 0)
        else:
            # Fallback: manual calculation
            cost_input = (input_tokens / 1_000_000) * 3.00
            cost_output = (output_tokens / 1_000_000) * 15.00
            cost_cache_creation = (cache_creation / 1_000_000) * 3.75
            cost_cache_read = (cache_read / 1_000_000) * 0.30
            total_cost = cost_input + cost_output + cost_cache_creation + cost_cache_read

        # NEW: Extract contextual metadata
        git_branch = get_git_branch()
        task_description = get_session_context()
        agent_name = get_agent_name(workspace_data)
        working_dir = os.path.basename(os.getcwd())

        # Structured metrics for analysis (with context!)
        metrics = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "model": model_name,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "cache_creation": cache_creation,
                "cache_read": cache_read,
                "total": total_tokens
            },
            "context_percent": round(context_info.get('percent', 0), 1),
            "cost_usd": round(total_cost, 4),
            "duration_minutes": round((cost_data.get('total_duration_ms', 0) / 60000), 2) if cost_data else 0,
            "lines_changed": {
                "added": cost_data.get('total_lines_added', 0) if cost_data else 0,
                "removed": cost_data.get('total_lines_removed', 0) if cost_data else 0
            },
            # NEW: Contextual metadata for future analysis
            "context": {
                "git_branch": git_branch,
                "task_description": task_description,
                "agent_name": agent_name,
                "working_dir": working_dir
            }
        }

        # Append to JSONL (atomic write for concurrent sessions)
        with open(metrics_file, "a") as f:
            f.write(json.dumps(metrics) + "\n")

        return True
    except Exception as e:
        # Fail silently - don't break statusline display
        return False

def get_context_display(context_info):
    """Generate context display with visual indicators."""
    if not context_info:
        return "🔵 ???"

    percent = context_info.get('percent', 0)
    warning = context_info.get('warning')

    # Color and icon based on usage level
    if percent >= 95:
        icon, color = "🚨", "\033[31;1m"  # Blinking red
        alert = "CRIT"
    elif percent >= 90:
        icon, color = "🔴", "\033[31m"    # Red
        alert = "HIGH"
    elif percent >= 75:
        icon, color = "🟠", "\033[91m"   # Light red
        alert = ""
    elif percent >= 50:
        icon, color = "🟡", "\033[33m"   # Yellow
        alert = ""
    else:
        icon, color = "🟢", "\033[32m"   # Green
        alert = ""

    # Create progress bar
    segments = 8
    filled = int((percent / 100) * segments)
    bar = "█" * filled + "▁" * (segments - filled)

    # Special warnings
    if warning == 'auto-compact':
        alert = "AUTO-COMPACT!"
    elif warning == 'low':
        alert = "LOW!"

    reset = "\033[0m"
    alert_str = f" {alert}" if alert else ""

    return f"{icon}{color}{bar}{reset} {percent:.0f}%{alert_str}"

def get_directory_display(workspace_data):
    """Get directory display name."""
    current_dir = workspace_data.get('current_dir', '')
    project_dir = workspace_data.get('project_dir', '')

    if current_dir and project_dir:
        if current_dir.startswith(project_dir):
            rel_path = current_dir[len(project_dir):].lstrip('/')
            return rel_path or os.path.basename(project_dir)
        else:
            return os.path.basename(current_dir)
    elif project_dir:
        return os.path.basename(project_dir)
    elif current_dir:
        return os.path.basename(current_dir)
    else:
        return "unknown"

def format_token_count(tokens):
    """
    Format token count in human-readable format (k/M).

    Examples:
        500 -> "500"
        1500 -> "2k"
        45000 -> "45k"
        1200000 -> "1.2M"
    """
    if tokens >= 1_000_000:
        return f"{tokens/1_000_000:.1f}M"
    elif tokens >= 1_000:
        return f"{tokens/1_000:.0f}k"
    else:
        return str(tokens)

def get_session_metrics(cost_data, context_info=None):
    """Get session metrics display."""
    if not cost_data and not context_info:
        return ""

    metrics = []

    # Token count (NEW in v3)
    if context_info:
        total_tokens = context_info.get('tokens', 0)
        if total_tokens > 0:
            token_str = format_token_count(total_tokens)
            # Color based on context usage
            percent = context_info.get('percent', 0)
            if percent >= 75:
                token_color = "\033[33m"  # Yellow for high usage
            else:
                token_color = "\033[36m"  # Cyan for normal
            metrics.append(f"{token_color}📊 {token_str}\033[0m")

    # Cost
    if cost_data:
        cost_usd = cost_data.get('total_cost_usd', 0)
        if cost_usd > 0:
            if cost_usd >= 0.10:
                cost_color = "\033[31m"  # Red for expensive
            elif cost_usd >= 0.05:
                cost_color = "\033[33m"  # Yellow for moderate
            else:
                cost_color = "\033[32m"  # Green for cheap

            cost_str = f"{cost_usd*100:.0f}¢" if cost_usd < 0.01 else f"${cost_usd:.3f}"
            metrics.append(f"{cost_color}💰 {cost_str}\033[0m")

        # Duration
        duration_ms = cost_data.get('total_duration_ms', 0)
        if duration_ms > 0:
            minutes = duration_ms / 60000
            if minutes >= 30:
                duration_color = "\033[33m"  # Yellow for long sessions
            else:
                duration_color = "\033[32m"  # Green

            if minutes < 1:
                duration_str = f"{duration_ms//1000}s"
            else:
                duration_str = f"{minutes:.0f}m"

            metrics.append(f"{duration_color}⏱ {duration_str}\033[0m")

        # Lines changed
        lines_added = cost_data.get('total_lines_added', 0)
        lines_removed = cost_data.get('total_lines_removed', 0)
        if lines_added > 0 or lines_removed > 0:
            net_lines = lines_added - lines_removed

            if net_lines > 0:
                lines_color = "\033[32m"  # Green for additions
            elif net_lines < 0:
                lines_color = "\033[31m"  # Red for deletions
            else:
                lines_color = "\033[33m"  # Yellow for neutral

            sign = "+" if net_lines >= 0 else ""
            metrics.append(f"{lines_color}📝 {sign}{net_lines}\033[0m")

    return f" \033[90m|\033[0m {' '.join(metrics)}" if metrics else ""

def main():
    try:
        # Read JSON input from Claude Code
        data = json.load(sys.stdin)

        # Extract information
        model_name = data.get('model', {}).get('display_name', 'Claude')
        workspace = data.get('workspace', {})
        transcript_path = data.get('transcript_path', '')
        cost_data = data.get('cost', {})
        session_id = data.get('session_id', 'unknown')

        # Parse context usage
        context_info = parse_context_from_transcript(transcript_path)

        # PRIMARY GOAL: Persist metrics with contextual metadata
        if context_info:
            persist_metrics(session_id, context_info, cost_data, model_name, workspace)

        # SECONDARY GOAL: Build status line display
        context_display = get_context_display(context_info)
        directory = get_directory_display(workspace)
        session_metrics = get_session_metrics(cost_data, context_info)  # Pass context_info (v3 change)

        # Model display with context-aware coloring
        if context_info:
            percent = context_info.get('percent', 0)
            if percent >= 90:
                model_color = "\033[31m"  # Red
            elif percent >= 75:
                model_color = "\033[33m"  # Yellow
            else:
                model_color = "\033[32m"  # Green

            model_display = f"{model_color}[{model_name}]\033[0m"
        else:
            model_display = f"\033[94m[{model_name}]\033[0m"

        # Combine all components
        status_line = f"{model_display} \033[93m📁 {directory}\033[0m 🧠 {context_display}{session_metrics}"

        print(status_line)

    except Exception as e:
        # Fallback display on any error
        print(f"\033[94m[Claude]\033[0m \033[93m📁 {os.path.basename(os.getcwd())}\033[0m 🧠 \033[31m[Error: {str(e)[:20]}]\033[0m")

if __name__ == "__main__":
    main()
