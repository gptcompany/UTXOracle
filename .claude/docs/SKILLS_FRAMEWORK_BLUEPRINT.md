# Skills Framework Blueprint for Claude Code

**Meta-documentation for implementing Agent Skills in ANY repository**

> 🎯 **Purpose**: Reusable framework to analyze your codebase and implement Skills that reduce token usage by 60-83% on repetitive operations.

**Based on**: UTXOracle production implementation (4 Skills, 87,600 tokens saved)

---

## 📚 Official Documentation (Required Reading)

**Anthropic Claude Docs**:
1. **Skills Overview**: https://docs.claude.com/en/docs/claude-code/skills
2. **Skills Best Practices**: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices
3. **API Quickstart**: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/quickstart
4. **Subagents vs Skills**: https://docs.claude.com/en/docs/claude-code/sub-agents
5. **Skills API Guide**: https://docs.claude.com/en/api/skills-guide

**UTXOracle Reference**:
- `CLAUDE.md` - Project instructions (adapt for your project)
- `SKILL_SUMMARY.md` - Token economics analysis
- `.claude/skills/` - 4 production Skills as templates

---

## 🎯 When to Use Skills (vs Subagents)

### ✅ Use Skills When:
- **Repetitive pattern** appears 3+ times in your project
- **Template-driven** output (tests, boilerplate, config files)
- **Simple transformation** with clear input/output
- **Token efficiency critical** (70-83% savings possible)
- **Portable across projects** (e.g., test generation)

### ❌ Use Subagents When:
- **Complex reasoning** required (algorithm design, architecture)
- **Deep domain expertise** needed (Bitcoin protocol, WebGL)
- **Multi-step workflows** with decision trees
- **Context-dependent** solutions (error handling strategies)
- **One-off tasks** (not repeated)

### 📊 Decision Tree

```
Does this task repeat 3+ times?
├─ NO → Use Subagent (or just do it manually)
└─ YES → Is it template-driven?
    ├─ YES → CREATE SKILL ✅
    └─ NO → Use Subagent
```

**Example (UTXOracle)**:
- ✅ Skill: Generate pytest tests (used 5-10+ times)
- ❌ Subagent: Implement ZMQ listener (used 1 time, complex)

---

## 📋 Repository Analysis Workflow

### Step 1: Identify Repetitive Patterns (15-30 min)

Analyze your codebase for patterns that repeat:

```bash
# Example analysis questions:
1. Do I create similar files repeatedly?
   → Tests, models, configs, API endpoints?

2. Do I write similar code blocks?
   → Boilerplate, validators, error handlers?

3. Do I follow a specific format?
   → Commit messages, PR descriptions, docstrings?

4. Do I import the same dependencies?
   → RPC clients, database connections, logging setup?
```

**UTXOracle Example**:
```
✅ Pattern found: Creating pytest tests for each module (5+ times)
✅ Pattern found: Pydantic models with validators (10+ times)
✅ Pattern found: GitHub PR descriptions following template (10+ times)
✅ Pattern found: Bitcoin RPC connection setup (3+ times)
```

### Step 2: Calculate Token ROI (10 min)

For each pattern, estimate:

```
Token Cost WITHOUT Skill:
  - Writing code manually: ~X tokens (Claude writes it)

Token Cost WITH Skill:
  - Loading Skill metadata: ~100-200 tokens
  - Writing specific instance: ~Y tokens

Savings = X - Y
ROI = (Savings / X) * 100%

Threshold: If ROI > 60% and used 3+ times → CREATE SKILL
```

**UTXOracle Example**:
```
pytest-test-generator:
  - Manual: 3,000 tokens per test file
  - With Skill: 500 tokens per test file
  - Savings: 2,500 tokens (83%)
  - Usage: 10+ test files
  - Total saved: 25,000 tokens ✅ CREATE

pydantic-model-generator:
  - Manual: 2,000 tokens per model
  - With Skill: 500 tokens per model
  - Savings: 1,500 tokens (75%)
  - Usage: 15+ models
  - Total saved: 22,500 tokens ✅ CREATE
```

### Step 3: Prioritize Skills (YAGNI Rule)

**IMPORTANT**: Don't create Skills "just in case"

```
Priority = (Token Savings) × (Frequency) × (Certainty)

High Priority (Create NOW):
  - >70% savings + >5 uses + 100% sure you need it

Medium Priority (Create when needed):
  - >60% savings + 3-5 uses + 80% sure

Low Priority (DON'T create):
  - <60% savings OR <3 uses OR hypothetical future use
```

**UTXOracle Example**:
```
✅ HIGH: pytest-test-generator (83% × 10 uses × 100% = CREATE)
✅ HIGH: pydantic-model-generator (75% × 15 uses × 100% = CREATE)
❌ LOW: zmq-subscriber-template (65% × 1 use × 100% = DON'T)
❌ LOW: module-boilerplate (70% × 5 uses × 50% = WAIT)
```

**YAGNI Applied**: Started with 2 Skills, added 2 more when ACTUALLY needed. Rejected 3 proposed Skills as over-engineering.

---

## 🏗️ Skill Anatomy (Standard Structure)

Every Skill follows this structure (based on Anthropic docs + UTXOracle patterns):

### File Structure
```
.claude/skills/
└── {skill-name}/
    ├── SKILL.md              # Required: Main skill file
    ├── templates/            # Optional: Template files
    │   ├── template1.txt
    │   └── template2.py
    ├── scripts/              # Optional: Executable scripts
    │   └── generate.sh
    └── REFERENCE.md          # Optional: Additional docs
```

### SKILL.md Template

```markdown
---
name: {skill-name}
description: {What this skill does and when Claude should use it. Max 1024 chars.}
---

# {Skill Name}

{Brief overview - 1-2 sentences}

## Quick Start

**User says**: "{Example user input}"

**Skill generates**:
```{language}
{Example output showing what the skill produces}
```

## Templates

### 1. {Template Name}
```{language}
{Template with {placeholders} in curly braces}
```

### 2. {Another Template}
```{language}
{Another template variant}
```

## Usage Patterns

### Pattern 1: {Use Case}
```
User: "{User request}"

Skill:
1. {Step 1}
2. {Step 2}
3. {Step 3}
```

### Pattern 2: {Another Use Case}
...

## {Domain-Specific Section}
{E.g., "Bitcoin-Specific Validators", "Test Fixtures", etc.}

## Automatic Invocation

**Triggers**:
- "{keyword phrase 1}"
- "{keyword phrase 2}"
- "{keyword phrase 3}"

**Does NOT trigger**:
- {What this skill doesn't handle}
- {When to use a different approach}

## Token Savings

| Task | Without Skill | With Skill | Savings |
|------|--------------|------------|---------|
| {Example 1} | X tokens | Y tokens | Z% |
| {Example 2} | X tokens | Y tokens | Z% |

**Average Savings**: {X%} ({before} → {after} tokens)
```

### Frontmatter Requirements

From Anthropic docs:

```yaml
---
name: skill-name-here
  # REQUIRED
  # Max 64 characters
  # Kebab-case recommended (lowercase-with-hyphens)
  # Should be descriptive but concise

description: What this skill does and when to use it.
  # REQUIRED
  # Max 1024 characters
  # Should explain BOTH what it does AND when Claude should invoke it
  # Include trigger keywords if helpful
---
```

**✅ Good Examples** (from UTXOracle):
```yaml
name: pytest-test-generator
description: Generate pytest test templates for UTXOracle modules following TDD patterns. Automatically creates RED phase tests with async fixtures, coverage markers, and integration test stubs.

name: pydantic-model-generator
description: Auto-generate Pydantic models from schema descriptions with type hints, validation rules, examples, and JSON schema export. 75% token savings (2,000→500).
```

**❌ Bad Examples**:
```yaml
name: test-gen  # Too vague
description: Generates tests.  # Doesn't explain WHEN to use it

name: SuperAwesomeUltimatePydanticModelGeneratorToolV2  # Too long (>64 chars)
description: Does stuff with models.  # Not specific enough
```

---

## 🔨 Skill Creation Workflow (Step-by-Step)

### Phase 1: Define the Skill (30 min)

**1.1 Name the Skill**
```bash
# Naming convention: {domain}-{action}-{object}
# Examples from UTXOracle:
pytest-test-generator       # domain=pytest, action=generate, object=tests
pydantic-model-generator    # domain=pydantic, action=generate, object=models
bitcoin-rpc-connector       # domain=bitcoin, action=connect, object=rpc
github-workflow             # domain=github, action=automate, object=workflow
```

**1.2 Write the description**
```
Template: "Auto-{action} {object} for {use case} with {key features}. {X%} token savings ({before}→{after})."

Example:
"Auto-generate pytest test templates for UTXOracle modules following TDD patterns. Automatically creates RED phase tests with async fixtures, coverage markers, and integration test stubs."
```

**1.3 Identify trigger keywords**
```
Brainstorm what users might say:
- "generate tests for [module]"
- "create test file for [file]"
- "add test for [function]"
- "write integration test"

Pick 3-5 most common ones
```

### Phase 2: Extract Templates (45-60 min)

**2.1 Find real examples in your code**
```bash
# Look for repetitive code patterns
git log --all --pretty=format: --name-only | sort | uniq -c | sort -rn | head -20

# Find similar files
find . -name "test_*.py" | head -5
# Read 3-5 files, extract common structure
```

**2.2 Templatize the pattern**
```python
# Before (specific):
def test_zmq_connection():
    listener = ZMQListener()
    assert listener.connect() == True

# After (template):
def test_{function_name}():
    {instance} = {ClassName}()
    assert {instance}.{method}() == {expected_value}
```

**2.3 Create 3-5 template variants**
- Basic template (80% use case)
- Advanced template (complex case)
- Edge case template (rare but important)

**UTXOracle Example** (pytest-test-generator):
```
1. Async Module Test Template (most common)
2. Sync Module Test Template
3. Integration Test Template
4. Coverage Marker Template
```

### Phase 3: Write the Skill (60-90 min)

**3.1 Create directory structure**
```bash
mkdir -p .claude/skills/{skill-name}
touch .claude/skills/{skill-name}/SKILL.md
```

**3.2 Fill in SKILL.md sections**

Use the template from "Skill Anatomy" above. Work in this order:

1. **Frontmatter** (5 min) - name, description
2. **Quick Start** (10 min) - Simple example showing input/output
3. **Templates** (30 min) - 3-5 template variants with placeholders
4. **Usage Patterns** (20 min) - Step-by-step workflows
5. **Automatic Invocation** (10 min) - Trigger keywords + what NOT to do
6. **Token Savings** (10 min) - Table with before/after comparisons

**3.3 Add project-specific sections** (optional)
```markdown
## {Your Domain}-Specific {Thing}

Examples from UTXOracle:
- Bitcoin-Specific Validators
- Test Fixtures Library
- RPC Method Wrappers
- WebSocket Message Types
```

### Phase 4: Test the Skill (15-30 min)

**4.1 Manual test**
```bash
# In Claude Code CLI or Desktop:
# Say one of your trigger phrases
"Generate tests for my_module"

# Verify:
1. Claude loads the Skill ✅
2. Claude generates correct output ✅
3. Output matches templates ✅
4. Placeholders are filled correctly ✅
```

**4.2 Measure token usage**
```
Before Skill:
  - Ask Claude to generate same output manually
  - Note token count in response

After Skill:
  - Use trigger phrase
  - Note token count

Verify savings match your estimate (±10%)
```

**4.3 Iterate**
```
Common issues:
- Triggers too vague → Add more specific keywords
- Templates too rigid → Add variants
- Output inconsistent → Improve examples in Quick Start
```

---

## 📊 Token Savings Analysis Template

Track actual savings to validate ROI:

```markdown
# {Skill Name} - Token Savings Analysis

## Baseline (Without Skill)

**Task**: {Describe the task}
**Method**: Manual Claude generation
**Average tokens**: {X tokens}
**Measured across**: {N samples}

Example prompt:
```
{Paste actual prompt used}
```

Output tokens: {Y}

## With Skill (After Implementation)

**Task**: {Same task}
**Method**: Skill invocation
**Average tokens**: {Z tokens}
**Measured across**: {N samples}

Example prompt:
```
{Paste trigger phrase}
```

Output tokens: {W}

## Results

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Tokens/task | {X} | {Z} | {%} |
| Time/task | {minutes} | {seconds} | {X}x faster |

**Actual Savings**: {X - Z} tokens ({%}%)
**Projected Savings** (if used {N} times): {(X-Z)*N} tokens

**ROI**: {pass/fail} (threshold: 60% savings, 3+ uses)
```

**UTXOracle Example**:
```markdown
# pytest-test-generator - Token Savings Analysis

Baseline: 3,000 tokens per test file (manual)
With Skill: 500 tokens per test file
Savings: 2,500 tokens (83%)

Used 10 times → Total saved: 25,000 tokens ✅
```

---

## ✅ Skill Validation Checklist

Before considering a Skill "complete":

### Technical Requirements
- [ ] `SKILL.md` file exists
- [ ] Frontmatter has `name` field (<64 chars)
- [ ] Frontmatter has `description` field (<1024 chars)
- [ ] YAML frontmatter is valid
- [ ] At least 1 "Quick Start" example
- [ ] At least 3 template variants
- [ ] "Automatic Invocation" section with triggers

### Quality Requirements
- [ ] Description explains WHEN to use (not just what)
- [ ] Templates have clear `{placeholders}`
- [ ] Examples show realistic input/output
- [ ] Token savings measured and documented
- [ ] Triggers tested and working

### YAGNI Requirements
- [ ] Pattern actually repeats 3+ times (not hypothetical)
- [ ] Token savings >60% (measured, not estimated)
- [ ] Will be used in next 2 weeks (not "someday")
- [ ] Can't easily be solved another way (no over-engineering)

### Documentation Requirements
- [ ] CLAUDE.md updated with new Skill
- [ ] Token savings added to SKILL_SUMMARY.md
- [ ] Skill added to `.claude/skills/` directory listing
- [ ] Consistency check passed (see CONSISTENCY_CHECK.md)

---

## 📁 Project Setup Template

### Minimal .claude Structure

```
your-project/
├── .claude/
│   ├── skills/                    # Skills directory
│   │   └── {skill-name}/
│   │       └── SKILL.md
│   ├── agents/                    # Subagents (if using)
│   │   └── {agent-name}.md
│   ├── prompts/                   # System prompts
│   │   └── system.md
│   ├── settings.local.json        # Permissions
│   └── config.json                # Project config
│
├── CLAUDE.md                      # Main project instructions
└── README.md
```

### CLAUDE.md Template (Adapt from UTXOracle)

```markdown
# CLAUDE.md

## Project Overview
{Your project description}

**🎯 Development Philosophy**: KISS + YAGNI
→ See [Development Principles](#development-principles)

## Skills ({N}) - Template-Driven Automation

| Skill | Purpose | Token Savings | Status |
|-------|---------|---------------|--------|
| {skill-1} | {purpose} | {%} ({before}→{after}) | ✅ |
| {skill-2} | {purpose} | {%} ({before}→{after}) | ✅ |

**Total Skill Savings**: ~{X} tokens/task

**Usage**: Automatically triggered by keywords:
- "{trigger 1}" → {skill-1}
- "{trigger 2}" → {skill-2}

## Development Principles

### 🎯 KISS & YAGNI Blueprint

#### KISS - Keep It Simple
- Choose boring technology
- Avoid premature optimization
- One module, one purpose
- Minimize dependencies
- Clear over clever code

#### YAGNI - You Ain't Gonna Need It
- Don't build for hypothetical futures
- Solve TODAY's problem
- Delete dead code
- Resist abstraction temptation

{Rest of your project-specific instructions}
```

---

## 🎓 Learning from UTXOracle (Real-World Example)

### What Worked ✅

**1. Started Small (2 Skills)**
- pytest-test-generator
- github-workflow

**2. Measured First, Optimized Later**
- Tracked actual token usage
- Validated 70-80% savings before scaling

**3. Said NO to Overengineering**
- Rejected 3 proposed Skills (YAGNI)
- Only added 2 more when actually needed

**4. Clear Trigger Keywords**
- "generate tests" → pytest-test-generator
- "create PR" → github-workflow
- "pydantic model" → pydantic-model-generator
- "bitcoin rpc" → bitcoin-rpc-connector

**5. Template Variants**
- Each Skill has 3-5 templates
- Covers 80% of use cases
- Remaining 20% → use Subagent

### What to Avoid ❌

**1. Creating Skills for One-Off Tasks**
- ❌ zmq-subscriber-template (used 1 time)
- ❌ fastapi-websocket-endpoint (used 1 time)

**2. Over-Generic Templates**
- ❌ "module-boilerplate" (too vague)
- ✅ "pydantic-model-generator" (specific)

**3. Premature Optimization**
- ❌ Creating 7 Skills upfront (YAGNI violation)
- ✅ Creating 2, then adding 2 more when needed

**4. Ignoring Token Economics**
- ❌ Creating Skill without measuring savings
- ✅ Validated 60%+ savings before implementing

---

## 🚀 Implementation Roadmap (Recommended)

### Week 1: Analysis & Planning
- [ ] Read Anthropic Skills documentation
- [ ] Analyze your codebase for patterns
- [ ] Calculate token ROI for top 5 patterns
- [ ] Prioritize 2 high-value Skills (YAGNI)

### Week 2: First Skill
- [ ] Create directory structure
- [ ] Write SKILL.md for Skill #1
- [ ] Test with 3-5 real examples
- [ ] Measure token savings
- [ ] Update CLAUDE.md

### Week 3: Second Skill
- [ ] Repeat for Skill #2
- [ ] Refine Skill #1 based on usage
- [ ] Document token economics

### Week 4: Validation
- [ ] Run consistency check
- [ ] Measure actual vs expected savings
- [ ] Identify next Skill (only if needed!)

### Week 5+: Iterate
- [ ] Add Skills ONLY when pattern appears 3+ times
- [ ] Say NO to hypothetical Skills
- [ ] Focus on using existing Skills effectively

**Do NOT**:
- Create all Skills upfront
- Over-engineer generic solutions
- Add Skills before validating need

---

## 📚 Resources & References

### Official Documentation
- **Claude Skills Overview**: https://docs.claude.com/en/docs/claude-code/skills
- **Skills Best Practices**: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices
- **Skills API Guide**: https://docs.claude.com/en/api/skills-guide
- **Subagents vs Skills**: https://docs.claude.com/en/docs/claude-code/sub-agents

### UTXOracle Reference Files
- **CLAUDE.md**: Project instructions template
- **SKILL_SUMMARY.md**: Token economics analysis
- **CONSISTENCY_CHECK.md**: Validation checklist
- **MCP_OPTIMIZATION.md**: MCP tools configuration
- **.claude/skills/**: 4 production Skills as examples
  - `pytest-test-generator/SKILL.md`
  - `pydantic-model-generator/SKILL.md`
  - `bitcoin-rpc-connector/SKILL.md`
  - `github-workflow/SKILL.md`

### Community
- Claude Code Docs: https://docs.claude.com/en/docs/claude-code
- Anthropic Discord: https://discord.gg/anthropic
- GitHub Issues: https://github.com/anthropics/claude-code/issues

---

## 🎯 Quick Reference Card

### When to Create a Skill?

```
✅ CREATE if:
   - Repeats 3+ times
   - Template-driven
   - >60% token savings
   - Will use in next 2 weeks

❌ DON'T CREATE if:
   - Used once
   - Complex reasoning needed
   - Hypothetical future use
   - <60% savings
```

### Skill File Checklist

```
Required:
  ✅ .claude/skills/{name}/SKILL.md
  ✅ Frontmatter: name, description
  ✅ Quick Start example
  ✅ 3+ templates
  ✅ Trigger keywords

Optional:
  ⭕ templates/ directory
  ⭕ scripts/ directory
  ⭕ REFERENCE.md
```

### Token Savings Formula

```
Savings = (Manual - Skill) × Frequency

Example:
  Manual: 3,000 tokens
  Skill: 500 tokens
  Frequency: 10 uses

  Savings = (3,000 - 500) × 10 = 25,000 tokens ✅
```

---

## 📝 Change Log

**2025-10-18**: Initial version based on UTXOracle production implementation
- 4 Skills created (pytest, pydantic, rpc, github)
- 87,600 tokens saved total
- YAGNI applied: Rejected 3 proposed Skills

---

*This blueprint is maintained as living documentation. Update when you discover new patterns or anti-patterns.*

**Next Steps**: Analyze YOUR repository using Step 1-3, then create your first Skill using Phase 1-4. Start with 1-2 Skills, NOT 5-7.
