# T08 Proof Summary

## Task
T08: I-10 Phase 2i self-check for large PR summarization

## Description
Added a "Large PR self-check" checkpoint after the existing 2f self-verification checkpoint in phase2-triage.md. When the PR exceeds 500 lines, the orchestrator must confirm it will also dispatch 2j file-level summarization agents in the same message for parallel execution.

This addresses benchmark evidence where large PRs (sentry-greptile at 3,293 lines, cal.com at 555 lines) failed to dispatch file-level summarization agents, violating Critical Rule #2.

## Implementation
Single line added to `skills/deep-review/references/phase2-triage.md` at line 134 (after existing 2f self-verification checkpoint, before section separator):

```
**Large PR self-check:** If the PR exceeds 500 lines, confirm you will also dispatch 2j file-level summarization agents. Launch 2f and 2j agents in the same message for parallel execution (see Critical Rule #2).
```

## Proof Artifacts

| File | Type | Status |
|------|------|--------|
| T08-01-file.txt | Self-check line placement verification | PASS |
| T08-02-file.txt | Cross-reference consistency (2j step, Critical Rule #2) | PASS |

## Files Modified
- `skills/deep-review/references/phase2-triage.md`
