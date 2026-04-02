# T02 BF-14 Proof Summary

**Task:** BF-14 -- Normalize legacy field names in filter_findings.py
**Status:** PASS (all requirements verified)

## Requirements Coverage

| Req | Description | Proof | Status |
|-----|-------------|-------|--------|
| R02.1 | body -> description when description absent | T02-01-test.txt | PASS |
| R02.2 | body+description keeps description unchanged | T02-01-test.txt | PASS |
| R02.3 | line -> line_start when line_start absent | T02-01-test.txt | PASS |
| R02.4 | blame_tag -> origin when origin absent | T02-01-test.txt | PASS |
| R02.5 | WARNING logged to stderr on normalization | T02-01-test.txt | PASS |
| R02.6 | SKILL.md merge instructions reinforce description | T02-02-file.txt | PASS |

## Proof Artifacts

1. **T02-01-test.txt** -- 11 unit tests for normalize_field_names covering all requirements
2. **T02-02-file.txt** -- SKILL.md merge instruction verification for R02.6
3. **T02-03-test.txt** -- Full regression suite (208 tests, 0 failures)

## Changes Made

- `scripts/filter_findings.py`: Added `normalize_field_names()` function and `_FIELD_RENAMES` constant. Called in `main()` after loading findings, before any filter.
- `tests/test_filter_findings.py`: Added `TestNormalizeFieldNames` class with 11 tests. Added `normalize_field_names` to imports.
- `skills/deep-review/SKILL.md`: Added item 4 to "Merge Phase 3 Outputs" section reinforcing that the pipeline field is `description`, not `body`.
