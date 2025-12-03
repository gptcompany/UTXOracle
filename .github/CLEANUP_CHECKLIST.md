# 🧹 Cleanup Checklist (Quick Reference)

**Run BEFORE every commit!**

---

## ⚡ Quick Commands

```bash
# 1. Remove Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete

# 2. Check for temp files
find . -type f \( -name "*.tmp" -o -name "*.bak" -o -name "*~" \)

# 3. Pre-commit checks
[ -z "$(find . -name '*.tmp' -o -name '*.bak')" ] && echo "✅ No temp files" || echo "❌ Temp files found"

# 4. Review uncommitted files
git status --short | grep "^??"
```

---

## ✅ Checklist (Copy-Paste)

Before committing, tick off each item:

- [ ] Removed temporary files (`.tmp`, `.bak`, `~`)
- [ ] Cleaned Python cache (`__pycache__`, `.pyc`)
- [ ] Removed debug `print()` statements
- [ ] Removed unused imports
- [ ] Deleted commented-out code blocks
- [ ] Resolved or removed TODO comments
- [ ] Updated CLAUDE.md if structure changed
- [ ] Ran linter (if available): `ruff check .`
- [ ] Tests pass: `uv run pytest tests/`
- [ ] Reviewed untracked files: `git status`
- [ ] File count reasonable (<20 files changed)

---

## 🗑️ Delete vs Keep

### ❌ DELETE
- `*.tmp`, `*.bak`, `*~` - Temporary files
- `__pycache__/`, `*.pyc` - Python cache
- `.pytest_cache/` - Test cache
- `debug_*.log` - Debug logs
- Commented code >1 week old
- Unused imports
- Experiment files outside `tests/`

### ✅ KEEP
- `historical_data/html_files/` - Historical data
- `tests/**/*.py` - Test files
- `.claude/` - Configuration
- `uv.lock` - Dependency lockfile (**COMMIT THIS!**)
- Documentation referenced in CLAUDE.md

---

## 📝 Commit Message Template

```bash
git commit -m "[Task XX] Module: Description

Changes:
- Implemented: feature.py
- Tests: test_feature.py (coverage: 85%)
- Cleanup: Removed 3 temp files, 2 unused imports

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

See **CLAUDE.md** → "Task Completion Protocol" for full details.
