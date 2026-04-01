# T01 Proof Summary

**Task**: Fix verify_findings.py script bugs (RF-01, RF-03, RF-04, RF-05)
**Status**: COMPLETED
**Timestamp**: 2026-03-31

## Artifacts

| File | Type | Status |
|------|------|--------|
| T01-01-test.txt | test | PASS |
| T01-02-file.txt | file | PASS |

## Bug Fixes Implemented

### RF-01: Grep searches from CWD, not repo root
- Added `_resolve_repo_root()` function using `git rev-parse --show-toplevel`
- Defined `REPO_ROOT` module-level constant with fallback to script's parent directory
- Changed grep call to use `REPO_ROOT` as search path instead of `"."`

### RF-03: grep rc=2 silently zeroes confidence
- Changed `_stderr` (discarded) to `grep_stderr` (captured) in grep call
- Added `if rc == 2:` guard that warns to stderr and continues (skips symbol)
- rc=1 (no match) still correctly appends symbol to `missing_symbols`

### RF-04: Empty diff string disables validation silently
- Changed `if not diff_text:` to `if diff_text is None:` in `parse_diff_lines`
- `None` → returns `None` (skip validation — retrieval failed)
- `""` → falls through, returns `set()` (all findings tagged surfaced — empty diff)
- Updated test: `test_empty_input` renamed to `test_empty_input_returns_empty_set`

### RF-05: Dead branch in sha_in_pr
- Removed unreachable `short_sha.startswith(full_sha)` branch
- Renamed parameter `short_sha` to `blamed_sha` for clarity
- Added comment explaining blamed_sha is always the shorter side

## Tests Added (7 new tests)
- `TestRepoRoot.test_repo_root_is_absolute` — REPO_ROOT is absolute path
- `TestRepoRoot.test_repo_root_is_directory` — REPO_ROOT exists as directory
- `TestRepoRoot.test_grep_called_with_repo_root` — grep arg is not "."
- `TestVerifyFactualGrepError.test_grep_rc2_skips_symbol_not_zeros_confidence` — rf-03
- `TestVerifyFactualGrepError.test_grep_rc1_still_records_missing_symbol` — rc=1 still flags
- `TestShaInPrDeadBranch.test_short_blamed_sha_matches_full_pr_sha` — correct match
- `TestShaInPrDeadBranch.test_full_blamed_sha_does_not_match_short_pr_sha` — dead branch

## Test Results
51 tests pass (was 44 before this task). Full suite: 140 tests pass.
