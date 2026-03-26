# T04 Proof Summary — Fix summarizer bias: frame change summaries as claims, not conclusions

## Context

The Phase 2e change summarizer was biasing review agents toward leniency on refactoring PRs. In the benchmark case (sentry/#80528), the summarizer described the PR as a "clean refactoring, code moved verbatim" and all agents took it at face value, producing 0 findings on a PR with 2 real bugs. This implements B7 from the improvement backlog.

## Requirements Verified

| Requirement | Status | Evidence |
|---|---|---|
| Summary framed as claims ("PR claims to do X") | PASS | T04-01-file.txt |
| Critical framing rule added | PASS | T04-01-file.txt |
| Prohibited evaluative language listed | PASS | T04-01-file.txt |
| Explicit prohibition on concluding correctness | PASS | T04-01-file.txt |

## Files Modified

- `skills/deep-review/SKILL.md` — Phase 2e section updated with framing rule, prohibited language, and explicit prohibition

## Change Summary

The Phase 2e section was updated from a single sentence ("Dispatch a Sonnet agent for a 3-5 sentence semantic summary: what the PR does...") to include:

1. **Framing change**: "what the PR does" replaced with "what the PR *claims* to do"
2. **Critical framing rule**: Summaries describe what the PR says it does, not whether it succeeded; template provided
3. **Prohibited evaluative language**: clean, correct, safe, straightforward, simple, trivial, verbatim
4. **Explicit prohibition**: Summary must never conclude a refactoring is correct
