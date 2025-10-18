# [Task {{TASK_NUMBER}}] {{MODULE_NAME}}

## Goal
{{GOAL}}

## Deliverables
- [ ] `{{DELIVERABLE_FILE}}`
- [ ] `{{TEST_FILE}}`
- [ ] Coverage >{{THRESHOLD}}%
- [ ] Integration with Task {{PREV_TASK}}

## Acceptance Criteria
{{CRITERIA}}

## Dependencies
- **Requires**: Task {{PREV_TASK}} ({{PREV_MODULE}})
- **Blocks**: Task {{NEXT_TASK}} ({{NEXT_MODULE}})
- **Related**: #{{RELATED_ISSUE}}

## Black Box Interface

### Input
```python
{{INPUT_SPEC}}
```

### Output
```python
{{OUTPUT_SPEC}}
```

## Resources
- **Task file**: `docs/tasks/{{TASK_NUMBER}}_{{MODULE_FILE}}.md`
- **Agent**: `{{AGENT_NAME}}`
- **Estimated time**: {{ESTIMATE}}
- **Priority**: {{PRIORITY}}

## Implementation Notes
{{NOTES}}

---

**Labels**: `enhancement`, `task-{{TASK_NUMBER}}`, `{{PRIORITY}}`
**Assignee**: @{{ASSIGNEE}}
**Milestone**: MVP Week {{WEEK}}
