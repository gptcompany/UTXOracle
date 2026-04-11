# Untracked Gemini/Helper Artifact Triage

Date: 2026-04-11

## Scope

This note classifies the currently untracked Gemini-related docs and helper scripts discovered during the execution-grade wave close-out.

Files reviewed:

- [docs/EXECUTION_GRADE_WAVE_054_059_COMMIT_REVIEW_2026-04-11.md](/media/sam/1TB/UTXOracle/docs/EXECUTION_GRADE_WAVE_054_059_COMMIT_REVIEW_2026-04-11.md)
- [docs/EXECUTION_GRADE_WAVE_054_059_FINAL_REPORT_2026-04-11.md](/media/sam/1TB/UTXOracle/docs/EXECUTION_GRADE_WAVE_054_059_FINAL_REPORT_2026-04-11.md)
- [docs/GEMINI_SPEC052_PHASED_IMPLEMENTATION_PROMPT.md](/media/sam/1TB/UTXOracle/docs/GEMINI_SPEC052_PHASED_IMPLEMENTATION_PROMPT.md)
- [docs/GEMINI_SPEC054_PHASED_IMPLEMENTATION_PROMPT.md](/media/sam/1TB/UTXOracle/docs/GEMINI_SPEC054_PHASED_IMPLEMENTATION_PROMPT.md)
- [docs/GEMINI_SPEC055_PHASED_IMPLEMENTATION_PROMPT.md](/media/sam/1TB/UTXOracle/docs/GEMINI_SPEC055_PHASED_IMPLEMENTATION_PROMPT.md)
- [docs/GEMINI_SPEC056_PHASED_IMPLEMENTATION_PROMPT.md](/media/sam/1TB/UTXOracle/docs/GEMINI_SPEC056_PHASED_IMPLEMENTATION_PROMPT.md)
- [docs/GEMINI_SPEC057_PHASED_IMPLEMENTATION_PROMPT.md](/media/sam/1TB/UTXOracle/docs/GEMINI_SPEC057_PHASED_IMPLEMENTATION_PROMPT.md)
- [docs/GEMINI_SPEC058_PHASED_IMPLEMENTATION_PROMPT.md](/media/sam/1TB/UTXOracle/docs/GEMINI_SPEC058_PHASED_IMPLEMENTATION_PROMPT.md)
- [docs/GEMINI_SPEC059_PHASED_IMPLEMENTATION_PROMPT.md](/media/sam/1TB/UTXOracle/docs/GEMINI_SPEC059_PHASED_IMPLEMENTATION_PROMPT.md)
- [scripts/gemini_prompt_queue.sh](/media/sam/1TB/UTXOracle/scripts/gemini_prompt_queue.sh)
- [scripts/add_health_entry.py](/media/sam/1TB/UTXOracle/scripts/add_health_entry.py)
- [scripts/append_boundary.py](/media/sam/1TB/UTXOracle/scripts/append_boundary.py)
- [scripts/build_boundary.py](/media/sam/1TB/UTXOracle/scripts/build_boundary.py)
- [scripts/update_docs.py](/media/sam/1TB/UTXOracle/scripts/update_docs.py)
- [scripts/update_registry.py](/media/sam/1TB/UTXOracle/scripts/update_registry.py)
- [scripts/bootstrap/sync_flows_to_questdb.py](/media/sam/1TB/UTXOracle/scripts/bootstrap/sync_flows_to_questdb.py)
- [scripts/clustering/backfill_entity_registry.py](/media/sam/1TB/UTXOracle/scripts/clustering/backfill_entity_registry.py)
- [scripts/clustering/backfill_entity_registry_fast.py](/media/sam/1TB/UTXOracle/scripts/clustering/backfill_entity_registry_fast.py)

## Recommended Disposition

| File / Group | Type | Recommendation | Reason |
|---|---|---|---|
| `docs/EXECUTION_GRADE_WAVE_054_059_COMMIT_REVIEW_2026-04-11.md` | final review artifact | keep and track | this is a durable repo artifact tied to the wave close-out |
| `docs/EXECUTION_GRADE_WAVE_054_059_FINAL_REPORT_2026-04-11.md` | final review artifact | keep and track | this is the consolidated close-out report |
| `docs/GEMINI_SPEC052_PHASED_IMPLEMENTATION_PROMPT.md` through `docs/GEMINI_SPEC059_PHASED_IMPLEMENTATION_PROMPT.md` | operator prompt docs | optional keep; do not treat as product docs | useful as execution logs/playbooks, but not part of runtime or contract source of truth |
| `scripts/gemini_prompt_queue.sh` | orchestration helper | keep only if Gemini-driven implementation remains a maintained workflow | script is coherent, but it is process tooling rather than product/runtime code |
| `scripts/add_health_entry.py` | one-shot migration helper | archive or discard | ad hoc YAML mutation, depends on `ruamel.yaml`, duplicates already-completed work |
| `scripts/append_boundary.py` | one-shot migration helper | archive or discard | hard-coded patch script for a historical spec-054 gap |
| `scripts/build_boundary.py` | one-shot migration helper | archive or discard | fragile generator with embedded assumptions and comments indicating prompt-driven improvisation |
| `scripts/update_docs.py` | one-shot migration helper | archive or discard | raw string replacement script; not durable tooling |
| `scripts/update_registry.py` | one-shot migration helper | archive or discard | historical migration script; not needed after the registry transition landed |
| `scripts/bootstrap/sync_flows_to_questdb.py` | operational data sync utility | evaluate for promotion or remove | looks like real operational tooling, but needs docs, ownership, and validation before tracking |
| `scripts/clustering/backfill_entity_registry.py` | operational backfill utility | evaluate for promotion or remove | real data task, but overlaps with existing tracked clustering/bootstrap flows and lacks tests/docs |
| `scripts/clustering/backfill_entity_registry_fast.py` | alternate operational backfill utility | remove unless deliberately standardized | appears to be an optimized variant of the previous script; keeping both unreviewed increases ambiguity |

## Detailed Notes

### 1. Review Artifacts

The two new wave reports should be tracked:

- [EXECUTION_GRADE_WAVE_054_059_COMMIT_REVIEW_2026-04-11.md](/media/sam/1TB/UTXOracle/docs/EXECUTION_GRADE_WAVE_054_059_COMMIT_REVIEW_2026-04-11.md)
- [EXECUTION_GRADE_WAVE_054_059_FINAL_REPORT_2026-04-11.md](/media/sam/1TB/UTXOracle/docs/EXECUTION_GRADE_WAVE_054_059_FINAL_REPORT_2026-04-11.md)

They are part of the close-out record for the wave and materially help future review.

### 2. Gemini Prompt Documents

The phased Gemini prompt documents are not runtime artifacts and should not be confused with contract or product docs.

They can be kept if the team wants a reproducible record of the operator prompts used to drive implementation, but they should be treated as:

- process artifacts
- historical execution notes
- optional reference material

If kept, they belong in a clearly-marked operational or archive area rather than as first-class product documentation.

### 3. One-Shot Migration Scripts

These scripts are classic temporary migration helpers:

- [add_health_entry.py](/media/sam/1TB/UTXOracle/scripts/add_health_entry.py)
- [append_boundary.py](/media/sam/1TB/UTXOracle/scripts/append_boundary.py)
- [build_boundary.py](/media/sam/1TB/UTXOracle/scripts/build_boundary.py)
- [update_docs.py](/media/sam/1TB/UTXOracle/scripts/update_docs.py)
- [update_registry.py](/media/sam/1TB/UTXOracle/scripts/update_registry.py)

Why they should not be promoted as stable tooling:

- they mutate canonical docs/contracts directly
- several depend on `ruamel.yaml`, which does not appear to be part of the tracked dependency surface for this repo
- they encode historical assumptions from the 054-059 migration path
- they are not tested
- at least one contains inline uncertainty/comments instead of a clean deterministic implementation

Recommended action:

- do not version them as supported tooling
- either archive them outside the main repo path or discard them after the relevant diffs are preserved in git history

### 4. Operational Scripts That Need an Explicit Decision

These look more substantial than one-shot patchers:

- [sync_flows_to_questdb.py](/media/sam/1TB/UTXOracle/scripts/bootstrap/sync_flows_to_questdb.py)
- [backfill_entity_registry.py](/media/sam/1TB/UTXOracle/scripts/clustering/backfill_entity_registry.py)
- [backfill_entity_registry_fast.py](/media/sam/1TB/UTXOracle/scripts/clustering/backfill_entity_registry_fast.py)

They may be useful, but they are not ready to be silently absorbed into the repo baseline because they currently lack:

- ownership and invocation docs
- tests or at least a smoke validation path
- clear placement relative to already-tracked bootstrap/materialization flows
- a decision on whether both normal and `fast` variants should exist

Recommended action:

1. keep out of the main tracked baseline until deliberately reviewed
2. if promoted later, require:
   - docstring/header explaining purpose and inputs
   - operator docs or README placement
   - at least one validation path
   - de-duplication against existing tracked scripts

## Practical Close-Out Recommendation

Short version:

- track the two execution-grade wave reports
- treat Gemini prompt docs as optional historical/process artifacts
- discard or archive the one-shot migration scripts
- promote the three operational data scripts only after separate review

This keeps the wave close-out clean without silently expanding the supported tooling surface.
