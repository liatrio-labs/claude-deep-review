# Claude Code has no Agent concurrency cap — your 2+3+2 batching is a model behavior

**Claude Code imposes no hard limit on the number of concurrent Agent tool calls per assistant response.** The 2+3+2 batching you're seeing is not an infrastructure constraint — it's the model self-limiting its parallel tool output, likely due to RLHF training conservatism and output token budget pressure. Every major skill and plugin that dispatches multiple agents sends all of them in a single message, and the runtime happily executes them concurrently up to a `maxConcurrency` default of 10. The fix is a combination of explicit prompting and token budget management, not architectural changes to your skill.

## The infrastructure supports 10+ concurrent agents without issue

Reverse-engineering of Claude Code's minified source reveals the core parallel execution engine uses an `all()` async generator with **`maxConcurrency = 10`** as the default. This function initializes up to 10 generators simultaneously and uses `Promise.race()` to process completions. There is no separate Agent-specific concurrency limit anywhere in the codebase.

Hard evidence supports this. GitHub Issue #15487 documents a case where **24 parallel subagent processes** spawned within a 2-minute window on a 4GB VPS — overwhelming the machine but proving no code-enforced cap exists. The `/batch` command supports **up to 30 simultaneous agents**. Anthropic closed a feature request for a `maxParallelAgents` configuration setting as "not planned," confirming no such limit was intended.

The API layer is equally unconstrained. Anthropic's tool use documentation states Claude "may use multiple tools to answer a user query" with **no stated upper bound** on `tool_use` blocks per response. The only documented control is `disable_parallel_tool_use=true`, which is binary (on/off), not a tunable cap.

## The model self-limits — and prompting fixes it

The 2+3+2 pattern is almost certainly the model's own conservative behavior. Multiple lines of evidence converge here:

**Training-induced caution.** Anthropic's own documentation acknowledges this explicitly: Claude 4 models "excel at parallel tool use" but "some minor prompting can boost this behavior to ~100% parallel tool use success rate." Older models are worse — Claude Sonnet 3.7 "may need stronger prompting," and Haiku is "less likely to use parallel tools without explicit prompting." The model was trained to be conservative with parallel execution, likely to avoid resource exhaustion and cascading failures.

**Documented inconsistency.** GitHub Issue #7406 ("Claude thinks it spawns agents in parallel, but it doesn't") reports the model claims to dispatch parallel agents but runs them sequentially. Issue #29181 documents the model emitting only 1 Task call when intending 3, with the other 2 results hallucinated. Both were closed as known issues, confirming Anthropic is aware of this behavior.

**The official fix is prompting.** Anthropic's Claude 4 best practices recommend adding this to your system prompt:

> *"For maximum efficiency, whenever you need to perform multiple independent operations, invoke all relevant tools simultaneously rather than sequentially."*

Claude Code's own system prompt already includes: "Launch multiple agents concurrently whenever possible" and "if you need to launch multiple agents in parallel, send a single message with multiple Task tool calls." Your skill's instructions should reinforce this aggressively with language like "You MUST emit all 7 Agent tool_use blocks in a single response — never batch or sequence them."

## Output token budget is the other likely culprit

Each Agent `tool_use` block contains JSON overhead plus the full `prompt` string. For 7 agents with detailed prompts, the math matters. Claude Code's **default `max_tokens` is 32,000** (increased to 64,000 for Opus 4.6). A typical Agent block with a ~500-token prompt runs **200–500 tokens per block**. Seven verbose blocks with explanatory text could consume 3,500–7,000+ tokens — well within budget at 32K, but the model may anticipate approaching the limit and preemptively split into smaller batches to avoid truncation.

Critically, Anthropic's docs warn: "If Claude's response is cut off due to hitting the max_tokens limit, and the truncated response contains an incomplete tool use block, you'll need to retry." The model likely learns to avoid this scenario by self-limiting batch size. You can increase the budget via the **`CLAUDE_CODE_MAX_OUTPUT_TOKENS`** environment variable — setting it to 64,000 or 128,000 (Opus 4.6 max) gives the model more room to emit all 7 blocks without anxiety about truncation. Keep your agent `prompt` fields as concise as possible to reduce per-block token overhead.

## Every major skill dispatches all agents at once — none batch

A survey of existing skills confirms the all-at-once pattern is standard:

- **Anthropic's code-review plugin** dispatches **5 Sonnet agents simultaneously** in Phase 4 of its pipeline, then spawns **N Haiku agents** (one per issue found) in parallel in Phase 5. No batching, no cap.
- **Anthropic's pr-review-toolkit** defines 6 expert review agents and dispatches all at once. Issue #319 on the plugins repo documented **9 parallel agents** observed in practice — more than defined, because the orchestrator created additional sub-agents. The complaint was about token waste from redundant data fetching, not about a dispatch limit.
- **cw-dispatch** (claude-workflow) explicitly dispatches "a single message with multiple Task tool calls for all unblocked tasks." The cap of ~3 workers users sometimes see reflects the task graph topology (how many tasks are independent), not a platform constraint.
- **obra/superpowers dispatching-parallel-agents** skill documents no hard cap. Its guidance: "Dispatch one agent per independent problem domain. Let them work concurrently." A worked example shows 3 agents for 6 test failures, noting "3 problems solved in time of 1."

None of these skills use `run_in_background: true`. All rely on foreground parallel dispatch.

## Background agents won't help — and are actively broken

Using `run_in_background: true` does **not** change the concurrency limit, and it introduces severe reliability problems. GitHub issues document a cascade of failures: background agents **cannot write files** (Issues #14521, #17011, #17147), **lose all output silently** (#17011), **lack MCP tool access** (#13254), cause **sessions to hang after completion** (#20679), and create **orphaned processes** (#17764). The model also **frequently drops the parameter** despite extensive prompt engineering (#23181).

Issue #20679's workaround is telling: "Don't use `run_in_background: true`. Instead, spawn multiple agents in a single message without the flag — all called in same message = parallel execution." This is the canonical approach. Background agents are for long-running tasks where the user wants to continue chatting, not for increasing concurrency.

## Named agents add no overhead that limits batch size

The `subagent_type` parameter controls which agent configuration loads, with two distinct spawn paths. **Fork agents** (no `subagent_type`) share the parent's prompt cache — the fork child receives the parent's rendered system prompt and exact tool array, producing byte-identical API request prefixes. **Typed agents** (`subagent_type` specified) start fresh with zero context but can use any model. 

Neither path imposes batch-size constraints. The named agent resolution is a simple lookup in the agent definition registry. Model resolution follows a priority chain: `CLAUDE_CODE_SUBAGENT_MODEL` env var → per-invocation `model` parameter → subagent definition's `model` frontmatter → main conversation's model. This is lightweight string matching, not a bottleneck that would limit how many agents can be dispatched simultaneously.

## The recommended pattern for 7 parallel agents

Based on all evidence, here is the most reliable approach, ordered by impact:

1. **Explicit parallel dispatch prompting.** In your skill's instructions, add: "You MUST emit all 7 Agent tool_use blocks in a single assistant message. Never batch, sequence, or split them across multiple responses. All 7 tasks are fully independent with no shared state." This alone should push Claude 4 models to ~100% parallel dispatch rate.

2. **Increase output token budget.** Set `CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000` (for Opus 4.6) or `64000` (for Sonnet 4.6). This eliminates the model's incentive to split batches to avoid truncation.

3. **Keep agent prompts concise.** Each `prompt` field consumes output tokens. If your 7 agent prompts average 1,000 tokens each, that's 7,000 tokens of output just for the tool_use blocks — significant at a 32K budget, trivial at 128K. Front-load critical instructions; omit verbose context.

4. **Use foreground dispatch, not `run_in_background`.** All 7 as foreground agents in one message is the canonical pattern — the runtime executes them concurrently via `Promise.allSettled()` up to `maxConcurrency = 10`. Background mode adds bugs without adding concurrency.

5. **Avoid the `mode` parameter — it doesn't exist.** The Agent tool schema has `subagent_type`, `description`, `prompt`, and optionally `model` and `run_in_background`. There is no `mode` parameter that reduces overhead. The `subagent_type: "Explore"` type uses Haiku and read-only tools — this is the closest thing to a lightweight mode if some of your 7 agents only need to read.

## Conclusion

The 2+3+2 batching is a solvable problem, not a platform limitation. **No hard cap exists** — the infrastructure supports 10 concurrent agents by default, the API has no per-response tool_use limit, and Anthropic's own plugins routinely dispatch 5–9 agents simultaneously. The two levers that matter are explicit prompting (telling the model to emit all calls in one shot) and token budget (giving it enough output room to do so). Combined, these should eliminate the batching behavior entirely. If it persists after both fixes, the remaining variable is model stochasticity — Claude 4 models have a "high success rate" at parallel dispatch but not 100% without prompting, and even with prompting, occasional batching may occur on low-probability sampling paths.
