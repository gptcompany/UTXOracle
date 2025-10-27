#!/usr/bin/env python3
"""
Auto-update CLAUDE.md repository structure from actual filesystem.

Generates a curated tree view that:
- Shows 1-2 levels of directory depth
- Aggregates large file collections (e.g., "672 HTML files")
- Preserves descriptive comments
- Removes status markers (TODO, IMPLEMENTED, etc.)

Usage:
    python update-claude-structure.py           # Update CLAUDE.md
    python update-claude-structure.py --dry-run # Preview changes
    python update-claude-structure.py --debug   # Show debug info
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Set, Optional
from collections import defaultdict


# ============================================================================
# Configuration
# ============================================================================

EXCLUDE_PATTERNS = {
    '.git', '.venv', 'venv', '__pycache__', '.pytest_cache',
    '.ruff_cache', '.mypy_cache', '.coverage', '*.pyc', '*.pyo',
    '*.egg-info', '.DS_Store', '*.swp', '*.tmp', '*.bak', '*.log',
}

# Status markers to remove
STATUS_MARKERS = [
    r'\s*\(TODO\)', r'\s*\(IMPLEMENTED\)', r'\s*\(IN PROGRESS\)',
    r'\s*\(✅[^)]*\)', r'\s*\(❌[^)]*\)', r'\s*\(⚠️[^)]*\)',
    r'\s*\(CURRENT[^)]*\)', r'\s*\(FUTURE[^)]*\)',
    r'\s*\(ready[^)]*\)', r'\s*\(Created[^)]*\)',
]

# Structure template - defines what to show
STRUCTURE = {
    'UTXOracle.py': 'Reference implementation v9.1 (IMMUTABLE)',
    'main.py': 'Live system entry point',
    'orchestrator.py': 'Pipeline orchestration',
    'pyproject.toml': 'UV workspace root',
    'uv.lock': 'Dependency lockfile (commit this!)',
    '.python-version': 'Python version specification',
    '.env': 'Environment variables (DO NOT COMMIT)',

    'live/': 'Modular live system implementation',
    'live/backend/': 'Python modules (ZMQ, processing, API)',
    'live/frontend/': 'HTML/JS/CSS visualization',
    'live/shared/': 'Shared data models',

    'core/': 'Extracted algorithm modules (future: Rust/Cython candidates)',

    'tests/': 'Test suite (pytest)',
    'tests/integration/': 'End-to-end tests',
    'tests/benchmark/': 'Performance benchmarks',
    'tests/fixtures/': 'Test data',

    'docs/': 'Documentation',
    'docs/tasks/': 'Agent task specifications (01-05)',

    'scripts/': 'Utilities (batch processing, etc.)',
    'specs/': 'Feature specifications (SpecKit)',
    'examples/': 'Example outputs and screenshots',
    'historical_data/': '672 days of historical outputs',
    'historical_data/html_files/': 'HTML price analysis files',
    'archive/': 'Previous versions (v7, v8, v9)',

    '.claude/': 'Claude Code configuration',
    '.claude/agents/': '6 specialized subagents',
    '.claude/skills/': '4 template-driven automation skills',
    '.claude/hooks/': 'Pre/post tool execution hooks',
    '.claude/prompts/': 'Orchestration rules',
    '.claude/tdd-guard/': 'TDD enforcement data',
    '.claude/commands/': 'Custom slash commands (SpecKit)',
    '.claude/docs/': 'Meta-documentation',
    '.claude/research/': 'Research notes',
    '.claude/logs/': 'Session logs',

    '.serena/': 'Serena MCP (code navigation memory)',
    '.specify/': 'SpecKit (task management)',

    '.github/': 'Cleanup automation tools',

    'CLAUDE.md': 'THIS FILE - Claude Code instructions',
    'README.md': 'Project overview',
    'LICENSE': 'Blue Oak Model License 1.0.0',
}


# ============================================================================
# Core Functions
# ============================================================================

def should_exclude(name: str) -> bool:
    """Check if file/directory should be excluded."""
    if name in EXCLUDE_PATTERNS:
        return True
    for pattern in EXCLUDE_PATTERNS:
        if '*' in pattern:
            import fnmatch
            if fnmatch.fnmatch(name, pattern):
                return True
    return False


def extract_existing_comments(claude_md_path: Path) -> Dict[str, str]:
    """Extract existing comments from CLAUDE.md Core Structure section."""
    comments = STRUCTURE.copy()

    if not claude_md_path.exists():
        return comments

    content = claude_md_path.read_text()

    # Find Core Structure section
    match = re.search(r'### Core Structure\s*```\s*UTXOracle/\s*(.*?)\s*```', content, re.DOTALL)
    if not match:
        return comments

    tree_section = match.group(1)

    # Parse tree lines
    for line in tree_section.split('\n'):
        # Match: "├── path/    # Comment"
        match = re.match(r'[├└│ ]*(?:├──|└──)?\s*([^\s#]+(?:/)?)\s*#\s*(.+)', line)
        if match:
            path_part = match.group(1).strip()
            comment = match.group(2).strip()

            # Remove status markers
            for marker in STATUS_MARKERS:
                comment = re.sub(marker, '', comment)
            comment = comment.strip()

            if comment and path_part not in comments:
                comments[path_part] = comment

    return comments


def count_files_in_dir(dir_path: Path, pattern: str = "*") -> int:
    """Count files matching pattern in directory."""
    try:
        import fnmatch
        count = 0
        for item in dir_path.iterdir():
            if item.is_file() and fnmatch.fnmatch(item.name, pattern):
                count += 1
        return count
    except:
        return 0


def scan_repository(repo_root: Path, comments: Dict[str, str]) -> List[tuple]:
    """
    Scan repository and build structured list.
    Returns: List of (path, depth, is_dir, comment, file_count)
    """
    items = []

    # Process root files first
    for key in sorted(STRUCTURE.keys()):
        if '/' not in key:  # Root files
            path = repo_root / key
            if path.exists():
                comment = comments.get(key, STRUCTURE.get(key, ''))
                items.append((key, 0, path.is_dir(), comment, 0))

    # Add blank line separator
    items.append(('', 0, False, '', 0))

    # Process directories depth-first
    processed_dirs = set()

    def add_directory(dir_key: str, depth: int = 0):
        if dir_key in processed_dirs:
            return
        processed_dirs.add(dir_key)

        dir_path = repo_root / dir_key.rstrip('/')
        if not dir_path.exists() or not dir_path.is_dir():
            return

        # Add directory itself
        comment = comments.get(dir_key, STRUCTURE.get(dir_key, ''))
        items.append((dir_key, depth, True, comment, 0))

        # Check for special aggregation cases
        if dir_key == 'historical_data/html_files/':
            count = count_files_in_dir(dir_path, "*.html")
            if count > 0:
                items.append((f'[{count} HTML files]', depth + 1, False, '', count))
            return

        if dir_key.endswith('html_files/'):
            return  # Skip showing individual HTML files

        # Get subdirectories and files
        try:
            contents = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        except PermissionError:
            return

        # Add immediate files (selective)
        files_shown = 0
        for item in contents:
            if item.is_file() and not should_exclude(item.name):
                rel_key = f"{dir_key}{item.name}"
                if rel_key in STRUCTURE or depth == 0:  # Show if explicitly listed or root level
                    comment = comments.get(rel_key, STRUCTURE.get(rel_key, ''))
                    items.append((rel_key, depth + 1, False, comment, 0))
                    files_shown += 1
                if files_shown >= 15 and depth > 0:  # Limit files shown per directory
                    remaining = sum(1 for x in contents[contents.index(item):] if x.is_file())
                    if remaining > 1:
                        items.append((f'[...and {remaining} more files]', depth + 1, False, '', remaining))
                    break

        # Process subdirectories (limited depth)
        if depth < 1:  # Only go 1 level deep
            for item in contents:
                if item.is_dir() and not should_exclude(item.name):
                    subdir_key = f"{dir_key}{item.name}/"
                    if subdir_key in STRUCTURE or depth == 0:
                        add_directory(subdir_key, depth + 1)

    # Process main directories
    for key in sorted(STRUCTURE.keys()):
        if '/' in key and key.count('/') == 1:  # Top-level directories
            add_directory(key, 0)

    return items


def format_tree(items: List[tuple]) -> str:
    """Format items as tree structure."""
    lines = ["UTXOracle/"]

    for i, (path, depth, is_dir, comment, file_count) in enumerate(items):
        if path == '':
            lines.append('│')
            continue

        # Special formatting for aggregations
        if path.startswith('['):
            prefix = '│   ' * depth
            lines.append(f"{prefix}└── {path}")
            continue

        # Determine if this is last item at this depth
        is_last = True
        for j in range(i + 1, len(items)):
            next_path, next_depth, _, _, _ = items[j]
            if next_depth < depth:
                break
            if next_depth == depth and next_path != '':
                is_last = False
                break

        # Build prefix
        prefix = ''
        for d in range(depth):
            if d < depth - 1:
                prefix += '│   '
            else:
                prefix += ('└── ' if is_last else '├── ')

        # Format name
        name = path.split('/')[-2] + '/' if is_dir and '/' in path else path.split('/')[-1]

        # Format line with comment
        if comment:
            line = f"{prefix}{name:<35} # {comment}"
        else:
            line = f"{prefix}{name}"

        lines.append(line)

    return '\n'.join(lines)


def update_claude_md(claude_md_path: Path, new_tree: str, dry_run: bool = False) -> bool:
    """Update CLAUDE.md with new tree structure."""
    if not claude_md_path.exists():
        print(f"ERROR: {claude_md_path} not found")
        return False

    content = claude_md_path.read_text()

    # Find Core Structure section
    pattern = r'(### Core Structure\s*```\s*)UTXOracle/.*?(```)'

    if not re.search(pattern, content, re.DOTALL):
        print("ERROR: Could not find '### Core Structure' section in CLAUDE.md")
        return False

    # Replace with new tree
    new_content = re.sub(
        pattern,
        r'\g<1>' + new_tree + r'\n\g<2>',
        content,
        flags=re.DOTALL
    )

    # Check if anything changed
    if new_content == content:
        print("✅ No changes needed - CLAUDE.md is up to date")
        return False

    if dry_run:
        print("🔍 DRY RUN - Changes that would be made:\n")
        print("=" * 80)
        print(new_tree)
        print("=" * 80)
        return False

    # Write updated content
    claude_md_path.write_text(new_content)
    print(f"✅ Updated {claude_md_path}")
    return True


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Auto-update CLAUDE.md repository structure"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Show debug information'
    )

    args = parser.parse_args()

    # Determine repository root
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent.parent
    claude_md_path = repo_root / "CLAUDE.md"

    if args.debug:
        print(f"Repository root: {repo_root}")
        print(f"CLAUDE.md path: {claude_md_path}")

    # Extract existing comments
    print("📖 Reading existing comments from CLAUDE.md...")
    comments = extract_existing_comments(claude_md_path)

    if args.debug:
        print(f"Found {len(comments)} comment mappings")

    # Scan repository
    print("🌳 Scanning repository structure...")
    items = scan_repository(repo_root, comments)

    # Format tree
    tree = format_tree(items)

    # Update CLAUDE.md
    print("📝 Updating CLAUDE.md...")
    updated = update_claude_md(claude_md_path, tree, dry_run=args.dry_run)

    if updated and not args.dry_run:
        print("\n✅ CLAUDE.md updated successfully!")
        print("   Remember to stage and commit the changes:")
        print(f"   git add {claude_md_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
