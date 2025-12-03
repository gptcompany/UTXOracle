# Pull Request: [Task {{TASK_NUMBER}}] {{MODULE_NAME}}

## Summary
{{DESCRIPTION}}

## Changes
- **Deliverable**: `{{FILE_PATH}}`
- **Tests**: `{{TEST_FILE}}` ({{TEST_COUNT}} tests)
- **Coverage**: {{COVERAGE}}%
- **Integration**: Task {{PREV_TASK}} → Task {{NEXT_TASK}}

## Test Plan
- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] Coverage >{{THRESHOLD}}%
- [ ] Manual testing completed

## Implementation Details
{{IMPLEMENTATION_NOTES}}

## Checklist
- [ ] Code follows UTXOracle style (black box architecture)
- [ ] TDD cycle completed (RED-GREEN-REFACTOR)
- [ ] Black box interface maintained
- [ ] Documentation updated (CLAUDE.md, task file)
- [ ] No external dependencies added (Python stdlib only)

## Related
- Closes #{{ISSUE_NUMBER}}
- Part of #epic-mempool-live
- Depends on: #{{DEPENDS_ON}}

## Screenshots (if applicable)
{{SCREENSHOTS}}

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Agent**: {{AGENT_NAME}}
**Estimated Time**: {{TIME_ESTIMATE}}
