# 48 Laws of Power for Meta-Learning & Teaching Teams

**Adapted from**: Robert Greene's 48 Laws of Power, Sun Tzu's Art of War, Machiavelli's The Prince

**Context**: A meta-level teaching & verification team that supervises coding agents, teaches best practices (TDD, KISS, YAGNI), verifies compliance, learns from session statistics, and prevents recurring issues.

**Date**: 2025-10-19
**Version**: 1.0

---

## Law 1: Never Outshine the Agents

**Original**: Never Outshine the Master - Make your superiors feel superior.

**Adapted for Meta-Team**: The meta-team guides but never implements. Let agents take credit for their work.

**Application**:
- Meta-team writes teaching plans, agents execute and receive credit
- When mempool-analyzer succeeds 8/8 tests → celebrate the agent, not the teacher
- Teaching team provides framework (TDD guard, Skills), agents build features
- Never say "I implemented this" → Say "Agent X implemented this following our guidance"

**Anti-Law** (What NOT to do):
- ❌ Meta-team writes production code (undermines agent autonomy)
- ❌ Takes credit for agent successes ("I made them do it")
- ❌ Shows off superior knowledge without empowering agents

---

## Law 2: Never Put Too Much Trust in Agents, Learn to Monitor Performance

**Original**: Never Put Too Much Trust in Friends, Learn How to Use Enemies

**Adapted for Meta-Team**: Trust agents with implementation, but verify through statistics and compliance checks.

**Application**:
- Track agent success rates (mempool-analyzer: 100%, tx-processor: 0% due to TDD blocker)
- Monitor tool usage patterns (Serena: 23%, GitHub: 0% in Session fdd4c6d3)
- Auto-checkpoint after agent completion (prevent context loss)
- Statistical validation: tests passing, coverage ≥80%, no blockers

**Anti-Law**:
- ❌ Assume agents follow TDD without verification
- ❌ Delegate without monitoring (leads to blockers)
- ❌ Trust agent reports without running tests

---

## Law 3: Conceal Your Teaching Intentions Until Agents Internalize Them

**Original**: Conceal Your Intentions

**Adapted for Meta-Team**: Embed best practices into workflows so agents learn through doing, not lecturing.

**Application**:
- TDD guard hook enforces RED-GREEN-REFACTOR automatically (no lecture needed)
- Skill templates guide agents toward good patterns (pytest-test-generator saves 83% tokens)
- MCP profiles optimize token usage invisibly (agents don't think about it)
- CLAUDE.md embeds KISS/YAGNI principles in project structure

**Anti-Law**:
- ❌ Lecture agents on TDD theory without automated enforcement
- ❌ Explain principles without embedding them in tools
- ❌ Visible micromanagement (agents should feel autonomous)

---

## Law 4: Always Say Less Than Necessary (But Log Everything)

**Original**: Always Say Less Than Necessary

**Adapted for Meta-Team**: Minimize agent instruction overhead, but maximize statistical data collection.

**Application**:
- Agent prompts: concise instructions (tdd-guard.md: 256 lines, not 2,000)
- Skills use templates → 60-83% token reduction vs verbose instructions
- PostToolUse hook logs silently without interrupting workflow
- Monthly reports synthesize patterns → no need for daily reminders

**Anti-Law**:
- ❌ Verbose agent prompts (wastes tokens, context window)
- ❌ Redundant instructions in every session
- ❌ Over-explanation when a template/hook would suffice

---

## Law 5: So Much Depends on Agent Reputation – Guard It With Statistics

**Original**: So Much Depends on Reputation – Guard It With Your Life

**Adapted for Meta-Team**: Track and publish agent success rates to identify stars and strugglers.

**Application**:
- Monthly reports: "mempool-analyzer: 100% success, tx-processor: blocked by TDD"
- Public dashboard: agent performance over time
- Celebrate high performers (reinforces good patterns)
- Remediate low performers (fix blockers, not blame agents)

**Anti-Law**:
- ❌ Hide agent failures (prevents learning)
- ❌ Blame agents for systemic issues (TDD hook was the problem, not tx-processor)
- ❌ No transparency → agents don't know what "good" looks like

---

## Law 6: Court Attention to Critical Metrics, Ignore Vanity Metrics

**Original**: Court Attention at All Costs

**Adapted for Meta-Team**: Focus on metrics that matter: test coverage, blocker frequency, token efficiency.

**Application**:
- **Critical**: Coverage ≥80%, TDD compliance, agent success rate
- **Critical**: Token waste (Session fdd4c6d3: 4,000 tokens on unused MCPs)
- **Critical**: Blocker recurrence (TDD hook blocked 2/4 agents)
- **Vanity**: Total tool calls, lines of code, session duration

**Anti-Law**:
- ❌ Track everything (noise drowns signal)
- ❌ Celebrate "100 tool calls!" (irrelevant if half were wasted)
- ❌ Focus on quantity over quality (more code ≠ better)

---

## Law 7: Get Agents to Do the Work, But Always Provide Clear Framework

**Original**: Get Others to Do the Work for You, but Always Take the Credit

**Adapted for Meta-Team**: Agents implement, meta-team provides architecture/tools. Share credit.

**Application**:
- Meta-team: Creates TDD guard, MCP profiles, Skills framework
- Agents: Implement features using provided tools
- Credit split: "Agent X implemented feature Y using Skill Z"
- Framework quality determines agent productivity

**Anti-Law**:
- ❌ Take all credit (demoralizes agents)
- ❌ Provide poor framework then blame agents for failure
- ❌ No framework → agents waste time reinventing wheels

---

## Law 8: Make Agents Come to You – Use Hooks as Bait

**Original**: Make Other People Come to You – Use Bait If Necessary

**Adapted for Meta-Team**: Hooks trigger when agents need guidance, not proactive nagging.

**Application**:
- PreToolUse TDD guard: Triggers when agent writes code without tests
- PostTask checkpoint: Triggers when agent completes work
- PreCompact validator: Triggers before context loss risk
- Agents learn rules by hitting guard rails, not by reading manuals

**Anti-Law**:
- ❌ Proactive nagging ("Did you write tests?")
- ❌ Hooks that trigger too often (alert fatigue)
- ❌ No hooks → agents drift off-process

---

## Law 9: Win Through Statistical Evidence, Never Through Argument

**Original**: Win Through Your Actions, Never Through Argument

**Adapted for Meta-Team**: Show agent performance data, don't debate methodology.

**Application**:
- "Mempool-analyzer 100% success with TDD, tx-processor 0% without" → TDD wins
- "GitHub MCP unused in 75% of sessions" → disable by default
- "Batch TDD blocked 2/4 agents" → fix hook logic
- Numbers end debates (no need for philosophical arguments)

**Anti-Law**:
- ❌ Argue TDD benefits without data
- ❌ Enforce rules "because I said so"
- ❌ Ignore statistical evidence that contradicts theory

---

## Law 10: Avoid the Unhappy and Blocked Agents – Fix Systemic Issues

**Original**: Infection: Avoid the Unhappy and Unlucky

**Adapted for Meta-Team**: When agents fail, diagnose systemic blockers, don't quarantine agents.

**Application**:
- tx-processor blocked → Root cause: TDD hook design flaw
- Don't label agent as "bad" → Fix batch TDD validation
- Track blocker recurrence: Same issue 3+ times → systemic problem
- Isolate blockers, not agents

**Anti-Law**:
- ❌ "This agent always fails" (blame-focused)
- ❌ Move on without fixing blocker (recurs in next session)
- ❌ Treat symptoms (manual workarounds) instead of curing disease (fix hook)

---

## Law 11: Learn to Keep Agents Dependent on Quality Tools

**Original**: Learn to Keep People Dependent on You

**Adapted for Meta-Team**: Provide tools so valuable that agents rely on them (but could fork if needed).

**Application**:
- Skills framework: 60-83% token savings → agents won't want to work without it
- TDD guard: Prevents bugs before they ship → agents appreciate guard rails
- MCP profiles: Automatic token optimization → invisible productivity boost
- Tools enhance autonomy (black box architecture) → not lock-in

**Anti-Law**:
- ❌ Create tool lock-in (violates KISS/YAGNI, black box principles)
- ❌ Tools that waste time (agents will bypass)
- ❌ No tools → agents rebuild from scratch (inefficient)

---

## Law 12: Use Selective Transparency to Disarm Skeptical Agents

**Original**: Use Selective Honesty and Generosity to Disarm Your Victim

**Adapted for Meta-Team**: Publish session stats transparently, but analyze patterns privately first.

**Application**:
- Monthly reports: Full transparency on successes/failures
- Private analysis first: Detect patterns → validate → publish recommendations
- Admit meta-team mistakes: "TDD hook blocked 2 agents → we're fixing it"
- Builds trust through vulnerability

**Anti-Law**:
- ❌ Hide meta-team failures (agents lose trust)
- ❌ Publish raw data without insights (overwhelms agents)
- ❌ Cherry-pick successes only (dishonest)

---

## Law 13: When Asking Agents for Feedback, Appeal to Data, Not Sentiment

**Original**: When Asking for Help, Appeal to People's Self-Interest, Never to Their Mercy or Gratitude

**Adapted for Meta-Team**: Frame feedback requests around performance improvement, not feelings.

**Application**:
- "Which tools save you the most tokens?" (self-interest)
- "What blockers slow you down?" (efficiency)
- "Rate Skills by time saved" (quantifiable)
- Avoid: "Do you like TDD?" (opinion, not actionable)

**Anti-Law**:
- ❌ "Please follow TDD for me" (emotional appeal)
- ❌ Ask subjective questions without metrics
- ❌ Ignore agent feedback ("I'm blocked by TDD hook")

---

## Law 14: Pose as a Collaborator, Monitor as a Guardian

**Original**: Pose as a Friend, Work as a Spy

**Adapted for Meta-Team**: Collaborate with agents, but validate through hooks and stats.

**Application**:
- Agent: "I implemented feature X"
- Meta-team: "Great! Let's validate..." (runs TDD guard, coverage check)
- Friendly tone + strict validation = trust + quality
- PostToolUse hook logs silently (monitoring without micromanagement)

**Anti-Law**:
- ❌ Spy-like surveillance ("I'm watching you")
- ❌ Collaborate without verification (quality suffers)
- ❌ Adversarial relationship (agents resent meta-team)

---

## Law 15: Crush Recurring Blockers Totally

**Original**: Crush Your Enemy Totally

**Adapted for Meta-Team**: When a blocker recurs 3+ times, eliminate root cause completely.

**Application**:
- TDD hook blocked 2/4 agents → Don't patch → Redesign with intelligent mode detection
- GitHub MCP unused in 75% of sessions → Don't remind → Disable by default in profile
- Test timeout issue 2x → Don't increase timeout → Fix test bug
- Partial fixes lead to recurrence → Total solutions end problems permanently

**Anti-Law**:
- ❌ Workarounds ("Just use --no-verify this time")
- ❌ Incremental patches on systemic issues
- ❌ Leave blocker partially alive (recurs in 2 weeks)

---

## Law 16: Use Strategic Absence to Increase Agent Autonomy

**Original**: Use Absence to Increase Respect and Honor

**Adapted for Meta-Team**: Don't micromanage. Let agents struggle briefly, then intervene with framework.

**Application**:
- Agent hits TDD blocker → Hook explains issue + solution (not meta-team nagging)
- Agent completes task → PostTask hook auto-checkpoints (no manual reminder)
- Agent explores codebase → Serena MCP available (not pre-loaded docs)
- Automated systems = meta-team absence = agent empowerment

**Anti-Law**:
- ❌ Constant supervision ("Did you run tests?")
- ❌ Immediate intervention before agent tries
- ❌ Over-presence reduces agent learning

---

## Law 17: Keep Agents in Productive Uncertainty – Not Terror

**Original**: Keep Others in Suspended Terror: Cultivate an Air of Unpredictability

**Adapted for Meta-Team**: Hooks should surprise agents occasionally (prevent complacency), not constantly.

**Application**:
- TDD guard triggers unexpectedly if agent skips tests → teachable moment
- PreCompact validator warns if uncommitted work → prevents data loss surprise
- Monthly reports reveal unexpected patterns ("You used GitHub MCP 0 times!")
- Productive uncertainty keeps agents sharp without fear

**Anti-Law**:
- ❌ Terror/fear-based enforcement (TDD guard that blocks arbitrarily)
- ❌ Total predictability → agents game the system
- ❌ Chaos → agents can't learn stable patterns

---

## Law 18: Do Not Isolate Meta-Team – Engage With Agent Feedback

**Original**: Do Not Build Fortresses to Protect Yourself – Isolation Is Dangerous

**Adapted for Meta-Team**: Meta-team learns from agents, not dictates from ivory tower.

**Application**:
- Agent: "TDD hook blocks batch TDD" → Meta-team listens and fixes
- Session stats reveal GitHub MCP unused → Meta-team adapts MCP profiles
- Agent feedback loop: PostTask reports → Pattern detection → Meta-learning updates
- Isolation = blind spots → Engagement = continuous improvement

**Anti-Law**:
- ❌ "We know best, follow rules" (ignores reality)
- ❌ No feedback mechanisms
- ❌ Meta-team doesn't read agent reports

---

## Law 19: Know Which Agents You're Dealing With – Adapt Teaching Style

**Original**: Know Who You're Dealing With – Do Not Offend the Wrong Person

**Adapted for Meta-Team**: Different agents need different guidance (mempool-analyzer ≠ tx-processor).

**Application**:
- mempool-analyzer (100% success) → Minimal supervision, trust autonomy
- tx-processor (blocked) → Active intervention, fix systemic blocker
- Specialized agents (bitcoin-onchain-expert) → Domain-specific MCPs (context7 for PyZMQ)
- General agents → Standard toolkit (Serena, basic Skills)

**Anti-Law**:
- ❌ One-size-fits-all teaching (ignores agent specialization)
- ❌ Over-supervise high performers (wastes time)
- ❌ Under-support struggling agents (blockers persist)

---

## Law 20: Do Not Commit to Rigid Rules – Adapt to Context

**Original**: Do Not Commit to Anyone

**Adapted for Meta-Team**: Principles are firm (TDD, KISS), but implementations adapt (batch vs incremental TDD).

**Application**:
- TDD principle: Non-negotiable
- TDD mode: Flexible (batch, incremental, manual)
- Coverage threshold: 80% minimum, but context-aware (frontend JS may differ from backend Python)
- MCP profiles: Task-specific (code-implementation ≠ github-workflow)

**Anti-Law**:
- ❌ Rigid rules that ignore context (incremental TDD enforcement for batch workflow)
- ❌ No principles (chaos)
- ❌ Principles without adaptation (dogma)

---

## Law 21: Play a Student to Learn Agent Patterns – Seem Curious, Not Omniscient

**Original**: Play a Sucker to Catch a Sucker – Seem Dumber Than Your Mark

**Adapted for Meta-Team**: Ask agents "What worked?" to discover patterns, don't assume you know.

**Application**:
- "Why did mempool-analyzer succeed?" → Agent reveals best practices
- "What blocked tx-processor?" → Uncovers TDD hook flaw
- Statistical analysis reveals patterns meta-team didn't anticipate (Serena 23%, GitHub 0%)
- Humility enables learning

**Anti-Law**:
- ❌ "We already know everything" (miss emergent patterns)
- ❌ Ignore agent insights
- ❌ Assume statistical models are perfect (they evolve)

---

## Law 22: Use the Checkpoint Tactic: Transform Agent Work Into Permanent Memory

**Original**: Use the Surrender Tactic: Transform Weakness Into Power

**Adapted for Meta-Team**: Auto-checkpoint after agent completion transforms ephemeral work into permanent memory.

**Application**:
- PostTask hook commits agent work automatically
- Git history becomes learning database (agent performance over time)
- Session fdd4c6d3 checkpoint preserves context even if session dies
- "Surrender" to automation (don't manually checkpoint) → strength through consistency

**Anti-Law**:
- ❌ No auto-checkpoint → agent work lost if session interrupted
- ❌ Manual checkpoints → inconsistent, error-prone
- ❌ Treat sessions as isolated → lose longitudinal learning

---

## Law 23: Concentrate Your Meta-Team Forces on High-Impact Metrics

**Original**: Concentrate Your Forces

**Adapted for Meta-Team**: Focus on bottlenecks (TDD blocker affects 50% of agents) over minor issues.

**Application**:
- Priority 1: Fix TDD hook (25% session impact)
- Priority 2: MCP profiles (token savings)
- Priority 3: Dashboard (nice-to-have)
- Don't diffuse effort across 100 minor issues

**Anti-Law**:
- ❌ Spread attention equally (miss critical bottlenecks)
- ❌ Fix cosmetic issues before systemic blockers
- ❌ No prioritization → random walk

---

## Law 24: Play the Perfect Meta-Courtier – Serve Agents and Project Goals Equally

**Original**: Play the Perfect Courtier

**Adapted for Meta-Team**: Balance agent autonomy with project quality standards.

**Application**:
- Agent wants speed → Meta-team provides Skills (83% token reduction)
- Project needs quality → Meta-team provides TDD guard (≥80% coverage)
- Agent blocked → Meta-team fixes systemic issue, not blame
- Serve both masters: agent productivity + project integrity

**Anti-Law**:
- ❌ Serve agents only (quality suffers)
- ❌ Serve project only (agents frustrated)
- ❌ Adversarial relationship (agents vs meta-team)

---

## Law 25: Re-Create Yourself – Meta-Team Evolves With Each Session

**Original**: Re-Create Yourself

**Adapted for Meta-Team**: Update CLAUDE.md Meta-Learning section after every major session.

**Application**:
- Session N: TDD hook blocks batch TDD → Log issue
- Session N+1: Fix TDD guard v2 → Update meta-learning
- Session N+10: New pattern emerges → Adapt framework
- Meta-team isn't static → learns and re-invents continuously

**Anti-Law**:
- ❌ Static meta-team (same rules forever)
- ❌ No learning from sessions
- ❌ Ignore new patterns

---

## Law 26: Keep Your Hands Clean – Let Hooks Enforce, Not Manual Intervention

**Original**: Keep Your Hands Clean

**Adapted for Meta-Team**: Automated hooks enforce rules, meta-team doesn't play cop.

**Application**:
- TDD guard hook blocks code without tests → Not meta-team saying "no"
- PostToolUse stats collected automatically → Not manual logging
- PreCompact validator warns → Not meta-team nagging
- Agents respect hooks more than human reminders

**Anti-Law**:
- ❌ Manual enforcement ("You didn't write tests!")
- ❌ Blame agents for violations
- ❌ No automation → meta-team becomes bottleneck

---

## Law 27: Play on Agents' Need for Efficiency to Promote Best Practices

**Original**: Play on People's Need to Believe to Create a Cultlike Following

**Adapted for Meta-Team**: Show agents that TDD/Skills/KISS save time → they adopt willingly.

**Application**:
- pytest-test-generator: 83% token reduction → agents believe in Skills
- TDD prevents bugs → agents believe in testing
- MCP profiles: invisible token savings → agents believe in optimization
- Cult = best practices adopted as "obvious truth"

**Anti-Law**:
- ❌ Force practices without demonstrating value
- ❌ Hide efficiency gains (agents don't see benefits)
- ❌ Dogma without data

---

## Law 28: Enter Agent Guidance With Boldness

**Original**: Enter Action With Boldness

**Adapted for Meta-Team**: When launching new hook/tool, commit fully (don't pilot tentatively).

**Application**:
- TDD guard v2: Full redesign with intelligent mode detection (not incremental patch)
- MCP profiles: Switch default to code-implementation (not "try it optionally")
- PostTask checkpoint: Auto-commit always (not "if you want")
- Tentative rollouts signal lack of confidence → agents ignore

**Anti-Law**:
- ❌ "Try TDD if you want" (optional = ignored)
- ❌ Half-measures on systemic issues
- ❌ Apologetic enforcement ("Sorry, but please write tests...")

---

## Law 29: Plan All the Way to the End – Meta-Learning Roadmap

**Original**: Plan All the Way to the End

**Adapted for Meta-Team**: Every hook/tool has clear success metrics and sunset criteria.

**Application**:
- TDD guard v2: Success = 0 batch TDD blocks in 10 sessions
- MCP profiles: Success = 90% token waste reduction
- Statistical pipeline: Success = monthly reports guide decisions
- If tool fails metrics after 3 months → deprecate or redesign

**Anti-Law**:
- ❌ Launch tools without success criteria
- ❌ No exit strategy (failed tools accumulate)
- ❌ Endless pilots without decision

---

## Law 30: Make Your Meta-Team Accomplishments Seem Effortless

**Original**: Make Your Accomplishments Seem Effortless

**Adapted for Meta-Team**: Agents shouldn't notice meta-team working (hooks run silently, reports auto-generate).

**Application**:
- PostToolUse stats collected silently
- Monthly reports appear automatically
- MCP profile optimization invisible to agents
- Agents just notice: "Huh, things work smoothly now"

**Anti-Law**:
- ❌ Brag about meta-team effort ("Look how hard we worked!")
- ❌ Visible complexity (agents see the sausage-making)
- ❌ Constant announcements ("We updated the TDD guard again!")

---

## Law 31: Control the Options: Provide Agent Templates, Not Blank Canvases

**Original**: Control the Options: Get Others to Play With the Cards You Deal

**Adapted for Meta-Team**: Skills provide templates → agents choose variations, not reinvent.

**Application**:
- pytest-test-generator: Agents choose test names/params, not write boilerplate from scratch
- github-workflow: Agents choose PR title, not format from blank slate
- MCP profiles: Agents choose code-implementation or github-workflow, not configure 80 tools
- Constrained creativity → faster + consistent

**Anti-Law**:
- ❌ Total freedom → agents waste time on decisions
- ❌ Total rigidity → agents can't adapt to edge cases
- ❌ No templates → reinvent wheel every time

---

## Law 32: Play to Agents' Fantasies of Efficiency

**Original**: Play to People's Fantasies

**Adapted for Meta-Team**: Show agents "You can implement features 3x faster with TDD + Skills."

**Application**:
- "mempool-analyzer finished 8/8 tasks in 30 minutes with Skills"
- "tx-processor blocked for 2 hours due to missing TDD"
- Fantasy: "I want to be like mempool-analyzer (fast + successful)"
- Reality: Follow framework → achieve fantasy

**Anti-Law**:
- ❌ Promise unrealistic efficiency ("10x faster!")
- ❌ Hide tradeoffs (TDD takes time upfront)
- ❌ No success stories to inspire

---

## Law 33: Discover Each Agent's Bottleneck (Thumbscrew)

**Original**: Discover Each Man's Thumbscrew

**Adapted for Meta-Team**: Identify each agent's recurring blocker and fix systemically.

**Application**:
- tx-processor: TDD hook (thumbscrew) → Fix batch mode validation
- mempool-analyzer: No blocker (thumbscrew = none)
- visualization-renderer: JavaScript TDD (thumbscrew) → Adapt hook for JS
- Generic guidance doesn't work → targeted unblocking does

**Anti-Law**:
- ❌ Ignore agent-specific blockers
- ❌ One-size-fits-all solutions
- ❌ Don't track individual agent patterns

---

## Law 34: Be Royal in Principle Enforcement: Act With Confidence, Be Treated With Respect

**Original**: Be Royal in Your Own Fashion: Act Like a King to Be Treated Like One

**Adapted for Meta-Team**: Enforce TDD/KISS/YAGNI with confidence → agents respect principles.

**Application**:
- TDD guard blocks confidently: "Tests required. No exceptions."
- KISS principle stated clearly in CLAUDE.md: "Boring technology wins."
- No apologies for quality standards
- Confidence → agents internalize principles as "truth"

**Anti-Law**:
- ❌ Apologetic enforcement ("Sorry, but TDD is kinda important...")
- ❌ Inconsistent application (TDD required sometimes)
- ❌ Weak enforcement → agents ignore

---

## Law 35: Master the Art of Timing – Know When to Launch New Tools

**Original**: Master the Art of Timing

**Adapted for Meta-Team**: Launch TDD guard v2 after Session N blocker, not randomly.

**Application**:
- Wait for blocker recurrence (3+ times) before redesigning
- Don't launch MCP profiles until token waste measured (4,000 tokens/session)
- Monthly reports timed after 10+ sessions (statistical significance)
- Right timing → high adoption. Wrong timing → ignored.

**Anti-Law**:
- ❌ Premature optimization (fix non-problems)
- ❌ React to single incident (not pattern)
- ❌ Launch during crisis (agents overwhelmed)

---

## Law 36: Disdain Vanity Metrics You Cannot Control: Focus on Coverage, Not LOC

**Original**: Disdain Things You Cannot Have: Ignoring Them Is the Best Revenge

**Adapted for Meta-Team**: Ignore metrics outside meta-team control (agent talent). Focus on controllable (framework quality).

**Application**:
- Controllable: TDD guard quality, Skill templates, MCP profiles
- Uncontrollable: Agent inherent skill, session context window limits
- Measure framework impact: "Did agents succeed MORE with new TDD guard?"
- Don't obsess over: "Why is tx-processor less talented?"

**Anti-Law**:
- ❌ Blame agents for factors outside their control
- ❌ Measure irrelevant metrics (lines of code)
- ❌ Envy other projects' agents

---

## Law 37: Create Compelling Statistical Dashboards

**Original**: Create Compelling Spectacles

**Adapted for Meta-Team**: Monthly reports with charts/graphs compel action more than raw data.

**Application**:
- Dashboard: Agent success rates over time (visual trend)
- MCP utilization heatmap (shows waste clearly)
- TDD blocker timeline (dramatic before/after fix)
- Spectacle → memorable → action

**Anti-Law**:
- ❌ Raw JSONL data dumps (no one reads)
- ❌ Text-only reports (boring)
- ❌ No visualization → patterns missed

---

## Law 38: Think Innovatively but Behave Conservatively (KISS/YAGNI)

**Original**: Think as You Like but Behave Like Others

**Adapted for Meta-Team**: Experiment privately (TDD guard v2 design), deploy conservatively (test thoroughly first).

**Application**:
- Internal: Explore AI-based pattern detection
- Public: Deploy proven hooks (TDD, PostTask checkpoint)
- Think: "Could we predict blockers with ML?"
- Behave: "Let's start with rule-based detection"

**Anti-Law**:
- ❌ Deploy experimental tools to agents without testing
- ❌ Conservative thinking (no innovation)
- ❌ Radical changes without validation

---

## Law 39: Stir Up Statistical Waters to Catch Hidden Patterns

**Original**: Stir Up Waters to Catch Fish

**Adapted for Meta-Team**: Run A/B tests (MCP profiles vs no profiles) to reveal true efficiency gains.

**Application**:
- Test hypothesis: "GitHub MCP unused in code tasks"
- Experiment: Disable GitHub for 5 sessions → measure impact
- Compare: Sessions with vs without GitHub MCP
- Hidden pattern emerges: "No difference → permanent disable"

**Anti-Law**:
- ❌ Assume patterns without testing
- ❌ Static analysis only (miss dynamic insights)
- ❌ No experimentation → stagnation

---

## Law 40: Despise the Free Lunch – Invest Tokens in Quality Tools

**Original**: Despise the Free Lunch

**Adapted for Meta-Team**: Building Skills/hooks costs tokens upfront, but pays dividends.

**Application**:
- pytest-test-generator: 5,000 token investment → 83% savings per use
- TDD guard v2: 10,000 token redesign → eliminates 25% session failures
- MCP profiles: 2,000 token setup → 24,000 tokens/year saved
- Upfront cost = long-term ROI

**Anti-Law**:
- ❌ Avoid investing in tools (short-term thinking)
- ❌ Expect quality without effort
- ❌ Use quick hacks instead of proper solutions

---

## Law 41: Avoid Stepping Into a Previous Meta-Team's Shoes – Create Your Own Identity

**Original**: Avoid Stepping Into a Great Man's Shoes

**Adapted for Meta-Team**: Learn from past sessions, but don't blindly repeat old solutions.

**Application**:
- Session fdd4c6d3: TDD hook failed
- Don't: Copy old incremental TDD logic
- Do: Redesign with intelligent mode detection (batch + incremental)
- Honor history, innovate solutions

**Anti-Law**:
- ❌ "We've always done TDD this way"
- ❌ Ignore past learnings
- ❌ Blindly copy old systems without questioning

---

## Law 42: Strike the Blocker Root Cause and Secondary Issues Will Scatter

**Original**: Strike the Shepherd and the Sheep Will Scatter

**Adapted for Meta-Team**: Fix TDD hook → tx-processor and viz-renderer unblock automatically.

**Application**:
- Root blocker: TDD hook batch mode conflict
- Secondary issues: tx-processor stuck, viz-renderer stuck, orchestrator delayed
- Fix root → all secondary issues resolve
- Don't fix symptoms individually

**Anti-Law**:
- ❌ Patch each agent individually (treats symptoms)
- ❌ Ignore root cause (blocker recurs)
- ❌ Diffuse effort across secondary issues

---

## Law 43: Work on the Hearts and Minds of Agents Through Efficiency Gains

**Original**: Work on the Hearts and Minds of Others

**Adapted for Meta-Team**: Agents adopt TDD when they see it saves debugging time, not because meta-team lectures.

**Application**:
- Show: mempool-analyzer (TDD) = 0 bugs, tx-processor (no TDD) = blocked
- Show: Skills save 60-83% tokens → agents want more Skills
- Show: MCP profiles invisible but faster → agents trust meta-team
- Hearts/minds won by results, not rhetoric

**Anti-Law**:
- ❌ Lecture on principles without demonstrating value
- ❌ Force compliance without showing benefits
- ❌ Hide efficiency gains

---

## Law 44: Disarm and Infuriate Blockers With the Statistical Mirror Effect

**Original**: Disarm and Infuriate With the Mirror Effect

**Adapted for Meta-Team**: Show agents their own data → self-awareness triggers improvement.

**Application**:
- "You called GitHub MCP 0 times in 10 sessions" → agent realizes waste
- "Your coverage dropped from 85% to 67%" → agent fixes tests
- Mirror = non-judgmental reflection → agent owns solution
- No blame, just data

**Anti-Law**:
- ❌ Accuse agents ("You're wasting tokens!")
- ❌ Hide data → agents unaware of issues
- ❌ Judge instead of reflect

---

## Law 45: Preach the Need for Continuous Improvement, but Don't Overwhelm With Changes

**Original**: Preach the Need for Change, but Never Reform Too Much at Once

**Adapted for Meta-Team**: Fix TDD hook first, then MCP profiles, then dashboard. Not all at once.

**Application**:
- Priority 1 (Week 1): TDD guard v2
- Priority 2 (Week 2-3): MCP profiles + PostTask checkpoint
- Priority 3 (Month 2): Statistical pipeline
- Gradual rollout → agents adapt. Mass change → chaos.

**Anti-Law**:
- ❌ Deploy 5 new hooks in one session (overwhelming)
- ❌ No changes (stagnation)
- ❌ Change for change's sake (no clear benefit)

---

## Law 46: Never Appear Too Perfect – Admit Meta-Team Mistakes

**Original**: Never Appear Too Perfect

**Adapted for Meta-Team**: "TDD hook blocked 2 agents. Our mistake. We're fixing it."

**Application**:
- Transparency: Meta-team isn't omniscient
- Admit: TDD hook design flaw
- Fix: Publicly, with explanation
- Humility → trust → agents feel safe reporting issues

**Anti-Law**:
- ❌ Blame agents for meta-team tool failures
- ❌ Hide mistakes
- ❌ Appear infallible (agents fear reporting issues)

---

## Law 47: Do Not Go Past the Mark – Know When Statistical System is "Good Enough"

**Original**: Do Not Go Past the Mark You Aimed For; In Victory, Learn When to Stop

**Adapted for Meta-Team**: TDD hook fixed, agents unblocked → stop iterating. Don't over-engineer.

**Application**:
- Goal: Unblock batch TDD → TDD guard v2 achieves this → STOP
- Don't: Add 10 more TDD modes "just in case"
- YAGNI: You ain't gonna need it
- Victory = goal met. Overreach = complexity debt.

**Anti-Law**:
- ❌ Endless iteration after problem solved
- ❌ Add features "because we can"
- ❌ Ignore YAGNI principle

---

## Law 48: Assume Formlessness – Meta-Team Adapts to Every Session Context

**Original**: Assume Formlessness

**Adapted for Meta-Team**: Meta-team isn't rigid. Adapt to agent specialization, task type, session goals.

**Application**:
- Formless: TDD guard adapts mode (batch/incremental/manual)
- Formless: MCP profiles switch per task (code/github/full)
- Formless: Statistical thresholds adjust over time (coverage 80% → 85% as agents improve)
- Formless: Meta-team principles firm, implementations fluid

**Anti-Law**:
- ❌ Rigid rules that don't adapt to context
- ❌ Formless principles (chaos)
- ❌ One fixed approach for all agents/tasks

---

## Summary: The Meta-Learning Meta-Laws

### Core Principles (Immutable)
1. **TDD/YAGNI/KISS**: Non-negotiable
2. **Statistical learning**: Always collect data
3. **Agent autonomy**: Meta-team guides, doesn't implement
4. **Continuous improvement**: Learn from every session

### Adaptive Implementations (Context-Dependent)
1. **TDD mode**: Batch/incremental/manual
2. **MCP profiles**: Task-specific loading
3. **Hooks**: Intelligent, not rigid
4. **Agent supervision**: High-performers autonomous, strugglers supported

### The Ultimate Law
**Learn, Adapt, Optimize, Repeat.**

The meta-team that learns from every session, adapts tools to reality, optimizes bottlenecks, and repeats this cycle → becomes progressively more intelligent.

---

**Counter-Examples from Session fdd4c6d3**

| Law Violated | Evidence | Cost | Fix |
|--------------|----------|------|-----|
| Law 10 (Avoid blockers) | TDD hook blocked 2/4 agents | 25% session failure | TDD guard v2 |
| Law 6 (Court critical metrics) | Tracked vanity metrics, missed token waste | 4,000 wasted tokens | MCP profiles |
| Law 26 (Keep hands clean) | No PostTask auto-checkpoint | Context loss risk | PostTask hook |
| Law 42 (Strike root cause) | Patched symptoms, not root | Blocker recurred | Systemic fix |

---

**Version History**
- v1.0 (2025-10-19): Initial adaptation of 48 Laws for meta-learning team

**Next Steps**
1. Validate laws against future sessions
2. Add case studies per law
3. Update as meta-team evolves

**This is not dogma. This is a living document that adapts with experience.** ✅
