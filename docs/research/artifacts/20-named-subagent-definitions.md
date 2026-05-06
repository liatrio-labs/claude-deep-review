# Named subagent definitions for Claude Code skills: what works, what doesn't, and what to do

**Named subagent definitions bundled inside plugins are a fully supported, first-class deployment mechanism** — and they solve the core problem of prompt-assembled agent dispatch dropping tool restrictions. A plugin's `agents/` directory ships `.md` files with YAML frontmatter where `tools:` acts as a **hard system-level constraint**, not a prompt suggestion. However, the deployment path has real limitations: plugin-shipped agents cannot define hooks or override permission modes, a known bug prevents plugin agents from accessing co-bundled plugin skills, and agents load only at session start. The practical recommendation for the deep-review skill is to migrate to the plugin + named agents pattern, with `.claude/agents/` in the project repo as a fallback for teams that resist plugin infrastructure.

---

## Plugins can bundle agent definitions — here's exactly how

The plugin directory structure explicitly supports an `agents/` subdirectory as a first-class component, alongside `skills/`, `commands/`, and `hooks/`. Claude Code auto-discovers `.md` agent files from this directory without requiring explicit references in `plugin.json`:

```
deep-review-plugin/
├── .claude-plugin/
│   └── plugin.json
├── agents/
│   ├── bug-detector.md
│   ├── security-reviewer.md
│   └── compliance-checker.md
├── skills/
│   └── review-conventions/SKILL.md
└── README.md
```

When installed, **plugin agents appear namespaced** as `deep-review-plugin:bug-detector` to avoid conflicts. Claude Code loads them from the plugin cache directory (`~/.claude/plugins/cache/`) — the install process does **not** copy files into `.claude/agents/`. Multiple official Anthropic plugins ship this way: `pr-review-toolkit` bundles 6 named agents (`comment-analyzer`, `pr-test-analyzer`, `silent-failure-hunter`, `type-design-analyzer`, `code-reviewer`, `code-simplifier`), `feature-dev` bundles 3, and `plugin-dev` bundles 3.

There is **no post-install hook or lifecycle event** in the plugin system. Installation is declarative: users run `/plugin install deep-review@your-marketplace` and agents become available at next session start. If the `plugin.json` needs to reference agent files explicitly (e.g., from non-standard paths), the `agents` field **must be an array** — passing a string like `"agents": "./agents/"` silently fails (GitHub issue #21598).

A critical caveat: **agents bundled inside a plugin cannot currently access that plugin's co-bundled skills** (GitHub issue #11955, still open). If `bug-detector.md` lists `skills: [review-conventions]`, the skill resolution may fail. The workaround is to inline the skill content directly into the agent's system prompt body.

## Path resolution follows a strict priority chain

When the orchestrator encounters `subagent_type: "deep-review-bug-detector"`, Claude Code resolves the agent definition through this priority order:

1. **Programmatic (SDK `agents` parameter)** — highest priority, overrides everything
2. **Project-level** — `.claude/agents/deep-review-bug-detector.md` relative to the project root
3. **User-level** — `~/.claude/agents/deep-review-bug-detector.md` in the user's home directory
4. **Plugin-provided** — agents from installed plugins, namespaced as `plugin-name:agent-name`
5. **Built-in** — `Explore`, `Plan`, `general-purpose`, `Bash`, `Claude Code Guide`

A skill **cannot reference agent definitions bundled within its own directory** using a relative path. Skills and agents live in separate resolution namespaces. A skill can reference a named agent via `context: fork` + `agent: bug-detector` in its frontmatter, but this triggers a **known bug (GitHub issue #17283)**: when a skill is invoked via the Skill tool (model-initiated), the `context: fork` and `agent:` fields are silently ignored, and the skill runs in the main conversation context instead. The fields work correctly only when the skill is invoked via its `/skill-name` slash command.

Agents are **loaded at session start only**. Creating a new agent file mid-session requires a restart or running `/agents` to reload. The `claude agents` CLI command lists all configured agents grouped by source, useful for verifying resolution.

## What Anthropic's code-review plugin actually does — and why it matters

Anthropic's official `code-review` plugin uses **inline prompt-based dispatch**, not named agent `.md` files. The entire review workflow lives in a single `commands/code-review.md` file that contains natural language instructions like "launch 5 parallel Sonnet agents" and "Use a Haiku agent to return a summary." The command prompt describes each agent's role, model, and task inline — agents are spawned via the Agent tool with prompt-assembled specifications rather than referencing pre-defined definitions.

This is the same architectural pattern as the deep-review skill's current inline `Agent()` dispatch. The critical difference is that Anthropic's code-review plugin does **not** specify tool restrictions on its spawned agents. Each agent inherits the full tool set from the parent session. This works for their use case (code review needs read + bash access for `gh` CLI), but confirms that **prompt-assembled agent dispatch provides no mechanism for tool restriction** — the orchestrator must voluntarily include `tools` in the Agent tool call, and as observed in the deep-review benchmarks, it consistently omits them.

In contrast, the `pr-review-toolkit` plugin does use named agent `.md` files in its `agents/` directory. This is the pattern to follow when tool restrictions matter.

## Tool restrictions are a hard sandbox, with historical caveats

The `tools` frontmatter field on a named subagent is **system-enforced at the runtime level, not advisory**. When `tools: Read, Grep, Glob, LSP` is specified, the subagent physically cannot access Bash, Write, Edit, or any MCP tools — these tools are not presented to the model and calls to them would be rejected. Community testing confirms this: "A reviewer defined with only Read, Grep, Glob cannot write files. That's not a naming convention or a prompt instruction, it's a hard constraint."

The resolution logic when both fields are present: `disallowedTools` is applied first to remove tools from the inherited pool, then `tools` is resolved against the remaining set. If `tools` is omitted entirely, the subagent **inherits all tools** from the parent session, including MCP tools — a dangerous default for review agents.

Three important enforcement details:

- **Permission mode inheritance is one-way restrictive.** If the parent session runs in `bypassPermissions` or `auto` mode, those take precedence and cannot be overridden by the subagent's `permissionMode` frontmatter.
- **Plugin-shipped agents face additional security restrictions.** They cannot define `hooks`, `mcpServers`, or `permissionMode` in their frontmatter. This is a hard security boundary.
- **Historical bugs have temporarily broken enforcement.** In March 2026, a fix addressed `deny: ["mcp__servername"]` permission rules not removing MCP server tools before sending to the model (v2.1.78). Another fix addressed `PreToolUse` hooks returning `"allow"` bypassing `deny` rules, including enterprise managed settings (v2.1.77). These are now patched, but they demonstrate that the enforcement layer has had real gaps.

The `allowed-tools` field on a SKILL.md also provides system-level tool restriction when the skill is active in the main session — "Claude reads and analyzes files but cannot write, edit, or run bash commands. Even if Claude wanted to 'just quickly fix' something, the tool restriction prevents it." This is an alternative to full subagent isolation, though it lacks the context-window separation.

## Three deployment strategies for 10+ developer teams

**Strategy 1: Plugin via private marketplace (recommended).** Create a Git repository with `marketplace.json`, host it on GitHub/GitLab, and have teams add it once via `/plugin marketplace add org/claude-plugins`. Then each developer runs `/plugin install deep-review@org-plugins`. Commit a shared `.claude/settings.json` to project repos with `enabledPlugins` and `extraKnownMarketplaces` pre-configured so plugins auto-install on trust approval. Updates propagate when developers run `/plugin marketplace update`. This is the **lightest-weight approach for ensuring all repos have agent definitions** — one install command per developer, plus a settings.json in shared repos.

**Strategy 2: Project-level `.claude/agents/` in version control.** Commit agent `.md` files directly to each repo's `.claude/agents/` directory. Every developer who clones the repo gets the agents automatically. Updates propagate via normal git pull. The downside: you must duplicate agent files across every repo that needs them, or use git submodules. The upside: no plugin infrastructure needed, agents take precedence over user-level definitions, and there are no namespacing issues.

**Strategy 3: Enterprise managed settings for policy enforcement.** Deploy `managed-settings.json` via MDM (at `/etc/claude-code/managed-settings.json` on Linux, `/Library/Application Support/ClaudeCode/managed-settings.json` on macOS). This can enforce `allowManagedPermissionRulesOnly`, `allowManagedHooksOnly`, and `enabledPlugins`. However, **managed settings cannot directly deploy agent definitions** — they can only enforce which plugins are enabled and which permissions apply. Use managed settings to mandate plugin installation, then distribute agents through those plugins.

A `.claude/settings.json` in a shared config **cannot point to shared agent definitions or remote agent files**. It can only configure plugins, permissions, hooks, and MCP servers. For organizations that need a single source of truth for agent definitions across many repos, the plugin marketplace pattern is the only supported approach.

## Memory persists across sessions, hooks scope to the subagent only

The `memory` frontmatter field gives a subagent a persistent directory that survives across conversations, introduced in Claude Code **v2.1.33 (February 2026)**. Three scopes are available:

| Scope | Location | Shareable via Git | Cross-project |
|-------|----------|:-:|:-:|
| `user` | `~/.claude/agent-memory/<name>/` | No | Yes |
| `project` | `.claude/agent-memory/<name>/` | **Yes** | No |
| `local` | `.claude/agent-memory-local/<name>/` | No | No |

The first **200 lines or 25KB** of `MEMORY.md` in the memory directory are injected into the subagent's system prompt at startup. The system auto-enables Read, Write, and Edit tools so the subagent can manage its memory files, even if those tools are not in the `tools` allowlist. The subagent is instructed to curate `MEMORY.md` when it exceeds limits.

For the deep-review use case, `memory: project` is the most interesting scope — a reviewer's accumulated knowledge about codebase patterns, recurring issues, and architectural decisions gets committed alongside the code and **shared across all developers** who pull the repo. New team members (and new agent sessions) inherit that institutional knowledge immediately. The `user` scope is per-developer and not shared; `local` is project-specific but excluded from version control.

Hooks defined in a subagent's frontmatter **run only while that specific subagent is active** and are cleaned up when it finishes. They do not propagate to the parent session or to other subagents. All hook events are supported (`PreToolUse`, `PostToolUse`, etc.), but the most common for subagents are `PreToolUse` (to validate commands before execution) and `PostToolUse` (to run linters after edits). Separately, `SubagentStart` and `SubagentStop` events in the parent session's `settings.json` let you hook into subagent lifecycle from the outside.

**Plugin-shipped agents cannot define hooks** — this is a hard security restriction. If the deep-review skill needs hooks on its agents (e.g., to validate that a reviewer doesn't exceed read-only scope), the agents must be defined at the project level (`.claude/agents/`) rather than bundled in the plugin.

## Recommendation: migrate to plugin with named agents, fall back to project-level files

Given the observed problem — inline `Agent()` dispatch consistently omitting `tools` and `effort` fields across 5/5 benchmark sessions — the migration path is clear. Named subagent definitions with frontmatter `tools:` fields make tool restrictions **deterministic and system-enforced**, eliminating the prompt-compliance failure mode entirely.

The recommended architecture combines three approaches. First, create a **plugin with named agents** in the `agents/` directory for distribution, each specifying strict `tools:` allowlists and `model:` overrides. Second, **inline critical skill content directly into agent system prompts** rather than using the `skills:` field, because the plugin-agent-skill cross-reference bug (#11955) makes the `skills:` field unreliable for plugin-bundled agents. Third, maintain **project-level `.claude/agents/` copies as fallback** for teams that haven't adopted the plugin, since project-level agents take precedence over plugin agents anyway and serve as an override mechanism.

The one gap this architecture cannot fill: plugin agents cannot define hooks. If your review workflow needs `PreToolUse` hooks to validate that Bash commands stay read-only (e.g., blocking `rm`, `mv`, `git push`), those hooks must live in the project's `.claude/settings.json` or in the project-level agent definitions — not in the plugin. This split (agents in plugin for distribution, hooks in project settings for enforcement) is an unavoidable constraint of the current security model, which deliberately prevents plugins from controlling permission-sensitive features.
