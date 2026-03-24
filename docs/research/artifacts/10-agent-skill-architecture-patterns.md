# How production multi-agent skill systems actually work under the hood

**Skills in Claude Code inject additional tokens into the context window as user messages — they never replace existing instructions.** This additive loading model, combined with a three-tier progressive disclosure system, defines the fundamental architecture. Across all major frameworks, no production system has solved the tension between modular skill reuse and simple debuggability: official Anthropic plugins themselves use self-contained agent definitions rather than delegating to skills, and research on instruction positioning reveals that dynamically loaded instructions face measurable disadvantages compared to system-prompt-level directives. Here's what the documentation, source code, and production deployments actually show.

---

## 1. Skills consume additional context tokens — they never replace anything

When Claude Code invokes a skill during execution, the skill's content is **injected as new `role: "user"` messages** appended to the conversation history. The agent's existing system prompt and all prior messages remain intact. This is prompt expansion, not instruction replacement.

The injection produces two new messages: a short visible metadata status message (e.g., `<command-message>The "pdf" skill is loading</command-message>`) and the **full SKILL.md content as a hidden user message** (flagged `isMeta: true` so it's sent to the API but hidden from the UI). A context modifier then adjusts allowed tools, can override the model, and tweak thinking parameters. Reverse-engineering of the actual API request structure confirms skills appear as additional entries in the `messages` array alongside all existing conversation history.

The progressive disclosure model operates across three tiers with distinct token costs:

| Loading tier | When loaded | Token cost | What loads |
|---|---|---|---|
| **Metadata** | Always at startup | **~100 tokens per skill** | `name` and `description` from YAML frontmatter, embedded in the Skill meta-tool's description |
| **Instructions** | When skill triggers | **Up to 5,000 tokens** | Full SKILL.md body injected as a user message |
| **Resources** | On demand | Varies (scripts: output only; references: full file; assets: 0) | Bundled files loaded individually as needed |

The metadata tier has a **15,000 character budget** across all installed skills. With 10 skills installed but inactive, only ~1,000 tokens of metadata load — **98% savings** versus loading all skill content upfront. Community measurements (ClaudeFast Code Kit) report recovering roughly **15,000 tokens per session** across 20+ skills compared to stuffing everything into CLAUDE.md. Per-invocation overhead runs approximately **1,500+ tokens** per skill call (combining metadata message, skill prompt, and permission messages), versus ~100 tokens for a normal tool call.

**Latency comes from an extra API round-trip, not algorithmic lookup.** There is no embedding search, classifier, or pattern matching for skill selection. All skill names and descriptions sit as text in the Skill tool's prompt description. Claude's transformer forward pass does the "lookup" as part of normal inference. The actual file read is sub-millisecond local I/O. But skill invocation requires **at minimum one additional inference round-trip**: Claude first decides to invoke the Skill tool, the system loads SKILL.md and injects it, then Claude processes the enriched context to proceed with actual work. Each round-trip costs hundreds of milliseconds to seconds of model inference. However, the smaller resulting context (only the relevant skill loaded) can partially offset this by reducing per-inference latency. Anthropic has not published specific latency benchmarks.

**Once loaded, skill tokens persist** in the conversation history for all subsequent turns until compaction occurs. They don't "unload." When auto-compaction triggers at ~75% context usage, skill prompt content may be summarized or compressed along with other messages — potentially losing the skill instructions entirely.

---

## 2. Frameworks split roles from capabilities in fundamentally different ways

The four major multi-agent frameworks take architecturally distinct approaches to separating agent identity from reusable capabilities.

**LangGraph** treats agents as graph nodes and tools as independently defined Python functions bound to LLMs via `llm.bind_tools(tools)`. Agent "roles" exist only as system prompt strings — there is no first-class `Agent` class with structured role definitions. Tools are defined once with `@tool` decorators and passed to any number of agents. LangGraph is unique in offering **middleware-based dynamic tool filtering**, the closest any framework comes to progressive capability loading: tools can be revealed or hidden based on conversation state at runtime. Shared state flows between agents via `MessagesState` TypedDict, and `Command` objects handle routing.

**CrewAI** enforces the **strongest explicit separation**. Agent identity is defined as a structured triplet — `role`, `goal`, `backstory` — typically in YAML configuration files. Tools are Python objects (subclassing `BaseTool` or using `@tool` decorators) that must be instantiated in code and cannot appear in YAML. This forces a clean boundary: YAML handles persona, Python handles capabilities. The same tool instance can be passed to multiple agents. DocuSign's production deployment uses CrewAI's Flow + Crew architecture, with deterministic Flows providing business logic scaffolding and reusable agent Crews providing intelligence within each step.

**AutoGen v0.4** uses a layered architecture. At the high level (AgentChat API), `AssistantAgent` takes a `system_message` string for identity and a `tools` list of Python functions that auto-wrap as `FunctionTool` objects. At the Core API level, agents are message-handling actors with explicit tool schemas. AutoGen Studio provides a visual drag-and-drop interface where skills (Python functions) and models are independently attachable entities exported as JSON — the closest AutoGen gets to a shared capability library. A community feature request for a Voyager-style persistent skill library was filed but never implemented as a first-class feature.

**Magnetic-One** takes the most rigid approach: **agents ARE their specializations**. Its fixed five-agent architecture (Orchestrator, WebSurfer, FileSurfer, Coder, ComputerTerminal) embeds capabilities directly in each agent's implementation and system prompt. There is no shared tool library; each agent type has built-in capabilities. The Orchestrator maintains structured Task and Progress Ledgers for planning. Different LLMs can power different agents (e.g., o1-preview for the Orchestrator, GPT-4o for workers).

| Feature | LangGraph | CrewAI | AutoGen v0.4 | Magnetic-One |
|---|---|---|---|---|
| Agent identity | System prompt string | role + goal + backstory | system_message string | Hardcoded agent class |
| Tool-agent binding | `create_agent(model, tools=[])` | `Agent(tools=[])` | `AssistantAgent(tools=[])` | Implicit per agent type |
| Shared tool instances | ✅ | ✅ | ✅ | ❌ |
| Config file separation | No | ✅ YAML roles / Python tools | JSON export from Studio | No |
| Dynamic tool filtering | ✅ Via middleware | ❌ | ❌ | ❌ |
| Progressive loading | ✅ Via middleware | ❌ | ❌ | ❌ |

**None of these frameworks implement progressive disclosure as a first-class feature.** Claude Code's three-tier skill loading model remains architecturally distinct from these frameworks.

---

## 3. Subagents can invoke skills, but nesting is shallow and buggy

Subagents spawned via the Agent/Task tool **can invoke skills** through two mechanisms. First, the `skills:` YAML frontmatter field on agent definitions preloads specific skills at startup, injecting full content immediately. Second, if the `Skill` tool is included in a subagent's allowed tools, the subagent can dynamically invoke skills during execution — confirmed by GitHub issue #18057 showing a subagent successfully calling `{"name":"Skill","input":{"skill":"meta-claude:release-notes"}}`.

**Nesting is hard-limited to exactly one level.** Official documentation states plainly: "Subagents cannot spawn other subagents. If your workflow requires nested delegation, use Skills or chain subagents from the main conversation." An inline skill (running without `context: fork`) executes in the main agent's context and can trigger additional skills sequentially. A forked skill (`context: fork`) runs as a subagent and therefore cannot spawn further subagents. Skills can instruct Claude to spawn a subagent via the Task tool, but that spawned subagent faces the same constraint.

**Multiple confirmed bugs affect skill-subagent interaction**, all documented in the anthropics/claude-code GitHub issue tracker:

- **Issue #18394**: `context: fork` fails inconsistently — "95%+ of the time, the skill just runs in existing context instead of spawning the specified subagent"
- **Issue #17283**: Skill tool ignores `context: fork` and `agent:` frontmatter entirely in some scenarios
- **Issue #18057**: Subagent crashes the entire Claude Code process when the Skill tool invokes a non-existent skill (Abort() instead of graceful error handling)
- **Issue #10061**: Sub-agents load skills from the global `~/.claude/skills/` directory instead of project-local `.claude/skills/`, breaking project-specific customization
- **Issue #24072**: The built-in Plan subagent intentionally excludes the Skill tool — not documented
- **Issue #24110**: Claude Code is "often ignoring specialized subagents and skills" unless coaxed via CLAUDE.md
- **obra/superpowers #237**: Subagent sessions don't receive hook-injected context, so they "can see the skill list but lack the discipline framework that drives skill-first behavior"

---

## 4. Skill content loads into whichever context invokes it — never both

The progressive disclosure model interacts with subagent context windows through four distinct scenarios, each with different behavior:

**Preloaded skills** (via `skills:` frontmatter on agent definition) load into the **subagent's context only**. Progressive disclosure is bypassed — full SKILL.md content injects at startup because the subagent starts with fresh context and needs instructions immediately. The parent never sees this content; it only receives the subagent's final output as the Agent tool result.

**Dynamic Skill tool invocation inside a subagent** loads into the **subagent's context only**. Each subagent has an isolated context window. The progressive disclosure sequence (metadata → SKILL.md → references) operates within the subagent's context. The parent receives only the subagent's summarized result.

**Inline skill execution** (no `context: fork`) loads into the **parent/main context**. The instructions and relevant content add to the current conversation directly.

**Forked skill execution** (`context: fork`) loads into a **new subagent context**. The skill content becomes the prompt for a freshly spawned subagent with no conversation history.

The critical implication: **an agent running in its own isolated context window cannot see skills loaded in the parent conversation**. This architectural boundary is why, in practice, agents bake in their own instructions.

---

## 5. Official Anthropic plugins are entirely self-contained — no agent-to-skill delegation exists

Examination of actual plugin source code reveals that **in all official Anthropic plugins, agents carry baked-in instructions and do not delegate to skills for methodology**. Skills and agents are sibling constructs occupying separate directories, not hierarchical components.

The **code-review plugin** (Boris Cherny, Anthropic) has no `agents/` or `skills/` directories at all. Everything lives in `commands/code-review.md`, which contains all orchestration logic inline: a Haiku eligibility-check subagent, a Sonnet compliance agent, an Opus bug-finding agent, parallel validation subagents, and Haiku scoring agents — all with instructions baked directly into the command markdown. No external skill files are referenced.

The **pr-review-toolkit plugin** (Anthropic) has six fully self-contained agent definitions (`code-reviewer.md`, `code-simplifier.md`, `comment-analyzer.md`, `pr-test-analyzer.md`, `silent-failure-hunter.md`, `type-design-analyzer.md`) and **no `skills/` directory**. Each agent .md file contains complete YAML frontmatter plus full methodology, scoring rubrics, and example trigger scenarios in the markdown body.

The **feature-dev plugin** has both agents and a `frontend-design` skill, but they operate independently — the skill auto-invokes for frontend work, providing design guidance, while agents handle codebase analysis and architecture. The agents don't reference the skill. The **plugin-dev plugin** is the closest to a delegation pattern with 3 agents and 7 skills, but even here agents carry their own instructions and skills provide supplementary domain knowledge.

**The architecture supports a one-way relationship: skills CAN delegate TO agents** (via `context: fork` + `agent:` field in SKILL.md frontmatter), **but agents cannot explicitly invoke or reference skills**. Agent `.md` files have no mechanism for this. Community plugins follow identical patterns — either agents-only, skills-only, or both as independent siblings.

---

## 6. Split behavior makes debugging 3-5× harder, and the industry knows it

Production teams consistently report that splitting agent behavior across definitions and skills introduces significant debugging friction. The core challenge shifts from debugging *logic errors* to debugging *discovery failures* — why a skill wasn't triggered, not why it produced wrong output.

**Block Engineering**, running 100+ internal skills in production, documents a "two-zone" debugging model: deterministic scripts (easy, traditional debugging) versus agent interpretation (non-deterministic, much harder). Their principle: "If it needs to be consistent across runs and across users, don't leave it to the model. Put it in a script." They found that constitutional constraints — explicit MUST NOT rules in SKILL.md — were essential because "without these constraints, agents will find creative ways to be 'helpful' that break your workflow."

**Arize** (shipping their Alyx agent to production) found their agent tried to call functions that didn't exist — "runtime failure, completely invisible in unit tests." They now run structured validation cross-referencing tool names in prompts against actual tool decorators in code. **GitHub's Copilot team** discovered that without typed interfaces and strict schemas at every agent boundary, debugging became intractable: "This changes debugging from 'inspect logs and guess' to 'this payload violated schema X.'"

Practitioner reports on Hacker News describe the hardest failure mode: "Agent A correctly doing its job, but passing slightly malformed state to Agent B, which then confidently executes a destructive action. By the time you see the error, the root cause is three steps up the chain." Multiple sources cite **3-5× longer debugging times** for multi-agent versus single-agent systems, with teams spending up to **40% of sprint time** investigating agent failures.

**OpenTelemetry has emerged as the de facto observability standard**, with Langfuse, Arize Phoenix, LangSmith, and framework-native tracing all converging on OTEL. The practical consensus from production teams follows a clear trajectory: start self-contained (all logic in one place, simple debugging), evolve to modular (skills/split definitions) only when concrete scaling needs demand it. Microsoft's Cloud Adoption Framework states it directly: "Debugging becomes straightforward when all logic resides in one place."

---

## 7. System prompt instructions measurably outperform mid-execution instructions

Research provides strong evidence that instruction position affects output quality through three reinforcing mechanisms, all disadvantaging dynamically loaded skill instructions.

**Architectural primacy** is real and well-documented. The landmark "Lost in the Middle" paper (Liu et al., TACL 2024) demonstrated a **U-shaped performance curve** across 7+ models: performance dropped by **over 30%** when relevant information moved from the start or end of context to the middle. This held for explicitly long-context models including GPT-4 32K and Claude 100K. Tool outputs — which is how skill content arrives — land squarely in this low-attention middle zone.

**The Instruction Hierarchy** (Wallace et al., OpenAI, 2024) established and implemented an explicit priority ordering in production models: **System Messages > User Messages > Tool Outputs**. Tool outputs occupy the lowest privilege tier. Models are fine-tuned via RLHF to enforce this hierarchy, meaning skill content loaded as tool results or user messages is architecturally treated as lower-authority than system prompt instructions. The "Position is Power" paper (arXiv 2505.21091) directly demonstrated that identical instructions placed in a system prompt versus a user prompt produce measurably different outputs from Claude 3.5.

**Primacy effects are robust across all major LLMs.** A comprehensive study across GPT-3.5, GPT-4, Llama2, Claude, T5, and FlanT5 (arXiv 2406.15981) found serial position effects consistently observed in every model tested, with fine-tuned versions exhibiting **more pronounced primacy bias** than pre-trained counterparts. RLHF significantly amplifies these effects. The "Control Illusion" paper (arXiv 2502.15851) found that even state-of-the-art models fail to maintain instruction priorities: GPT-4o achieved only **40.8% Priority Adherence Rate**, Claude 23.6%.

**No published study directly benchmarks "system prompt instructions" versus "identical instructions loaded via tool call" on task quality.** The evidence is assembled from related findings rather than a single targeted experiment. But it strongly favors system prompt placement for critical behavioral instructions. The practical recommendation emerging from this research: **anchor identity, constraints, and quality standards in the system prompt** (high privilege, primacy position); use skills for **procedural details and domain knowledge** that can tolerate lower adherence; and implement aggressive context management to prevent degradation in long sessions.

---

## Conclusion

The skill architecture in Claude Code represents a genuine innovation in context management — recovering **80-98% of tokens** compared to monolithic instructions — but carries underappreciated tradeoffs. Skill content arrives as additive user messages that persist until compaction, face primacy disadvantages from both positional and privilege hierarchies, and interact with subagent context windows in ways that remain buggy. Tellingly, **Anthropic's own plugin teams don't use the agent-delegates-to-skill pattern**: every official plugin ships self-contained agent definitions with baked-in instructions.

The architectural insight across all frameworks is consistent: tools and capabilities are reusable objects shared across agents, but agent identity and behavioral instructions remain self-contained per agent. No production framework has implemented true progressive disclosure of capabilities as a first-class feature — Claude Code's skill system is architecturally unique in this regard, and its rough edges reflect the difficulty of the problem.

For teams deciding between skill-based modularity and self-contained instructions, the evidence points toward a hybrid: **use skills for domain knowledge and procedural guidance that supplements agent behavior** (the "what to know" layer), while keeping **critical behavioral instructions, quality standards, and constraints baked into agent definitions or system prompts** (the "how to behave" layer). Start self-contained. Split only when maintenance burden or context window pressure demands it. And invest in OTEL-based observability before making the split — you'll need it.