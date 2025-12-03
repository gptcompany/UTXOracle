# .claude Directory - Documentation Index

**Configuration and meta-documentation for Claude Code in this repository**

---

## 📖 Documentation Hierarchy

### 1️⃣ **For Working on UTXOracle** (Start Here)
```
../CLAUDE.md
  ↓
  Main project instructions
  - What this project is
  - How to run it
  - Development principles (KISS/YAGNI)
  - Skills available (4)
  - Agent architecture (6 subagents)
```

### 2️⃣ **For Understanding Skills** (UTXOracle-Specific)
```
skills/
  ├── SKILLS_QUICK_REFERENCE.md    ⭐ START HERE - One-page cheat sheet
  ├── pytest-test-generator/       - Test template generation
  ├── github-workflow/              - PR/Issue/Commit automation
  ├── pydantic-model-generator/    - Data model generation
  ├── bitcoin-rpc-connector/       - RPC client setup
  └── SKILLS_ANALYSIS.md           - Token economics deep dive
```

### 3️⃣ **For Implementing Skills in OTHER Projects** (META)
```
SKILLS_FRAMEWORK_BLUEPRINT.md  📘 PORTABLE META-FRAMEWORK
  ↓
  Complete guide for implementing Skills in ANY repository
  - Anthropic docs references
  - Repository analysis workflow
  - Skill creation step-by-step
  - Token savings formula
  - Real-world examples from UTXOracle
  - YAGNI/KISS application
  - Validation checklist
```

**Use this to**:
- Set up Skills in your other Claude Code projects
- Train other developers on Skills
- Understand the meta-patterns behind UTXOracle's Skills

---

## 🎯 Quick Navigation

| I Want To... | Go To... |
|--------------|----------|
| Work on UTXOracle Tasks 01-05 | `../CLAUDE.md` |
| Use existing Skills | `skills/SKILLS_QUICK_REFERENCE.md` |
| Create a new Skill for UTXOracle | `SKILLS_FRAMEWORK_BLUEPRINT.md` → Step 1-4 |
| Set up Skills in ANOTHER project | `SKILLS_FRAMEWORK_BLUEPRINT.md` |
| Check Skills are configured correctly | `CONSISTENCY_CHECK.md` |
| Understand token economics | `SKILL_SUMMARY.md` or `skills/SKILLS_ANALYSIS.md` |
| Optimize MCP tools | `MCP_OPTIMIZATION.md` |
| See agent definitions | `agents/{agent-name}.md` |

---

## 📂 Directory Structure

```
.claude/
├── README.md                          # THIS FILE - Documentation index
│
├── SKILLS_FRAMEWORK_BLUEPRINT.md     # 📘 META: Portable Skills framework for ANY project
├── SKILLS_QUICK_REFERENCE.md         # One-page Skills cheat sheet (UTXOracle)
├── CONSISTENCY_CHECK.md               # Validation report (structure compliance)
├── MCP_OPTIMIZATION.md                # MCP tools configuration guide
├── SKILLS_ANALYSIS.md                 # Extended Skills token analysis
│
├── agents/                            # Subagents (6) - Complex reasoning
│   ├── bitcoin-onchain-expert.md      # Task 01 - ZMQ listener
│   ├── transaction-processor.md       # Task 02 - Binary parsing
│   ├── mempool-analyzer.md            # Task 03 - Price estimation
│   ├── data-streamer.md               # Task 04 - WebSocket API
│   ├── visualization-renderer.md      # Task 05 - Canvas/WebGL
│   └── tdd-guard.md                   # TDD enforcement
│
├── skills/                            # Skills (4) - Template automation
│   ├── pytest-test-generator/
│   │   ├── SKILL.md                   # Main skill file
│   │   └── TDD_INTEGRATION.md
│   ├── github-workflow/
│   │   ├── SKILL.md
│   │   ├── templates/
│   │   └── TOKEN_ANALYSIS.md
│   ├── pydantic-model-generator/
│   │   └── SKILL.md
│   └── bitcoin-rpc-connector/
│       └── SKILL.md
│
├── prompts/
│   └── utxoracle-system.md            # Orchestration rules
│
├── tdd-guard/                         # TDD enforcement data
│   └── data/
│
├── logs/                              # Session logs (auto-generated)
├── commands/                          # Custom slash commands
├── settings.local.json                # Permissions & hooks
└── config.json                        # Project configuration
```

---

## 🚀 Getting Started

### For UTXOracle Development
1. Read `../CLAUDE.md` (main instructions)
2. Check `skills/SKILLS_QUICK_REFERENCE.md` (available Skills)
3. Use Skills via trigger keywords (e.g., "generate tests")

### For Skills in Other Projects
1. Read `SKILLS_FRAMEWORK_BLUEPRINT.md`
2. Follow "Repository Analysis Workflow" (Step 1-3)
3. Create your first Skill (Phase 1-4)
4. Measure and validate token savings

---

## 📊 Token Economics Summary

### Current UTXOracle Skills (4)
| Skill | Saves | Used |
|-------|-------|------|
| pytest-test-generator | 83% (3,000→500) | 10+ times |
| github-workflow | 79% (18,900→4,000) | 10+ times |
| pydantic-model-generator | 75% (2,000→500) | 15+ times |
| bitcoin-rpc-connector | 60% (2,500→1,000) | 3+ times |

**Total Saved**: ~20,400 tokens/task (77% on template operations)

**Combined with MCP Optimization**: 87,600 tokens total

---

## 🔗 External Resources

### Anthropic Official Docs
- **Skills Overview**: https://docs.claude.com/en/docs/claude-code/skills
- **Best Practices**: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices
- **API Guide**: https://docs.claude.com/en/api/skills-guide
- **Subagents vs Skills**: https://docs.claude.com/en/docs/claude-code/sub-agents

### Community
- Claude Code Docs: https://docs.claude.com/en/docs/claude-code
- Anthropic Discord: https://discord.gg/anthropic
- GitHub Issues: https://github.com/anthropics/claude-code/issues

---

## ⚠️ Important Notes

### KISS & YAGNI Principles
- **Don't over-engineer**: Start with 1-2 Skills, not 5-7
- **Only create when needed**: Pattern must repeat 3+ times (real, not hypothetical)
- **Measure first**: Validate >60% token savings before implementing
- **Delete if unused**: Remove Skills not used in 2 weeks

### File Naming Conventions
- **Skills**: Must be named `SKILL.md` (Anthropic requirement)
- **Agents**: Can be any `.md` name
- **Templates**: Any name in `skills/{name}/templates/`

### Maintenance
- Update `../CLAUDE.md` when adding/removing Skills
- Run consistency check after structural changes
- Document token savings in `SKILL_SUMMARY.md`

---

## 🎓 Learning Path

**Beginner** (First time using Skills):
1. Read `../CLAUDE.md` → Understand project
2. Use existing Skills → Learn by using
3. Read `SKILLS_QUICK_REFERENCE.md` → Quick patterns

**Intermediate** (Want to create Skills for UTXOracle):
1. Read `SKILLS_FRAMEWORK_BLUEPRINT.md` → Sections 1-3
2. Follow "Skill Creation Workflow" → Phase 1-4
3. Check `CONSISTENCY_CHECK.md` → Validate

**Advanced** (Want to implement Skills in other projects):
1. Study `SKILLS_FRAMEWORK_BLUEPRINT.md` → Complete framework
2. Analyze UTXOracle Skills → Extract patterns
3. Apply "Repository Analysis Workflow" → Your project
4. Create portable Skills → Share across projects

---

## 📝 Change Log

**2025-10-18**: Initial comprehensive documentation
- Created SKILLS_FRAMEWORK_BLUEPRINT.md (meta-framework)
- Created SKILLS_QUICK_REFERENCE.md (cheat sheet)
- Updated CLAUDE.md with blueprint references
- Organized 4 production Skills
- Documented token savings (87,600 total)
- Applied YAGNI (rejected 3 Skills as unnecessary)

---

## 🤝 Contributing

When modifying this structure:
1. Update `../CLAUDE.md` file structure section
2. Run consistency check (verify against Anthropic docs)
3. Update this README.md if navigation changes
4. Document token savings if adding Skills
5. Follow KISS/YAGNI principles

---

**Next Steps**:
- **Using UTXOracle**: Read `../CLAUDE.md`
- **Creating Skills for UTXOracle**: Read `SKILLS_FRAMEWORK_BLUEPRINT.md`
- **Applying to other projects**: Copy `SKILLS_FRAMEWORK_BLUEPRINT.md` and adapt

*Last updated: 2025-10-18*
