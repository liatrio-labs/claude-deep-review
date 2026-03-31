# T48 Proof Summary — Update orchestrator dispatch to use named subagents

**Task:** T01.4 — Update orchestrator dispatch to use named subagents
**Status:** COMPLETED
**Timestamp:** 2026-03-30

## Changes Made

Updated 4 files to replace inline `Agent()` calls (with manually assembled prompts from `agents/{dim}.md` + `references/agent-prompt-template.md`) with the named subagent dispatch pattern `Agent(subagent_type: "deep-review:{agent-name}", ...)`.

### Files Modified

1. **skills/deep-review/references/phase3-dispatch.md**
   - Rewrote "What Each Agent Receives" section to describe named subagent architecture
   - Replaced Agent tool call template with `subagent_type: "deep-review:{dimension}"` pattern
   - Added Frontier mode model override example
   - Updated Agent Roster to use `deep-review:` subagent names instead of `agents/*.md` references
   - Fixed Per-Agent Context Scoping step references (2g/2i instead of 2f/2h)

2. **skills/deep-review/references/phase2-triage.md**
   - Section 2f (change-summarizer): replaced inline Agent template with `subagent_type: "deep-review:change-summarizer"`
   - Section 2j (per-file summarizer): replaced inline Agent template with same subagent, added `Mode: per-file summary` in prompt

3. **skills/deep-review/references/validation-pipeline.md**
   - Phase 5: replaced validator Agent template with `subagent_type: "deep-review:validator"`; added note that rubric/format is in agent definition
   - Phase 7: replaced challenger Agent template with `subagent_type: "deep-review:challenger"`; model override for Frontier mode

4. **skills/deep-review/SKILL.md**
   - Phase 3: added inline note about `subagent_type` dispatch pattern
   - Phase 5: updated Agent tool call template to use `subagent_type: "deep-review:validator"`
   - Phase 6: updated code-simplifier dispatch prose to reference named subagent pattern
   - Phase 7: updated Agent tool call template to use `subagent_type: "deep-review:challenger"`
   - Critical Rule #2: fixed phase number from 2e/2i to 2f/2j for change-summarizer

## Proof Artifacts

| Artifact | Type | Status |
|---|---|---|
| T48-01-file.txt | file — subagent_type in phase3-dispatch.md | PASS |
| T48-02-file.txt | file — no residual agent-prompt-template refs | PASS |
| T48-03-file.txt | file — all 5 dispatch locations updated | PASS |

## Key Invariants Maintained

- The orchestrator provides **only dynamic content** in each prompt: project context, change summary, risk classification, scoped diff (or findings/code for validator/challenger)
- Agent definitions carry: role, instructions, rubric, output schema, effort, model, tools
- Frontier mode override (model: "opus") is documented at each dispatch site
- Security-reviewer always-Opus policy is preserved in the Roster
- "Do NOT include original reasoning or evidence" rule for challenger is preserved
