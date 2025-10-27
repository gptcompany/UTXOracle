# CLAUDE.md Structure Auto-Update

Automated system for keeping CLAUDE.md repository structure synchronized with the actual filesystem.

## Overview

When you commit changes that affect repository structure (new directories, files in `live/`, `tests/`, etc.), the pre-commit hook automatically:

1. Scans the repository structure
2. Generates a curated tree view (1-2 levels deep)
3. Preserves descriptive comments from existing CLAUDE.md
4. Removes status markers (`TODO`, `IMPLEMENTED`, etc.)
5. Updates CLAUDE.md Core Structure section
6. Auto-stages CLAUDE.md if modified

## Benefits

- ✅ **Zero manual maintenance** - Structure always reflects reality
- ✅ **Clean documentation** - No stale status markers
- ✅ **Consistent formatting** - Tree structure auto-formatted
- ✅ **Smart aggregation** - Large file collections summarized (e.g., "672 HTML files")
- ✅ **Comment preservation** - Descriptive comments maintained across updates

## How It Works

### Automatic Mode (Pre-Commit Hook)

When you commit changes to these directories:
- `live/`
- `tests/`
- `docs/`
- `.claude/`
- `scripts/`
- `specs/`

The hook automatically runs:

```bash
python3 .claude/hooks/update-claude-structure.py
```

If CLAUDE.md is updated, it's automatically staged for the commit.

### Manual Mode

You can manually update CLAUDE.md anytime:

```bash
# Update CLAUDE.md
python3 .claude/hooks/update-claude-structure.py

# Preview changes without modifying
python3 .claude/hooks/update-claude-structure.py --dry-run

# Show debug information
python3 .claude/hooks/update-claude-structure.py --debug
```

## Installation

The hook is already integrated into `.github/pre-commit.hook`. To activate:

```bash
# Install the pre-commit hook
cp .github/pre-commit.hook .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Configuration

### Adding New Important Paths

Edit `.claude/hooks/update-claude-structure.py` and add to `STRUCTURE` dict:

```python
STRUCTURE = {
    # ...existing entries...
    'new_directory/': 'Description of what this directory contains',
    'important_file.py': 'Description of this file',
}
```

### Excluding Files/Directories

Add to `EXCLUDE_PATTERNS` set:

```python
EXCLUDE_PATTERNS = {
    # ...existing patterns...
    'my_temp_dir',
    '*.ignore',
}
```

### Customizing Depth

By default, shows 1-2 levels of depth. To change:

```python
# In scan_repository() function
if depth < 2:  # Change from 1 to 2 for deeper nesting
    add_directory(subdir_key, depth + 1)
```

## What Gets Shown

### Always Shown
- Root-level important files (UTXOracle.py, main.py, CLAUDE.md, etc.)
- Main directories (live/, tests/, docs/, .claude/, etc.)
- First-level subdirectories
- Files explicitly listed in `STRUCTURE`

### Aggregated
- `historical_data/html_files/` → Shows "[672 HTML files]" instead of listing each one
- Large directories → Shows first 15 files + "[...and N more files]"

### Never Shown
- Build artifacts (`.venv`, `__pycache__`, `.pytest_cache`)
- Temporary files (`*.tmp`, `*.bak`, `*.swp`)
- Cache directories (`.ruff_cache`, `.mypy_cache`)
- Version control (`.git/`)

## Status Markers Removed

The following patterns are automatically stripped from comments:

- `(TODO)`
- `(IMPLEMENTED)`
- `(IN PROGRESS)`
- `(✅ Created)`, `(✅ ready for implementation)`, etc.
- `(❌ ...)`
- `(⚠️ ...)`
- `(CURRENT IMPLEMENTATION TARGET)`
- `(FUTURE - not yet created)`

**Example:**

```
Before:  live/backend/  # Python modules (ZMQ, processing, API) (✅ Created, ready for implementation)
After:   live/backend/  # Python modules (ZMQ, processing, API)
```

## Comment Preservation

Comments are preserved across updates using this priority:

1. **Existing CLAUDE.md comments** (if found)
2. **STRUCTURE template comments** (default)
3. **No comment** (if not defined)

### Adding/Updating Comments

**Method 1: Edit CLAUDE.md directly**
```markdown
live/backend/  # My custom description here
```

Next auto-update will preserve "My custom description here".

**Method 2: Edit STRUCTURE in script**
```python
STRUCTURE = {
    'live/backend/': 'My custom description here',
}
```

## Troubleshooting

### "ERROR: Could not find '### Core Structure' section"

The script looks for this exact section header in CLAUDE.md:

```markdown
### Core Structure

```
UTXOracle/
...
```
```

Make sure it exists.

### CLAUDE.md not updating despite structure changes

Check if you committed files in watched directories:

```bash
# See what directories are watched
grep -A 1 "STRUCTURE_CHANGED" .github/pre-commit.hook

# Manually trigger update
python3 .claude/hooks/update-claude-structure.py
```

### Tree structure looks wrong

Run with debug mode to see what's happening:

```bash
python3 .claude/hooks/update-claude-structure.py --debug --dry-run
```

### Want to skip auto-update for one commit

Use `--no-verify` to bypass all pre-commit hooks:

```bash
git commit --no-verify -m "Emergency commit"
```

## Examples

### Before Auto-Update

```markdown
### Core Structure

```
UTXOracle/
├── live/                     # Modular live system (CURRENT IMPLEMENTATION TARGET)
│   ├── backend/              # (✅ Created, ready for implementation)
│   │   ├── zmq_listener.py   # Task 01 - ZMQ interface (TODO)
│   │   ├── api.py            # Task 04 - API server (IMPLEMENTED)
...
```
```

### After Auto-Update

```markdown
### Core Structure

```
UTXOracle/
├── live/                     # Modular live system
│   ├── backend/              # Python modules (ZMQ, processing, API)
│   │   ├── zmq_listener.py
│   │   ├── api.py
...
```
```

**Changes:**
- ✅ Status markers removed
- ✅ Clean, factual descriptions
- ✅ Actual filesystem reflected

## Philosophy

This system follows the principle that **CLAUDE.md should describe the architecture, not track implementation status**:

- ❌ **Don't:** Use as progress tracker with TODO/DONE markers
- ✅ **Do:** Describe what each directory/file's purpose is
- ❌ **Don't:** Mark files as "ready for implementation"
- ✅ **Do:** Explain the architectural role
- ❌ **Don't:** Show every single file
- ✅ **Do:** Show meaningful structure (1-2 levels)

Status tracking belongs in:
- `docs/IMPLEMENTATION_CHECKLIST.md`
- Git history
- Issue/PR tracking systems
- `.claude/tdd-guard/data/`

## Maintenance

### Updating the Script

The script is at `.claude/hooks/update-claude-structure.py`. Key functions:

- `STRUCTURE` - Template of paths and comments
- `scan_repository()` - Walks filesystem and builds list
- `format_tree()` - Converts list to tree string
- `update_claude_md()` - Replaces Core Structure section

### Testing Changes

Always test with `--dry-run` first:

```bash
python3 .claude/hooks/update-claude-structure.py --dry-run | less
```

## See Also

- `.github/CLEANUP_CHECKLIST.md` - Pre-commit cleanup checklist
- `.github/pre-commit.hook` - Full pre-commit hook script
- `.claude/hooks/AUTO_FORMAT_GUIDE.md` - Auto-formatting system
- `.claude/hooks/GIT_SAFETY_GUIDE.md` - Git safety checks
