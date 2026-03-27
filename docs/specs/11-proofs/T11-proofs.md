# T11 Proof Summary

Task: Create references/phase3-dispatch.md — extract agent roster, context scoping, and dispatch template

## Artifacts

| File | Type | Status | Description |
|------|------|--------|-------------|
| T11-01-file.txt | file | PASS | phase3-dispatch.md exists with all required sections |
| T11-02-file.txt | file | PASS | SKILL.md Phase 3 compressed to 11 lines (target ~20) with required inline content |
| T11-03-file.txt | file | PASS | Critical constraints preserved: tools/effort fields, assembly instructions, agent-prompt-template.md refs |

## Summary

- Created `skills/deep-review/references/phase3-dispatch.md` (81 lines, target ~75)
- Modified `skills/deep-review/SKILL.md` Phase 3 section: ~78 lines → 11 lines
- All 6 required sections moved to reference file (agent context, scoping, roster, template, self-verification, failure handling)
- Required inline content preserved verbatim: "You cannot perform the review yourself", fire-and-forget, SECURITY BOUNDARY note
- Agent() call template preserved with `tools: [Read, Grep, Glob, LSP]` and `effort: "high"`
- 8-step assembly instructions referencing agent-prompt-template.md preserved verbatim
- security-reviewer always Opus constraint preserved in roster and template

## All Checks: PASS
