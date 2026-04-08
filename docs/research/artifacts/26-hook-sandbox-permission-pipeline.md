# How Claude Code resolves hooks, sandbox, and permissions for every Bash call

**PreToolUse hooks always fire first — before sandbox auto-allow, before permission mode checks, before everything.** A hook returning `permissionDecision: "deny"` will block a Bash command even when `autoAllowBashIfSandboxed: true` is active, even under `bypassPermissions` mode, and even with the `--dangerously-skip-permissions` flag. The sandbox auto-allow check operates downstream in the permission pipeline, meaning hooks sit above it architecturally and can override it in the deny direction. This design is intentional: hooks enforce policy that no other setting can circumvent. The reverse, however, is asymmetric — a hook returning `"allow"` cannot loosen restrictions past what deny rules permit, a principle hardened by a critical security fix in **v2.1.77** (March 18, 2026).

## The complete decision tree from tool call to execution

When Claude generates a Bash tool call, the evaluation pipeline proceeds through a strict waterfall. Understanding this sequence resolves every interaction question between hooks, sandbox, and permissions.

**Stage 1 — PreToolUse hooks fire (all matching hooks, in parallel).** Every hook whose `matcher` regex matches `"Bash"` and whose optional `if` condition (e.g., `Bash(git commit *)`) matches the command content executes simultaneously. Hooks from all sources — user settings, project settings, local settings, plugins, managed policy, skill/agent frontmatter — merge and run together. When multiple hooks return conflicting decisions, Claude Code applies **most-restrictive-wins precedence**: `deny > defer > ask > allow`. A single `deny` from any hook terminates the pipeline immediately. If hooks return `"allow"`, execution continues to Stage 2 — the allow does not skip subsequent deny-rule evaluation. If hooks return `"ask"`, the command is forced to the interactive permission prompt regardless of auto-allow settings.

**Stage 2 — Deny rules evaluated (from all settings scopes, merged).** Permission rules from managed settings, CLI arguments, local project, shared project, and user settings are concatenated and deduplicated. Deny rules are checked first. If any deny rule matches the command pattern (e.g., `Bash(rm -rf *)`) the call is **blocked unconditionally** — no other setting, mode, or hook can override a deny rule. This is true even if a PreToolUse hook previously returned `"allow"`.

**Stage 3 — Ask rules and tool-specific safety checks.** Ask rules force an interactive prompt. Safety checks for dangerous paths (`.git/`, `.claude/`, `.bashrc`, `.gitconfig`, `.zshrc`, `.vscode/`, `.idea/`) trigger prompts even in `bypassPermissions` mode — these are **bypass-immune** hardcoded protections added in v2.1.78.

**Stage 4 — Permission mode applied.** The active permission mode determines the default disposition: `bypassPermissions` approves everything reaching this stage, `acceptEdits` approves file operations, `plan` blocks modifications, `auto` routes to a two-stage Sonnet classifier, `dontAsk` denies anything not already resolved, and `default` falls through.

**Stage 5 — Sandbox auto-allow check.** If sandbox is enabled and `autoAllowBashIfSandboxed` is `true` (the default), a **per-command static analyzer** examines whether the command can be proven safe within the sandbox boundary. Commands with literal arguments, pipes, `&&`, `;`, `||`, and control flow auto-approve. Commands containing bare shell expansions (`$USER`, `$(date)`) may still trigger prompts because the static analyzer cannot prove them safe — this is a known limitation tracked in GitHub issue #43713. If the command passes static analysis, it executes inside the OS-level sandbox (Bubblewrap on Linux, Seatbelt on macOS) without prompting.

**Stage 6 — Allow rules evaluated.** If no prior stage resolved the command, explicit allow rules (e.g., `Bash(npm test)`) are checked. A match auto-approves the call.

**Stage 7 — User prompt or final denial.** In interactive mode, the user sees a permission dialog. In non-interactive/headless mode (`-p` flag), unresolved calls are denied. At this stage, `PermissionRequest` hooks fire if a dialog appears (note: these do not fire in non-interactive mode).

## Hook deny overrides everything, but hook allow cannot loosen restrictions

The asymmetry between deny and allow in hook decisions is the most important architectural principle. **A PreToolUse hook returning `permissionDecision: "deny"` is absolute** — it blocks execution before permission rules are even evaluated. This means a hook deny overrides `autoAllowBashIfSandboxed`, `bypassPermissions`, `--dangerously-skip-permissions`, and any allow rules in settings. The official documentation states: "This lets you enforce policy that users cannot bypass by changing their permission mode."

The reverse path has a critical guardrail: a hook returning `"allow"` only skips the interactive permission prompt. **Deny and ask rules from settings are still evaluated after a hook returns allow.** Prior to v2.1.77, this was broken — hooks returning `"allow"` could bypass deny rules, including enterprise managed settings deny lists. This was a significant security vulnerability, now fixed. The current rule is: hooks can tighten restrictions but never loosen them past what permission rules permit.

For exit-code-based hooks (not using JSON output), exit code **2** blocks the tool call, exit code **0** allows it to proceed, and exit code **1** produces a non-blocking warning. A bug fixed in **v2.1.90** caused hooks that emitted JSON to stdout *and* exited with code 2 to not correctly block — the JSON processing path was bypassing the exit-code denial check.

## autoAllowBashIfSandboxed evaluates per-command, not per-session

Each Bash command undergoes independent static analysis to determine whether it can run safely inside the sandbox. The setting `autoAllowBashIfSandboxed` is not a session-wide toggle that blanket-approves all commands — it gates a **per-command decision** based on whether the static analyzer can prove the command safe.

Commands the analyzer handles well include literal arguments, pipes, boolean operators (`&&`, `||`), semicolons, and standard control flow. Commands that fail static analysis and still trigger prompts despite the setting include those with bare shell expansions (`echo $USER`), command substitutions (`$(date)`), and certain unhandled AST node types. Notably, shell variables inside double-quoted strings (`echo "user is $USER"`) do auto-approve, but bare expansions do not. This gap is documented in issue #43713, where the reporter argues the sandbox boundary should be the security boundary rather than the static analyzer.

The sandbox filesystem configuration determines what paths are writable. By default, the current working directory and its subdirectories are read-write; everything else is read-only; and sensitive paths like `~/.ssh`, `~/.gnupg`, and credentials files are denied entirely. Custom `allowWrite` entries in `sandbox.filesystem` extend the writable zone. Critically, `Edit()` allow rules — not `Write()` rules — control bash filesystem writes in sandbox mode, because `Write()` only governs Claude's Write tool, not subprocess file operations.

## Plugin hooks and project hooks merge and run with equal priority

Plugin-level hooks (defined in `hooks/hooks.json` within the plugin directory) and project-level hooks (defined in `.claude/settings.json`) use nearly identical JSON schemas and **merge at runtime**. There is no execution priority difference between them — all matching hooks from all sources run in parallel, and the most-restrictive-wins rule applies to conflicting decisions.

The only structural difference is that plugin `hooks/hooks.json` files wrap the hook configuration in an object with an optional `description` field and use environment variables `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` for portable paths. Project hooks use relative paths resolved against the project root.

Hook sources and their scoping behavior are as follows:

- **Managed policy hooks** (organization-level): Cannot be overridden by any other level. Enterprise admins can set `allowManagedHooksOnly: true` to block all user, project, and plugin hooks
- **User hooks** (`~/.claude/settings.json`): Apply to all projects on the machine
- **Shared project hooks** (`.claude/settings.json`): Apply to the project, committed to version control
- **Local project hooks** (`.claude/settings.local.json`): Apply to the project, gitignored
- **Plugin hooks** (`hooks/hooks.json`): Active when the plugin is enabled, merge with other hooks
- **Skill/agent frontmatter hooks**: Scoped to the component's lifecycle only, cleaned up when the skill or subagent finishes; `Stop` hooks in agent frontmatter auto-convert to `SubagentStop`

The `/hooks` menu in Claude Code labels each hook with its source (`[User]`, `[Project]`, `[Local]`, `[Plugin]`, `[Session]`, `[Built-in]`) for transparency.

## Settings and configurations that control hook execution alongside auto-allow

Because hooks fire before auto-allow by default, no special setting is needed to "force" hooks to run when `autoAllowBashIfSandboxed` is active — they already do. However, several settings can suppress or constrain hook execution:

- **`disableAllHooks: true`** disables all hooks across every scope. If set in managed settings, only a managed-level override can re-enable them
- **`allowManagedHooksOnly: true`** (managed settings only) blocks user, project, and plugin hooks while preserving managed and SDK hooks
- **`--bare` flag** skips hooks, LSP, plugin sync, and skill directory walks entirely — a complete bypass of the hook system
- **The `if` field** (added in v2.1.85) narrows when a hook handler spawns, using permission rule syntax like `"Bash(git commit *)"`. This does not affect whether hooks fire but filters which handlers within a matched hook group actually execute
- **The `once` field** (skills only) causes a hook handler to run once per session and then self-remove
- **The `async: true` field** runs a hook in the background without blocking tool execution — useful for logging but dangerous for security enforcement
- **The `timeout` field** defaults to 600 seconds for command hooks, 30 seconds for prompt hooks, and 60 seconds for agent hooks

The Hookify plugin provides an alternative rule-authoring surface using Markdown files with YAML frontmatter (`.claude/hookify.{rule-name}.local.md`), which translate into PreToolUse hooks at runtime. Hookify rules take effect immediately without session restart.

## Historical bugs reveal the pipeline's fragility

The hook-sandbox-permission pipeline has been incrementally hardened through a series of bug fixes that illuminate its internal architecture:

| Version | Fix | What it reveals |
|---------|-----|-----------------|
| **v2.1.34** | Excluded commands (`sandbox.excludedCommands`) could bypass Bash ask rules when `autoAllowBashIfSandboxed` was enabled | Sandbox exclusion was evaluated before permission rules |
| **v2.1.77** | Hooks returning `"allow"` bypassed deny rules, including enterprise managed settings | Hook results were applied before deny-rule evaluation |
| **v2.1.78** | Protected directories (`.git`, `.claude`) writable without prompt in bypass mode | Added bypass-immune safety checks |
| **v2.1.90** | Hooks emitting JSON + exit code 2 not blocking | JSON processing path bypassed exit-code denial |
| **Issue #20946** (open) | Hooks fire but don't block synchronously in `--dangerously-skip-permissions` mode | Bypass flag makes the pipeline asynchronous; commands execute while hooks run in background |
| **Issue #37420** (open) | A hook returning `"ask"` permanently switches the session out of bypass mode | State management bug in permission mode tracking |

Issue #20946 is particularly concerning: a user demonstrated that with `--dangerously-skip-permissions`, a PreToolUse hook's denial arrived **37 seconds** after the command already executed. Nine hook denials were issued while five git commits succeeded. This suggests that in bypass mode, the pipeline may not wait for hooks synchronously — undermining the documented guarantee that hook denials are absolute.

## Conclusion

The documented architecture places PreToolUse hooks at the top of the evaluation chain, firing before sandbox auto-allow, before permission mode checks, and before any allow/deny rule evaluation. A hook `deny` is architecturally the strongest veto in the system, while a hook `allow` is the weakest approval — it can be overridden by any downstream deny rule. The `autoAllowBashIfSandboxed` setting operates per-command through static analysis at a later pipeline stage, meaning hooks always get first say. Plugin and project hooks carry equal runtime priority, merging and executing in parallel with most-restrictive-wins conflict resolution.

However, the gap between documented behavior and actual behavior is non-trivial. Open issues demonstrate that hook denials may not block synchronously in bypass mode (#20946), that the static analyzer undermines `autoAllowBashIfSandboxed` for common shell constructs (#43713), and that hook interactions with permission modes can corrupt session state (#37420). Organizations building security-critical hook policies should pin to versions at or after **v2.1.90**, avoid combining hooks with `--dangerously-skip-permissions` until #20946 is resolved, and test hook enforcement under their exact permission mode and sandbox configuration rather than relying solely on documented guarantees.