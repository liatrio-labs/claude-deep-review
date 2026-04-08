# How Claude Code's sandbox decides which Bash commands to auto-allow

Claude Code's sandbox auto-allow system uses **tree-sitter-bash WASM to build a full AST of every command**, then applies a fail-closed allowlist of recognized node types before checking redirect targets against the write allowlist. Any unrecognized AST node — including ANSI-C quoting (`$'...'`), bare variable expansion (`$VAR`), command substitution (`$(...)`), and brace expansion (`{a,b,c}`) — causes the parser to return `too-complex`, which triggers a permission prompt *even when `autoAllowBashIfSandboxed: true` is set*. This is a known, unresolved architectural conflict: the static analyzer gates auto-allow decisions before the sandbox trust model gets a chance to override them. Issue #43713, filed April 5, 2026, documents this comprehensively and remains open with no Anthropic response.

## The parser uses tree-sitter-bash AST analysis with a strict node-type allowlist

The primary parsing gate lives in `src/utils/bash/ast.ts`, which calls **tree-sitter-bash compiled to WASM** to produce a full abstract syntax tree. The function `parseForSecurityFromAst` walks this tree against a hardcoded allowlist of "safe" node types.

**Structural nodes** that the walker traverses into include `program`, `list`, `pipeline`, and `redirected_statement`. When the walker reaches leaf nodes (commands, arguments, strings), it flattens each command segment into a normalized `SimpleCommand` structure:

```typescript
type SimpleCommand = {
  argv: string[]           // argv[0] = command name, rest = resolved arguments
  envVars: { name: string; value: string }[]
  redirects: Redirect[]    // Output/input redirections extracted separately
  text: string             // Original source span
}
```

This normalization eliminates quoting ambiguity — downstream validators work with resolved argument arrays, not raw strings. The critical design principle is **fail-closed**: any AST node type not explicitly in the allowlist causes an immediate `too-complex` return, forcing a permission prompt. This is why so many legitimate shell constructs trigger prompts — they produce AST nodes the allowlist doesn't cover.

Beyond tree-sitter, Claude Code maintains **three separate parsers** that make load-bearing security decisions simultaneously: `splitCommand_DEPRECATED` (using the `shell-quote` npm library, still called in 9+ files), `tryParseShellCommand`, and `ParsedCommand.parse` (tree-sitter-based). A documented parser differential exists where `shell-quote` treats `\r` as a token boundary (because JavaScript's `\s` includes carriage return) while bash's IFS does not — creating a known attack vector for permission bypass.

## Why `$'...'` triggers a prompt but regular quotes don't

The tree-sitter-bash parser produces an `ansi_c_string` AST node for `$'...'` syntax. **This node type is not in the allowlist**, so `parseForSecurityFromAst` immediately returns `too-complex`. The permission prompt shows "Contains ansi_c_string."

Within the 25+ regex-based security validator chain in `bashSecurity.ts`, only `validateObfuscatedFlags` recognizes ANSI-C quoting. However, `extractQuotedContent` — the function used by **all other validators** to parse quoted strings — does not understand `$'...'` syntax at all. The source itself warns about this fragility. So the system has partial, inconsistent handling: one validator catches it as potentially dangerous, but the core content-extraction function ignores it entirely.

Regular single quotes (`'...'`) and double quotes (`"..."`) produce AST node types that *are* in the allowlist, so they parse successfully and the command proceeds to auto-allow evaluation. The distinction is purely about which node types tree-sitter produces and whether those types appear in the hardcoded allowlist.

## A detailed matrix of which Bash syntax patterns trigger prompts

Issue #43713 provides a precise behavior matrix tested on **v2.1.92 (macOS, Apple Silicon)**. The results reveal inconsistencies that stem from incomplete AST node coverage:

**Auto-approved (allowlisted node types)**:
- Simple commands: `ls /tmp`, `cat /etc/hosts`
- Semicolons, pipes, logical operators: `date; uptime | tail -1`
- Control flow: `if true; then echo y; fi`
- Test expressions: `[[ -f /etc/hosts ]] && echo yes`
- Here-strings: `cat <<< "hello"`
- Mixed literal+expansion strings: `echo "user is $USER"`, `echo "$HOME/x"`

**Triggers permission prompt (unrecognized node types)**:

| Pattern | AST node produced | Reason shown |
|---------|-------------------|--------------|
| `echo $USER`, `ls $HOME` | `simple_expansion` | "Contains simple_expansion" |
| `echo "$HOME"` (expansion-only string) | `string` | "Unhandled node type: string" |
| `echo $(date)` | `command_substitution` | "Contains command_substitution" |
| `echo $'hello world'` | `ansi_c_string` | "Contains ansi_c_string" |
| `echo {a,b,c}` | `brace_expression` | "Contains brace_expression" |
| Heredocs with `${var}` | parse failure | "Bad substitution" error |

A striking inconsistency: **`echo "user is $USER"` auto-approves** but **`echo "$HOME"` prompts**. This suggests the parser handles `string` nodes containing a mix of literal text and expansions differently from strings consisting entirely of an expansion. The tree-sitter AST likely produces different node structures for these cases, and only one variant appears in the allowlist.

Heredocs have additional problems beyond auto-allow. Issue #18499 documents that `${idx}` inside heredoc bodies causes a "Bad substitution" parse error that breaks the entire session. Issue #9323 shows that JavaScript template literal syntax (`${func()}`) inside single-quoted heredocs (`<<'EOF'`) also fails, even though single-quote heredocs should pass content literally. Issue #18713 reveals a self-contradicting design: the system prompt instructs Claude to use heredocs for `git commit`, but heredocs create temp files in `/tmp` which the sandbox blocks (only `/tmp/claude/` is writable).

## Redirect targets must be literal strings resolved from the AST

Redirects (`>>`, `>`) are extracted during AST parsing and stored in the `redirects` field of each `SimpleCommand`. The `validateRedirections` validator in `bashSecurity.ts` then checks these targets against the write allowlist.

Path validation occurs through several functions in `pathValidation.ts`: **`isPathAllowed`** is the primary entry point, `isDangerousRemovalPath` blocks `rm` on system roots (`/etc`, `/usr`, `/var`, `/bin`), and `expandTilde` safely resolves `~` to `$HOME` while explicitly blocking `~username` expansion. The function `normalizeCaseForComparison` lowercases paths before dangerous-file checks, preventing case-manipulation bypass on macOS/Windows (e.g., `.cLauDe/Settings.locaL.json`).

**The redirect target must be a literal string** that the AST parser can fully resolve. If the target path contains a variable (`$VAR`), the AST produces a `simple_expansion` node which triggers the `too-complex` path before redirect validation ever runs. The parser cannot resolve variables — it has no access to the shell environment. This means `echo x >> $TMPDIR/out.log` will always prompt, even if `$TMPDIR` resolves to an allowlisted path.

A subtle security gap exists in `validateRedirections`: it's classified as a "non-misparsing" check. If it catches a dangerous redirect but no "misparsing" validator also fires, the permission layer may discard the warning when the user has a matching allow rule like `Bash(echo:*)`.

## Five conditions must all be true for auto-allow

For a Bash command to execute without a permission prompt under `autoAllowBashIfSandboxed: true`, the complete pipeline must pass:

1. **Sandbox is available and enabled**: The platform must be macOS (Seatbelt), Linux (bubblewrap), or WSL2+. The `sandbox.enabled` setting must be `true`. Checked by `checkSandboxAutoAllow` in `bashPermissions.ts`.

2. **`autoAllowBashIfSandboxed` is `true`**: This is the default. Combined with condition 1, this enables the auto-allow path.

3. **The static analyzer must fully parse the command**: Every AST node produced by tree-sitter-bash must be in the hardcoded allowlist. Any `simple_expansion`, `command_substitution`, `ansi_c_string`, `brace_expression`, or other unrecognized node causes a `too-complex` return that **overrides the sandbox trust model**. This is the root cause of issue #43713.

4. **All redirect targets must be in the write allowlist**: Paths extracted from `>` and `>>` operators are checked against allowed write directories (CWD and subdirectories by default, plus configured `sandbox.filesystem.allowWrite` paths). Paths must be literal strings. Mandatory deny paths are always enforced: `.bashrc`, `.bash_profile`, `.zshrc`, `.gitconfig`, `.gitmodules`, `.mcp.json`, and directories like `.git/hooks/`, `.vscode/`, `.claude/`.

5. **The command must not be in the excluded commands list**: `sandbox.excludedCommands` patterns (exact, prefix, wildcard) are checked, with iterative stripping of env vars and wrapper commands (e.g., `timeout 300 FOO=bar bazel run` is analyzed to extract `bazel`).

The permission evaluation order is: deny rules → ask rules → allow rules (first match wins), then config rules, pre-tool hooks, the ML-based "YOLO classifier" (a two-stage LLM that reviews commands), static analysis, security validators, path validation, and finally the sandbox auto-allow check. Critically, **static analysis runs before sandbox auto-allow**, which is why the auto-allow setting is effectively bypassed for any command the parser can't fully understand.

## Subagents face a fundamentally different permission environment

Multiple open issues (#25526, #37730, #27661, #29610) confirm that **subagent sessions do not inherit parent session permissions, hooks, or sandbox settings**. The differences are significant:

Subagents launched via the Task tool cannot show interactive UI dialogs. Any undecided permission prompt that reaches the interactive handler is **auto-denied** for subagents — there's no user to approve it. This means that commands producing `too-complex` from the static analyzer, which would show a prompt in the main session, silently fail in subagent sessions. The only escape is for pre-tool hooks to pre-approve specific operations, or for the parent to use `bypassPermissions` mode (which itself has restrictions: issue #29610 shows `bypassPermissions` still blocks Bash/Read access outside the project root for background subagents).

Global permission settings like `Bash(cat:*)` also don't propagate — every subagent re-prompts independently. Project-scoped settings from `.claude/settings.json` may not apply in worktree sessions. This creates a compounding problem: commands that already trigger false-positive prompts due to the static analyzer become completely unusable in subagent contexts.

## Source code, documentation, and changelog references

The implementation details come from several authoritative sources. The **official documentation** at `code.claude.com/docs/en/sandboxing` describes the sandbox architecture, configuration schema, OS-level enforcement (Seatbelt/bubblewrap), and auto-allow modes. It reports **~84% fewer permission prompts** with auto-allow mode enabled. The **sandbox-runtime package** (`@anthropic-ai/sandbox-runtime`) is open-source at `github.com/anthropic-experimental/sandbox-runtime` under Apache-2.0, containing the `SandboxManager` class, proxy implementations, and platform-specific sandboxing code.

The Claude Code source code itself was first exposed through npm sourcemaps in v2.1.88 (March 31, 2026) and later officially added to the repository. Key files total **12,414 lines** for the BashTool alone — 90% dedicated to safety. The `CHANGELOG.md` contains relevant entries including a v2.1.34 fix for excluded commands bypassing permissions (the inverse of #43713), fixes for compound command permission matching, and additions to the read-only auto-approval allowlist (`lsof`, `pgrep`, `tput`, `ss`, `fd`, `fdfind`).

The settings schema at `json.schemastore.org/claude-code-settings.json` documents all configuration options. An example configuration lives at `examples/settings/settings-bash-sandbox.json` in the repository.

## Conclusion

The core architectural tension in Claude Code's sandbox auto-allow system is that **static analysis gates the auto-allow decision**. The tree-sitter-bash AST parser's fail-closed design — essential for security — means any unrecognized node type blocks auto-approval, even when OS-level sandboxing would contain the command's effects. The fix proposed in issue #43713 is straightforward: check sandbox auto-allow *before* returning `too-complex` from the static analyzer. Until this ships, real-world commands containing `$VAR`, `$(cmd)`, `$'...'`, `{a,b,c}`, or heredocs with variables will continue triggering prompts, making the documented "sandbox + auto-allow" workflow unreliable for automated pipelines. The three-parser architecture and inconsistent node-type coverage add further fragility — `echo "user is $USER"` auto-approves while the semantically equivalent `echo "$USER"` prompts, a distinction that has no security justification.