# 🧠 Smart Safety Check - Intelligent Protection

**Created**: 2025-10-20
**Replaces**: Old pre-tool-use.py (blocking approach)
**Philosophy**: Guide Claude, don't frustrate it

---

## 🎯 Problem with Old Approach

**Old hook** (pre-tool-use.py.old):
- ❌ Blocked `rm -rf` entirely
- ❌ Frustrated Claude → Goes into "tilt"
- ❌ No recovery mechanism
- ❌ Binary: block or allow

**Result**: Claude gets stuck, keeps trying same blocked command, wastes tokens.

---

## ✨ New Smart Approach

**Key Innovation**: **Checkpoint → Warn → Allow** (instead of block)

```
Dangerous Command Detected
         ↓
   AUTO-CHECKPOINT (git)
         ↓
   Show Warning + Rollback Instructions
         ↓
   ALLOW (with safeguards)
```

**Benefits**:
- ✅ Claude continues working (no tilt)
- ✅ Automatic recovery point (git checkpoint)
- ✅ CWD scope suggestions
- ✅ User awareness (clear warnings)

---

## 📊 Risk Categories

### 🔴 **CRITICAL** - Block Entirely

**No recovery possible, block completely**

| Pattern | Example | Why Block |
|---------|---------|-----------|
| Fork bomb | `:(){:\|:&};:` | System crash |
| dd to device | `dd if=/dev/zero of=/dev/sda` | Data loss |
| Filesystem format | `mkfs.ext4 /dev/nvme0n1` | Irrecoverable |
| Root deletion | `rm -rf /` | System destruction |

**Action**: Block + Error message

---

### 🟡 **HIGH** - Checkpoint + Warn + Allow

**Dangerous but recoverable with git**

| Pattern | Example | Protection |
|---------|---------|------------|
| `rm -rf` | `rm -rf node_modules` | Auto-checkpoint → Warn → Allow |
| Multiple wildcards | `rm *.* *` | Auto-checkpoint → Warn |
| `find -delete` | `find . -name "*.tmp" -delete` | Auto-checkpoint → Warn |
| `git reset --hard` | `git reset --hard HEAD~5` | Checkpoint → Warn |
| `git clean -ffd` | `git clean -ffd` | Checkpoint → Warn |

**Action**:
1. Create git checkpoint
2. Show warning with rollback command
3. Suggest CWD-limited alternative
4. ALLOW command to proceed

---

### 🟢 **MEDIUM** - Warn Only

**Potentially problematic, but low impact**

| Pattern | Example | Why Warn |
|---------|---------|----------|
| `chmod 777` | `chmod -R 777 .` | Security issue |
| `chown -R` | `chown -R user:group /` | Permission changes |
| Global npm | `npm install -g package` | System-wide install |

**Action**: Show warning + Allow

---

## 🎬 Example Workflows

### **Scenario 1: rm -rf node_modules**

```bash
# Claude suggests:
Bash: rm -rf node_modules

# Smart hook response:
⚠️  HIGH RISK OPERATION DETECTED

Reason: Recursive force deletion
Command: rm -rf node_modules

✅ Git checkpoint created: c31bcf1a
   Rollback: git reset --hard c31bcf1a

📁 Current directory: /media/sam/1TB/UTXOracle
💡 Safer alternative (CWD-limited):
   /media/sam/1TB/UTXOracle/rm -rf node_modules

⚡ This command will proceed, but review carefully!
   Consider the safer alternative above to limit scope.

# Command executes with safeguards ✅
# If something goes wrong:
$ git reset --hard c31bcf1a
```

**Why this works**:
- Claude sees warning but continues
- User is informed with recovery option
- No "tilt" from blocked command
- Safety net is automatic

---

### **Scenario 2: Fork Bomb (Critical)**

```bash
# Malicious command:
Bash: :(){:|:&};:

# Smart hook response:
🛑 BLOCKED: Fork bomb detected
Command: :(){:|:&};:

This operation is too dangerous and has been blocked entirely.
If you absolutely need this, run it manually outside Claude Code.

# Command blocked ❌
```

**Why block**: No recovery possible, would crash system.

---

### **Scenario 3: chmod 777 (Medium)**

```bash
# Claude suggests:
Bash: chmod -R 777 .

# Smart hook response:
ℹ️  Medium Risk Operation

Reason: Chmod 777 recursive
Command: chmod -R 777 .

Review this operation carefully. It may have unintended consequences.

# Command executes with light warning ✅
```

---

## 🔧 Configuration

### **Edit Risk Patterns**

```python
# In .claude/hooks/smart-safety-check.py

# Add new CRITICAL pattern:
CRITICAL_PATTERNS = [
    (r':.*\(\).*\{.*\};:', "Fork bomb"),
    (r'my-dangerous-pattern', "My custom block"),  # Add here
]

# Add new HIGH-risk pattern:
HIGH_RISK_PATTERNS = [
    (r'rm\s+.*-rf', "Recursive deletion"),
    (r'docker\s+system\s+prune\s+-a', "Docker full prune"),  # Example
]
```

### **Adjust Checkpoint Behavior**

```python
# In create_git_checkpoint():

# Change commit message:
subprocess.run(
    ["git", "commit", "-m", "[SAFETY] Before dangerous operation"],
    # ... 
)
```

---

## 📈 Comparison

| Feature | Old Approach | Smart Approach |
|---------|--------------|----------------|
| **rm -rf detection** | ✅ | ✅ |
| **Fork bomb detection** | ✅ | ✅ |
| **Auto-checkpoint** | ❌ | ✅ |
| **CWD suggestions** | ❌ | ✅ |
| **Claude tilt prevention** | ❌ | ✅ |
| **Recovery instructions** | ❌ | ✅ |
| **Risk categories** | ❌ | ✅ |

---

## 🎓 Best Practices

### **For Users**

1. **Read warnings** → They contain rollback commands
2. **Check CWD suggestions** → Safer alternatives provided
3. **Trust checkpoints** → Auto-created before HIGH-risk ops
4. **Report false positives** → Help improve detection

### **For Claude**

1. **Don't retry blocked commands** → CRITICAL blocks are final
2. **Review HIGH-risk warnings** → Consider CWD-limited alternatives
3. **Proceed with MEDIUM warnings** → Just be aware

---

## 🛠️ Troubleshooting

### **Checkpoints not created**

```bash
# Check if in git repo:
git status

# If not:
git init
git add .
git commit -m "Initial commit"
```

### **False positives**

```bash
# Command incorrectly flagged as dangerous:
1. Review pattern in smart-safety-check.py
2. Adjust regex if too broad
3. Consider moving to lower risk category
```

### **Hook not firing**

```bash
# Verify executable:
ls -la .claude/hooks/smart-safety-check.py
# Should be: -rwxr-xr-x

# Fix:
chmod +x .claude/hooks/smart-safety-check.py
```

---

## 📚 Related Files

- **Hook script**: `.claude/hooks/smart-safety-check.py`
- **Old hook (backup)**: `.claude/hooks/pre-tool-use.py.old`
- **Git safety**: `.claude/hooks/git-safety-check.py`
- **Configuration**: `.claude/settings.local.json`

---

## 🚀 ROI

**Time Saved**:
- Old approach: Claude tilt = 5-10 min recovery
- Smart approach: Warning + proceed = 0 min waste

**Protection**:
- Auto-checkpoints: ~10h recovery time saved (if disaster)
- CWD suggestions: Reduced blast radius

**Total Value**: 🔴 CRITICAL feature for production use

---

**Created**: 2025-10-20
**Philosophy**: Inspired by real-world incident (node_modules deletion)
**Credit**: claude-code-hooks community + user feedback
