# AST-Safe Finding Emission Design

## Problem

Phase 3 review agents emit findings via `echo '...' >> ".deep-review/..."` Bash commands. Two issues cause permission prompts that break the subagent UX:

1. **Plugin hooks don't propagate to subagents.** The `validate_bash_subagent.py` PreToolUse hook never fires for Phase 3 agent Bash calls. This is a documented Claude Code platform gap (7 GitHub issues, no fix as of v2.1.96). The hook works in the main session but the plugin hook pool is not copied into subagent execution contexts.

2. **ANSI-C quoting (`$'...'`) is rejected by the sandbox AST parser.** When JSON content contains apostrophes, agents switch from `echo '...'` to `echo $'...'`. The tree-sitter-bash parser produces an `ansi_c_string` AST node which is NOT in the hardcoded allowlist, returning `too-complex`. For subagents with no interactive prompt, `too-complex` = auto-denied.

### Root cause chain

```
Plugin hooks/hooks.json
  -> merged into PARENT session hook pool
  -> NOT propagated to subagent execution contexts
  -> hook never fires for Phase 3 agent Bash calls
  -> no permissionDecision: "allow" at Stage 1
  -> falls through to Stage 5 (AST static analysis)
  -> echo $'...' produces ansi_c_string node (not in allowlist)
  -> parser returns "too-complex"
  -> Stage 7: subagent has no interactive prompt -> auto-denied
```

For `echo '...'` with regular single quotes, Stage 5 auto-approves because those AST nodes ARE in the allowlist. The hook never mattered for those commands.

### What auto-approves vs what prompts

| Pattern | AST nodes | Result |
|---------|-----------|--------|
| `echo '...' >> "literal_path"` | `raw_string`, `string` | Auto-approved |
| `echo "..." >> "literal_path"` | `string` | Auto-approved |
| `echo $'...' >> "path"` | `ansi_c_string` | Prompt/deny |
| `echo '...' >> $VAR/path` | `simple_expansion` | Prompt/deny |
| `python3 -c "..."` | varies | Prompt/deny |
| Heredocs with `${var}` | parse failure | Error |

## Design

This is additive to V6-01's truncation-robust output protocol and V7-01's dual-channel emission design. It does not replace them -- it hardens the Bash emission channel against sandbox rejection.

### Principle

Agents emit ONLY patterns the tree-sitter AST parser can fully resolve. The hook becomes a nice-to-have security layer, not a load-bearing mechanism. The text fallback channel (already parsed by `merge_findings.py`) is the code-controlled safety net -- if an echo is ever denied, findings in the agent's text response are still captured.

### Layer 1 -- AST-safe emission (primary, no hook needed)

Agents use ONLY this pattern:

```bash
echo '<json_with_no_literal_single_quotes>' >> ".deep-review/deep-review-{agent}-{sha}.ndjson"
```

Rules:
- Regular single quotes around payload (AST node: `raw_string`, in allowlist)
- Literal path in double quotes (AST node: `string`, in allowlist)
- **For apostrophes in JSON values**: replace `'` with `\u0027` before emitting. This is valid JSON -- `json.loads()` decodes `\u0027` back to `'`. No shell metacharacters.
- **Prohibited**: `$'...'` (ANSI-C quoting), `$VAR` in paths, heredocs, `python3 -c`, command substitution

Why `\u0027`: JSON allows Unicode escapes in string values. `{"description": "doesn\u0027t handle null"}` is identical to `{"description": "doesn't handle null"}` after parsing. Inside shell single quotes, `\u0027` is a literal string with no special meaning -- no quoting conflict.

### Layer 2 -- Hook as defense-in-depth (fires when it fires)

Keep the plugin hook unchanged:
- Returns `deny` for non-echo commands (git, rm, cat, etc.)
- Returns `allow` for valid echo-append commands
- Works in the main session; may propagate in future Claude Code versions
- Accept the documented platform limitation for subagent sessions

### Layer 3 -- Agent instructions explain the constraint

Each discovery agent gets a brief explanation **at the top of its emission section** (primacy bias -- artifact #24 shows earlier instructions are followed more reliably):

> The sandbox AST parser auto-approves `echo '...'` but rejects `$'...'` (ANSI-C quoting). In subagent sessions, rejected commands are silently denied with no recovery. If your JSON contains apostrophes, replace them with `\u0027` (valid JSON Unicode escape) before emitting. Never use `$'...'`, `$VAR` in paths, heredocs, or `python3 -c`.

This matters because agents under cognitive load need to understand the *consequence* of deviating, not just the rule (per research artifact #24).

Each agent's emission example must include a **few-shot instance showing `\u0027`** in context (artifact #17: 3.25x tool-calling compliance with exact format examples). Not just a description of the rule, but an example finding with an apostrophe:

```bash
echo '{"id":"bug-1","title":"Race condition in cache update","description":"The function doesn\u0027t acquire a lock before mutating shared state","severity":"high","confidence":88,"file":"src/cache.py","line_start":42,"line_end":47,"dimension":"bug"}' >> ".deep-review/deep-review-bug-detector-abc12345.ndjson"
```

## What this eliminates

- All permission prompts (AST auto-approves the exact pattern)
- Hook dependency (works even when hooks don't propagate)
- Platform dependency (no temp paths, no `$TMPDIR`)
- Quoting fragility (`\u0027` handles any content safely)

## What we keep

- The plugin hook (partial security when it fires, future-proofing)
- The `.deep-review/` repo-local output directory
- The `$DEEP_REVIEW_OUTPUT_DIR` env var override for CI
- The `merge_findings.py` dual-channel parsing (NDJSON + text fallback) -- this is the code-controlled safety net (artifact #17: code enforcement > prompt enforcement). If the NDJSON channel fails for any reason, the text fallback captures findings from agent responses

## Implementation Tasks

### T01: Update all 7 discovery agent emission instructions

**Files:** `agents/bug-detector.md`, `agents/security-reviewer.md`, `agents/cross-file-impact.md`, `agents/test-analyzer.md`, `agents/conventions-and-intent.md`, `agents/code-simplifier.md`, `agents/type-design-analyzer.md`

In each agent's emission/output section:
1. Add the AST constraint explanation **at the top of the emission section** (primacy bias, artifact #24)
2. Update the emission example to include a `\u0027` in the description (few-shot, artifact #17 -- 3.25x compliance)
3. Explicitly prohibit `$'...'`, `$VAR`, heredocs, `python3 -c` with the consequence: "silently denied, no recovery"
4. Show the correct pattern with regular single quotes
5. This is additive to the existing V6-01 trailing-prose prohibition -- do not remove or relocate existing emission instructions

### T02: Update SKILL.md Phase 3 dispatch and emission protocol

**File:** `skills/deep-review/SKILL.md`

1. Add a "Finding emission protocol" subsection that documents the AST-safe pattern
2. Update the Phase 3 dispatch template to include the `\u0027` instruction
3. Document WHY: link to the platform limitation (hooks don't propagate to subagents)

### T03: Update phase3-dispatch.md reference

**File:** `skills/deep-review/references/phase3-dispatch.md`

1. Update the emission protocol section with AST-safe requirements
2. Update dispatch template per-agent `Findings file:` instructions
3. Add the prohibited patterns list

### T04: Update validate_bash_subagent.py for `\u0027` pattern

**File:** `scripts/validate_bash_subagent.py`

The hook's ECHO_APPEND_RE regex should continue to accept the echo-append pattern. Verify that `\u0027` inside single-quoted payloads is handled correctly (it should be -- `\u0027` is just literal characters inside single quotes). No regex changes expected, but verify and add test cases.

### T05: Add test cases for `\u0027` emission pattern

**File:** `tests/test_validate_bash_subagent.py`

Add test cases:
- Echo with `\u0027` in payload -> allowed
- Echo with `$'...'` ANSI-C quoting -> denied (existing, verify)
- Echo with payload containing escaped apostrophes -> allowed

### T06: Archive research artifacts

**Files to create:**
- `docs/research/artifacts/25-sandbox-bash-ast-auto-allow.md`
- `docs/research/artifacts/26-hook-sandbox-permission-pipeline.md`
- `docs/research/artifacts/27-plugin-hook-subagent-propagation.md`

Copy the three research artifacts from `/Users/lee/Downloads/` into the research directory with sequential numbering and kebab-case names.

### T07: Update research README

**File:** `docs/research/README.md`

1. Add rows to the artifacts table for #25, #26, #27 with summaries
2. Add design decision mappings to the "How these informed the design" table:
   - AST-safe emission pattern (`\u0027` for apostrophes, no `$'...'`) -> #25, #26
   - Hook as defense-in-depth, not primary mechanism -> #26, #27
   - Platform limitation acceptance (plugin hooks don't reach subagents) -> #27
3. Update the "next" number in the "Adding new research" section to `28-`

### T08: Update CLAUDE.md

**File:** `CLAUDE.md`

Update the "Output directory convention" section to mention:
- The AST-safe emission requirement (regular single quotes only, `\u0027` for apostrophes)
- The hook limitation (doesn't propagate to subagents, defense-in-depth only)

### T09: Update memory files

**Files:**
- `project_deep_review_architecture.md` -- add note about AST-safe emission and hook propagation limitation
- `MEMORY.md` -- update index line if description changes

## Testing

- All existing 483 tests must continue to pass
- New test cases in T06 for `\u0027` pattern
- Manual validation: run a review on a PR with findings containing apostrophes, verify zero permission prompts

## Success Criteria

1. Zero permission prompts during Phase 3 agent finding emission
2. Findings containing apostrophes (e.g., "doesn't", "won't", "it's") emit correctly as valid NDJSON
3. `merge_findings.py` correctly parses `\u0027` in finding descriptions from both NDJSON and text fallback channels
4. The hook continues to work in the main session for non-emission commands
5. All tests pass (existing 483 + new `\u0027` cases)
6. Research artifacts #25-#27 archived and indexed in README with design decision mappings
