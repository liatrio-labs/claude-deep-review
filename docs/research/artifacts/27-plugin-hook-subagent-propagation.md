# Plugin hooks don't reach Claude Code subagents

**PreToolUse hooks defined in a plugin's `hooks/hooks.json` do not reliably fire for Bash tool calls made by subagents spawned via the Agent tool.** Your empirical finding — zero firings across 46 subagent Bash commands in session a10705b4 — aligns with a well-documented architectural gap in Claude Code's hook propagation system. At least **seven GitHub issues** on `anthropics/claude-code` report variants of this problem, with no definitive fix shipped as of v2.1.96. The situation is complicated by contradictory evidence: official documentation implies settings-level hooks *should* fire for subagent tool calls, and at least one issue (#33049) confirms PreToolUse/PostToolUse *do* fire in certain subagent configurations. The most likely explanation is that **plugin hooks specifically have a propagation gap** that settings.json hooks may not, compounded by version-specific bugs in the hook merging pipeline.

## The documented design versus observed reality

Claude Code's hook system is designed around a per-event-occurrence evaluation model. When any tool call happens — whether in the parent session or a subagent — the system should match it against all registered hooks (from `~/.claude/settings.json`, `.claude/settings.json`, managed policies, and enabled plugin `hooks/hooks.json`). The official documentation supports this: hook input JSON includes **`agent_id`** and **`agent_type`** fields specifically to let hooks discriminate between parent and subagent contexts. The Agent SDK docs explicitly recommend using "PreToolUse hooks to auto-approve specific tools" as a workaround for subagent permission issues — which only makes sense if those hooks fire in subagent contexts.

Yet the empirical evidence tells a different story. GitHub Issue #27661 ("Subagents should inherit parent session hooks and permission rules") directly reports that "PreToolUse hooks defined in `.claude/settings.json`" do not fire for Task tool subagents. Issue #6522 confirms hooks "don't seem to execute" for subagents. Issue #25000 documents subagents running **22+ Bash commands** (including `cat ~/.bashrc`, `ls -la ~/.ssh/`) while completely bypassing deny rules. And your own testing with plugin hooks shows a clean 0/46 failure rate.

The resolution appears to be that **hook propagation to subagents is inconsistent and partially broken**, with the exact behavior depending on hook source (plugin vs. settings), subagent type (fork vs. typed), Claude Code version, and possibly the specific lifecycle event. Issue #33049 notably states that "PreToolUse, PostToolUse fire correctly for the subagent" while the Stop hook does not — suggesting partial, unreliable propagation rather than a complete architectural barrier.

## Plugin hooks versus settings.json hooks in subagent contexts

There is a meaningful distinction between these two hook sources, and it likely explains your specific failure mode. Plugin hooks follow a different lifecycle than settings.json hooks:

Plugin hooks are loaded from `hooks/hooks.json` when the plugin is enabled and **merged** into the session's hook pool. They appear in the `/hooks` menu labeled `[Plugin]` and can reference scripts via `${CLAUDE_PLUGIN_ROOT}`. However, multiple bugs have been documented in the plugin hook pipeline: v2.1.83 fixed "uninstalled plugin hooks continuing to fire until the next session," Issue #10412 confirmed plugin-installed Stop hooks with exit code 2 fail while identical settings.json hooks work, and Issue #18547 reported plugin hooks not loading at all in the VS Code extension.

Settings.json hooks (`~/.claude/settings.json` or `.claude/settings.json`) are loaded as part of the core configuration at session initialization. These appear to have a more robust propagation path — the egghead.io tutorial demonstrates that settings.json PostToolUse hooks *do* create infinite loops when subagents inherit them, proving propagation works in at least some configurations.

**The critical security restriction compounds the problem**: the official docs state that "for security reasons, plugin subagents do not support the `hooks`, `mcpServers`, or `permissionMode` frontmatter fields." While this refers to agents *defined by* plugins (not hooks *defined in* plugins), it reveals that the plugin system has deliberately restricted hook-related capabilities in subagent contexts. The plugin hook merge step may similarly fail to extend into subagent execution contexts, even though settings-level hooks survive the transition.

## The scoping rule: frontmatter hooks versus plugin hooks

The research artifact's statement — "Skill/agent frontmatter hooks: Scoped to the component's lifecycle only, cleaned up when the skill or subagent finishes" — describes a scoping model that **does not apply to plugin hooks**. These are fundamentally different mechanisms:

**Frontmatter hooks** are registered in memory when a skill or agent activates. They run only during that component's execution and are deregistered on completion. For subagents, `Stop` hooks in frontmatter automatically convert to `SubagentStop`. This lifecycle scoping is deliberate and documented.

**Plugin hooks** are session-wide. They merge into the global hook pool when the plugin is enabled and persist for the entire session regardless of which skill or agent is active. They are *not* scoped to any component's lifecycle. However, "session-wide" apparently means the **parent session** — the hook pool that subagent execution contexts reference may be a subset or a separate copy that doesn't include plugin-sourced hooks. This is the likely root cause of your observed behavior.

**Settings.json hooks** are also session-wide and persistent, but they're loaded through a different code path (core configuration rather than plugin merging) and appear to have better subagent propagation — though still buggy per multiple issues.

## Seven GitHub issues document this gap

The `anthropics/claude-code` repository (note: there is no `anthropic/claude-code` repo) contains extensive documentation of hook/permission propagation failures in subagent contexts:

- **#27661** (Closed) — "Subagents should inherit parent session hooks and permission rules." Proposed `propagateToSubagents: true` config. No maintainer response visible.
- **#18392** (Closed as duplicate) — Hooks in agent frontmatter not executed for subagents. Notes the `tools:` allowlist is also not enforced.
- **#6522** (Closed as duplicate) — PostToolUse hooks don't execute for subagents. Tested with golangci-lint integration.
- **#25000** (Closed as duplicate) — Sub-agents bypass permission deny rules entirely. Documented **22 autonomous Bash commands** accessing SSH keys and shell history.
- **#23983** (Open) — PermissionRequest hooks not triggered for subagent permission requests in Agent Teams.
- **#33049** (Closed) — Subagent Stop hook doesn't fire, but claims PreToolUse/PostToolUse do fire. Labeled `area:agents, area:hooks, bug, has repro`.
- **#40241** (Open) — `--dangerously-skip-permissions` doesn't propagate to subagents. Confirms hooks are "not the cause" after testing.

Several of these were closed as duplicates, suggesting Anthropic is aware of the issue class, but **no public fix or design change has been announced**. Feature requests #14859 (agent hierarchy in hook events, 4 thumbs-up) and #5812 (context bridging between subagent/parent hooks) remain open.

## Recommended mechanisms for enforcing Bash restrictions on subagents

Given the propagation gap, here are the five options evaluated from most to least effective:

**(d) Remove Bash from agent tool lists entirely** — the most reliable approach. Define custom agents in `.claude/agents/` with `tools: Read, Grep, Glob` (or whichever subset you need). This physically prevents Bash access rather than trying to filter it. **Caveat**: Issue #18392 reports the `tools:` allowlist in frontmatter "is also not enforced (known issue)," though this may be fixed in v2.1.96. Test empirically.

**(a) Define hooks in agent frontmatter** — the officially documented workaround. Create custom agent definitions in `.claude/agents/` (not in the plugin's `agents/` directory, since plugin subagents cannot carry hooks) with PreToolUse hooks matching Bash. **Caveats**: Issue #18392 reported frontmatter hooks not firing for subagents; each new hook must be manually duplicated into every agent file; agent definitions drift out of sync with plugin hooks.

**(b) Use `.claude/settings.json` project-level hooks** — may have better propagation than plugin hooks based on the evidence (egghead.io infinite loop proof, Issue #33049 confirmation). Move your PreToolUse Bash hooks from the plugin's `hooks/hooks.json` into `.claude/settings.json`. This loses the portability benefit of plugin packaging but may fix the propagation issue. Test empirically against subagent Bash calls.

**(c) Use permission deny rules** — `"deny": ["Bash(rm *)", "Bash(curl *)"]` in settings.json. **Not recommended**: Issue #25000 explicitly documents subagents bypassing deny rules, and Issue #22665 confirms the permission allowlist doesn't propagate either. Permission rules have the same propagation gap as hooks.

**(e) Hybrid approach** (recommended) — Combine **(d)** and **(b)**: restrict subagent tool lists to exclude Bash where possible, and for agents that need Bash, define PreToolUse hooks in both `.claude/settings.json` (for potential propagation) and the agent's frontmatter in `.claude/agents/` (as a belt-and-suspenders measure). Monitor with `SubagentStart` hooks in settings.json to log when subagents spawn.

## The matcher field does not affect subagent propagation

The `matcher` field in hooks.json is a **regex string** tested against the tool name (e.g., `"Bash"`, `"Edit|Write"`, `"mcp__memory__.*"`). It operates identically regardless of whether the tool call originates from the parent session or a subagent — `"Bash"` matches the same `Bash` tool in both contexts. The matcher evaluation happens *after* the hook is registered in the evaluation pipeline, so if the hook never enters the subagent's pipeline (the propagation gap), the matcher never runs. The issue is not matcher semantics but **whether the hook is present in the subagent's evaluation context at all**.

When hooks do fire in subagent contexts, the `agent_id` and `agent_type` fields in hook input JSON let you distinguish the source. You could write a hook that matches `"Bash"` but only blocks when `agent_type` is present (subagent context) — but only if the hook actually fires.

## Conclusion

Your observation is correct and well-documented across the Claude Code issue tracker. **Plugin hooks defined in `hooks/hooks.json` do not propagate to subagent execution contexts** in v2.1.96. The root cause appears to be an incomplete hook merging pipeline: plugin hooks are merged into the parent session's hook pool but not into the execution contexts created for subagents via the Agent tool. Settings.json hooks *may* propagate more reliably (conflicting evidence), but the entire hook-to-subagent propagation system is inconsistent. No `propagateToSubagents` configuration option exists despite being proposed in Issue #27661. The most defensive strategy is to eliminate Bash from subagent tool lists and define redundant hooks in both `.claude/settings.json` and agent frontmatter files stored in `.claude/agents/` (not in the plugin directory, since plugin-defined agents cannot carry hooks). This is an active area of instability in Claude Code's architecture with no announced resolution timeline.
