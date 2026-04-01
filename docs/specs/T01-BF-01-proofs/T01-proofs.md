# T01-BF-01 Proof Summary

## Task
T01-BF-01: Resolve plugin root path for all resource references (BF-01)

Fix all references to plugin-root resources (scripts/, agents/) across SKILL.md and all reference files. Add a one-time resolution step early in the pipeline that establishes the plugin root path. Replace all `{plugin_base}/scripts/` references with concrete path guidance.

## Problem
The plugin directory structure has `scripts/` and `agents/` at the plugin root, but the skill base directory provided by Claude Code is `skills/deep-review/`. The orchestrator had ambiguous `{plugin_base}/scripts/` and `{skill_base}/scripts/` references that couldn't be resolved at runtime.

## Implementation

### Changes Made

**skills/deep-review/SKILL.md:**
- Added "Plugin root path resolution" section to Phase 1 (before Eligibility checks)
- Explains that `plugin_root` = `dirname(dirname(dirname(SKILL.md path)))` = two levels above `skills/deep-review/`
- Includes sanity check: `ls {plugin_root}/scripts/ {plugin_root}/agents/`
- Lists all three script invocation patterns
- Replaced two `{plugin_base}/scripts/` references with `{plugin_root}/scripts/`

**skills/deep-review/references/validation-pipeline.md:**
- Replaced `python3 scripts/verify_findings.py` with `python3 {plugin_root}/scripts/verify_findings.py`
- Replaced `python3 scripts/filter_findings.py` with `python3 {plugin_root}/scripts/filter_findings.py`

**skills/deep-review/references/phase8-delivery.md:**
- Replaced `{skill_base}/scripts/post_review.py` with `{plugin_root}/scripts/post_review.py`

**skills/deep-review/references/delivery-guide.md:**
- Replaced two `{skill_base}/scripts/post_review.py` with `{plugin_root}/scripts/post_review.py`

**skills/deep-review/references/phase3-dispatch.md:**
- No changes needed (no script path references)

### Files Not Modified
- `references/phase3-dispatch.md` — no script references
- `references/report-format.md` — only prose mentions of script names (not executable commands)

## Proof Artifacts

| File | Type | Status |
|------|------|--------|
| T01-01-file-changes.txt | file | PASS |
| T01-02-resolution-step.txt | file | PASS |
| T01-03-test.txt | test | PASS |

## Verification
- No `{plugin_base}` or `{skill_base}/scripts/` references remain in the skill
- All 5 targeted files now use `{plugin_root}/scripts/` for executable commands
- 149 tests pass with no regressions
