# T09 Proof Summary — Separate Agent calls from Bash in parallel batches (BF-09)

## Context

When Bash commands fail in a parallel batch within Claude Code, all co-dispatched Agent calls are cancelled. This forces expensive re-dispatch of Agent operations that were unrelated to the Bash failure. The task was to clarify in phase2-triage.md that Agent calls (2f, 2j) must be separated from Bash/Glob/Grep operations (2g, 2h, 2i) and dispatched in their own parallel group.

## Requirement

File to modify: `skills/deep-review/references/phase2-triage.md`

Establish clear guidance that:
1. Agent dispatch (2f and 2j) occurs in BATCH 1
2. Bash/file operations (2g, 2h, 2i) occur in BATCH 2
3. Batches are sequential, not concurrent
4. This prevents Agent cancellation on Bash errors

## Implementation Summary

Three modifications were made to phase2-triage.md:

### 1. Section 2f: Added CRITICAL RULE (Line 116)

Inserted mandatory guidance stating that Agent calls (2f and 2j) must NOT be bundled with Bash/Glob/Grep commands (2g, 2h, 2i). Explained the consequence: when Bash fails, Claude Code cancels co-dispatched Agents, forcing re-dispatch.

### 2. Section 2j: Added IMPORTANT directive (Line 186)

Appended a clear statement that 2f and 2j Agent dispatch must be in a SEPARATE parallel message from 2g/2h/2i operations. Instructed: "Dispatch 2f+2j agents in one parallel batch, then in a NEW message dispatch 2g/2h/2i Bash/Glob/Grep operations."

### 3. New Section: Phase 2 Parallel Execution Strategy (Lines 204-225)

Added comprehensive section describing the two-batch execution model:
- **BATCH 1 (Agent Dispatch):** 2f + 2j in one message
- **BATCH 2 (File Discovery & History):** 2e, 2g, 2h, 2i in a NEW message
- Explained the rationale: separates expensive operations from failure-prone Bash commands

## Files Modified

- `skills/deep-review/references/phase2-triage.md` — Three targeted clarifications added

## Verification

| Requirement | Status | Evidence |
|---|---|---|
| CRITICAL RULE added to 2f (line 116) | PASS | T09-02-file.txt |
| IMPORTANT directive added to 2j (line 186) | PASS | T09-02-file.txt |
| New Phase 2 Parallel Execution Strategy section (lines 204-225) | PASS | T09-02-file.txt |
| Diff preserved in version control | PASS | T09-01-file.txt |

## Impact

These changes provide explicit guidance to future implementation teams and orchestrators about the critical operational constraint: Agent calls must not be co-dispatched with Bash operations that could cause cancellation of expensive agent work. This reduces wasted compute and improves reviewer latency in Phase 2 triage.
