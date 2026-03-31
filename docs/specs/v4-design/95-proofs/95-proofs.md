# T11.1 Proof Summary — Context-pulling + LSP in all 7 review agents

**Task**: T11.1 (#95) — Add context-pulling + LSP instructions to all 7 review agents
**Completed**: 2026-03-31
**Model**: sonnet

## Requirements checked

| Requirement | Status |
|-------------|--------|
| R11.1.1: All 7 agents have context-pulling instruction | PASS |
| R11.1.2: LSP emphasized for symbol resolution | PASS |
| R11.1.3: Instructions are concise (2-3 lines) | PASS |

## Proof artifacts

| File | Type | Status |
|------|------|--------|
| 95-01-cli.txt | cli — grep count | PASS (9 total, 7 target agents confirmed) |
| 95-02-cli.txt | cli — per-agent check | PASS (7/7 review agents verified) |

## What was changed

All 7 `## Context-pulling instructions` sections were rewritten to:
1. Open with "Don't rely solely on the diff and pre-loaded context."
2. Specify agent-relevant Read/Grep investigation steps
3. Add LSP operations tailored to each agent's task

### Per-agent LSP focus

- **bug-detector**: hover for types, findReferences for callers, goToDefinition for dependencies
- **security-reviewer**: LSP to check sanitization functions, auth checks, and sink reachability
- **cross-file-impact**: findReferences for all consumers, goToDefinition for interface hierarchies
- **test-analyzer**: findReferences to check if a code path has coverage elsewhere
- **conventions-and-intent**: goToDefinition to verify referenced types exist, hover for parameter types
- **type-design-analyzer**: goToDefinition for base types/interfaces, findReferences for construction sites
- **code-simplifier**: findReferences before suggesting extraction/inlining

## Note on proof count

The proof command `grep -l 'LSP' agents/*.md | wc -l` returns 9, not 7, because challenger.md
and validator.md already had "LSP" in their frontmatter `tools:` fields before this task.
The requirement is satisfied: all 7 target review agents now have LSP in their context-pulling
sections.
