# T06 Proofs — Add missing tests

## Summary

Added regression/edge-case tests identified during V7 code review, plus restored the deleted hooks/hooks.json file.

### Tests Added

**1. validate_bash_subagent.py — 6 adversarial pattern tests (commit e569d2b)**

Identified gap: The hook script's regex was changed to support double-quoted paths and
prevent false-positive blocking of `&&` and `>` inside single-quoted JSON payloads.
Tests were needed to lock in the security properties.

| Test | What it verifies |
|------|-----------------|
| `test_double_quoted_path_allowed` | Double-quoted `"$TMPDIR/deep-review-*"` path is allowed |
| `test_ampersand_in_json_payload_allowed` | `&&` inside single-quoted payload doesn't trigger shell-op check |
| `test_greater_than_in_json_payload_allowed` | `>` inside single-quoted payload doesn't trigger redirect check |
| `test_subshell_injection_blocked` | `$(rm -rf /)` subshell injection is rejected |
| `test_backtick_injection_blocked` | backtick injection is rejected |
| `test_newline_injection_blocked` | Embedded newline in command is rejected (regex uses `\Z`) |

**2. filter_findings.py — 2 regression tests (commit d1216e5)**

Identified gap: V7-02 cross-agent dedup introduced a sibling-preservation bug
(same-agent findings in a multi-agent group were incorrectly deduped against each other).
Also, bucket boundary handling had no explicit coverage.

| Test | What it verifies |
|------|-----------------|
| `test_bucket_boundary_straddling` | Finding with line_start=10, line_end=20 straddling bucket boundary lands in correct bucket |
| `test_mixed_agent_group_same_agent_siblings_preserved` | Same-agent siblings in cross-agent group are all kept; only cross-agent dups are deduped |

### hooks/hooks.json Restored

The hooks/ directory was deleted from the working tree by a prior worker. This commit
restores `hooks/hooks.json` to match HEAD (commit e569d2b), which registers the
`validate_bash_subagent.py` PreToolUse hook for Bash commands.

## Proof Artifacts

| File | Type | Status |
|------|------|--------|
| T06-01-test.txt | 6 adversarial validate_bash_subagent tests | PASS |
| T06-02-test.txt | 2 filter_findings regression tests | PASS |
| T06-03-test.txt | Full 461-test suite run + hooks.json state | PASS |

## Test Count

Before T06 additions: 453 tests
After T06 additions: 461 tests (+8 new tests)
All 461 tests pass.
