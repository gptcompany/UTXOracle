# Auto-Format Hook - Guide

**Status**: ✅ Active
**File**: .claude/hooks/auto-format.py

## What It Does

Auto-formats Python files with Ruff after Write/Edit.

## Example

Before: `def func(x,y): return x+y`
After: `def func(x, y): return x + y`

## Files Affected

✅ live/, core/, scripts/
❌ archive/, .venv/, tests/

## Performance

~200-300ms (minimal impact)

## Test

```bash
echo '{"tool_name": "Write", "tool_input": {"file_path": "test.py"}}' | \
  .claude/hooks/auto-format.py
```

Created: 2025-10-20
