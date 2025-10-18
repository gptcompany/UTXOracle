# Agent Skills vs Subagents - UTXOracle Strategy

## 📊 Comparison Matrix (from Claude Docs)

| Feature | **Skills** | **Subagents** | **UTXOracle Current** |
|---------|-----------|--------------|----------------------|
| **Model** | Parent model | Custom or parent | Subagents (6 agents) |
| **Context** | Stays in window, progressive disclosure | Disposable, all-in-one | Disposable (task files) |
| **Activation** | Model-invoked | Model or user activated | Model-invoked |
| **Parallelism** | None | Chain or parallel | Designed for sequential |
| **Use Case** | Simple, template-driven | Complex, multi-step, deep context | Complex (Tasks 01-05) |
| **Token Cost** | Low (~100 metadata, <5k instructions) | High (full context) | High (full agent def) |

## 🎯 Skills vs Subagents Decision Tree

```
┌─────────────────────────────────────┐
│ Is task complex, multi-step,       │
│ requiring deep context?             │
└────────┬─────────────────┬──────────┘
         │ YES             │ NO
         ▼                 ▼
   ┌──────────┐      ┌──────────┐
   │ SUBAGENT │      │  SKILL   │
   └──────────┘      └──────────┘
   Examples:          Examples:
   - Task 01-05       - Test templates
   - Full modules     - Boilerplate gen
   - Algorithm port   - Validation
   - Integration      - Formatting
```

## 🛠️ Proposed Hybrid Architecture for UTXOracle

### **Keep as Subagents** (Complex, Deep Context)

| Agent | Reason | Token Cost | Justification |
|-------|--------|-----------|---------------|
| bitcoin-onchain-expert | ZMQ integration complexity | High | Requires Bitcoin Core protocol knowledge |
| transaction-processor | Binary parsing logic | High | Complex deserialization + UTXOracle filtering |
| mempool-analyzer | Statistical algorithm | High | Steps 5-11 porting from UTXOracle.py |
| data-streamer | WebSocket architecture | Medium | FastAPI + async patterns |
| visualization-renderer | Browser graphics | Medium | Canvas/WebGL implementation |
| tdd-guard | TDD enforcement | Low | Could be Skill, but needs reasoning |

**Total Subagents**: 5-6 (keep current)

---

### **Create as Skills** (Template-Driven, Lightweight)

#### **Skill 1: Test Generator** 🧪
```yaml
---
name: pytest-test-generator
description: Generate pytest test templates for UTXOracle modules following TDD patterns. Auto-creates RED phase tests with fixtures.
---

# Pytest Test Generator

## Usage
When user says "generate tests for [module]", create:
- test_[module].py with fixtures
- Async test patterns for ZMQ/WebSocket
- Coverage markers for pytest-cov

## Templates
- test_zmq_connection()
- test_transaction_parsing()
- test_price_estimation()
```

**Token Savings**: ~4,800 tokens vs full tdd-guard subagent

#### **Skill 2: Boilerplate Code Generator** 📦
```yaml
---
name: utxoracle-boilerplate
description: Generate standard UTXOracle module structure with black box interfaces, type hints, and docstrings.
---

# UTXOracle Boilerplate Generator

## Module Template
```python
"""
Module: {module_name}
Task: {task_number}
Interface: Input -> Process -> Output
"""
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class {ModuleName}Config:
    """Configuration for {module_name}"""
    pass

class {ModuleName}:
    def __init__(self, config: {ModuleName}Config):
        self.config = config

    def process(self, input_data) -> Optional[Output]:
        """
        Black box interface

        Args:
            input_data: {description}

        Returns:
            {output_description} or None if filtered
        """
        pass
```

**Token Savings**: ~3,200 tokens vs repeating patterns in each subagent

#### **Skill 3: Git Commit Message Template** 📝
```yaml
---
name: utxoracle-commit-template
description: Generate standardized commit messages following UTXOracle conventions with task tracking and Claude attribution.
---

# UTXOracle Commit Template

## Format
```
[Task XX] Module Name: Brief description

Changes:
- Deliverable: file.py
- Tests: test_file.py
- Coverage: XX%
- Integration: Task XX → Task YY

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Token Savings**: ~1,500 tokens per commit message generation

#### **Skill 4: TDD Cycle Validator** ✅
```yaml
---
name: tdd-cycle-validator
description: Quick validation of RED-GREEN-REFACTOR cycle. Checks if tests exist, run, and coverage meets threshold before allowing code commits.
---

# TDD Cycle Validator

## Checks
1. RED: Tests exist and fail
   ```bash
   uv run pytest tests/test_*.py -v
   ```

2. GREEN: Tests pass after implementation
   ```bash
   uv run pytest tests/test_*.py -v
   ```

3. REFACTOR: Coverage >80%
   ```bash
   uv run pytest --cov=live/backend --cov-report=term-missing
   ```

## Output
✅ TDD Cycle Valid
❌ TDD Violation: [reason]
```

**Token Savings**: ~2,400 tokens vs full tdd-guard reasoning

#### **Skill 5: API Contract Validator** 🔌
```yaml
---
name: black-box-interface-validator
description: Validate black box interfaces between Tasks 01-05. Ensures type signatures match across module boundaries.
---

# Black Box Interface Validator

## Validation Rules
Task 01 Output → Task 02 Input:
- Type: bytes (raw Bitcoin transaction)

Task 02 Output → Task 03 Input:
- Type: ProcessedTx
- Fields: txid (str), outputs (List[Output]), timestamp (float)

Task 03 Output → Task 04 Input:
- Type: PriceEstimate
- Fields: price (float), confidence (float), sample_size (int)

## Usage
Run after implementing module:
```python
validator.check_interface("task_01", "task_02")
```
```

**Token Savings**: ~2,100 tokens vs embedding in each subagent

---

## 💡 Recommended Hybrid Strategy

### **Phase 1: MVP (Week 1-4)** - Subagents Only
- Use current 6 subagents
- Build foundation without optimization
- Focus on functionality first

### **Phase 2: Optimization (Week 5-6)** - Add Skills
Create 5 Skills:
1. `pytest-test-generator` - Auto-generate test boilerplate
2. `utxoracle-boilerplate` - Module structure templates
3. `utxoracle-commit-template` - Standardized commits
4. `tdd-cycle-validator` - Quick TDD checks
5. `black-box-interface-validator` - Type checking

### **Phase 3: Refactor (Week 7+)** - Hybrid Workflow
```
User: "Implement Task 02 transaction processor"

Main Claude:
├─ Skill: utxoracle-boilerplate (generate module structure)
├─ Skill: pytest-test-generator (create test template)
├─ Subagent: transaction-processor (implement complex parsing logic)
├─ Skill: tdd-cycle-validator (check RED-GREEN-REFACTOR)
└─ Skill: utxoracle-commit-template (create commit message)
```

**Estimated Token Savings**: ~14,000 tokens per task (40% reduction)

---

## 📁 Proposed Skill File Structure

```
.claude/
├── agents/                    # Subagents (complex tasks)
│   ├── bitcoin-onchain-expert.md
│   ├── transaction-processor.md
│   ├── mempool-analyzer.md
│   ├── data-streamer.md
│   └── visualization-renderer.md
│
├── skills/                    # NEW: Skills (template-driven)
│   ├── pytest-test-generator/
│   │   ├── SKILL.md
│   │   ├── templates/
│   │   │   ├── test_zmq.py.template
│   │   │   ├── test_async.py.template
│   │   │   └── pytest.ini
│   │   └── generate_test.py
│   │
│   ├── utxoracle-boilerplate/
│   │   ├── SKILL.md
│   │   ├── templates/
│   │   │   ├── module_template.py
│   │   │   ├── __init__.py.template
│   │   │   └── config_template.py
│   │   └── generate_module.py
│   │
│   ├── utxoracle-commit-template/
│   │   ├── SKILL.md
│   │   └── commit_msg_generator.py
│   │
│   ├── tdd-cycle-validator/
│   │   ├── SKILL.md
│   │   └── validate_tdd.sh
│   │
│   └── black-box-interface-validator/
│       ├── SKILL.md
│       ├── interface_schemas.json
│       └── validate_interface.py
│
└── prompts/
    └── utxoracle-system.md
```

---

## 🎯 Implementation Roadmap

### **Week 1-2: Skill Development**
- [ ] Create `pytest-test-generator` Skill
- [ ] Create `utxoracle-boilerplate` Skill
- [ ] Create `tdd-cycle-validator` Skill
- [ ] Test Skills in isolation

### **Week 3-4: Integration**
- [ ] Update `utxoracle-system.md` with Skill usage patterns
- [ ] Train team on when to use Skills vs Subagents
- [ ] Benchmark token savings

### **Week 5+: Production**
- [ ] Use hybrid approach for all new Tasks
- [ ] Refactor existing subagents to delegate to Skills
- [ ] Monitor performance and adjust

---

## 📊 Expected Benefits

| Metric | Before (Subagents Only) | After (Hybrid) | Improvement |
|--------|------------------------|----------------|-------------|
| **Avg tokens/task** | ~35,000 | ~21,000 | **40% reduction** |
| **Context pollution** | High (all agent definitions) | Low (progressive disclosure) | **60% cleaner** |
| **Boilerplate time** | 10-15 min/module | 2-3 min/module | **5x faster** |
| **TDD enforcement** | Manual reasoning | Automated checks | **100% consistent** |
| **Reusability** | Low (agent-specific) | High (cross-project) | **Portable** |

---

## ⚠️ Trade-offs & Considerations

### **When Skills are BETTER**:
✅ Repetitive patterns (test generation, boilerplate)
✅ Simple validation (coverage checks, type validation)
✅ Template-driven output (commit messages, docstrings)
✅ Cross-project reusability
✅ Token efficiency critical

### **When Subagents are BETTER**:
✅ Complex reasoning (algorithm porting, architecture design)
✅ Deep domain expertise (Bitcoin protocol, statistical methods)
✅ Multi-step workflows (full module implementation)
✅ Context-dependent decisions (error handling strategies)
✅ Custom model needs (e.g., Opus for complex tasks)

### **Current UTXOracle Assessment**:
- **Tasks 01-05**: Keep as Subagents (too complex for Skills)
- **Boilerplate generation**: Convert to Skills (high repetition)
- **TDD validation**: Hybrid (Skill for checks, Subagent for enforcement reasoning)
- **Git operations**: Convert to Skills (template-driven)

---

## 🚀 Recommendation

**Adopt Incremental Hybrid Approach**:
1. **Now**: Continue with current 6 subagents for MVP
2. **Week 5**: Add 2-3 high-value Skills (test-generator, boilerplate)
3. **Week 8**: Measure token savings and developer experience
4. **Week 10**: Expand Skills library based on patterns observed

**Expected Outcome**:
- 40% token reduction
- 5x faster boilerplate generation
- 100% consistent TDD enforcement
- Portable Skills for future Bitcoin projects

---

## 📚 Resources

- [Agent Skills Docs](https://docs.claude.com/en/docs/agents-and-tools/agent-skills)
- [Skills vs Subagents Table](attachment://screenshot.png)
- [UTXOracle Subagents](/.claude/agents/)
- [Modus Operandi](/.claude/prompts/utxoracle-system.md)
