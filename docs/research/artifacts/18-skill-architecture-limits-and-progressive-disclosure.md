# Claude Code skills: architecture, limits, and design patterns for scale

**The 500-line limit on Claude Code skill files is a soft guideline, not a hard technical cap — but the real constraints run deeper than line counts.** Anthropic's official documentation recommends keeping SKILL.md bodies under 500 lines "for optimal performance," yet no enforcement mechanism truncates or rejects longer files. The actual bottlenecks are a **2% context-window metadata budget** that gates skill discovery, **attention degradation** that erodes instruction compliance linearly with length, and **context competition** where every loaded skill token crowds out conversation history. Production plugins like Anthropic's code review and obra's superpowers solve this through progressive disclosure, reference file architectures, and multi-agent orchestration — patterns that provide a clear blueprint for building complex skills that far exceed 500 lines of total instruction content.

---

## The 500-line limit is real guidance, not a wall

Anthropic's official best-practices documentation states: *"Keep SKILL.md body under 500 lines for optimal performance. If your content exceeds this, split it into separate files using the progressive disclosure patterns described earlier."* The same recommendation appears in Anthropic's skill-creator reference skill and the Claude Code docs site. It is framed as an optimization target, not a technical constraint.

**No enforcement exists.** There is no validation step that rejects, truncates, or warns about oversized SKILL.md files. When a skill is invoked, the full SKILL.md body — regardless of length — gets injected into the conversation as a hidden message via an `isMeta: true` flag. The system simply reads the file and passes it through. The superpowers plugin's writing-skills SKILL.md runs to approximately **655 lines** (22,463 bytes, ~5,600 tokens) and functions without errors.

The hard-enforced limits that do exist are narrower: skill **names** max at 64 characters, **descriptions** at 1,024 characters, and neither may contain XML tags or the reserved words "anthropic" or "claude." These are validated and will produce errors if violated.

## Three constraints actually govern skill size

The line count guideline proxies for three deeper constraints, each with distinct mechanisms and implications.

**First: the metadata discovery budget.** At session start, Claude Code builds an `<available_skills>` XML block containing the name, description, and location of every discoverable skill. This block is embedded in the Skill tool's description field and has a **hard character budget of 2% of the context window**, with a 16,000-character fallback. Each skill consumes approximately its description length plus ~109 characters of XML overhead. When skills exceed this budget, the system silently truncates: GitHub Issue #13099 documented cases where Claude displayed "Showing 42 of 63 skills due to token limits," rendering remaining skills **completely invisible and uninvocable**. This budget can be overridden via the `SLASH_COMMAND_TOOL_CHAR_BUDGET` environment variable.

**Second: context window competition.** A real-world `/context` readout shows the allocation breakdown: system prompt consumes ~5.9K tokens (0.6%), system tools ~9.1K (0.9%), memory files ~11K (1.1%), and skills metadata ~1.2K (0.1%). Once a skill is invoked, its full body enters the messages array and competes directly with conversation history for the remaining context. Anthropic's documentation describes the context window as a *"public good"* — every skill token displaces a conversation token. A 5,600-token skill body (like superpowers' writing-skills) is modest in a 200K window, but in extended sessions with accumulated context, it becomes significant.

**Third: attention and instruction-following degradation.** This is the constraint that makes 500 lines a meaningful guideline rather than arbitrary conservatism, and it deserves detailed examination.

## Research quantifies exactly how length degrades compliance

Multiple peer-reviewed studies converge on a clear picture of how instruction-following deteriorates with input length, and the implications for skill design are precise.

The **IFScale benchmark** (Distyl AI, July 2025) tested 20 state-of-the-art models across up to 500 keyword-inclusion instructions. Claude Sonnet 4 exhibited **linear decay** — steady, proportional decline in instruction-following accuracy from the first instruction onward, with no safe plateau. Even the best frontier reasoning models achieved only **68% accuracy at 500 instructions** and maintained near-perfect performance only through approximately **150 instructions**. Critically, the ~50 instructions already in Claude Code's system prompt consume roughly **25–33% of that reliable instruction-following budget** before any CLAUDE.md, skill content, or user messages enter the picture.

The **"Lost in the Middle" paper** (Liu et al., TACL 2024) established the **U-shaped attention curve**: LLMs perform best when relevant information sits at the beginning or end of input, with significant degradation for information in the middle. This held across all seven models tested, including Claude 1.3 and GPT-4. Anthropic's own long-context research confirmed this and recommended *"placing instructions at the end of the prompt"* for maximum recall.

However, the **IBM "Boosting Instruction Following at Scale" paper** (2025) offered an important correction: at scale, the primary driver of instruction-following failure is not positional but rather **soft conflicts** — tensions between instructions that make simultaneous satisfaction increasingly difficult. As instruction count grows, adding even one conflicting instruction degrades compliance across *all* instructions, not just nearby ones.

Perhaps most alarming for skill designers, **Levy, Jacoby & Goldberg (ACL 2024)** showed that reasoning performance degrades at approximately **3,000 tokens of input** — far below any technical maximum — regardless of whether the additional tokens contain useful information or padding. Chain-of-thought prompting does not mitigate this effect.

These findings, taken together, suggest the 500-line guideline is if anything generous. A SKILL.md at 500 lines likely contains **2,000–3,000 tokens**, placing it right at the threshold where reasoning degradation begins. The optimal strategy is not to pack SKILL.md to its maximum but to minimize it aggressively and offload everything possible to on-demand reference files.

## How the progressive disclosure architecture actually works

Claude Code's skill loading system implements a three-level progressive disclosure model that is central to understanding how complex skills should be built.

**Level 1 — Metadata (always loaded, ~100 tokens per skill).** At startup, only the YAML frontmatter's `name` and `description` fields are extracted from all discovered SKILL.md files. These populate the `<available_skills>` block in the Skill tool's description. Crucially, skills do **not** live in the system prompt itself — reverse-engineering by multiple independent researchers confirmed they reside in the `tools` array as part of the Skill tool's description field.

**Level 2 — Instructions (loaded on demand, target under 5K tokens).** When a user invokes a skill via `/skill-name` or Claude determines a skill is relevant, the system reads the full SKILL.md body from the filesystem and injects it as a hidden conversation message. The SKILL.md body enters the context only at this point — not before.

**Level 3 — Resources (loaded as needed, effectively unlimited).** Supporting files in the skill directory — reference documents, templates, examples, scripts — are never loaded automatically. The SKILL.md must explicitly instruct Claude to read them when relevant. Scripts are **executed** via bash, meaning only their output enters context, not their source code. This level has no practical token limit since unused files consume zero tokens.

This architecture means that a skill's total instruction content can vastly exceed 500 lines, so long as the SKILL.md itself stays concise and delegates detail to reference files. The constraint shifts from "how much can you write" to "how well can you organize."

## Production patterns for skills exceeding a single file

Four distinct architectural patterns emerge from examining production-grade Claude Code skills and plugins.

**The reference file pattern** is the most common and officially recommended approach. The SKILL.md serves as an orchestrator containing core workflow logic and explicit pointers to reference files. Anthropic's official documentation provides the canonical structure:

```
my-skill/
├── SKILL.md              # Core instructions (<500 lines)
├── references/
│   ├── aws.md            # Loaded only for AWS tasks
│   ├── gcp.md            # Zero tokens until needed
│   └── azure.md
├── scripts/
│   └── analyze.py        # Executed, never loaded into context
└── examples/
    └── sample.md
```

The superpowers plugin's writing-skills skill exemplifies this pattern — its 655-line SKILL.md references `anthropic-best-practices.md`, `persuasion-principles.md`, `testing-skills-with-subagents.md` (~385 lines), and example files that are only loaded when Claude needs them during execution. Superpowers explicitly avoids the `@` syntax for cross-references because it force-loads files immediately, instead using path-based references that Claude reads on demand. Official guidance recommends keeping references **one level deep** from SKILL.md and including a table of contents for reference files exceeding 300 lines.

**The multi-agent command orchestration pattern** powers Anthropic's own code review plugin — the most complex official skill. Rather than splitting knowledge across files, it splits *execution* across agents. A single `commands/code-review.md` file orchestrates a pipeline of specialized subagents: Haiku agents for cheap eligibility checks and file listing, parallel Sonnet agents for independent code review passes (CLAUDE.md compliance, shallow bug scan, git blame analysis, prior PR review, code comment compliance), parallel Haiku agents for confidence scoring each finding on a 0–100 rubric, then filtering to findings above 80. This pattern achieves complexity through **model tiering and parallelism** rather than instruction length — each agent receives a focused, concise prompt rather than one agent receiving a massive instruction set.

**The skills-into-subagents pattern** uses the confirmed `skills:` frontmatter field in subagent definitions:

```yaml
---
name: db-admin
description: Database administration tasks
tools: Bash, Read
skills: database-migration, postgres-ops
---
```

This pre-loads specified skill content into a subagent at creation, giving it domain expertise without polluting the main conversation context. A complex skill can thus split into a lightweight main SKILL.md that orchestrates subagents, each of which loads its own subset of detailed skills. The current limitation is that all skills in `~/.claude/skills/` and `.claude/skills/` have their metadata loaded for the main agent regardless of whether they're intended only for subagents — there is no `main-agent: false` flag yet.

**The cross-skill reference pattern** used by superpowers allows skills to reference each other without duplication. Skills use explicit markers like `REQUIRED BACKGROUND:`, `REQUIRED SUB-SKILL:`, and `Complementary skills:` to create a web of interconnected expertise. All references use namespace prefixes (e.g., `superpowers:test-driven-development`) for unambiguous resolution.

One important caveat: the `context: fork` frontmatter field, which should spawn a skill in a separate subagent context, is **currently broken** per GitHub Issue #17283. Skills specifying `context: fork` run in the main conversation context instead.

## What the superpowers and code review plugins reveal

The superpowers plugin (108K+ stars, by Jesse Vincent) provides the clearest case study in scaling skill complexity. A common misconception is that its writing-skills skill is 23K *lines* — it is actually **22,463 bytes (~655 lines, ~5,600 tokens)**. While this exceeds the 500-line guideline, the overshoot is modest. The plugin's real scale comes from distributing content across the directory hierarchy: writing-skills alone spans 7+ files totaling well over 1,000 lines when counting all references and examples.

Superpowers' key architectural decisions include a **dual-repository design** (lightweight plugin shim + separate skills repo that auto-updates), a **session-start hook** that loads only the bootstrap skill (`using-superpowers`, 896 tokens) rather than all content, and aggressive **lazy loading** with path-based rather than force-loading references. GitHub Issue #190 revealed that despite this design, Claude Code's Skill tool definition was at one point preloading all 14 skills (~22K tokens) into the tool description — consuming **11% of the 200K context window** at startup. Issue #832 proposed reducing total skill content from 3,150 to 977 lines (69% reduction) by removing rationalization tables, verbose examples, and marketing copy, and moving heavy content to reference files.

Anthropic's code review plugin takes a fundamentally different approach. It uses **zero reference files** — everything lives in a single command markdown file that describes a multi-phase agent pipeline. Its complexity comes from orchestration logic, not instruction density. The plugin achieves a **<1% false positive rate** on production PRs at Anthropic, with substantive review comments rising from 16% to **54%** of PRs. This demonstrates that agent delegation can substitute for instruction length when the complexity is procedural rather than encyclopedic.

## Designing skills that need more than 500 lines

The research and production examples converge on a clear set of principles for complex skill architecture.

**What must live in SKILL.md** is the high-attention content: the skill's core workflow and decision logic, critical behavioral constraints that must never be violated, the classification of when to use which reference file, and any instructions that require reliable compliance. Position the most critical rules at the **beginning and end** of SKILL.md to exploit the U-shaped attention curve. The middle section should contain less critical workflow steps. Bold or use XML tags for non-negotiable constraints.

**What should live in reference files** includes detailed templates, code examples, API references, domain-specific knowledge (like cloud provider details in an aws.md vs. gcp.md split), error catalogs, and any content exceeding ~100 lines. Reference files for large content (>300 lines) should include a table of contents. The superpowers plugin's guidance: *"When reference material exceeds 100 lines, it's too large to keep inline."*

**What should be delegated to scripts** includes anything deterministic — validation, formatting, file generation, data transformation. Script output enters context but source code does not, making this the most token-efficient pattern. Prefer linters and formatters over LLM instructions for code style enforcement.

The optimal architecture for a skill requiring, say, 2,000 lines of total instruction content looks like this: a **150–300 line SKILL.md** containing core workflow, decision trees, and explicit file-reading directives; **3–5 reference files** of 200–400 lines each for domain-specific knowledge; **executable scripts** for deterministic tasks; and optionally, **subagent definitions** with pre-loaded sub-skills for isolated complex subtasks. This keeps the per-invocation context cost under 2,000 tokens for the SKILL.md while making the full knowledge base available on demand.

## Conclusion

The 500-line limit is a well-calibrated guideline grounded in real cognitive constraints of transformer models, not an arbitrary number. Research shows instruction compliance degrades linearly for Claude Sonnet from the first instruction onward, reasoning performance drops at ~3,000 input tokens regardless of content relevance, and the system prompt already consumes ~25–33% of the model's reliable instruction-following budget. The progressive disclosure architecture — metadata at startup, SKILL.md on invocation, reference files on demand — is not just a convenience pattern but a direct mitigation of these constraints.

The most important insight from production plugins is that **the unit of skill complexity is the directory, not the file**. The superpowers plugin's writing-skills spans 7+ files and over 1,000 lines of total content. Anthropic's code review plugin achieves its sophistication through agent orchestration, not instruction density. Both approach the problem by minimizing what enters context at any single moment while maximizing what's available on demand. For anyone building complex skills, the question is not "how do I fit more into SKILL.md?" but "how do I ensure Claude loads exactly the right 150 lines at exactly the right moment?"