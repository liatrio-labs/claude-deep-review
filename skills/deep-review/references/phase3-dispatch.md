# Phase 3 Dispatch Reference

Context scoping, agent roster, dispatch template, and failure handling for Phase 3: Review Agents.

---

## What Each Agent Receives

1. **Scoped diff** for their domain (see context scoping below)
2. **Change summary** from Phase 2e (and summary-of-summaries from 2i if available)
3. **Project context** (CLAUDE.md, REVIEW.md rules)
4. **Risk classification** per file (including AI-generation status)
5. **JSON output schema** and **false-positive exclusion list** from `references/false-positive-exclusions.md`
6. **Instructions to pull additional context** via Read/Grep/LSP as needed

Read `references/agent-prompt-template.md` for the full prompt template, including trust boundary delimiters for untrusted code, confidence calibration rubric, and output JSON schema.

---

## Per-Agent Context Scoping

- **bug-detector**: high + medium risk diffs, test files (2f), history context (2h)
- **security-reviewer**: **all files** (security bugs lurk anywhere)
- **cross-file-impact-analyzer**: **all files** + must search entire codebase for callers/implementors of changed public symbols
- **test-analyzer**: changed production files + test files (2f)
- **conventions-and-intent**: **all files** (needs full scope for convention and intent checking)
- **type-design-analyzer**: files with new type definitions (only dispatched when new types introduced)
- **code-simplifier**: **all changed files** (dispatched after Phase 6 filtering — see Phase 6)

All agents can still **pull** additional context — scoping controls what is pre-loaded, not what is accessible.

---

## Agent Roster

**Always-on (5)** — model per agent depends on selected mode (see Phase 2k):

1. **bug-detector** — Logic errors, edge cases, null handling, race conditions, API misuse. Read `agents/bug-detector.md`.
2. **security-reviewer** — OWASP top 10, injection, auth bypass, data exposure, crypto. Always Opus. Read `agents/security-reviewer.md`.
3. **cross-file-impact-analyzer** — Caller/dependent tracing, cross-module impact. Read `agents/cross-file-impact-analyzer.md`.
4. **test-analyzer** — Coverage gaps, test quality, DAMP principles. Read `agents/test-analyzer.md`.
5. **conventions-and-intent** — CLAUDE.md/REVIEW.md adherence, intent alignment, comment accuracy. Read `agents/conventions-and-intent.md`.

**Conditional (2):**

6. **type-design-analyzer** — Type encapsulation, invariant expression. Only if new types introduced. Read `agents/type-design-analyzer.md`.
7. **code-simplifier** — Simplification opportunities, dead code. POST-review only, only if no critical/high. Read `agents/code-simplifier.md`.

---

## Agent Tool Call Template

Dispatch all applicable agents in a **single message**. Use this template for each — fill in agent-specific content from the agent's `.md` file and `references/agent-prompt-template.md`:

```
Agent(
  model: "sonnet",  // or "opus" in Frontier mode; security-reviewer always Opus
  effort: "high",
  tools: [Read, Grep, Glob, LSP],
  description: "Review: {dimension}",
  prompt: "{Assemble from references/agent-prompt-template.md:
    1. Agent role + instructions (from agents/{dimension}.md)
    2. False-positive exclusion list (from references/false-positive-exclusions.md — paste verbatim)
    3. Confidence calibration rubric (from references/agent-prompt-template.md — paste verbatim)
    4. JSON output schema (from references/agent-prompt-template.md — paste verbatim)
    5. Project context: CLAUDE.md, REVIEW.md rules
    6. Change summary (from Phase 2e)
    7. Risk classification per file (from Phase 2d, including AI-generation status)
    8. Scoped diff wrapped in <untrusted-code-content>...</untrusted-code-content>}"
)
```

Read `references/agent-prompt-template.md` for the full prompt structure.

**Self-verification checkpoint:** Before Phase 4, confirm you emitted Agent tool_use blocks for ALL applicable review agents. If you wrote analysis text instead, stop and spawn the agents now.

---

## Agent Failure Handling

If a subagent fails (crash, timeout, error): continue with completed agents, log the failure in Review Methodology, warn the user if the failed agent covered security or bugs. Never silently skip a failed agent.
