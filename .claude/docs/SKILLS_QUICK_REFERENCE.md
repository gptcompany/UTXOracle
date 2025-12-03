# Skills Quick Reference Card

**One-page cheat sheet for working with Skills in this repository**

---

## 🎯 Current Skills (4)

| Skill | Trigger | Saves | Use When |
|-------|---------|-------|----------|
| **pytest-test-generator** | "generate tests" | 83% | Creating test files |
| **github-workflow** | "create PR" | 79% | GitHub operations |
| **pydantic-model-generator** | "pydantic model" | 75% | Data models |
| **bitcoin-rpc-connector** | "bitcoin rpc" | 60% | RPC client setup |

**Total Savings**: ~20,400 tokens/task (77% reduction on templates)

---

## 🚦 Decision Tree

```
Need to do something repetitive?
├─ Will I do this 3+ times?
│  ├─ NO → Just do it manually
│  └─ YES → Is it template-driven?
│     ├─ YES → Use existing Skill or create new one
│     └─ NO → Use Subagent for complex logic
```

---

## ✅ When to Create a NEW Skill

**Create if ALL true**:
- ✅ Repeats 3+ times (real, not hypothetical)
- ✅ Template-driven (clear input/output)
- ✅ Saves >60% tokens (measured)
- ✅ Will use in next 2 weeks (not "someday")

**Don't create if ANY true**:
- ❌ Used once or twice
- ❌ Needs complex reasoning
- ❌ "Might need it later" (YAGNI!)
- ❌ Saves <60% tokens

---

## 📋 Skill Creation Checklist

```bash
# 1. Create directory
mkdir -p .claude/skills/{skill-name}

# 2. Create SKILL.md with frontmatter
cat > .claude/skills/{skill-name}/SKILL.md << 'EOF'
---
name: {skill-name}
description: {What it does and when to use it}
---

# {Skill Name}

## Quick Start
...
EOF

# 3. Test it
# In Claude Code, say trigger phrase

# 4. Measure savings
# Compare tokens before/after

# 5. Update docs
# Add to CLAUDE.md, SKILL_SUMMARY.md
```

---

## 📊 Token Savings Formula

```
Savings per use = Manual tokens - Skill tokens
Total saved = Savings per use × Frequency

Example (pytest-test-generator):
  Manual: 3,000 tokens
  Skill: 500 tokens
  Used: 10 times
  Total saved: (3,000 - 500) × 10 = 25,000 tokens ✅
```

---

## 🔧 Troubleshooting

**Skill not triggering?**
- Check trigger keywords in SKILL.md
- Try exact trigger phrase from "Automatic Invocation"
- Verify SKILL.md is in `.claude/skills/{name}/`

**Output inconsistent?**
- Add more template variants
- Improve "Quick Start" examples
- Make placeholders `{clearer}`

**Token savings lower than expected?**
- Recalculate baseline (manual generation)
- Simplify templates (remove redundancy)
- Consider if Skill is too generic

---

## 📚 Resources

**Internal Docs**:
- `.claude/SKILLS_FRAMEWORK_BLUEPRINT.md` - Full framework for ANY project
- `SKILL_SUMMARY.md` - Token economics analysis
- `CLAUDE.md` - Project instructions
- `.claude/CONSISTENCY_CHECK.md` - Validation report

**Anthropic Docs**:
- Skills Overview: https://docs.claude.com/en/docs/claude-code/skills
- Best Practices: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices
- API Guide: https://docs.claude.com/en/api/skills-guide

**Examples**:
- `.claude/skills/pytest-test-generator/SKILL.md`
- `.claude/skills/pydantic-model-generator/SKILL.md`

---

## 🎯 KISS & YAGNI Reminder

**KISS** - Keep It Simple
- Start with 1-2 Skills, not 5-7
- Use boring templates, not clever abstractions
- Clear over generic

**YAGNI** - You Ain't Gonna Need It
- Don't create Skills "just in case"
- Only create when ACTUALLY needed 3+ times
- Delete if unused for 2 weeks

**Remember**: The best code is no code. The second best is deleted code. The third best is simple code.

---

*Last updated: 2025-10-18 | Skills: 4 | Total saved: 87,600 tokens*
