# 🔒 Git Safety Check - User Guide

**Installed**: 2025-10-20
**Status**: ✅ Active
**Hook**: `.claude/hooks/git-safety-check.py`

---

## 🎯 What It Protects

### ❌ **BLOCKED Operations** (Exit code 1)

| Operation | Example | Why Blocked |
|-----------|---------|-------------|
| Force push to protected branches | `git push --force origin main` | Prevents rewriting shared history |
| Delete protected branches | `git branch -D main` | Protects main/master/production |
| Reset on main branch | `git reset --hard HEAD~5` (on main) | Prevents data loss |

**Protected branches**: `main`, `master`, `production`

---

### ⚠️ **WARNED Operations** (Exit code 0, shows warning)

| Operation | Example | Why Warned |
|-----------|---------|------------|
| Force push to feature branches | `git push --force origin feature-x` | May overwrite remote, use carefully |
| Commit sensitive files | `git add .env` | May leak secrets |
| Commit large files | `git add large_file.bin` (>50MB) | Bloats repository |
| Sensitive keywords in message | `git commit -m "Added API key"` | May indicate secret leak |

---

## 📋 Sensitive File Patterns (UTXOracle)

**Automatically detected**:
```
.env                    # Environment variables
.env.local              # Local env overrides
.env.production         # Production secrets
bitcoin.conf            # Bitcoin RPC credentials
.cookie                 # Bitcoin auth cookie
*.pem                   # SSL/TLS certificates
*.key                   # Private keys
id_rsa                  # SSH private key
.aws/credentials        # AWS credentials (future)
.pypirc                 # PyPI credentials
```

**Sensitive keywords in content**:
```
BROWSERBASE_API_KEY
BROWSERBASE_PROJECT_ID
rpcuser
rpcpassword
private_key
secret_key
api_key
password
token
```

---

## 🧪 Test Examples

### ✅ **Test 1: Block force push to main**

```bash
# Try to force push (will be BLOCKED)
git push --force origin main

# Output:
❌ BLOCKED: Force push to protected branch 'main' is not allowed.
   Use 'git push' without --force, or create a feature branch first.
```

---

### ✅ **Test 2: Warn on sensitive file commit**

```bash
# Stage .env file
git add .env

# Try to commit (will WARN but allow)
git commit -m "Update config"

# Output:
⚠️  WARNING: Attempting to commit sensitive files:
   - .env
   Review carefully before proceeding. Consider adding to .gitignore.
```

---

### ✅ **Test 3: Allow normal operations**

```bash
# Normal push (no warnings)
git push origin feature-branch

# No output = all clear ✅
```

---

## 🔧 Configuration

### **Edit Protected Branches**

```python
# In .claude/hooks/git-safety-check.py
PROTECTED_BRANCHES = ["main", "master", "production", "release"]  # Add more
```

### **Edit Large File Threshold**

```python
# In .claude/hooks/git-safety-check.py
LARGE_FILE_THRESHOLD = 100_000_000  # Change to 100MB
```

### **Add Custom Sensitive Patterns**

```python
# In .claude/hooks/git-safety-check.py
SENSITIVE_PATTERNS = [
    r'\.env$',
    r'my-custom-secret\.json$',  # Add your patterns
]
```

---

## 🚨 Bypass Hook (Emergency Only)

**WARNING**: Only use in genuine emergencies!

### **Option 1: Temporary disable in settings.local.json**

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": []  // Empty = disabled
      }
    ]
  }
}
```

### **Option 2: Git bypass (NOT RECOMMENDED)**

```bash
# This bypasses ALL hooks (dangerous!)
git push --force --no-verify origin main
```

**Better approach**: Fix the issue instead of bypassing!

---

## 📊 Common Scenarios

### **Scenario 1: Need to force push feature branch**

```bash
# ✅ ALLOWED (with warning)
git push --force origin feature-xyz

# Output:
⚠️  WARNING: Force push detected on branch 'feature-xyz'.
   This may overwrite remote history. Proceed with caution.

# → Review warning, proceed if intentional
```

---

### **Scenario 2: Accidentally staged .env**

```bash
# ⚠️ WARNED
git add .env
git commit -m "Config update"

# Output:
⚠️  WARNING: Attempting to commit sensitive files:
   - .env
   Review carefully before proceeding. Consider adding to .gitignore.

# → Fix:
git reset HEAD .env           # Unstage
echo ".env" >> .gitignore     # Prevent future accidents
git add .gitignore
git commit -m "Add .env to gitignore"
```

---

### **Scenario 3: Large historical data file**

```bash
# Commit 100MB HTML file
git add historical_data/large_analysis.html

# Output:
⚠️  WARNING: Large files detected in commit:
   - historical_data/large_analysis.html (98.5 MB)
   Consider using Git LFS for files >50MB.

# → Options:
1. Use Git LFS: git lfs track "*.html"
2. Compress: gzip large_analysis.html
3. Archive separately: Move to external storage
```

---

## 🛠️ Troubleshooting

### **Hook not firing**

```bash
# Check hook is executable
ls -la .claude/hooks/git-safety-check.py
# Should show: -rwxr-xr-x (executable)

# Fix if needed:
chmod +x .claude/hooks/git-safety-check.py

# Verify settings.local.json
cat .claude/settings.local.json | grep -A 5 '"matcher": "Bash"'
```

---

### **False positives**

```bash
# If hook blocks legitimate operation:
1. Review why it's blocking (check error message)
2. Adjust configuration if needed (see Configuration section)
3. Report issue if bug

# Example: bitcoin.conf is NOT sensitive in your case
# → Remove from SENSITIVE_PATTERNS in git-safety-check.py
```

---

### **Hook errors**

```bash
# Check Python syntax
python3 .claude/hooks/git-safety-check.py

# Test manually
echo '{"tool_input": {"command": "git status"}}' | .claude/hooks/git-safety-check.py
```

---

## 📈 Statistics

Track how often hook prevents issues:

```bash
# Count blocks (manual for now)
grep "BLOCKED" .claude/logs/*.jsonl | wc -l

# Count warnings
grep "WARNING" .claude/logs/*.jsonl | wc -l
```

---

## 🎓 Best Practices

1. **Never force push to main** → Create feature branch instead
2. **Review all warnings** → They exist for a reason
3. **Keep .gitignore updated** → Prevent sensitive file commits
4. **Use .env for secrets** → Never hardcode in code
5. **Compress large files** → Or use Git LFS (>50MB)

---

## 📚 Related Files

- Hook script: `.claude/hooks/git-safety-check.py`
- Configuration: `.claude/settings.local.json`
- Analysis: `.claude/HOOKS_ANALYSIS.md`
- .gitignore: `/.gitignore` (add sensitive patterns)

---

**Installed**: 2025-10-20
**Version**: 1.0
**Maintained by**: Auto-updates via git-safety-check.py
**ROI**: 1 disaster prevented = >10h recovery saved
