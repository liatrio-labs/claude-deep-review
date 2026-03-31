# Writing REVIEW.md files that actually improve code quality

**The single most important insight from cross-referencing CodeRabbit, Greptile, SonarQube, ESLint, and practitioner case studies: keep 15–25 high-signal rules per file, always include rationale, and use prescriptive language for security and correctness but directional language for design preferences.** Frontier LLMs can reliably follow roughly 150–200 total instructions before adherence degrades uniformly across all rules — and your review system's own system prompt already consumes 50+ of those slots. This means every rule you add competes for attention, making precision in rule writing the highest-leverage activity in your entire configuration.

The research draws on Anthropic's internal code review data (where AI reviews caught issues missed in 84% of previously rubber-stamped PRs), Beko's industrial case study of 4,335 PRs with 73.8% acceptance rate on AI suggestions, the SmartBear/Cisco study of 2,500 reviews across 3.2M lines, and real-world configurations from CodeRabbit (13M+ PRs reviewed), Greptile, Cursor, and open-source repositories like Appsmith and Nx.

---

## How to write rules that AI reviewers actually follow

The difference between a rule that catches bugs and one that generates noise comes down to three properties: **specificity**, **rationale**, and **verifiability**. Research from Anthropic's prompt engineering documentation, HumanLayer's CLAUDE.md guide, and DataCamp's configuration experience converge on a consistent framework.

**Prescriptive rules** ("All async methods MUST accept CancellationToken as the last parameter") produce binary pass/fail evaluations with low false-positive rates. Use these for security and correctness where violations are always wrong. **Directional rules** ("Prefer immutable types where practical") handle edge cases gracefully but produce inconsistent flagging. Use these for style and design preferences. CodeRabbit's pre-merge checks formalize this distinction with `error` mode for prescriptive rules and `warning` mode for directional ones.

Always include rationale. DataCamp's CLAUDE.md guide captures why: "Never force push" is a flat instruction the AI might ignore under pressure, but "Never force push — this rewrites shared history and is unrecoverable for collaborators" gives the AI enough context to generalize. It won't just avoid `git push --force`; it'll also hesitate before `git reset --hard` on a shared branch. Anthropic's own documentation explicitly recommends explaining constraints because rationale helps the model apply rules correctly in edge cases it hasn't seen.

**Rule length sweet spot**: one-liners for unambiguous prescriptive rules, 2–3 sentences with rationale for contextual rules. CodeRabbit's path_instructions support up to 10,000 characters per instruction block, but practitioners report that concise, deterministic pass/fail criteria outperform lengthy paragraphs. When a rule needs examples, reference a separate document rather than inlining — this follows the progressive disclosure pattern that HumanLayer recommends for keeping CLAUDE.md files under 60 lines.

**Severity hints** embedded in rules significantly improve AI reviewer behavior. Structure critical rules with explicit severity markers: "CRITICAL: Never store secrets in code or config files" versus "SUGGESTION: Consider extracting magic numbers into named constants." But use IMPORTANT or MUST sparingly — DataCamp warns that "if every rule is marked important, the emphasis becomes invisible."

Here are concrete examples of well-written versus poorly-written rules:

**Effective rules:**
```
- All async methods must accept CancellationToken as the last parameter.
  Omitting tokens prevents graceful shutdown and causes resource leaks
  under load.

- CRITICAL: Never use .Result or .Wait() on async calls. This deadlocks
  ASP.NET Core's synchronization context. Use await instead.

- Validate all API request bodies with Zod schemas at the boundary.
  Use .safeParse() instead of type assertions — runtime validation
  catches contract drift that TypeScript compilation misses.

- EF Core queries in loops indicate N+1 problems. Use .Include() for
  eager loading or restructure to batch queries. Flag any LINQ
  expression inside a foreach/for loop that touches DbContext.
```

**Ineffective rules:**
```
- Write clean code
- Follow best practices
- Make sure code is readable
- Check for security issues
- Format code properly
```

The ineffective rules fail because they're unverifiable — the AI cannot determine a binary pass/fail condition, so it either flags everything or nothing.

---

## The 15–25 rule ceiling and why it matters

Research on LLM instruction-following reveals a hard constraint that should drive your entire configuration strategy. Frontier models (Claude Opus, GPT-4) can follow approximately **150–200 total instructions** with reasonable consistency. Beyond that threshold, adherence degrades uniformly — the model doesn't just ignore new rules; it starts ignoring all of them more frequently. Smaller models degrade exponentially rather than linearly.

Your review system's built-in system prompt already consumes roughly 50 instructions. Each REVIEW.md file in the hierarchy adds to this total. With three files (root + backend + frontend), you have roughly **100–150 slots** shared across all three. This means **15–25 rules per file** is the practical ceiling before signal-to-noise degrades.

The SmartBear/Cisco study corroborates this from the human side: checklist-driven reviews increase defect detection by over **66.7%**, but each person typically makes the same 10 mistakes repeatedly. Personal checklists of 15–20 items are the recommended maximum. The parallel to AI review rules is direct — focus on the 15–25 rules that catch the bugs your team actually introduces, not a comprehensive catalog of everything that could theoretically go wrong.

LLMs also exhibit a **peripheral bias** — they attend more strongly to instructions at the beginning and end of the prompt. Place your most critical rules (security, correctness) first and your most commonly violated rules last.

---

## Where each rule belongs: the placement framework

The hierarchical accumulation model (settings override, rules accumulate) creates a natural taxonomy. The key principle borrowed from EditorConfig's design: **root config = shared baseline of universal rules; subdirectory = only what differs for that technology stack.**

**Root REVIEW.md** should contain rules that apply regardless of language, framework, or directory:

- Security rules (secrets exposure, authentication checks, input validation principles)
- Architecture principles (dependency direction, module boundaries, API contract stability)
- Git and CI conventions (commit message format, PR size limits, required CI checks)
- Cross-cutting quality rules (error handling patterns, logging standards, documentation requirements)
- Cross-file impact guidance (what constitutes a breaking change, how to flag cross-boundary modifications)

**Subdirectory REVIEW.md** should contain technology-specific rules that would be noise in the other stack:

- `backend/`: CancellationToken enforcement, EF Core query patterns, DI lifetime rules, async/await anti-patterns, xUnit conventions
- `frontend/`: React hook rules, TypeScript strict mode enforcement, RTK Query cache invalidation patterns, Zod schema validation requirements, Tailwind conventions

**The decision test**: if a rule would generate false positives when applied to the other stack, it belongs in a subdirectory. "Never use `async void`" is meaningless in React — it goes in `backend/`. "Validate all user input" applies everywhere — it goes in root.

**Granularity threshold**: stop at the second level (`backend/`, `frontend/`). Going deeper (`backend/Modules/Coaching/`) creates maintenance burden that exceeds the signal improvement. The Beko case study found that recursive, increasingly granular review configurations generated developer frustration without proportional quality gains. If a module needs special rules, add a scoped rule in the `backend/` REVIEW.md with a path qualifier in the rule text: "For files in Modules/Coaching/: prefer event-sourced state transitions over direct entity mutation."

**Avoiding rule conflicts**: since rules accumulate rather than override, never write contradictory rules across levels. Root says "prefer immutable types" — the backend REVIEW.md should not say "use mutable for performance." Instead, write the root rule with an escape hatch: "Prefer immutable types unless hot-path profiling demonstrates a measurable performance requirement, documented with a comment." Subdirectory rules should extend, not contradict. Never reference root rules explicitly ("In addition to root security rules...") — the system handles accumulation automatically, and cross-references add confusion.

---

## Recommended structure for each REVIEW.md file

Based on the section ordering that CodeRabbit, Greptile, and Cursor configurations converge on, organize each file to match how the review system processes it: settings first (processed as overrides), then rules (accumulated), then exclusions (accumulated).

**Root REVIEW.md template:**
```markdown
## Severity Threshold
low

## Confidence Threshold
80

## Model Tier
frontier

## Max Findings
0

## Focus
bugs, security, cross-file-impact, tests, conventions, types, simplification

## Skip
**/bin/**
**/obj/**
**/dist/**
**/node_modules/**
**/.next/**
**/Migrations/*.Designer.cs
**/Generated/**
**/*.g.cs
package-lock.json
pnpm-lock.yaml
**/*.suo
**/*.user
**/.vs/**

## Rules

### Security
- CRITICAL: Never commit secrets, API keys, or connection strings in source
  files. Use environment variables or secret managers. This includes
  appsettings.json values — use User Secrets locally and Key Vault in
  production.
- CRITICAL: All user-supplied input must be validated before processing.
  Never trust client-side validation alone — server-side validation is
  the security boundary.
- All API endpoints must enforce authentication and authorization checks.
  Missing auth on a single endpoint exposes the entire resource.

### Architecture
- Dependencies flow inward: API layer → Application layer → Domain layer.
  Domain must never reference infrastructure or API concerns.
- Changes to shared API contracts (request/response DTOs, OpenAPI specs)
  require both backend and frontend review. Flag any PR that modifies
  contract types without corresponding consumer updates.
- Prefer composition over inheritance. Deep inheritance hierarchies
  make behavior unpredictable and testing difficult.

### Git and CI
- Commit messages follow Conventional Commits format
  (feat|fix|docs|refactor|test|chore: description). This drives
  automated changelog generation.
- PRs should address a single concern. Mixed refactor + feature + style
  changes reduce review quality — split into separate PRs.

### Error handling
- All public API endpoints must return structured error responses with
  consistent error codes. Never expose stack traces or internal details
  to clients.
- Log errors with sufficient context for debugging: correlation ID,
  operation name, relevant entity IDs. Avoid logging sensitive data.

## Ignore
conventions:"commit message format" for merge commits
```

**backend/REVIEW.md template:**
```markdown
## Model Tier
frontier

## Skip
**/TestFixtures/**/*.json
**/Snapshots/**

## Rules

### Async patterns
- All async methods must accept CancellationToken as the last parameter.
  Public methods use default value (CancellationToken ct = default);
  private methods require it explicitly. Omitting tokens prevents
  graceful shutdown under load.
- CRITICAL: Never use .Result, .Wait(), or .GetAwaiter().GetResult() on
  async calls. These deadlock ASP.NET Core's thread pool. Use await.
- Never use async void except for event handlers. Async void swallows
  exceptions and prevents proper error propagation.
- Use ConfigureAwait(false) in library/shared code but not in
  controllers or middleware where HttpContext access is needed.

### EF Core
- Watch for N+1 queries: any LINQ expression that touches DbContext
  inside a loop is a performance bug. Use .Include() for eager loading
  or restructure to batch queries.
- Read-only queries must use .AsNoTracking() to avoid unnecessary change
  tracking overhead.
- DbContext must be scoped (never singleton). Verify DI registration
  lifetime in service configuration.
- CRITICAL: EF Core FindAsync with CancellationToken requires explicit
  object[] cast: FindAsync(new object[] { id }, cancellationToken).
  Without the cast, the token is silently ignored.

### Dependency injection
- Verify service lifetime correctness: never inject Scoped services into
  Singleton consumers. This causes captive dependency bugs that surface
  only under concurrent load.
- Disposable services must be registered so the DI container manages
  their lifecycle. Manual using blocks in consuming code indicate a
  registration problem.

### Testing (xUnit)
- Tests must follow Arrange/Act/Assert structure with clear visual
  separation. Each test method verifies one behavior.
- Use [Theory] with [InlineData] or TheoryData<T> for parameterized
  tests. Limit InlineData parameters to 3–4; more indicates the test
  covers too many scenarios.
- Test names follow MethodName_Scenario_ExpectedBehavior convention.
  Descriptive names replace the need for test comments.

### Eval infrastructure
- Eval datasets must never be modified without a corresponding entry in
  the eval decision log. Dataset integrity is critical for measuring
  AI coaching quality over time.

## Ignore
conventions:"file naming" for EF Core migration files
types:"nullable reference" for test assertion helpers
```

**frontend/REVIEW.md template:**
```markdown
## Model Tier
frontier

## Skip
**/generated/**
**/__mocks__/**/*.json
**/public/assets/**

## Rules

### TypeScript strictness
- CRITICAL: Never use 'any' type. Use 'unknown' with runtime type
  narrowing instead. 'any' defeats TypeScript's type system entirely
  and hides bugs that surface only in production.
- Ban @ts-ignore and @ts-expect-error without an accompanying comment
  explaining why the suppression is necessary and when it can be removed.
- Type assertions (as) should be replaced with Zod runtime validation
  at API boundaries. Assertions create invisible contract drift between
  frontend expectations and backend responses.

### React patterns
- Never call hooks conditionally or inside loops. This violates React's
  Rules of Hooks and causes unpredictable state behavior.
- Every useEffect must have a cleanup function that releases event
  listeners, subscriptions, and timers. Missing cleanup causes memory
  leaks that compound across navigation.
- Flag missing useEffect dependency arrays. Empty arrays ([]) are
  acceptable only when the effect genuinely runs once on mount.
  Missing dependencies create stale closure bugs.
- Props drilling beyond 2 levels signals need for Context or RTK state.
  Deep prop chains make refactoring fragile and testing verbose.

### RTK Query
- Every mutation endpoint must specify invalidatesTags. Missing cache
  invalidation causes stale data that appears to users as "my changes
  didn't save."
- API response types must be validated with Zod schemas in
  transformResponse. Type-only validation misses runtime contract
  violations from backend changes.
- Use providesTags with entity IDs for granular cache invalidation.
  Tag-level invalidation without IDs causes unnecessary refetches
  across unrelated queries.

### Zod and validation
- Define Zod schemas as the single source of truth. Infer TypeScript
  types with z.infer<typeof Schema> rather than defining interfaces
  separately. Dual definitions drift apart silently.
- Use .safeParse() at API boundaries, .parse() in internal transforms
  where failure indicates a bug. safeParse returns structured errors
  suitable for user-facing validation messages.

### Tailwind
- Extract component classes when Tailwind strings exceed ~8 utilities.
  Long class strings harm readability and make responsive behavior
  hard to audit visually.

## Ignore
simplification:"optional chaining" for Zod schema definitions
conventions:"file length" for RTK Query API slice definitions
```

---

## Skip patterns: what to exclude and what to review differently

The skip pattern strategy follows a clear principle: **skip files where AI review adds zero value; use focused rules (not skipping) for files that need partial review.**

**Always skip** (generated, binary, or lock files where review is meaningless):
- Build outputs: `**/bin/**`, `**/obj/**`, `**/dist/**`, `**/.next/**`
- Dependencies: `**/node_modules/**`
- Lock files: `package-lock.json`, `pnpm-lock.yaml`, `packages.lock.json`
- Generated code: `**/Migrations/*.Designer.cs`, `**/*.g.cs`, `**/Generated/**`
- IDE files: `**/.vs/**`, `**/*.suo`, `**/*.user`
- Binary assets: `**/*.png`, `**/*.jpg`, `**/*.woff2`

**Never skip test files.** This is the most common skip pattern mistake. Tests need review — but with different emphasis. The Appsmith CodeRabbit configuration demonstrates the correct approach: their test path_instructions say "Review test code briefly. Focus on test coverage and proper mocking. Skip detailed style comments." Your REVIEW.md rules handle this naturally since test-specific rules (Arrange/Act/Assert, naming conventions) appear in the backend REVIEW.md alongside production code rules.

**The "review but only for security" pattern** is handled through the Focus section in subdirectory configs. If you had a `vendor/` directory, you'd create a `vendor/REVIEW.md` with `## Focus` restricted to `security` only. For your monorepo, this pattern applies to migration files: don't skip them entirely (hand-edited migrations with SQL injection are a real risk), but suppress conventions and simplification findings using Ignore patterns.

**Common mistakes to avoid**: skipping all `*.json` files (misses config changes with security implications), using overly broad patterns like `**/test*/**` (catches `testing-utils/` production code), and not skipping designer files for EF Core migrations (they generate enormous, meaningless diffs).

---

## Confidence and severity tuning strategy

**Start strict, loosen based on data.** This is the strongest consensus across all sources — CodeRabbit recommends introducing "guardrails in a warning state first, allowing your team to adjust," Propel advises enabling "rules tied to security, correctness, or compliance first," and Anthropic's own evaluation guidance says "capability evals should start at a low pass rate."

For your configuration with frontier model tier and all dimensions enabled, the recommended rollout:

1. **Weeks 1–2**: Run with confidence threshold at **85** (above default 80). This surfaces only high-conviction findings while you calibrate. Set severity threshold to **medium** to avoid the firehose.
2. **Weeks 3–4**: Lower severity threshold to **low** and track what percentage of low-severity findings developers actually act on. If acceptance rate drops below 20% for low-severity findings, raise the threshold back to medium permanently.
3. **Week 5+**: Lower confidence threshold to **75** (just above the security auto-floor of 70) if your false-positive rate on security findings is acceptable.

**Backend and frontend should use the same thresholds** initially. Diverging thresholds adds cognitive overhead for developers who work across both stacks. Only split if empirical data shows one stack has significantly higher false-positive rates.

The key metric to track: **alert acceptance rate**. Anthropic's internal data shows less than 1% of their AI review findings are marked incorrect. Industry benchmarks for well-configured tools show **73.8%** acceptance rates (Beko study) and **50%** fix rates (Cursor BugBot). If your acceptance rate is below 20%, your rules need pruning before you expand coverage.

Severity threshold at **low** (report everything) is useful during the calibration period but typically creates noise in steady state. SonarQube's explicit design target is "zero false positives for bugs and code smells" — a reminder that more findings is not inherently better. The value of `low` severity is discovering patterns you didn't know about; once discovered, either promote them to explicit rules or ignore them.

---

## Ignore patterns: managing false positives without losing signal

The `dimension:"pattern"` format requires balancing specificity with maintainability. Too specific ("bugs:null reference in UserService.GetCoach line 47") and the pattern breaks when code moves. Too broad ("bugs:null reference") and you suppress genuine findings.

**Target the middle ground**: describe the pattern category, not the instance. Good examples:
```
conventions:"file naming" for EF Core migration files
types:"nullable reference" for test assertion helpers  
simplification:"optional chaining" for Zod schema definitions
security:"hardcoded string" for test fixture data
```

**Pre-populate ignore patterns for known framework idioms.** Every .NET project generates false positives on EF Core migration file naming. Every React project triggers simplification suggestions on Zod's fluent API chains. Add these on day one rather than waiting for developers to encounter and dismiss them repeatedly. The pattern here mirrors CodeRabbit's "Learnings" system — once a false positive is identified, suppress it permanently so the team never wastes time on it again.

**Date-stamped comments are essential for long-term maintenance:**
```
## Ignore
# 2026-03-25: EF Core migrations are generated, naming conventions don't apply
conventions:"file naming" for migration files
# 2026-03-25: Test helpers intentionally use nullable without guards
types:"nullable reference" for test assertion helpers
```

This creates an audit trail. When you review ignore patterns quarterly, you can evaluate whether each suppression still applies. If you migrated away from EF Core, the date tells you when the ignore was added and that it's now stale.

**Manage ignore pattern growth** by setting a soft cap of **10–15 patterns per file**. If you exceed this, it signals either over-sensitive rules that should be removed entirely, or a systematic mismatch between your rules and your codebase. CodeAnt AI's research found that once teams reach the "category blindness" stage — where engineers ignore entire categories of findings — the review tool becomes "actively harmful." Regular ignore pattern audits prevent this cascade.

---

## Lessons from CodeRabbit, Greptile, and SonarQube configurations

**CodeRabbit's most effective path_instructions** share three properties: they target specific file types with glob patterns, they list concrete checkable items (not vague directives), and they differentiate review depth by file purpose. Appsmith's configuration — the most sophisticated public example found — uses different instruction blocks for Cypress tests ("avoid cy.wait, use data-* attributes for selectors"), API routes, and UI components. The key pattern: **test files get lighter review focused on coverage and mocking, not style**.

**Greptile's hierarchical `.greptile/` directory** is the closest analog to your REVIEW.md hierarchy. Their design validates your approach: settings override (strictness level), but rules and context accumulate. Greptile adds one feature worth noting: **rule IDs** (`"id": "no-raw-sql"`) that enable precise suppression. If your system supports it, assign stable identifiers to rules.

**SonarQube's quality profile design** offers two transferable principles. First, their "Sonar way" default profile is deliberately conservative — designed as a starting point, not a complete configuration. They recommend extending it rather than replacing it, to automatically inherit new rules as they're added. This mirrors your root REVIEW.md philosophy: start with universals, let subdirectories extend. Second, SonarQube's false-positive targets are explicit: **zero false positives** for bugs and code smells, **80%+ true positives** for security findings. These targets give you a calibration benchmark.

**ESLint's rule type taxonomy** (problem, suggestion, layout) maps directly to review severity. "Problem" rules identify code that will cause errors — these are your CRITICAL rules. "Suggestion" rules propose better alternatives — these are directional rules. "Layout" rules handle formatting — these should **never be AI review rules**; use deterministic linters instead. DataCamp's CLAUDE.md guide puts it bluntly: "Never send an LLM to do a linter's job."

**Google's code review guidelines** contribute the most important meta-principle: "Technical facts and data overrule opinions and personal preferences." Write rules that reference objective criteria (performance benchmarks, security standards, type safety guarantees) rather than subjective preferences. Google also formalizes severity with three labels — unlabeled (must address), "Nit:" (minor), and "Optional/Consider:" — which maps to your severity threshold system.

---

## The rule audit checklist

Run this audit quarterly, or whenever alert acceptance rate drops below 50%:

1. **Acceptance rate per rule**: Which rules have findings that developers consistently dismiss? Rules below 30% acceptance should be rewritten or removed.
2. **Coverage check**: Review the last 20 merged PRs. Did the review system miss any bugs that reached production? Missing categories indicate rule gaps.
3. **Staleness scan**: Does every rule still apply to the current tech stack and architecture? Flag rules that reference deprecated patterns, removed libraries, or obsoleted conventions.
4. **Contradiction audit**: Read all three REVIEW.md files in sequence. Do any accumulated rules conflict? Root says "prefer X" while subdirectory implies "avoid X"?
5. **Ignore pattern review**: Check each date-stamped ignore pattern. Is the suppressed framework pattern still in use? Remove stale ignores.
6. **Rule count check**: Count total rules across all files. If exceeding **50 total** (across root + backend + frontend), prioritize ruthlessly. Each rule beyond the ceiling dilutes all others.
7. **Severity calibration**: Are CRITICAL rules actually catching critical issues, or have they been diluted by overuse of the label? Restrict CRITICAL to maximum 3–4 rules per file.
8. **Linter overlap**: Are any rules duplicating what ESLint, Roslyn analyzers, or other deterministic tools already catch? Remove these — deterministic tools are faster, cheaper, and more reliable for objective checks.

---

## Recommended day-one configuration versus what to add later

**Day one** (start here, tune for 2–4 weeks before expanding):

- Root: 8–10 rules covering security (3), architecture (2), git conventions (2), error handling (2)
- Backend: 5–7 rules covering async patterns (3), EF Core (2), DI lifetime (1)
- Frontend: 5–7 rules covering TypeScript strictness (2), React hooks (2), RTK Query (2)
- Severity threshold: **medium** (avoid the firehose)
- Confidence threshold: **85** (above default, surfaces only high-conviction findings)
- Model tier: **frontier** (for your reasoning-heavy agents, this is correct)
- Skip patterns: full set of generated/binary/lock files from day one

**Add at week 4** (after reviewing acceptance rate data):

- Lower severity to **low** if medium-severity acceptance rate exceeds 60%
- Lower confidence to **80** (default)
- Add testing convention rules to both stacks
- Add Zod/validation rules to frontend
- Add eval infrastructure rules to backend

**Add at month 3+** (based on actual incidents and patterns):

- Performance-specific rules (N+1 detection, unnecessary re-renders)
- Cross-file impact rules for API contract changes
- Backwards compatibility rules as the API stabilizes
- Ignore patterns for recurring false positives identified during the first 3 months

This phased approach follows the strongest finding across all case studies: **teams that deploy broad AI review on day one generate noise and lose trust**, while teams that start narrow and expand based on data build lasting adoption. Collin Wilkins' practitioner guideline captures it: "Hard gates with high false positive rates get routed around fast."

---

## Conclusion

The optimal REVIEW.md configuration is not the most comprehensive one — it's the most precisely targeted one. **Fifteen to twenty-five rules per file, each with rationale, each verifiable, each addressing a real pattern your team encounters.** The research consistently shows that rule quality dominates rule quantity: Anthropic's internal reviews achieve less than 1% incorrect findings not because they check everything, but because each check is precisely scoped.

The hierarchical model works when you respect its accumulation semantics: root rules define the floor that every file stands on, subdirectory rules add the technology-specific walls. Never contradict across levels, never duplicate what linters handle deterministically, and never add a rule without knowing what false positive it might generate. Date-stamp your ignore patterns, audit quarterly, and track the one metric that matters most: **what percentage of findings result in code changes**. If that number stays above 50%, your configuration is working. If it drops below 20%, stop adding rules and start removing them.