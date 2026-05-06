# Designing hierarchical REVIEW.md configuration from real-world precedent

**The strongest pattern for a directory-scoped REVIEW.md system is "nearest-only with explicit inheritance"** — the model adopted by Ruff, Biome v2, and ESLint's flat config after years of painful lessons with implicit cascading. CLAUDE.md's own hierarchy uses an additive merge model where all discovered files combine with specificity-based precedence, but multiple tools that tried similar implicit cascading (ESLint legacy, ASP.NET Web.config) eventually retreated from it. The ideal REVIEW.md system would combine a root-level config establishing global defaults with optional subdirectory files that explicitly declare their relationship to the parent — whether they extend, override, or stand alone.

## How CLAUDE.md's directory hierarchy actually works

CLAUDE.md uses an **additive merge with specificity-based precedence** model. Claude Code recursively discovers CLAUDE.md files from multiple locations and merges their contexts, with more specific locations taking precedence over broader ones when instructions conflict. This is neither pure override nor pure cascade — all files contribute to the context simultaneously.

The resolution order, from highest to lowest precedence, follows a clear hierarchy. **Managed policy files** (system-level, at `/etc/claude-code/CLAUDE.md` on Linux or `/Library/Application Support/ClaudeCode/CLAUDE.md` on macOS) load first and cannot be excluded. Next comes the **user global** file at `~/.claude/CLAUDE.md`, followed by the **project root** `./CLAUDE.md` or `./.claude/CLAUDE.md`. Parent directory CLAUDE.md files load by walking up from the current working directory. All of these load at launch.

The critical architectural distinction is **lazy loading for subdirectories**. CLAUDE.md files below the working directory do not load at startup — they load on demand when Claude reads or edits files in those subdirectories. This design optimizes token usage in monorepos where loading every package's instructions upfront would be wasteful. However, multiple GitHub issues (#2571, #3529, #24987) report that this on-demand loading doesn't always work reliably, particularly in the VS Code extension.

CLAUDE.md also supports a complementary `.claude/rules/*.md` system where rule files with `paths` YAML frontmatter activate only when Claude touches files matching specified glob patterns. This is functionally similar to CodeRabbit's `path_instructions` — path-scoped rules living in a centralized location rather than distributed across directories. The `@import` syntax allows CLAUDE.md files to reference other files inline, with imports resolving relative to the containing file and supporting up to **5 hops** of recursion.

One crucial caveat for any REVIEW.md design: **CLAUDE.md instructions are advisory, not deterministic.** The system prompt notes that CLAUDE.md content "may or may not be relevant" to the current task. For rules that must execute every time, Anthropic recommends hooks (deterministic shell commands). A REVIEW.md system for code review should consider whether certain rules need enforcement guarantees beyond advisory context injection.

## The industry has converged on nearest-only with explicit extends

Seven major developer tools reveal three distinct inheritance models, and the industry trend strongly favors one of them.

**ESLint's cautionary tale is the most instructive.** Its legacy `.eslintrc` system used full merge-up cascading — searching from the file's directory upward, merging all found configs with the closest taking precedence for conflicts. The `root: true` flag stopped upward traversal. This model proved deeply problematic at scale. The ESLint team wrote: "The config cascade continued to cause problems for users. Most frequently, people wouldn't realize that they had a config file in an ancestor directory... This would create confusion because they would be getting ESLint settings that they seemingly hadn't configured." ESLint's flat config system (`eslint.config.js`) abandoned directory cascading entirely in favor of a single file with glob-based path targeting. The `root: true` flag was removed because flat config acts as if `root: true` is always set.

**EditorConfig** succeeds with nearest-ancestor merging because its scope is narrow — just **indent style, line endings, and character encoding**. Properties from all ancestor `.editorconfig` files merge, with closer files winning per-property. The `root = true` flag stops upward traversal. This model works precisely because EditorConfig has very few properties with simple, non-interacting values. Complex rule systems with hundreds of interacting settings would suffer under this model.

**Prettier takes the simplest approach**: nearest-only, no cascading, no merging. Only one config file is ever used — the first one found walking upward. There is no `root` flag because the search stops at the first file. Prettier intentionally rejects global configuration to guarantee identical behavior across machines.

**Ruff and Biome represent the modern consensus.** Ruff finds the nearest config and ignores all parent configs, but provides an explicit `extend` field for opt-in inheritance (`extend = "../pyproject.toml"`). Biome v2 adds a `root` boolean on nested configs and an `extends: "//"` microsyntax meaning "extend from the root configuration regardless of nesting depth." Both tools make inheritance visible and intentional rather than implicit and surprising.

| Tool | Model | Merges ancestors? | Stop mechanism | Explicit extends |
|------|-------|-------------------|----------------|-----------------|
| ESLint (legacy) | Merge-up cascade | Yes | `root: true` | `extends` key |
| ESLint (flat) | Single-file array | N/A | Always root | `extends` in array |
| EditorConfig | Nearest-ancestor merge | Yes (per-property) | `root = true` | None |
| Prettier | Nearest-only | No | Stops at first | None |
| Ruff | Nearest-only | No | Stops at first | `extend` field |
| Biome v2 | Nearest + explicit | No | `root: true/false` | `extends: "//"` |

The pattern producing **least developer surprise** is nearest-only resolution with opt-in explicit inheritance. This gives predictability (you always know which config applies) while supporting monorepos when explicitly requested.

## AI code review tools split between centralized path rules and distributed files

Only two AI code review tools offer genuine per-path rule customization: **CodeRabbit** and **GitHub Copilot code review**. The rest limit path-based configuration to file exclusion.

CodeRabbit's `path_instructions` system embeds per-directory review rules inside a single `.coderabbit.yaml` at the repo root. Each entry pairs a glob pattern with natural language instructions up to **10,000 characters**. Multiple patterns can match a single file, and all matching instructions combine. This centralized model means one file controls all path-specific review behavior, with precedence flowing from YAML config → repository settings → organization settings.

GitHub Copilot code review takes a **distributed approach** with `*.instructions.md` files in `.github/instructions/`. Each file uses YAML frontmatter with an `applyTo` property specifying glob patterns, then Markdown-format natural language instructions in the body. This is architecturally closer to what a distributed REVIEW.md system would look like — individual instruction files scoped to specific paths.

**Greptile provides the most relevant precedent for REVIEW.md design.** They explicitly moved from a single `greptile.json` to a cascading `.greptile/` directory system after documenting the pain points of centralized config in monorepos: "Monorepos with multiple teams can't express 'strict about SQL injection in the database package, lenient about logging in scripts.' Everyone shares one file. Ownership conflicts happen when multiple teams need different review rules." Their hybrid solution uses clear rules: **settings are overridden, but rules and context are combined**. Child directories inherit all parent rules and only specify differences. Org-level enforced rules cannot be disabled by any local configuration.

Codacy, DeepSource, and Sourcery all support only path exclusion — you can tell them to skip directories but cannot specify different review standards per directory. This limitation pushes teams toward the underlying linter's own per-directory config (like `.eslintrc` files) rather than the review tool's configuration.

## Config scaffolding should start minimal and grow deliberately

First-time config creation patterns split into three camps. **Interactive wizards** (ESLint's `npm init @eslint/config` asks 5-7 questions about framework, TypeScript, modules) generate minimal, functional configs tailored to the project. **Template-based generators** (Biome's `biome init` creates ~10 lines, .NET's `dotnet new editorconfig` creates 200+ settings with extensive comments) produce files without user interaction. **No scaffolding** (Prettier recommends manually creating an empty `{}` file) relies on sensible defaults.

The most effective pattern for a REVIEW.md init command draws from several best practices:

- **Start minimal, grow over time.** ESLint, Biome, Prettier, and the Ruff community all advocate starting with defaults and adding rules incrementally. A comprehensive initial file overwhelms users and discourages customization.
- **Include explanatory comments** when the format supports them. The .NET editorconfig template is exemplary — every section has inline documentation explaining what each setting does and what values are valid.
- **Detect the environment.** ESLint's init detects frameworks and languages; a REVIEW.md init should detect project structure (monorepo vs single package), languages present, and existing CI configuration.
- **Include schema references.** Biome and CodeRabbit embed `$schema` URLs for editor autocompletion and validation. A REVIEW.md system using YAML or JSON should do the same.
- **Never overwrite existing config.** Ruff's proposed init emphasizes appending to existing files. A REVIEW.md init should detect existing configurations and either merge or warn.

A REVIEW.md scaffolding command should generate a minimal file with 3-5 commented sections (project context, global rules, confidence thresholds, ignore patterns) plus a link to full documentation, rather than a comprehensive template that users won't read.

## What belongs at root versus directory level

The scoping question has a clear answer from cross-tool analysis. **Root-level configuration** should contain settings that apply universally and establish the project's baseline: global ignore patterns (generated code, vendor directories, build artifacts), default confidence thresholds for flagging issues, shared coding standards and style preferences, CI integration settings, and organization-mandated policies that cannot be overridden.

**Directory-level REVIEW.md files** earn their complexity cost in specific scenarios. The strongest case is **security-sensitive directories** — `src/auth/`, `src/crypto/`, `src/payments/` — where stricter review standards, mandatory security-focused checks, and lower confidence thresholds for flagging issues are justified. The second case is **technology boundaries** in polyglot or monorepo projects where `packages/frontend/` needs React-specific review guidance while `packages/api/` needs different patterns. The third case is **team ownership boundaries** where different teams have different standards and want autonomy over their review configuration.

The case against subdirectory REVIEW.md files is maintenance burden. Greptile's documentation explicitly notes that distributed configs create "merge conflicts in config" and reduce "visibility into what rules actually apply to a specific file without mentally resolving the entire config." The Google SRE Workbook emphasizes that configuration changes should be "deliberate, testable, and auditable" — distributed configs make auditing harder.

A pragmatic REVIEW.md design should **default to root-only configuration with path-based rules** (like CodeRabbit's `path_instructions`) and support subdirectory REVIEW.md files as an opt-in power feature for monorepos and large teams, with explicit `extends: root` or `standalone: true` declarations.

## Tools should suggest config changes, never auto-modify

The consensus across infrastructure engineering, SRE literature, and developer tooling is emphatic: **tools should suggest configuration changes through reviewable mechanisms, not modify files automatically.** The Google SRE Workbook warns that "trivial configuration changes can impact a production system in dramatic ways" and recommends deliberate, testable, auditable changes. Renovate Bot provides the gold-standard pattern — it creates pull requests to suggest config migrations rather than directly modifying files.

For a REVIEW.md system, this means dismissed findings should not automatically append to an ignore list in the config file. Instead, the tool should suggest additions via PR comments or a separate command (`review config add-ignore RULE-123`). Stale configuration should trigger warnings ("this rule references a path that no longer exists") rather than silent removal. **Configuration drift detection** — comparing the REVIEW.md against actual project structure and flagging contradictions — is valuable but should produce reports, not automated fixes.

Config versioning deserves explicit support. A `version` field in REVIEW.md enables migration tooling when the schema evolves. Schema evolution should follow the principle of backward compatibility: add new fields with sensible defaults, deprecate rather than remove old fields, and provide migration scripts that generate reviewable diffs.

## Centralized path rules vs distributed files is a false binary

The single-file versus multi-file debate resolves into a spectrum with a clear sweet spot. **Pure centralized** (one file with all path rules) works for small-to-medium projects but breaks down in monorepos with multiple teams — CodeRabbit users with 50+ path_instructions entries find the file unwieldy. **Pure distributed** (ESLint legacy cascading) creates debugging nightmares and surprising interactions. The emerging best practice is a **hybrid with explicit composition**.

The optimal REVIEW.md architecture mirrors Biome v2 and Greptile's approach:

- A **root REVIEW.md** establishes global defaults, shared rules, and path-based instructions for common patterns (test directories, generated code, CI scripts)
- **Subdirectory REVIEW.md files** are optional and must explicitly declare their relationship: `extends: root` (inherit and add/override), `extends: ../REVIEW.md` (inherit from specific parent), or `standalone: true` (ignore all ancestors)
- **Settings override** (confidence thresholds, severity levels) while **rules and context accumulate** (a subdirectory inherits parent rules and adds its own)
- An **organization-level enforced rules** mechanism ensures security policies cannot be disabled by any local configuration

This hybrid gives small projects the simplicity of a single file while giving monorepos the flexibility of distributed ownership. The explicit `extends` declaration eliminates the implicit cascading that plagued ESLint's legacy system. Most importantly, it makes the inheritance chain visible — a developer reading `src/auth/REVIEW.md` can immediately see whether it extends the root or stands alone, without needing to understand an implicit resolution algorithm.

## Conclusion

Three design principles emerge from this cross-tool analysis. First, **make inheritance explicit, not implicit** — the universal lesson from ESLint's retreat from cascading, Ruff's `extend` field, and Biome's `extends: "//"` syntax. A REVIEW.md in a subdirectory should declare its relationship to its parent, never inherit silently. Second, **separate what overrides from what accumulates** — Greptile's distinction between settings (override) and rules (combine) prevents the common failure mode where a subdirectory config accidentally disables important parent rules. Third, **start with the centralized model and offer distributed as an escape hatch** — most projects will never need subdirectory REVIEW.md files, and the path-based rules pattern (à la CodeRabbit's `path_instructions`) handles 80% of per-directory customization needs within a single root file. The distributed model should exist for the 20% of projects — primarily large monorepos with multiple teams — where centralized config creates genuine ownership conflicts.
