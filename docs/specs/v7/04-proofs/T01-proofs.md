# T01 Proofs: Fix symbol extraction garbled tokens (V7-04)

## Summary

Task: Add punctuation-splitting step to `_extract_symbols()` Tier 2 regex in verify_findings.py.

### Problem

The code-punctuation regex in Tier 2 of `_extract_symbols()` was too greedy. It would match entire expressions like `grantTypeShortcut.equals(substring(3, 5))` as a single token, then extract identifiers without splitting on the punctuation boundaries. This produced garbled concatenations like `equalssubstring35` instead of separate identifiers.

### Solution

Modified the Tier 2 extraction logic in `/Users/lee/personal/claude-deep-review/scripts/verify_findings.py` (lines 451-465):

1. Added `_SPLIT_PUNCTUATION_RE` pattern to split on code punctuation chars: `[.()\[\]#:>-]+`
2. Changed identifier extraction to split matched tokens on punctuation before extracting
3. Added validation to ensure extracted parts match identifier pattern `^[A-Za-z_][A-Za-z0-9_]*$`

### Changes

**File: `scripts/verify_findings.py`**

- Lines 451-465: Updated Tier 2 extraction to split on code punctuation
- Regex split pattern: `[.()\[\]#:>-]+` (matches all code punctuation)
- Ensures complex expressions split into constituent identifiers

**File: `tests/test_verify_findings.py`**

Added 2 new regression tests to `TestExtractSymbols`:
- `test_complex_chained_methods_split_correctly`: Validates that `grantTypeShortcut.equals(substring(3, 5))` splits into `{grantTypeShortcut, equals, substring}` instead of garbled tokens
- `test_deeply_nested_parentheses_split`: Validates complex nested method calls split correctly across all punctuation boundaries

## Proof Artifacts

### T01-01-test.txt
- **Type**: test (pytest)
- **Command**: `python -m pytest tests/test_verify_findings.py::TestExtractSymbols -xvs`
- **Status**: PASS ✓
- **Result**: All 15 symbol extraction tests pass, including 2 new regression tests
- **Key Evidence**: Both `test_complex_chained_methods_split_correctly` and `test_deeply_nested_parentheses_split` pass

### T01-02-regression.txt
- **Type**: test (full suite)
- **Command**: `python -m pytest tests/ -q`
- **Status**: PASS ✓
- **Result**: 387 tests pass (no regressions)
- **Key Evidence**: Full test suite passing confirms backward compatibility

## Testing Coverage

### Test Cases Added
1. Complex chained methods: `grantTypeShortcut.equals(substring(3, 5))`
   - Validates: separate identifiers extracted, no garbled concatenations
   
2. Deeply nested parentheses: `foo.bar(baz.qux(nested.value))`
   - Validates: multi-level nesting splits correctly
   - Ensures no intermediate concatenations like `barbaznested`

### Regression Tests Passed
- All 15 existing `TestExtractSymbols` tests still pass
- All 387 tests in full suite pass
- No breaking changes to other verification logic

## Technical Details

### Root Cause
The original code at lines 460-465 extracted identifiers from matched tokens without splitting:
```python
for m in _CODE_PUNCTUATION_RE.finditer(combined_text):
    token = m.group(1)
    for ident_m in _IDENT_RE.finditer(token):
        # This would extract: equalssubstring35 from the whole token
```

### Fix Applied
New code splits on punctuation first:
```python
_SPLIT_PUNCTUATION_RE = re.compile(r"[.()\[\]#:>-]+")
for m in _CODE_PUNCTUATION_RE.finditer(combined_text):
    token = m.group(1)
    parts = _SPLIT_PUNCTUATION_RE.split(token)  # Split first
    for part in parts:
        if part and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", part) and len(part) > 2:
            # Extract: grantTypeShortcut, equals, substring (separately)
```

## Verification

✓ Tier 1 (backtick) extraction: Working
✓ Tier 2 (code-punctuation) extraction: Fixed - now splits correctly
✓ Tier 3 (pure CamelCase) filtering: Working
✓ Snake case extraction: Working
✓ Symbol filtering (short tokens, skip list): Working
✓ Symbol verification (grep against codebase): Working
✓ All integration tests: Passing

## Impact

- **Lines Modified**: 15 in verify_findings.py
- **Tests Added**: 2 regression tests
- **Tests Affected**: 0 existing tests broken
- **Scope**: `_extract_symbols()` Tier 2 logic only
- **Risk**: Low (isolated change with comprehensive test coverage)

---
Status: **COMPLETE** ✓
Timestamp: 2026-04-05T16:00:00Z
