# T02 Proof Summary

**Task**: T02 - Fix filter_findings.py bugs (RF-02, RF-06)
**Status**: COMPLETED
**Date**: 2026-03-31

## Requirements Verified

| Req | Description | Status |
|-----|-------------|--------|
| RF-02 | REVIEW.md `ignore:` patterns merged into exclusion_patterns before apply_exclusions() | PASS |
| RF-06 | apply_exclusions docstring updated from "title or body" to "title or description" | PASS |

## Proof Artifacts

| File | Type | Command | Status |
|------|------|---------|--------|
| T02-01-cli.txt | cli | `grep -n "title or description" scripts/filter_findings.py` | PASS |
| T02-02-cli.txt | cli | `grep -n 'config.get.*ignore.*load_exclusions' scripts/filter_findings.py` | PASS |
| T02-03-cli.txt | cli | End-to-end: ignore pattern from REVIEW.md eliminates matching finding | PASS |

## Change Summary

Modified `scripts/filter_findings.py`:

**RF-06 fix** (line 944):
- Changed docstring from "Remove findings whose title or body matches..."
  to "Remove findings whose title or description matches..."

**RF-02 fix** (line 1050):
- Changed `exclusion_patterns = load_exclusions(args.exclusions_md)`
  to `exclusion_patterns = config.get("ignore", []) + load_exclusions(args.exclusions_md)`
- This ensures `ignore:` entries parsed from REVIEW.md are actually applied
  in the exclusion filter pipeline
