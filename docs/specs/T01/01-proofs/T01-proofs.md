# T01 Proof Summary

**Task:** T01 — Standardize filter_findings.py to canonical agent schema + parser warning
**Status:** COMPLETED
**Date:** 2026-03-31

## Requirements Verified

| ID | Requirement | Status |
|----|-------------|--------|
| R01.1 | All finding.get() calls use canonical field names: description, line_start, line_end, dimension, origin | PASS |
| R01.2 | Module docstring input JSON schema reflects canonical field names | PASS |
| R01.3 | No remaining references to 'body', 'blame_tag' as finding field accessors | PASS |
| R01.4 | parse_review_md() emits warn() when falling back to whole-file scan | PASS |
| R01.5 | Script parses cleanly and --help works | PASS |

## Proof Artifacts

| File | Type | Result |
|------|------|--------|
| T01-01-cli.txt | CLI: --help | PASS (exit 0 with usage info) |
| T01-02-cli.txt | CLI: AST parse | PASS (exit 0, clean syntax) |
| T01-03-cli.txt | CLI: grep for old fields | PASS (no matches, confirms R01.3) |

## Changes Made

### scripts/filter_findings.py

1. **Module docstring (R01.2):** Updated input JSON schema from old fields (`body`, `line`, `blame_tag`, `dimensions`) to canonical fields (`description`, `line_start`, `line_end`, `origin`, `dimension`).

2. **Field accessors (R01.1, R01.3):** Updated all `.get()` calls throughout the script:
   - `finding.get("body", "")` → `finding.get("description", "")` (6 sites)
   - `finding.get("line", ...)` → `finding.get("line_start", ...)` (8 sites)
   - `finding.get("dimensions", [])` → derive from `finding.get("dimension", "")` (2 sites)
   - Duplicate-signature key updated: `finding.get("line")` → `finding.get("line_start")`

3. **Parser warning (R01.4):** Added `warn()` call in `parse_review_md()` when no block pattern matches and falling back to whole-file scan (line ~142).

4. **Comments updated:** Internal variable names and comments (`body` → `description`, `body_word_count` → `description_word_count`, injection pattern comments).
