# claude-deep-review

A comprehensive, research-backed code review skill for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that orchestrates parallel concern-specialized agents, cross-validates findings with deterministic verification, and produces unified review reports.

## What it does

Deep Review dispatches 5-7 specialized agents in parallel, each examining your code changes through a different lens:

| Agent | Model | Focus |
|-------|-------|-------|
| **bug-detector** | Opus | Logic errors, edge cases, error handling, resource leaks |
| **security-reviewer** | Opus | OWASP top 10, injection, auth, SSRF, deserialization |
| **cross-file-impact-analyzer** | Opus | How changes affect callers and dependents across the codebase |
| **test-analyzer** | Sonnet | Test coverage gaps, test quality, missing edge cases |
| **conventions-and-intent** | Sonnet | CLAUDE.md compliance, spec alignment, comment accuracy |
| **type-design-analyzer** | Sonnet | Type encapsulation and invariant design (conditional) |
| **code-simplifier** | Opus | Simplification opportunities (post-review, conditional) |

After agents report findings, a validation pipeline filters false positives:

1. **Deterministic verification** — confirms findings reference real code at correct locations
2. **LLM judgment** — attempts to disprove each finding with a calibrated confidence rubric
3. **Dimension-specific thresholds** — security uses 70 (false negatives are costly), others use 80
4. **Challenge round** — agents vote on blocking findings to resolve disagreements
5. **Contradiction resolution** — specs suppress bug findings, security wins ties

## Key features

- **Concern-parallel, not file-parallel** — each agent sees the full diff with cross-file context, because bugs at module boundaries are invisible to file-scoped reviewers
- **Full-codebase investigation** — security and cross-file-impact agents trace data flows beyond the diff into the entire repository (matching [Anthropic's own approach](https://docs.anthropic.com/en/docs/claude-code/code-review))
- **Prompt injection defense** — code under review is untrusted input, wrapped in trust boundary delimiters with output scanning for injection artifacts
- **Context-pulling** — agents actively investigate using Read/Grep/LSP rather than receiving a passive context dump (51% fewer false positives per research)
- **GitHub + GitLab** — auto-detects platform from git remote, supports both `gh` and `glab` CLIs
- **REVIEW.md configuration** — project maintainers can customize focus areas, skip patterns, custom rules, and thresholds
- **Flexible delivery** — PR/MR comments (inline + summary), markdown file, chat, or all three

## Installation

Install as a Claude Code plugin:

```bash
claude plugin add liatrio-labs/claude-deep-review
```

Or install manually by cloning and adding to your plugins configuration:

```bash
git clone https://github.com/liatrio-labs/claude-deep-review.git ~/.claude/plugins/claude-deep-review
```

## Usage

The skill triggers automatically when you ask for a code review in Claude Code:

```
# Review a PR (GitHub)
deep review PR #42

# Review a merge request (GitLab)
review MR !89 thoroughly

# Review local uncommitted changes
comprehensive review of my changes

# Focused review
deep review PR #42, focus only on security and error handling
```

Or invoke it directly:

```
/deep-review
```

## How it works

The review runs through 7 phases:

1. **Pre-flight** — checks if the PR/MR is eligible (not closed, draft, or already reviewed)
2. **Triage** — classifies files by risk, detects AI-generated code, discovers related tests, gathers project context, produces a change summary
3. **Dispatch** — launches 5-7 agents in parallel with scoped context and trust boundary delimiters
4. **Validate** — deterministic verification, confidence filtering, injection artifact scanning, challenge round, contradiction resolution, deduplication
5. **Report** — generates a structured report with severity-ranked findings, GitHub/GitLab permalinks, and a methodology section
6. **Deliver** — asks how you want results: PR/MR comments, markdown file, chat, or all three

## Research backing

Every architectural decision is grounded in published research:

| Decision | Research basis |
|----------|---------------|
| 5-7 agents | Quality plateaus at 4-6 agents (DeepMind 2025); unstructured parallel systems amplify errors 17.2x |
| Concern decomposition | Anthropic, Ellipsis, Qodo all use concern-parallel, not file-parallel |
| Deterministic verification | LLM-on-LLM verification shares correlated errors ~60% of the time; deterministic grounding is essential |
| Context-pulling | cubic achieved 51% fewer false positives switching from push to pull |
| Security threshold 70 | Anthropic's own judge filtered 7/8 security findings at threshold 80, including real ones |
| Overconfidence calibration | Xiong et al. (ICLR 2024): LLMs cluster confidence in 80-100 range |
| Full-codebase security | Cat Wu (Anthropic): "agents often take the entire codebase into account" |
| Prompt injection defense | Every major AI review tool has been exploited; 5-layer defense recommended |
| LSP-first navigation | 900x faster than grep (50ms vs 30-60s); eliminates false matches |
| AI-code risk elevation | CodeRabbit: 75% more logic errors in AI-authored code |
| 500-line large-PR threshold | Review effectiveness drops sharply above 400 lines |

## Project structure

```
claude-deep-review/
├── .claude-plugin/
│   └── plugin.json                       # Plugin manifest
├── skills/
│   └── deep-review/
│       ├── SKILL.md                      # Main orchestration (7 phases)
│       ├── agents/
│       │   ├── bug-detector.md           # Correctness + error handling (Opus)
│       │   ├── security-reviewer.md      # Security vulnerabilities (Opus)
│       │   ├── cross-file-impact-analyzer.md  # Cross-file impact (Opus)
│       │   ├── test-analyzer.md          # Test coverage gaps (Sonnet)
│       │   ├── conventions-and-intent.md # Conventions + intent + comments (Sonnet)
│       │   ├── type-design-analyzer.md   # Type design (Sonnet, conditional)
│       │   └── code-simplifier.md        # Simplification (Opus, conditional)
│       └── references/
│           ├── false-positive-exclusions.md  # Unified false positive filter
│           ├── report-format.md          # Report template with permalinks
│           └── review-md-spec.md         # REVIEW.md configuration spec
└── README.md
```

## REVIEW.md configuration

Create a `REVIEW.md` in your repository root to customize review behavior:

```markdown
## Focus
- bugs
- security
- tests

## Skip
- "vendor/**"
- "**/*.generated.cs"

## Rules
- All database queries must use parameterized statements
- Public API endpoints must validate request body schema

## Severity Threshold
medium

## Confidence Threshold
75
```

See [references/review-md-spec.md](references/review-md-spec.md) for the full specification.

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) with a Max or Team plan (for subagent support)
- `gh` CLI (for GitHub) or `glab` CLI (for GitLab)
- Git

