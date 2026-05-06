# How AI code review tools actually fight false positives

**The honest picture is messier than vendor claims suggest.** Every production AI code review system—Anthropic Code Review, CodeRabbit, Ellipsis, and Qodo—uses multi-agent architectures with separate generation and filtering stages, but none employs formal statistical calibration techniques from the academic literature. Confidence thresholds are tuned empirically through internal usage, not rigorous methodology. The only truly independent benchmark (Martian Code Review Bench, covering ~300,000 PRs) shows the best tools achieving roughly **50% precision**—meaning about half of all posted comments lead to developer action. Cross-model verification offers modest gains in theory, but frontier LLMs share correlated errors ~60% of the time even across model families, undermining the core assumption. The most effective false positive reduction comes not from LLM-on-LLM verification but from grounding AI findings in deterministic tools: linters, AST analysis, and executable verification scripts.

---

## Confidence scoring relies on LLM self-assessment, not formal calibration

All four systems generate confidence scores through some form of LLM self-evaluation—the model rates its own certainty—rather than using established calibration techniques like Platt scaling or temperature scaling that academic research shows dramatically improve reliability.

**Anthropic Code Review** is the most transparent. It runs **4–5 parallel Sonnet agents**, each examining a PR from a different angle (CLAUDE.md compliance, bug detection, git blame context, PR comment verification). After these agents submit findings, separate **Haiku "judge" agents** score each issue on a **0–100 scale** with a default threshold of **80**. The rubric is explicit: 0 means "not confident, false positive," 50 means "real but minor," 100 means "absolutely certain." Anything below 80 gets suppressed before reaching the developer. Anthropic reports a **<1% developer rejection rate** from months of internal use, though this metric means developers actively dismissed fewer than 1% of surviving comments—a narrow definition that doesn't capture ignored comments. Notably, when Qodo's team ran Claude Code against its own PR, the judge filtered 7 of 8 findings below 80, including security-relevant issues like path validation bypass—raising questions about over-filtering.

**Ellipsis** published actual pseudocode showing a `ConfidenceFilter` class with a per-customer configurable threshold. Their **default is 0.7**, with **0.9 recommended for noisy codebases**. Confidence scores are assigned by the generating LLM during comment creation. Ellipsis is the most architecturally transparent system, openly using multiple model families simultaneously—GPT-4o and Claude Sonnet—with the philosophy "why choose when you can have both?"

**Qodo's** open-source PR-Agent uses a **0–10 scale** with a default threshold of 0 (no filtering), and documentation warns not to set it above 8 to avoid clipping relevant suggestions. Their proprietary Qodo 2.0 adds a separate "judge agent" that resolves conflicts between specialized review agents, removes duplicates, and filters low-signal results. Qodo frames this as a "responsibility router" rather than a binary filter, using a gradient of severity rather than a hard cutoff.

**CodeRabbit** takes a fundamentally different approach: **no numeric confidence scores at all.** Instead of thresholds, they use verification agents that generate shell and Python scripts (grep, ast-grep) to confirm assumptions before posting comments, combined with 40+ integrated linters and a learnings database that stores developer feedback as vector embeddings to suppress previously-rejected comment types.

The academic literature confirms why self-assessed confidence is problematic. Research by Xiong et al. (ICLR 2024) shows LLMs are **highly overconfident**, with verbalized confidence predominantly clustering in the **80–100% range** in multiples of 5—mimicking human overconfidence patterns. Spiess et al. (ICSE 2025) demonstrated that Platt scaling significantly improves LLM confidence calibration for code tasks, yet no production system has adopted it. This explains why Anthropic's threshold sits at 80: the LLM's "50% confident" likely corresponds to much lower actual accuracy.

---

## Cross-model verification helps less than expected for frontier models

The theoretical basis for using different LLMs to check each other's work is error decorrelation: different architectures trained on different data should make partially independent mistakes. The empirical reality is more nuanced.

The most important finding comes from Kim et al. (ICML 2025), who evaluated **350+ LLMs** across major benchmarks. Their central result: **models agree on the wrong answer roughly 60% of the time when both err**, and critically, **larger, more accurate models have highly correlated errors even across distinct architectures and providers**. This means swapping Claude for GPT as a verifier provides less decorrelation than expected precisely for the frontier models that production code review systems use.

Panel-based approaches do show improvement. Verga et al. (2024, Cohere) found a panel of three smaller models from **disjoint families** (Command R, Claude Haiku, GPT-3.5) outperformed a single GPT-4 judge, achieving **Cohen's Kappa of 0.763 vs. 0.627** with human judgments—and at 7x lower cost. The "Wisdom and Delusion of LLM Ensembles" paper (2024) studied 10 LLMs from 5 families across software engineering benchmarks, finding that **diversity-based selection** realizes up to 95% of theoretical ensemble potential, while naive consensus voting falls into a "popularity trap" that amplifies shared errors.

A striking counterpoint comes from Song (2026), who found that **context isolation matters more than model identity**. Cross-Context Review—reviewing in a fresh session without the original production context—achieved F1 of **28.6% vs. 24.6%** for same-session review. When they tried multi-stage verification with shared context (Worker→Verifier→Director), they got **100% sycophantic confirmation**—the verifier simply agreed with every finding.

**No published paper directly studies cross-model verification specifically for code review false positive reduction.** The closest analog is Microsoft's CORE system (FSE 2024), which uses a Proposer LLM to generate code fixes and a separate Ranker LLM to evaluate them, reducing rejection rates to 47.55% when surfacing only "strongly accepted" candidates. The strongest evidence suggests **hybrid approaches—combining LLM review with deterministic tools—provide far more false positive reduction than LLM-only cross-model verification.**

---

## Ellipsis's four-stage pipeline runs confidence first, not deduplication

Ellipsis co-founder Nick Bradford published the most detailed technical description of any AI code review filtering pipeline, including working pseudocode. The actual pipeline order—confirmed from the published code—is **ConfidenceFilter → DedupeFilter → HallucinationFilter → Comment Editing**, not the deduplication-first order sometimes described.

**Stage 1: Confidence Filter** applies the simplest check first, dropping any comment whose LLM-assigned confidence score falls below the customer's configured threshold (default 0.7). This is the coarsest filter, removing findings the model itself wasn't sure about.

**Stage 2: Deduplication Filter** removes overlapping comments that arise because multiple specialized generators run in parallel, potentially using different models. Two generators might independently flag the same issue with different phrasing. The blog explicitly notes this is "especially important given the Generators can sometimes overlap." The deduplication mechanism likely uses semantic similarity rather than exact matching, though the specific algorithm isn't documented.

**Stage 3: Hallucination Filter** (called "Logical Correctness filter(s)"—notably plural) is the most sophisticated stage. Each comment generator attaches **Evidence**—links to specific code snippets—to every finding. The hallucination filter cross-checks whether the comment's claims are actually supported by the cited evidence. Both generation and filtering leverage a shared **Code Search subagent** that can actively search the codebase to verify claims. Bradford notes they "start to see noticeably more hallucinations when more than half the context is filled," making this stage critical for large PRs.

**Stage 4: Comment Editing** normalizes rather than filters. It corrects line number errors (LLMs are "very bad at correctly identifying column numbers and often off by one on line numbers"), fixes inline code suggestion formatting, and applies fuzzy matching to the closest symbol name. This stage modifies comments rather than removing them.

An additional mechanism sits alongside the pipeline: **feedback-based filtering** using embedding search over historical thumbs-up/down reactions. When a developer downvotes a comment, similar future comments get suppressed. Bradford emphasizes this approach over fine-tuning because "feedback is reflected almost immediately in agent behavior." Importantly, **filtered comments and their reasoning are included in the output for transparency**—developers can see what was suppressed and why.

No quantitative effectiveness metrics are published for individual stages. The ZenML analysis explicitly confirms: "No quantitative results are provided—claims about 'significantly reduced false positive rates' are not backed by specific numbers."

---

## CodeRabbit's sandbox runs analysis scripts, not application code

CodeRabbit's "sandbox execution" is frequently mischaracterized. **It does not compile, build, or run the user's application code.** Instead, it clones the repository into a secure container and executes static analysis tools and LLM-generated verification scripts.

The sandbox runs on **Google Cloud Run** with 8 vCPUs and 32 GiB memory per instance, scaling to 200+ instances during peak load. Each review takes **10–20 minutes**. The architecture uses three layers of isolation: Cloud Run's gVisor kernel plus microVM, Jailkit for process isolation within containers, and cgroups for privilege restriction. A January 2025 security incident (discovered by Kudelski Security) where Rubocop ran outside the sandbox and enabled RCE via malicious config files prompted a comprehensive security overhaul confirming these tools do execute real code.

The verification pipeline works in three steps. First, the LLM generates review comments based on the diff plus assembled context. Second, **verification agents generate shell and Python scripts**—using tools like grep, ast-grep, ripgrep, and cat—to confirm assumptions before posting. Third, low-value feedback is filtered out. The official documentation is explicit about limitations: the sandbox **cannot run test suites** (dependencies aren't fully installed), **cannot access build artifacts** (build steps aren't executed), and **cannot execute arbitrary repository code**.

The 40+ integrated linters and SAST scanners (ESLint, Ruff, Rubocop, Biome, Gitleaks, ShellCheck, and others) run with zero-touch configuration and their results are validated by the verification agent. CodeRabbit combines AST-Grep with RAG to provide deterministic grounding—AST patterns extract concrete code structures that suppress hallucination.

**No benchmarks exist comparing sandbox verification effectiveness against static analysis alone.** The closest available data is CodeRabbit's overall performance on the Martian Code Review Bench: **F1 of 51.2%**, with precision of 49.2% and recall of 53.5% across approximately 300,000 PRs—ranking first in F1 among 13+ tools evaluated.

---

## False positive rates cluster around 50%, with no standardized taxonomy

The honest assessment is that published false positive rates vary wildly depending on who measures them and how. **No standardized false positive taxonomy exists** for AI code review, and most benchmarks are vendor-produced.

The **Martian Code Review Bench** (February 2026) provides the strongest independent data. Across its online benchmark measuring whether developers actually acted on comments, **CodeRabbit achieved 49.2% precision** (roughly half of comments led to code changes), **Graphite achieved 75.0% precision** but with only 8.8% recall (extremely conservative), and Qodo ranked second overall. The offline benchmark using 50 curated PRs with human-verified golden comments showed different rankings, highlighting how methodology shapes results. The key insight: tools optimizing for precision sacrifice recall, and vice versa.

**Anthropic's claimed <1% false positive rate** requires careful interpretation. Per their representative, this means fewer than 1% of findings are "actively resolved without fixing"—engineers explicitly dismissing a comment as wrong. This excludes comments that are simply ignored, and reflects Anthropic's own engineering culture on their own codebase. When Checkmarx Zero researchers independently tested Claude on a production codebase, only **2 of 8 identified vulnerabilities were true positives**. The ProjectDiscovery team found Claude Code produced 41 verified issues alongside **24 false positives** (~37% false positive rate) when benchmarked against runtime verification.

Qodo's own benchmark, using 100 real PRs with 580 injected defects, showed their best configuration achieving **F1 of 60.1%**—the highest among 8 tools tested. Their analysis across competitors revealed a consistent pattern: "Very high precision at the cost of extremely low recall"—most tools are conservative to avoid false positives but miss subtle bugs.

The breakdown of false positive types, synthesized from multiple sources, reveals five primary categories:

- **Hallucinated code references**: A study across 16 LLMs and 576,000 code samples found **19.7% of package recommendations were fabricated**, with open-source models hallucinating at 21.7% versus 5.2% for commercial models. These are findings referencing non-existent functions, APIs, or code constructs.
- **Pre-existing issues flagged as new**: Anthropic addresses this explicitly with a **purple severity label** distinguishing legacy bugs from PR-introduced issues. Other tools lack this distinction, and the Martian benchmark's offline set penalizes tools for finding real pre-existing issues not in the gold set.
- **Intentional changes flagged as bugs**: LLMs flag deliberate design choices—timeout values, helper function conventions, error handling patterns—lacking system-level awareness of why code is written a certain way.
- **Linter-catchable issues**: Many AI tools flag formatting, naming conventions, and unused imports that traditional linters already catch. Anthropic explicitly decided to "focus purely on logic errors" to avoid this category entirely.
- **Context-window degradation**: Tencent's enterprise study found LLMs are "significantly less effective at mitigating false positives in cases involving long code contexts," with failure cases averaging **95.6 lines longer** than successes.

Developer trust reflects these challenges. Stack Overflow's survey shows trust in AI accuracy **declined from 43% to 33%** between 2024 and 2025, with 46% of developers actively distrusting AI output. Sonar's State of Code 2025 found 96% of developers express doubts about AI-generated code reliability, even as 72% use AI coding tools daily.

---

## Conclusion: deterministic grounding beats LLM-on-LLM verification

Three patterns emerge clearly from the evidence. First, **every system uses multi-agent generation with separate filtering**, but the filtering mechanisms differ fundamentally—Anthropic uses numeric thresholds, CodeRabbit uses executable verification scripts, Ellipsis uses evidence-linked hallucination detection, and Qodo uses gradient severity routing. Second, **formal calibration techniques from the literature remain unadopted** despite strong evidence they would help; all systems rely on LLM self-assessment that academic research shows is systematically overconfident. Third, the most effective false positive reduction comes from **grounding AI findings in deterministic evidence**—linters, AST analysis, executable verification scripts, and runtime testing—rather than from having one LLM check another's work, since frontier models share correlated blind spots roughly 60% of the time.

The field's fundamental tension remains unresolved: **precision and recall trade off sharply**, with no system achieving both high detection rates and low noise. Anthropic optimizes aggressively for precision (filtering most findings), Qodo prioritizes recall (surfacing more with severity gradients), and CodeRabbit sits in the middle. The claimed "5–15% false positive rate" from vendor marketing materials bears little resemblance to the ~50% noise rates measured by independent benchmarks. Until standardized evaluation frameworks mature, the real false positive rate of any AI code review tool depends heavily on the codebase, the team's tolerance for noise, and what counts as "false."
