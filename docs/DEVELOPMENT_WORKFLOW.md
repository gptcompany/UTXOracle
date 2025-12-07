# Development Workflow

> **Note**: This file contains detailed development workflows and checklists.
> CLAUDE.md references this file for extended documentation.

## TDD Implementation Flow

**Red-Green-Refactor** (when applicable):

1. **🔴 RED**: Write failing test first
   ```bash
   uv run pytest tests/test_module.py::test_new_feature -v  # MUST fail
   git add tests/ && git commit -m "TDD RED: Add test for feature X"
   ```

2. **🟢 GREEN - BABY STEPS** (critical - TDD guard enforces this):

   **Step 2a**: Add MINIMAL stub (just method signature)
   ```python
   def new_method(self):
       """Stub - not implemented yet"""
       raise NotImplementedError
   ```
   Run test → Should fail differently (NotImplementedError instead of AttributeError)

   **Step 2b**: Add MINIMAL implementation
   ```python
   def new_method(self):
       """Minimal implementation to pass test"""
       return []  # Simplest return value
   ```
   Run test → May still fail on assertions

   **Step 2c**: Iterate until GREEN
   ```bash
   uv run pytest tests/test_module.py::test_new_feature -v  # Should pass
   git add . && git commit -m "TDD GREEN: Implement feature X"
   ```

3. **♻️ REFACTOR**: Clean up with tests passing
   ```bash
   # Improve code quality without changing behavior
   uv run pytest  # All tests still pass
   git add . && git commit -m "TDD REFACTOR: Clean up feature X"
   ```

**⚠️ TDD Guard Rules** (enforced automatically):
- ❌ **NEVER** implement without failing test first
- ❌ **NEVER** add multiple tests at once (one test at a time)
- ❌ **NEVER** implement more than needed to pass current test
- ✅ **ALWAYS** run pytest immediately before AND after each edit
- ✅ **ALWAYS** implement smallest possible change
- ✅ **FOLLOW** error messages literally (AttributeError → add method, AssertionError → fix logic)

**Baby Step Example**:
```python
# ❌ WRONG (too much at once):
def get_history(self):
    if not hasattr(self, 'history'):
        self.history = deque(maxlen=500)
    return list(self.history)

# ✅ CORRECT (baby steps):
# Step 1: Just stub
def get_history(self):
    pass

# Step 2: Minimal return
def get_history(self):
    return []

# Step 3: Add empty list if test needs it
def get_history(self):
    if not hasattr(self, 'history'):
        self.history = []
    return self.history

# Step 4: Fix after test shows we need deque
def get_history(self):
    if not hasattr(self, 'history'):
        self.history = deque(maxlen=500)
    return list(self.history)
```

**When TDD doesn't fit**: Frontend JS, visualization, exploratory code → Write tests after, document why.

---

## When Stuck Protocol

**CRITICAL**: Maximum **3 attempts** per issue, then STOP.

### After 3 Failed Attempts:

1. **Document failure**:
   ```markdown
   ## Blocker: [Issue Description]

   **Attempts**:
   1. Tried: [approach] → Failed: [error]
   2. Tried: [approach] → Failed: [error]
   3. Tried: [approach] → Failed: [error]

   **Why stuck**: [hypothesis]
   ```

2. **Research alternatives** (15min max):
   - Find 2-3 similar implementations (GitHub, docs)
   - Note different approaches used
   - Check if problem is already solved differently

3. **Question fundamentals**:
   - Is this the right abstraction level?
   - Can this be split into smaller problems?
   - Is there a simpler approach entirely?
   - Do I need this feature at all? (YAGNI check)

4. **Try different angle OR ask for help**:
   - Different library/framework feature?
   - Remove abstraction instead of adding?
   - Defer to later iteration?

**Never**: Keep trying the same approach >3 times. That's insanity, not persistence.

---

## Decision Framework

When multiple valid approaches exist, choose based on **priority order**:

1. **Testability** → Can I easily test this? (automated, fast, deterministic)
2. **Simplicity** → Is this the simplest solution that works? (KISS)
3. **Consistency** → Does this match existing project patterns?
4. **Readability** → Will someone understand this in 6 months? (Future you)
5. **Reversibility** → How hard to change later? (Prefer reversible)

**Example**:
```python
# ❌ Clever but hard to test
result = reduce(lambda x,y: x|y, map(parse, data), {})

# ✅ Simple, testable, readable
result = {}
for item in data:
    parsed = parse(item)
    result.update(parsed)
```

---

## Error Handling Standards

**Principles**:
- **Fail fast** with descriptive messages
- **Include context** for debugging (not just "Error")
- **Handle at appropriate level** (don't catch everywhere)
- **Never silently swallow** exceptions

**Good Error Messages**:
```python
# ❌ Bad
raise ValueError("Invalid input")

# ✅ Good
raise ValueError(
    f"Bitcoin RPC connection failed: {rpc_url} "
    f"(check bitcoin.conf rpcuser/rpcpassword)"
)
```

**Logging over print**:
```python
# ❌ Bad
print(f"Processing block {height}")  # Lost in production

# ✅ Good
logger.info(f"Processing block {height}", extra={"block_height": height})
```

---

## Test Guidelines

**Principles**:
- Test **behavior**, not implementation
- **One assertion** per test when possible (or closely related assertions)
- **Clear test names** describing scenario: `test_<what>_<when>_<expected>`
- **Use existing fixtures/helpers** (check `tests/conftest.py`)
- Tests must be **deterministic** (no random, no time dependencies)

**Good Test Structure**:
```python
def test_histogram_removes_round_amounts_when_filtering_enabled():
    """Round BTC amounts (1.0, 5.0) should be filtered from histogram."""
    # Arrange
    histogram = {"1.0": 100, "1.23456": 50, "5.0": 200}

    # Act
    filtered = remove_round_amounts(histogram)

    # Assert
    assert "1.0" not in filtered
    assert "5.0" not in filtered
    assert filtered["1.23456"] == 50
```

**Bad Tests**:
```python
# ❌ Testing implementation details
def test_histogram_uses_dict():
    assert isinstance(histogram, dict)  # Who cares?

# ❌ Multiple unrelated assertions
def test_everything():
    assert process() == expected  # Too vague
    assert config.loaded  # Unrelated
    assert server.running  # Unrelated
```

---

## Task Completion Protocol

**IMPORTANT**: Run this checklist BEFORE marking any task as complete or creating a commit.

### Pre-Commit Cleanup Checklist

When completing a task, **ALWAYS** do the following cleanup:

#### 1. Remove Temporary Files
```bash
# Check for temporary files
find . -type f \( -name "*.tmp" -o -name "*.bak" -o -name "*~" -o -name "*.swp" \)

# Remove if found (review first!)
# find . -type f \( -name "*.tmp" -o -name "*.bak" -o -name "*~" \) -delete
```

#### 2. Clean Python Cache
```bash
# Remove Python cache (auto-regenerates)
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete
```

#### 3. Remove Debug/Test Outputs
```bash
# Check for test artifacts
ls -la *.html *.json *.log 2>/dev/null | grep -v "UTXOracle_"

# Move to archive if historical data, delete if temporary
```

#### 4. Code Cleanup (Manual Review)

**Remove**:
- ❌ Commented-out code blocks (if >1 week old)
- ❌ `print()` debug statements
- ❌ Unused imports (`ruff check --select F401`)
- ❌ TODO comments that are now resolved
- ❌ Dead functions/classes (never called)

**Fix**:
- ✅ Run linter: `ruff check .` (if available)
- ✅ Format code: `ruff format .` (if available)
- ✅ Type hints: Add where missing

#### 5. Documentation Cleanup

**Consolidate**:
- ❌ Delete draft `.md` files not referenced anywhere
- ❌ Remove obsolete documentation
- ✅ Update `docs/ARCHITECTURE.md` if architecture/specs changed
- ✅ Update relevant task files in `docs/tasks/`

**Check**:
```bash
# Find unreferenced markdown files
find docs -name "*.md" -type f

# Review each - is it still needed?
```

#### 6. Git Status Review

```bash
# Check what's about to be committed
git status

# Review untracked files - keep or delete?
git status --short | grep "^??"

# Check for large files (>1MB)
find . -type f -size +1M -not -path "./.git/*" -not -path "./historical_data/*"
```

#### 7. Update .gitignore (If Needed)

If you find temporary files that shouldn't be committed:
```bash
# Add patterns to .gitignore
echo "*.tmp" >> .gitignore
echo "debug_*.log" >> .gitignore
echo ".DS_Store" >> .gitignore
```

---

### Before Every Commit

**Mandatory checks** (MUST pass before committing):

```bash
# 1. No uncommitted temporary files
[ -z "$(find . -name '*.tmp' -o -name '*.bak')" ] && echo "✅ No temp files" || echo "❌ Temp files found"

# 2. Tests pass (if applicable)
# uv run pytest tests/ && echo "✅ Tests pass" || echo "❌ Tests fail"

# 3. No obvious debug code
! git diff --cached | grep -E "(print\(|console\.log|debugger|import pdb)" && echo "✅ No debug code" || echo "⚠️  Debug code in commit"

# 4. File count reasonable
CHANGED=$(git diff --cached --name-only | wc -l)
[ $CHANGED -lt 20 ] && echo "✅ Changed files: $CHANGED" || echo "⚠️  Many files: $CHANGED (review needed)"
```

---

### What to DELETE vs KEEP

#### ❌ DELETE (Always)
- Temporary files (`.tmp`, `.bak`, `~`)
- Python cache (`__pycache__`, `.pyc`)
- Test cache (`.pytest_cache`, `.coverage`)
- Debug logs (`debug_*.log`, `*.trace`)
- Screenshots for debugging (unless documented)
- Experiment files not integrated (`test_*.py` outside tests/)
- Commented code blocks >1 week old
- Unused imports
- TODOs marked DONE

#### ✅ KEEP (Always)
- Historical data (`historical_data/html_files/`)
- Documentation (if referenced in CLAUDE.md or README)
- Tests (`tests/**/*.py`)
- Configuration files (`.claude/`, `pyproject.toml`, `.gitignore`)
- Source code in `live/`, `core/`, `scripts/`
- `uv.lock` (dependency lockfile - COMMIT THIS!)

#### ⚠️ REVIEW CASE-BY-CASE
- Jupyter notebooks (`.ipynb`) - Keep if documented, archive if experimental
- Large binary files (>1MB) - Consider git LFS or external storage
- Generated HTML files - Keep if part of output, delete if test artifacts
- Log files - Keep if needed for debugging, delete if >1 week old

---

### Post-Cleanup Commit Message

After cleanup, commit with clear message:

```bash
# Good commit message pattern:
git commit -m "[Task XX] Module: Description

Changes:
- Implemented: feature.py
- Tests: test_feature.py (coverage: 85%)
- Cleanup: Removed 3 temp files, 2 unused imports

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Periodic Cleanup (Weekly)

Run this every Friday or after completing a major task:

```bash
# Find files not modified in 2 weeks
find . -type f -mtime +14 -not -path "./.git/*" -not -path "./historical_data/*"

# Review and archive or delete
```

**Check for**:
- Orphaned files (not referenced anywhere)
- Old experiment branches (`git branch --merged`)
- Unused Skills (check usage in logs)
- Outdated documentation

---

### Cleanup Automation (Optional)

Create `.git/hooks/pre-commit` for automatic checks:

```bash
#!/bin/bash
# .git/hooks/pre-commit

echo "🧹 Running pre-commit cleanup..."

# Remove Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# Check for temp files
TEMP_FILES=$(find . -name "*.tmp" -o -name "*.bak" 2>/dev/null)
if [ -n "$TEMP_FILES" ]; then
    echo "❌ Temporary files found:"
    echo "$TEMP_FILES"
    echo "Remove them before committing"
    exit 1
fi

# Check for debug code
if git diff --cached | grep -E "(print\(|console\.log|debugger)"; then
    echo "⚠️  Debug code detected in staged files"
    echo "Review and remove before committing (or use --no-verify to skip)"
    # Don't block commit, just warn
fi

echo "✅ Pre-commit checks passed"
```
