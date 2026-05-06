# How AI code review systems engineer context windows for massive PRs

**AI code review tools face a fundamental paradox when handling large pull requests: models need context to understand code, but too much context degrades their performance.** The leading systems — PR-Agent, CodeRabbit, and others — have converged on surprisingly different architectural solutions, from token-aware compression with asymmetric context windows to recursive summarization and multi-agent pipelines. Research confirms the stakes are high: every model tested shows measurable performance degradation as context grows, with drops of 13–85% documented even when relevant information is perfectly retrievable. No tool has solved this problem completely — even the best achieves only a **60.1% F1 score** on code review benchmarks — but their engineering approaches reveal sophisticated tradeoffs worth understanding in detail.

## PR-Agent's two-tier token budgeting compresses diffs with surgical precision

PR-Agent (now Qodo Merge) implements its compression strategy primarily in `pr_agent/algo/pr_processing.py`, with support from `token_handler.py` and `git_patch_processing.py`. The default token ceiling is **32,000 tokens** (`max_model_tokens` in `configuration.toml`), regardless of the underlying model's actual capacity, with per-model overrides available in the `MAX_TOKENS` dictionary.

The core algorithm in `generate_full_patch()` uses a **two-tier threshold system** with distinct hard and soft buffer constants. As it iterates through files sorted by language priority and importance:

- **Soft threshold check**: If adding the next file's patch would exceed `max_model_tokens - OUTPUT_BUFFER_TOKENS_SOFT_THRESHOLD`, that file is deferred to a "remaining files" list for potential multi-chunk handling, but iteration continues to check whether smaller files might still fit.
- **Hard threshold check**: If total tokens exceed `max_model_tokens - OUTPUT_BUFFER_TOKENS_HARD_THRESHOLD`, all remaining files are skipped entirely — an absolute ceiling that prevents prompt overflow.

Files that survive budgeting get their full patch content included in the format `## File: 'filename'\n\n{patch_content}`. Files that don't fit are reduced to **filename-only listings** in the prompt. Deleted files receive only their filename and deletion status. The `TokenHandler` class applies a **30% safety margin** (`model_token_count_estimate_factor = 0.3`) when counting tokens, deliberately overestimating to prevent silent truncation.

For the `/improve` tool specifically, large PRs are split into **multiple LLM calls** via `get_pr_multi_diffs()`, each chunk staying within the token budget. Each chunk generates up to `num_code_suggestions_per_chunk` suggestions (default: 3), so suggestion count scales with PR size. PRs under roughly **600 lines of code** fit in a single call; beyond that, chunking activates. Log messages from production confirm this pipeline: `"Tokens: 97419, total tokens over limit: 32000, pruning diff"` appears when compression kicks in.

## Asymmetric context windows reflect a deliberate design philosophy

PR-Agent's context extension around each diff hunk is **intentionally asymmetric**, documented in their official codebase and design rationale. The configuration defaults in `configuration.toml` specify:

| Parameter | Default | Effect |
|---|---|---|
| `patch_extra_lines_before` | 3 | Added to unified diff's standard 3 = **6 total lines before** |
| `patch_extra_lines_after` | 1 | Added to unified diff's standard 3 = **4 total lines after** |
| `max_extra_lines_before_dynamic_context` | 8 | Maximum upward scan for enclosing function/class |
| `allow_dynamic_context` | true | Enables function/class detection expansion |

The rationale is stated explicitly in PR-Agent's documentation: *"The context preceding a code change is typically more crucial for understanding the modification than the context following it."* This yields a **3:1 asymmetry** in extra lines (before vs. after), or roughly **1.5:1** in total context lines including the unified diff baseline.

Beyond this static allocation, **dynamic context expansion** scans upward from each hunk looking for enclosing function or class definitions. This uses **heuristic/regex-based detection** — not AST parsing — searching for language-specific patterns like `def`, `class`, and function declarations. The heuristic approach was chosen deliberately for performance and language-agnostic compatibility across PR-Agent's supported languages. The upward scan is capped at `max_extra_lines_before_dynamic_context` (8 lines beyond the static extra lines) to prevent unbounded expansion. Files with extensions in `patch_extension_skip_types` (`.md`, `.txt`) skip dynamic context entirely.

The documentation acknowledges the tension directly: *"Enhanced context allows the model to better comprehend and localize the code changes"* but *"excessive context may overwhelm the model with extraneous information, creating a 'needle in a haystack' scenario."* Users can override all these values — one documented configuration uses symmetric 4/4 lines with dynamic context of 10.

## CodeRabbit's 1:1 ratio measures token composition, not line counts

CodeRabbit's frequently cited "1:1 code-to-context ratio" is widely misunderstood. It is **not** a line-for-line mapping of diff to surrounding code. It is a **token-level metric** describing prompt composition: roughly **50% of tokens are actual code under review**, and **50% are contextual signals** drawn from a rich set of non-code sources. As their engineering blog states: *"For every line of code under review, we're feeding the LLMs an equal weight of surrounding context. That includes key things like user intent, file dependencies, and expected outcome."*

That contextual half encompasses PR metadata, linked issue tracker tickets (Jira, Linear, GitHub Issues), **code dependency graph analysis** (rebuilt fresh for each review), semantic code embeddings of functions and classes, results from **40+ linters and SAST tools**, historical learnings from past reviews stored in a vector database, web query results for API documentation, imported coding guidelines, and MCP server integrations. The ratio is described as an average that varies per review.

CodeRabbit's architecture for handling large PRs is fundamentally different from PR-Agent's compression approach. Rather than fitting everything into one prompt, it uses **file-level concurrent processing** — each file in a PR is summarized and reviewed in parallel, then results are synthesized. For cross-file understanding, a **recursive summarization strategy** builds hierarchical context: each file diff is summarized individually, then a "summary of summaries" is generated and incrementally updated as commits arrive. This summary is persisted as a hidden comment on the PR itself and provided as context when reviewing each individual file.

The multi-stage pipeline routes tasks to different model tiers. Cheaper, faster models (NVIDIA Nemotron 3 Nano, GPT-4.1) handle context gathering and summarization. **Frontier reasoning models** (Claude Opus 4, GPT-5.x-Codex, o3/o4-mini) perform the actual deep code review. A verification stage runs generated scripts in isolated sandboxes to validate review comments, filtering hallucinations and low-value feedback before posting. Infrastructure scales elastically — during peak hours, over **200 Cloud Run instances** process reviews concurrently, each with 8 vCPUs and 32 GiB memory.

## Hierarchical approaches emerge as the dominant pattern for 50+ file PRs

The most architecturally sophisticated approach to massive PRs comes from **Salesforce's Prizm** system, which implements explicit hierarchical intent reconstruction. It first identifies broad conceptual groupings across changed files, refines them through semantic consolidation, then uses a **graph-based merge phase** that analyzes dependencies, file overlap, and conceptual similarity. Related changes — such as backend logic paired with corresponding UI updates — are reviewed together even when they span disparate directories. Progressive context disclosure then directs reviewer attention to security-sensitive changes and architectural decisions first.

**Augment Code** describes a similar 4-stage pipeline: estimate total scope across changed files, group related files within processing limits, reserve capacity for system prompts and cross-reference context, then run a synthesis pass combining insights from individual analyses. They claim to handle **400,000+ files** using semantic dependency graph analysis.

**cubic** takes a different multi-agent approach with specialized micro-agents (Planner, Security, Duplication, Editorial, Filtering) that run in parallel. Their key architectural insight was transitioning from **context-pushing to context-pulling** — rather than stuffing large context into agent prompts, agents request specific context as needed, yielding **51% fewer false positives** across hundreds of real PRs.

**Graphite** sidesteps the problem entirely through its stacked PR workflow, breaking large changes into smaller dependent PRs reviewed independently. **GitHub Copilot** uses a 192K token context window but has no documented chunking strategy — it reviews what fits and notes when files were skipped, with reports of consistent crashes on 1000+ file PRs. PR-Agent's open-source version uses its single-call compression for `/review` and multi-chunk processing only for `/improve`, though the commercial Qodo Merge 2.0 has moved to a multi-agent architecture where each specialized agent operates with its own dedicated context.

## Research quantifies severe quality degradation from context growth

While no study directly measures code review quality as a function of PR compression ratio, converging evidence from multiple research programs paints a clear picture. The **"Context Length Alone Hurts"** paper (arXiv 2510.05381) tested five LLMs on code generation tasks and found **13.9–85% performance degradation** as input length increased — critically, even when models could perfectly retrieve all relevant information. On HumanEval, Mistral showed up to a **17% drop** and Llama a **20% drop** under 30K space tokens. The degradation is caused by context length itself interfering with reasoning, not by retrieval failure.

The foundational **"Lost in the Middle"** research from Stanford documented a U-shaped performance curve where models perform best with relevant information at the beginning or end of context, with **over 30% accuracy degradation** when information sits in the middle. GPT-3.5-Turbo's performance with mid-positioned information was actually *lower* than its closed-book performance — meaning added context actively hurt. Chroma Research's **"Context Rot"** evaluation of 18 LLMs confirmed universal degradation across every model tested, finding that coherent text creates stronger recency bias than shuffled text, and that distractors amplify performance loss at longer lengths.

The **RULER benchmark** from NVIDIA provides the most granular measurements: GPT-4 dropped from 96.6 at 4K tokens to 81.2 at 128K (a 15.4-point decline, the best result), while Mixtral-8x22B showed near-random results at 128K with a **63.9-point drop**. Only 4 of 10 models could effectively handle even 32K tokens on complex tasks despite claiming much larger context windows.

Applied to code review specifically, the **SWR-Bench** evaluation of 1,000 manually verified PRs found that even with full project context available, current LLM-based review systems "generally underperform." Multi-review aggregation boosted F1 by up to **43.67%**, strongly suggesting single-pass reviews miss substantial issues. An industrial study of PR-Agent found that while **73.8% of automated comments were resolved** by developers, PR closure duration actually *increased* from 5h52m to 8h20m due to faulty reviews and irrelevant comments. Atlassian's RovoDev deployment across 2,000+ repositories achieved a **38.7% code resolution rate** versus 44.45% for human reviewers, with engineers specifically citing "lack of holistic code understanding" as the primary limitation.

## Conclusion

The engineering of context windows for large PRs reveals a field in active tension between two empirically validated principles: **models need surrounding context to understand code changes**, but **every additional token of context measurably degrades reasoning performance**. PR-Agent's response — a 32K default ceiling with asymmetric context favoring pre-change lines, heuristic function detection, and two-tier token budgeting — represents a pragmatic, tunable compression approach. CodeRabbit's strategy of concurrent file-level processing with recursive summarization avoids the single-prompt bottleneck entirely, trading cross-file coherence for per-file depth. The most advanced systems (Salesforce Prizm, Qodo 2.0, cubic) have converged on multi-agent architectures where specialized agents each receive focused context rather than one model receiving everything.

The research gap is notable: **no published study systematically varies context budget while holding code review tasks constant**. The closest evidence — RULER, Context Rot, and Lost in the Middle — consistently shows 15–64 point accuracy drops as context scales from 4K to 128K tokens. For a 5,000-line PR compressed to fit a 32K window, these findings suggest substantial review degradation is inevitable with single-pass approaches, which is precisely why the industry is moving toward multi-pass, multi-agent, and hierarchical architectures that keep each individual prompt focused and within the performance sweet spot.
