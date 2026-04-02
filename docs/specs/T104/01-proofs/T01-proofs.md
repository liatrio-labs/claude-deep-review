# T01 Proof Summary — BF-11: Robust diff fallback chain

**Task:** T01 (native ID: 117)
**Subject:** BF-11 — Robust diff fallback chain in verify_findings.py
**Status:** COMPLETE

## Artifacts

| File | Type | Status | Description |
|------|------|--------|-------------|
| T01-01-test.txt | test | PASS | test_verify_findings.py -- 60 tests pass |
| T01-02-test.txt | test | PASS | Full test suite -- 158 tests pass |

## Implementation Summary

Modified scripts/verify_findings.py get_diff() function:

- Removed: git diff HEAD fallback (always empty in CI -- wrong behavior)
- Added: Two-dot fallback: git diff {base} HEAD when three-dot fails
- Added: Return None when all git diffs fail (triggers skip-validation path per RF-04)
- Added: Stderr logging for which diff source succeeded with byte count

New fallback chain:
1. --diff-file (if provided)
2. git diff {base}...HEAD (three-dot merge-base)
3. git diff {base} HEAD (two-dot -- works without merge base)
4. None (skip diff validation)

Added 9 new tests in tests/test_verify_findings.py (TestGetDiff class).

## Requirements Coverage

| Req | Description | Status |
|-----|-------------|--------|
| R01.1 | get_diff reads from --diff-file when provided | PASS |
| R01.2 | get_diff tries two-dot diff when three-dot fails | PASS |
| R01.3 | get_diff returns None when all git diffs fail | PASS |
| R01.4 | get_diff logs which diff source was used to stderr with byte count | PASS |
| R01.5 | git diff HEAD fallback is removed entirely | PASS |
