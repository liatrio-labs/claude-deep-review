# T04 Proof Summary

**Task:** T04 — Add LSP-first investigation guidance to review agents
**Status:** COMPLETED
**Date:** 2026-03-31

## Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| R04.1 | bug-detector.md includes LSP goToDefinition guidance for delegation tracing and findReferences for caller checking | PASS |
| R04.2 | security-reviewer.md includes LSP goToDefinition for input-to-sink tracing and findReferences for sanitization checking | PASS |
| R04.3 | cross-file-impact.md includes LSP findReferences for caller/implementor discovery and goToDefinition for signature verification | PASS |
| R04.4 | type-design-analyzer.md includes LSP hover for type inspection and goToDefinition for hierarchy tracing | PASS |
| R04.5 | All 4 agents include explicit Grep fallback language | PASS |

## Proof Artifacts

| File | Type | Command | Expected | Result | Status |
|------|------|---------|----------|--------|--------|
| T04-01-cli.txt | cli | `grep -l 'LSP' agents/*.md` (4 target files) | all 4 files listed | all 4 files listed | PASS |
| T04-02-cli.txt | cli | `grep -c 'Fall back to Grep' agents/*.md` (4 target files) | each count >= 1 | all counts = 1 | PASS |

## Summary

Added brief LSP-first investigation guidance (2-3 sentences per agent) to the four review agents that benefit most:

- **agents/bug-detector.md**: Added `goToDefinition` for delegation chain tracing and `findReferences` for caller checking to step 10 (delegation/proxy tracing).
- **agents/security-reviewer.md**: Added `goToDefinition` for input-to-sink path tracing and `findReferences` for sanitization checking after step 1 (input-to-sink map).
- **agents/cross-file-impact.md**: Added new step 6 with `findReferences` for caller/implementor discovery and `goToDefinition` for signature verification.
- **agents/type-design-analyzer.md**: Added new "How to investigate" section with `hover` for type inspection and `goToDefinition` for hierarchy tracing.

All agents follow the LSP-first, Grep-fallback pattern with explicit "Fall back to Grep if LSP is unavailable" language.
