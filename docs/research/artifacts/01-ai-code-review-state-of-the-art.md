# AI-driven code review: the state of the art in 2026

**The most effective AI code review systems decompose reviews by issue class — not by file — dispatching parallel specialized agents that each probe for different categories of bugs, then verify their own findings before surfacing them.** This architecture, pioneered by Anthropic's managed Code Review service and independently converged upon by Ellipsis, Greptile, and community implementations, consistently outperforms both monolithic single-pass reviews and naive per-file decomposition. The critical insight across all production systems is that a verification/falsification step after initial detection reduces false positives to under 1%, making AI review genuinely useful rather than noisy. What follows is a detailed technical synthesis of the tools, architectures, and techniques that represent the best of AI code review today — organized to be directly actionable for building a local PR review skill.

---

## Anthropic's Code Review service uses dimension-parallel agents, not file-parallel

Anthropic launched its managed Code Review service on **March 9, 2026** as a research preview for Team and Enterprise plans. It is the system Anthropic runs on nearly every internal PR. After extensive research, **there is no public evidence of a "sub-agent-per-file" architecture**. All official sources consistently describe an **agents-per-issue-class** model — dimension-based parallelism where each agent specializes in a different category of defect.

The managed service works as follows: when a PR opens, multiple specialized agents are dispatched in parallel on Anthropic's infrastructure. Each agent examines the diff and surrounding code from a different angle — some probe for data-handling errors, off-by-one conditions, and API misuse, while others perform **cross-file consistency checks** and reason about developer intent. Cat Wu (Anthropic's Head of Product for Claude Code) confirmed that "the agents often take the **entire codebase** into account to ensure that a change in one file doesn't create new bugs because a few files interact with each other in unexpected ways." A verification step then tests each hypothesis to filter false positives, and a final aggregation agent consolidates, deduplicates, and ranks findings by severity.

The results are striking: on large PRs (1,000+ lines), **84% receive findings averaging 7.5 issues**. On small PRs under 50 lines, 31% receive findings averaging 0.5 issues. **Less than 1% of findings are marked incorrect** by engineers. Average review time is ~20 minutes at a cost of $15–25 per review.

The **open-source code-review plugin** (authored by Boris Cherny, shipped in the Claude Code repo) reveals a more concrete architecture. It runs four parallel agents: two Sonnet-class agents audit CLAUDE.md compliance, one Opus-class agent performs bug detection focused exclusively on the diff, and one Opus-class agent analyzes git blame/history context. For each issue found by the bug and history agents, **parallel validation subagents** are launched to independently confirm findings. Each issue receives a confidence score from 0–100, with a threshold of **80** filtering low-confidence findings. Configuration is via hierarchical `CLAUDE.md` files (project context) and `REVIEW.md` files (review-specific rules).

---

## The multi-agent pattern that actually works: decompose by concern, verify aggressively

The strongest production systems and research papers converge on a specific multi-agent pattern: **decompose by review concern, provide cross-file context to each agent, verify findings independently, then aggregate**. This is fundamentally different from the per-file approach.

**Research foundations.** CodeAgent (Tang et al., EMNLP 2024) introduced a multi-agent system with six defined roles including a QA-Checker that monitors conversations for prompt drifting — a major challenge where agent reasoning strays from the review question. It achieved a **41% increase in vulnerability detection** versus prior state-of-the-art. The MARG framework (D'Arcy et al., 2024) used leader-worker-expert agent groups for scientific paper review, reducing generic comments from 60% to 29%. Its architecture — distributing text across workers with specialized experts and a coordinating leader — maps directly to code review.

**Production implementations.** Ellipsis (YC W24, SOC II Type I) runs "dozens of smaller agents instead of one large agent," each finding different issue types. Their key innovation is a **four-stage filtering pipeline**: deduplication → confidence filtering → hallucination detection (checking Evidence links) → comment normalization. They enable **model mixing** — running GPT-4o and Claude Sonnet simultaneously on different review aspects. Qodo (formerly CodiumAI) deploys **15+ specialized review agents** with multi-repository context analysis. HAMY's open-source implementation uses **9 parallel Claude Code subagents** covering test running, linting, code review, security, style, test quality, performance, dependency safety, and maintainability — reporting a ~75% useful suggestion rate, up from under 50% with non-parallelized approaches.

**Why not per-file?** The Augment Code benchmark found that file-level reviewers are "excellent for file-level quality, blind to architectural context." Cross-service scenarios, breaking changes across module boundaries, and architectural drift are consistently missed. Google DeepMind's December 2025 study found that unstructured multi-agent networks can **amplify errors up to 17.2x** compared to single-agent baselines, making careful orchestration essential. The winning architecture provides each concern-specialized agent with cross-file context via code search or RAG, rather than isolating agents to single files.

The five synthesis patterns observed across production systems are:

- **Orchestrator aggregation** (Anthropic, Ellipsis, HAMY): each agent returns structured findings independently; a final step deduplicates, ranks, and consolidates
- **Leader-worker communication** (MARG): leader broadcasts queries, workers respond, leader synthesizes
- **Sequential pipeline with QA** (CodeAgent): outputs flow through phases with supervisory monitoring
- **Filtering pipeline** (Ellipsis): raw outputs pass through dedup → confidence → hallucination → normalization filters
- **Shared-state blackboard** (LangGraph): agents read/write to a shared directed graph of state

---

## Open source tools: how the best systems actually work

### CodeRabbit — the sandbox-execution pioneer

CodeRabbit (13M+ PRs reviewed, 2M+ repos) uses a **webhook → queue → execution** architecture on Google Cloud Run, with 200+ instances at peak, each with 8 vCPUs and 32 GiB RAM. Its differentiator is **agentic execution**: the LLM generates and runs shell scripts and Python code inside a double-sandboxed environment (Cloud Run + Jailkit + cgroups) to verify its own findings against actual code behavior. It builds a **Codegraph** (lightweight dependency map of definitions and references) and a **semantic index** using LanceDB vector embeddings of functions, classes, tests, and prior PRs. For context engineering, it follows a **1:1 code-to-context ratio** — for every line of code under review, an equal weight of surrounding context is injected. The system runs 40+ integrated linters and security scanners, with AI-generated verification scripts checking findings post-generation. Pricing is flat at $24/developer/month.

### PR-Agent (Qodo) — the inspectable reference implementation

PR-Agent is the most important open-source tool for understanding AI code review internals, as its entire codebase — prompts, compression logic, and all tools — is Apache 2.0 licensed. Its key architectural decision: **one LLM call per tool**, keeping response time under 30 seconds. Its PR compression strategy is sophisticated: deletion-only hunks are removed, files are grouped by language and sorted by token count, then packed into prompts using tiktoken until reaching a 32K-token buffer threshold. Overflow files are listed by filename only. Critically, it uses **asymmetric context windows** — more context before a change than after, since preceding code is more crucial for understanding modifications. Context windows are dynamically adjusted based on enclosing functions and classes. PR-Agent reads `AGENTS.MD`, `QODO.MD`, and `CLAUDE.MD` files from repositories for project-specific guidance, and supports any LLM backend including GPT, Claude, Gemini, Deepseek, and local Ollama models.

### Greptile — the code-graph approach

Greptile's differentiator is **full codebase graph indexing**. On setup, it builds a complete graph containing every code element — files, functions, variables, classes, directories — and how they connect. This graph updates continuously as code changes. When reviewing a PR, it queries the graph to find all callers/callees of changed functions, identify patterns in similar functions, check consistency, and perform impact analysis. It uses "multi-hop investigation" — tracing dependencies, checking git history, and following leads across files autonomously. Review completion takes under 30 seconds after indexing. Its Genius API ($0.45/request) enables programmatic codebase queries for custom tooling.

### Other notable tools

**GitHub Copilot Code Review** (GA March 2026) now uses an **agentic tool-calling architecture** that gathers repository context dynamically. Claude and Codex are available as coding agents within Copilot via Agent HQ, enabling multi-agent comparison. **Ellipsis** (YC W24) can implement fixes, not just comment — it reads reviewer comments and generates commits with fixes. **Graphite Diamond** provides codebase-aware review integrated with Graphite's stacked PR platform. **CodeScene** takes a unique behavioral analysis approach with CodeHealth™ metrics correlating with defect density. **Kodus** is a fully open-source self-hostable AI review agent that learns from team feedback.

---

## Advanced techniques that matter most for a local skill

### Tree-sitter and Difftastic for structural understanding

Tree-sitter produces concrete syntax trees that preserve all tokens and map nodes back to exact byte positions, with critical error tolerance for incomplete code. **Difftastic** layers on top for grammar-aware diffing that ignores formatting and whitespace changes, dramatically reducing token footprint. Baz Reviewer chains these: raw diff → Difftastic (filter noise) → Tree-sitter (structural understanding). Tree-sitter's **incremental parsing** efficiently updates syntax trees as code changes. Symflower reported a **36x speedup** migrating from JavaParser to Tree-sitter. For a local tool, the `mcp-server-tree-sitter` project exposes tree-sitter AST operations via MCP, and Aider uses tree-sitter for linting after every LLM edit, displaying errors within their containing function/class context.

### LSP integration provides 900x faster cross-file navigation

Claude Code gained native LSP support in December 2025 (v2.0.74), delivering **50ms for find-references versus 45 seconds for text search**. LSP provides go-to-definition, find-references, hover information, and diagnostics — precisely the cross-file navigation that makes per-concern agents aware of architectural context. CodeAnt AI's approach illustrates the power: start from the changed function, use `goToDefinition` to jump to definitions, use `findReferences` to trace every call site across services, follow types through the system, and map the entire flow. The open-source **Serena** project provides an MCP server exposing LSP capabilities to LLMs, while **LSP-AI** offers a language server backend supporting multiple AI providers. For a local skill, combining LSP for precise semantic navigation with tree-sitter for fast syntactic parsing and ripgrep for text patterns creates a comprehensive code intelligence layer.

### RAG with AST-based chunking bridges the context gap

Qodo's enterprise RAG system for 10K+ repositories reveals key strategies: use **language-specific CST parsing** to create chunks at meaningful boundaries (function definitions, class boundaries), then retroactively re-add critical context (imports, class definitions) that was removed during splitting. Crucially, they generate **natural language descriptions** for each code chunk before embedding, because "code embeddings often don't capture the semantic meaning of code, especially for natural language queries." CodeRabbit uses LanceDB with auto-updating vectors triggered on code changes, embedding PRs, issues, and chat conversations alongside code. The academic RARe system (Retrieval-Augmented Reviewer) uses Dense Passage Retrieval to find similar code and past reviews, combining them in augmented prompts that outperform both pure retrieval and pure generation.

### Multi-pass review architecture

The highest-performing systems use distinct passes with different models and prompts. CodeRabbit uses Nemotron 3 Super (120B parameter MoE model) for fast context summarization, frontier models from OpenAI/Anthropic for bug finding, and verification agents for post-generation hallucination checking. Endor Labs' multi-pass approach — detection → triage → remediation — claims **95% false positive reduction**. The optimal local implementation chains: **summarize** (cheaper model, identify high-risk areas) → **review** (frontier model, focused on high-risk areas) → **verify** (second model, validate findings) → **aggregate** (deduplicate, rank, format).

### Handling large PRs through risk-based prioritization

For PRs exceeding 1,000 lines, the best systems classify changed files by risk level: high-risk files (auth, security, payment, data access, public APIs) receive full function-level review with expanded context including callers, callees, and related tests; medium-risk files get changed-function review with minimal context; low-risk files (tests, config, documentation) get quick pattern-matching scans. PR-Agent's token-aware packing with overflow handling is the most reusable implementation of this pattern. CodeRabbit's approach of using "level-appropriate prompts" that adjust review depth based on file complexity provides a practical framework: different complexity levels warrant different prompts and models.

---

## Claude Code's local review capabilities and extension points

Claude Code provides a robust foundation for building a local PR review skill. The `/review` built-in skill examines code changes for bugs, logic errors, edge cases, and style issues, accepting PR numbers, URLs, or reviewing local uncommitted changes. The **Agent tool** (formerly Task) enables spawning up to **10 concurrent subagents**, each with its own independent context window of up to 200K tokens. Built-in subagent types include Explore (read-only), Plan, and general-purpose, with custom subagents definable as markdown files.

Skills are defined as `SKILL.md` files with YAML frontmatter supporting `allowed-tools` restrictions, `model` specification (enabling multi-model review), `context: fork` for isolated execution, and dynamic content injection via `` !`command` `` syntax. The skill budget is limited to 2% of the context window (~42 skills with typical descriptions), and bash command output is truncated at **30,000 characters** with a 120-second default timeout.

For git integration, Claude Code has full access to `git diff`, `git log`, `git blame`, `git status`, and the `gh` CLI for GitHub operations. The `-w` flag supports isolated git worktrees for parallel work. Existing community extensions include `code-review-skill` (11+ languages, 9,500+ lines of guidelines, four-phase workflow), `claude-git-pr-skill` (GitHub PR reviews via `gh`), `claude-pr-reviewer` (GitHub Action), and `diffreview` (pipe any git diff range into Claude Code).

Key gaps in the current system that a custom skill could address: no structured review output format (JSON/SARIF), no incremental review capability, no persistent review memory across sessions, limited automatic fix pipeline, and no built-in risk-based file prioritization for large PRs.

---

## Synthesis: the best architecture for a local PR review skill

Drawing from all research findings, the optimal architecture for a local Claude Code PR review skill combines the most effective patterns:

**Core architecture: concern-specialized parallel agents with shared code intelligence.** Spawn 4–6 parallel subagents, each focused on a different review dimension: correctness/logic bugs (Opus-class), security vulnerabilities (specialized security prompts), CLAUDE.md/style compliance (Sonnet-class), test coverage adequacy, and cross-file impact analysis. Each agent receives the diff plus targeted context — not the entire codebase, but precisely the callers, callees, imported types, and related tests identified by LSP/tree-sitter analysis in a pre-processing step.

**Pre-processing pipeline.** Before dispatching agents, a lightweight pre-processing step should: (1) parse the diff to identify changed files and symbols using tree-sitter, (2) classify files by risk level for prioritization, (3) use LSP find-references and go-to-definition to build a dependency context for each changed file, (4) apply PR-Agent's asymmetric context expansion (more context before changes than after), and (5) for large PRs, compress lower-priority files to filename-only listings using token-aware packing.

**Post-processing: verify then aggregate.** Following Anthropic's pattern, launch parallel validation subagents for each finding — each attempts to disprove the finding by examining the actual code behavior. Apply confidence scoring (0–100 scale, threshold of 80) and severity classification. A final aggregation step deduplicates, ranks by severity, and produces structured output.

**Configuration via REVIEW.md.** Support a hierarchical `REVIEW.md` configuration file (repository root, with directory-level overrides) that specifies: review focus areas, files/patterns to skip, custom rules in natural language, severity thresholds, and which review dimensions to enable.

**Concrete tool chain for each agent:**

- Tree-sitter (via `mcp-server-tree-sitter` or direct integration) for AST parsing and symbol extraction
- LSP for cross-file navigation (go-to-definition, find-references)
- `git diff`, `git log`, `git blame` via bash for change and history context
- `gh pr diff`, `gh pr view` for PR metadata when reviewing remote PRs
- Ripgrep for text pattern searches
- Difftastic for noise-filtered structural diffs

**Model routing for cost efficiency.** Use Opus-class models for complex reasoning tasks (bug detection, security analysis), Sonnet-class for style/compliance checks and validation, and Haiku-class for initial summarization and file classification. This mirrors the production patterns at Anthropic (open-source plugin), CodeRabbit (multi-model orchestration), and HAMY's subagent implementation.

**Feedback loop.** Store dismissed findings with embeddings in a local vector store (or simple JSON file with semantic similarity matching). On subsequent reviews, check new findings against dismissed history to avoid repeating false positives — the pattern used by Greptile, CodeRabbit, and Ellipsis without requiring fine-tuning.

This architecture should deliver review quality approaching the managed $15–25/review service while running entirely locally under a Max plan user's control, with the flexibility to customize review dimensions, models, and thresholds to match project needs.
