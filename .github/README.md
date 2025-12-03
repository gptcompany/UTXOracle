# .github Directory - Cleanup Tools

**Automation and checklists to keep the repository clean**

---

## 📋 Files

### CLEANUP_CHECKLIST.md
**Quick reference for manual cleanup before commits**

Use this for:
- Quick copy-paste commands
- Pre-commit checklist (tick boxes)
- DELETE vs KEEP guidelines
- Commit message template

**Usage**:
```bash
# View checklist
cat .github/CLEANUP_CHECKLIST.md

# Or keep it open in another terminal
less .github/CLEANUP_CHECKLIST.md
```

### pre-commit.hook
**Optional automated pre-commit validation**

Use this for:
- Automatic Python cache removal
- Block commits with temporary files
- Warn about debug code
- Check for large files
- (Optional) Run tests/linter before commit

**Installation** (optional):
```bash
# Install the hook
cp .github/pre-commit.hook .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Test it
git add .
git commit -m "Test commit"

# Bypass hook for emergency commits
git commit --no-verify -m "Emergency fix"
```

**What it does**:
1. ✅ Auto-removes `__pycache__`, `.pytest_cache`, `*.pyc`
2. ❌ Blocks commit if `*.tmp`, `*.bak`, `*~` files found
3. ⚠️  Warns about `print()`, `console.log`, `debugger` in staged code
4. ⚠️  Warns about large commits (>30 files)
5. ⚠️  Warns about large files (>5MB)
6. ⭕ Optional: Run tests (commented out)
7. ⭕ Optional: Run linter (commented out)

---

## 🚀 Recommended Workflow

### Option 1: Manual (No Hook)
**Best for**: Beginners, learning the cleanup process

```bash
# Before every commit:
1. Open .github/CLEANUP_CHECKLIST.md
2. Run each command
3. Tick off checklist items
4. Commit

# Quick commands:
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.tmp" -o -name "*.bak"  # Should be empty
git status --short | grep "^??"        # Review untracked
```

### Option 2: Automated (With Hook)
**Best for**: Experienced users, faster workflow

```bash
# One-time setup:
cp .github/pre-commit.hook .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Then just commit normally:
git add .
git commit -m "Your message"

# Hook automatically:
- Removes Python cache
- Blocks temp files
- Warns about debug code
```

### Option 3: Hybrid (Manual + Hook)
**Best for**: Balance of control and automation

```bash
# Install hook for safety nets:
cp .github/pre-commit.hook .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# But still review manually before commit:
cat .github/CLEANUP_CHECKLIST.md
# Run checks manually first
# Then commit (hook provides backup validation)
```

---

## 🔧 Customization

### Enable Tests in Pre-Commit Hook

Edit `.git/hooks/pre-commit`:
```bash
# Uncomment lines ~89-95:
echo "  Running tests..."
if ! uv run pytest tests/ -q; then
    echo "❌ COMMIT BLOCKED: Tests failed"
    exit 1
fi
```

### Enable Linter in Pre-Commit Hook

Edit `.git/hooks/pre-commit`:
```bash
# Uncomment lines ~100-107:
echo "  Running linter..."
if ! ruff check . --quiet; then
    echo "⚠️  WARNING: Linting errors"
fi
```

### Adjust Large File Threshold

Edit `.git/hooks/pre-commit` line ~70:
```bash
# Change 5M to your threshold
LARGE_FILES=$(... -size +5M ...)  # Change to +10M, +1M, etc.
```

---

## 🎯 When to Use What

| Scenario | Tool | Reason |
|----------|------|--------|
| Learning cleanup process | Manual checklist | Understand what/why |
| Fast iteration development | Automated hook | Save time |
| Before major commits | Manual checklist | Extra review |
| Emergency hotfix | `--no-verify` flag | Bypass hook |
| Weekly cleanup | Manual checklist + periodic commands | Deep clean |

---

## 📚 Related Documentation

- **Full cleanup protocol**: `/CLAUDE.md` → "Task Completion Protocol"
- **.gitignore patterns**: `/.gitignore` (auto-ignores temp files)
- **Skills framework**: `/.claude/SKILLS_FRAMEWORK_BLUEPRINT.md`

---

## 💡 Tips

### Quick Cleanup Commands

```bash
# One-liner cleanup
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; \
find . -type f -name "*.pyc" -delete

# Find files not modified in 2 weeks
find . -type f -mtime +14 -not -path "./.git/*" -not -path "./historical_data/*"

# Check git status before cleanup
git status --short | grep "^??"
```

### Bypass Hook for Emergency

```bash
# Emergency commit (skip all checks)
git commit --no-verify -m "Hotfix: Critical bug"

# Or temporarily disable hook
chmod -x .git/hooks/pre-commit  # Disable
git commit -m "Your message"
chmod +x .git/hooks/pre-commit  # Re-enable
```

### Review What Would Be Deleted

```bash
# Dry-run: See what would be deleted (don't delete yet)
find . -name "*.tmp" -o -name "*.bak"  # Review list
# If OK, then delete:
find . -name "*.tmp" -delete
```

---

## 🤝 Contributing

When modifying these tools:
1. Update this README
2. Update `/CLAUDE.md` → "Task Completion Protocol"
3. Test pre-commit hook with test commit
4. Document changes in commit message

---

*Last updated: 2025-10-18*
