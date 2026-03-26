# T05: Default PR Comment Cap 8 to 6 - Proof Artifacts

## Summary
Task T05 successfully updates the default PR comment cap from 8 to 6 findings, matching the research-optimal engagement volume per Doc #15 (optimal volume 5-6 comments per PR, adoption threshold 75-80% precision).

## Changes Made

### File 1: skills/deep-review/SKILL.md
**Location:** Phase 7, Stage 1, Step B - PR comment selection flow

Changed lines:
- Line 378: Label updated from "Default — top 8 by severity" to "Default — top 6 by severity"
- Line 385: Explanation updated from "select the top 8 findings" to "select the top 6 findings"

### File 2: skills/deep-review/references/delivery-guide.md
**Location:** PR/MR Comments section (platform-aware)

Changed lines:
- Line 13: Cap description updated from "Inline comment default cap: 8" to "Inline comment default cap: 6"
- Line 13: User selection text updated from "Default — top 8 by severity" to "Default — top 6 by severity"
- Line 13: Comment count updated from "top 8 findings" to "top 6 findings"
- Line 68: Python script comment updated from "up to 8 inline comments (cap)" to "up to 6 inline comments (cap)"

## Verification

All instances of the cap value have been updated:
- ✓ SKILL.md: Default option label (line 378)
- ✓ SKILL.md: Explanation text (line 385)
- ✓ delivery-guide.md: Cap specification (line 13)
- ✓ delivery-guide.md: User selection description (line 13)
- ✓ delivery-guide.md: Python API example comment (line 68)

The "Let me pick" flow remains uncapped as specified - users can select all findings if they explicitly choose them.

## Status
All changes committed successfully. No breaking changes - the modification is a pure config update that reduces the default cap from 8 to 6 while preserving user override capability.
