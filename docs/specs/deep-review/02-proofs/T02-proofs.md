# T02 Proof Summary: Diagnostic logging in post_review.py

## Task
Add diagnostic logging to post_review.py skip warnings so that line-mismatch vs path-mismatch can be diagnosed on the next benchmark run.

## Requirements Verified

| Requirement | Status | Evidence |
|-------------|--------|----------|
| R02.1: Skip warning includes sorted valid lines (up to 10) | PASS | T02-01-test.txt |
| R02.2: Handles valid_lines=None gracefully | PASS | T02-01-test.txt |

## Proof Artifacts

| File | Type | Status |
|------|------|--------|
| T02-01-test.txt | test | PASS |

## Changes Made

1. Added `valid_lines_for_file()` helper in `scripts/post_review.py` that extracts and sorts up to 10 valid line numbers for a given file from the diff validation set. Returns None when valid_lines is None.
2. Updated `post_github()` skip warning to append valid lines diagnostic.
3. Updated `post_gitlab()` skip warning to append valid lines diagnostic.
4. Added 8 new tests in `tests/test_post_review.py`:
   - 5 tests for `valid_lines_for_file()` (None handling, sorting, cap at 10, path stripping, empty result)
   - 3 tests for diagnostic logging in skip warnings (GitHub with lines, GitHub empty set, GitLab with lines)

## Test Results
- Full suite: 246 passed (238 baseline + 8 new)
- post_review tests: 41 passed (33 baseline + 8 new)
