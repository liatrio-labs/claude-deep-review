# REVIEW.md Specification

A `REVIEW.md` file in a repository root lets project maintainers customize how deep-review behaves. It's optional — sensible defaults apply when absent.

## Format

REVIEW.md is a markdown file with specific sections. Each section is optional.

```markdown
# Review Configuration

## Focus
<!-- Which review dimensions to prioritize. If specified, only these dimensions run. -->
<!-- Omit this section to run all applicable dimensions. -->
- bugs
- security
- error-handling

## Skip
<!-- File patterns to exclude from review (glob syntax). -->
<!-- These files won't be reviewed by any agent. -->
- "**/*.generated.cs"
- "**/*.designer.cs"
- "**/migrations/**"
- "vendor/**"
- "dist/**"

## Rules
<!-- Custom natural-language rules applied to all review agents. -->
<!-- These supplement (don't replace) the built-in review logic. -->
- All database queries must use parameterized statements, never string concatenation
- Public API endpoints must validate request body schema before processing
- Feature flags must have an expiration date comment
- Console.log statements should not be committed to main

## Severity Threshold
<!-- Minimum severity to include in the report. Default: low -->
<!-- Options: critical, high, medium, low -->
medium

## Confidence Threshold
<!-- Minimum confidence score (0-100) to include in the report. Default: 80 -->
75

## Ignore
<!-- Specific finding patterns to suppress. Useful for known false positives. -->
<!-- Format: dimension:pattern -->
- compliance:"import order"
- security:"console.log in development mode"
```

## Section Details

### Focus

Controls which review dimensions run. Valid values map to agents:
- `bugs` — Bug detection and error handling (bug-detector agent)
- `security` — Security vulnerability scanning (security-reviewer agent)
- `cross-file-impact` — Cross-file impact analysis (cross-file-impact-analyzer agent)
- `tests` — Test coverage gap analysis (test-analyzer agent)
- `conventions` — Convention compliance, intent alignment, and comment accuracy (conventions-and-intent agent)
- `types` — Type design analysis (type-design-analyzer agent)
- `simplification` — Code simplification (code-simplifier agent, runs post-review)

When omitted, all applicable dimensions run (the skill auto-detects which are relevant based on the changes).

When specified, ONLY the listed dimensions run — this is useful for projects that want to focus on specific areas.

### Skip

Glob patterns for files to exclude from review. Common uses:
- Generated code that shouldn't be manually modified
- Vendored dependencies
- Build output
- Migration files that are auto-generated
- Large data files

### Rules

Custom natural-language rules that all review agents should check in addition to their built-in logic. These are especially useful for project-specific conventions that aren't captured in CLAUDE.md.

Rules should be:
- Specific and actionable (not vague guidelines)
- Objectively verifiable (an agent can determine compliance)
- Focused on the code being reviewed (not process/workflow rules)

### Severity Threshold

The minimum severity level to include in the report:
- `critical` — Only blocking issues
- `high` — Critical + high priority
- `medium` — Critical + high + medium (default for most projects)
- `low` — Everything (default)

### Confidence Threshold

An integer from 0-100. Findings below this confidence score are filtered out before the report. Default is 80. Lower values (e.g., 70) surface more findings but may include more false positives. Higher values (e.g., 90) are stricter but may miss some real issues.

### Ignore

Patterns for suppressing known false positives. Format is `dimension:"pattern"` where:
- `dimension` is one of the review dimension names (or `*` for all)
- `pattern` is a substring to match against finding titles/descriptions

This is useful when a project has intentional patterns that agents consistently flag incorrectly.
