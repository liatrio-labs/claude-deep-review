# Robust PR diff strategies for automated code review

**The most reliable approach is API-first diff acquisition, not local git.** The root cause of the "fatal: no merge base" failure is well-understood: GitHub Actions defaults to `fetch-depth: 1`, and since Git 2.28, three-dot diff properly errors on shallow clones instead of silently degrading. The proposed `--diff-file` approach using `gh pr diff` output is the right architectural direction, but it must account for GitHub's hard API size limits (20,000 lines / 1 MB) and include a local git fallback chain. Mature tools like reviewdog and Danger.js already prefer API-based diffs, and the industry consensus points to a layered strategy: API diff first, local three-dot second, local two-dot third.

## Why the benchmark failed: anatomy of the cascade

The failure chain in the fork-based test repository follows a pattern that is **the single most common diff failure in CI environments**. Understanding each link matters for designing a robust fix.

**Step 1: `git diff {base}...HEAD` produces "fatal: no merge base."** With `actions/checkout`'s default `fetch-depth: 1`, only the tip commit exists locally. The merge base — the best common ancestor of the two branches — lies deeper in history and simply doesn't exist in the shallow clone. Prior to **Git 2.28** (released July 2020), this scenario silently fell back to two-dot behavior (`git diff A B`). Git 2.28 introduced commit `1457886` which changed this to properly error with `fatal: A...B: no merge base`. This behavioral change broke many CI workflows simultaneously, documented across multiple projects including pre-commit (#1554), diff-cover (#153), and backstage/community-plugins (#732).

**Step 2: `git diff HEAD` returns empty.** This fallback is fundamentally wrong. `git diff HEAD` compares the **working tree** against HEAD — and since `actions/checkout` just checked out HEAD cleanly, the working tree is identical to HEAD. The diff is empty regardless of whether HEAD points to the merge commit or the PR branch tip. The correct fallback would be `git diff HEAD^1 HEAD^2` (diffing the merge commit's parents) or a two-dot diff against the base branch ref.

**Step 3: 0% recall.** An empty diff means the tool sees zero changed lines, classifies nothing, and every real change is a false negative.

## How CI platforms actually expose PR diff information

Each major CI platform handles PR diffs differently, and **only GitLab provides the true merge base as a built-in variable**. This cross-platform gap is the root cause of widespread tooling fragility.

**GitHub Actions** checks out a synthetic merge commit at `refs/pull/{N}/merge` by default — this commit merges the PR head into the current base branch tip. The variable `github.event.pull_request.base.sha` is widely misunderstood: it records the **tip of the base branch at PR creation time**, not the `git merge-base`. Community discussion #39880 confirms this empirically. To get the actual merge base, you must compute `git merge-base $base_sha $head_sha` locally (which requires sufficient fetch depth) or extract it from the merge commit parents. The `GITHUB_BASE_REF` variable provides only the branch name (e.g., "main"), not a SHA.

**GitLab CI** stands out by providing `CI_MERGE_REQUEST_DIFF_BASE_SHA` — the actual `git merge-base` computed server-side. This is available in merge request pipelines and is the most developer-friendly approach among all platforms. However, it has a known bug (GitLab Issue #442031): changing the target branch of an MR may not update this variable. GitLab internally computes MR diffs using both a "base diff" (three-dot) and a "HEAD diff" (target merged into source, then diffed against target HEAD), storing versioned `MergeRequestDiff` records.

**Other platforms are less capable.** Bitbucket Pipelines provides `BITBUCKET_PR_DESTINATION_COMMIT` (destination branch tip, not merge base) and doesn't support fork PR triggers at all. Azure DevOps checks out a merge commit similar to GitHub but provides no merge-base variable — you must use the REST API (`/_apis/git/repositories/{repo}/pullRequests/{id}/iterations`). CircleCI has the worst PR support: `CIRCLE_PULL_REQUEST` is frequently empty, there's no target branch variable, and `pipeline.git.base_revision` represents the previous commit on the same branch, not the merge base against the target.

| Platform | True merge base variable | Checks out merge commit | Fork PR support |
|----------|------------------------|------------------------|----------------|
| GitHub Actions | No (must compute) | Yes | Yes (read-only token) |
| GitLab CI | Yes `DIFF_BASE_SHA` | Yes (merged results) | Yes |
| Bitbucket Pipelines | No | Yes | No |
| Azure DevOps | No | Yes | Yes |
| CircleCI | No | No (source only) | Yes |

## Three-dot vs two-dot: precise semantics and the Git 2.28 breaking change

The three-dot and two-dot notations have **inverted meanings between `git log` and `git diff`**, which is widely considered a design mistake by core Git maintainers, including Junio Hamano.

**`git diff A...B`** computes `git diff $(git merge-base A B) B` — it finds the merge base, then shows what B introduced since diverging from A. This isolates the PR author's changes and matches what GitHub displays in the "Files changed" tab. **`git diff A..B`** is identical to `git diff A B` — a direct comparison of tree states at two commits. This shows the net difference between branch tips, including changes on both sides since divergence.

For PR review, three-dot is generally more useful (it shows only what the author changed), but two-dot more accurately represents what will change in the codebase upon merge. When the base branch has advanced significantly, three-dot can miss conflicts while two-dot produces noisy diffs with changes the PR author didn't introduce. The practical advice: **keep branches short-lived and frequently rebased, where both produce identical results.**

Three-dot fails under these specific conditions:

- **Shallow clones** (most common): The merge base commit doesn't exist locally. Since Git 2.28, this is a hard fatal error rather than a silent degradation.
- **Disconnected histories**: Repos created with `git init` + `git remote add` instead of cloning, or orphan branches.
- **Unfetched fork history**: Only the PR branch was fetched, not the connecting ancestry.
- **Multiple merge bases**: Criss-cross merge histories can produce multiple merge bases; `git merge-base` picks one nondeterministically, which can cause inconsistent diffs.

**GitHub's PR "Files changed" view uses a three-dot diff**, but with an important nuance: PR pages use the merge base computed **at PR creation time** (potentially stale), while the compare page (`/compare/main...feature`) uses the current merge base. GitHub's REST API for PR diffs (`Accept: application/vnd.github.v3.diff`) also returns this three-dot diff, computed server-side.

## What `gh pr diff` actually does and where it breaks

The `gh pr diff` command is implemented in `pkg/cmd/pr/diff/diff.go` in the cli/cli repository. It calls the **GitHub REST API** — specifically `GET /repos/{owner}/{repo}/pulls/{number}` with `Accept: application/vnd.github.v3.diff` — and never touches local git history for the diff computation. GraphQL is used only to resolve branch names to PR numbers when no explicit number is given.

This makes `gh pr diff` **significantly more robust than local git** for most scenarios: it works without a full clone, handles fork-based PRs transparently (the server has all history), works after source branch deletion (GitHub retains `refs/pull/{N}/head` and `refs/pull/{N}/merge`), and functions for closed, merged, and draft PRs. The server always has the merge base available.

However, `gh pr diff` has a **critical hard limit**. The API returns HTTP 406 when the diff exceeds **20,000 lines or 1 MB** of raw diff data, or involves more than **300 files**. The diff is not truncated — it fails completely. Issue cli/cli#10712 confirms that even `gh pr diff --name-only` fails because it fetches the full diff first, then parses filenames client-side. The reviewdog project (issue #1696) encountered this limit as well, observing that some PRs triggered a 3,000-line limit in March 2024 (the limit may have been temporarily lowered). Standard REST API rate limits also apply: **1,000 requests/hour per repository** when using `GITHUB_TOKEN` in Actions.

The diff format from the API is **compatible with standard unified diff parsers** but not byte-identical to local `git diff` output. Both include `diff --git` headers, `a/`/`b/` prefixes, `index` lines, and standard `@@` hunk headers. Minor differences exist in hash abbreviation length, rename detection thresholds (server-side vs local `diff.renameLimit`), and binary file marker phrasing. These differences are cosmetic for any well-written unified diff parser.

## How mature PR automation tools solve this problem

The industry has converged on two architectural approaches, and tools that rely solely on local git are the ones that fail most often.

**API-first tools (more robust):** Danger.js fetches diffs via `GET /repos/{owner}/{repo}/pulls/{id}/files` with pagination (100 files per page). It never touches local git in CI mode. This makes it immune to shallow clone issues but exposes it to the 300-file API limit — Danger.js issue #1432 documents the HTTP 406 failure when PRs exceed 300 files. **reviewdog** uses a hybrid approach: it fetches the API diff for comment filtering in `github-pr-check` and `github-pr-review` modes, but uses local `git diff --find-renames` for line mapping because the API diff doesn't support rename tracking (issue #66). For fork PRs, reviewdog v0.9.15 introduced graceful degradation — falling back to GitHub Actions logging commands (`::warning::`, `::error::`) when the token lacks write access.

**Local-git-only tools (more fragile):** Danger Ruby uses `git merge-base` via the rugged gem and **crashes without fallback** when the merge base is unavailable (issue #768). Pronto similarly requires local git and an explicit `git fetch` of remote branches. SonarQube requires the target branch to be fetched and present locally with valid `.git` metadata — it analyzes all files and compares results against the target branch analysis.

**Cloud-hosted tools avoid the problem entirely.** CodeClimate, Codacy, and SonarCloud clone repositories on their own servers and compare analysis snapshots rather than parsing diffs. This sidesteps all merge-base issues but prevents local/self-hosted usage.

**Trunk Check** uses the most sophisticated approach: a "shadow tree" strategy that runs linters twice (once on upstream, once on current code), then diffs the results. This catches issues on unmodified lines introduced by the change, but requires full checkout of both versions.

## The `HEAD^1` trick and optimal fetch strategies

For workflows using `actions/checkout`'s default merge commit checkout, the **`HEAD^1` approach** is the most elegant solution that avoids merge-base computation entirely. Since the merge commit has two parents — first parent (`HEAD^1`) is the base branch tip, second parent (`HEAD^2`) is the PR head — `git diff HEAD^1 HEAD^2` produces the PR diff without needing any history beyond `fetch-depth: 2`. The GrantBirki/git-diff-action uses this approach in production.

For three-dot diffs, there is **no guaranteed minimal fetch depth** because the merge base can be arbitrarily deep depending on branch divergence. Three strategies exist in order of reliability:

- **`fetch-depth: 0`** (full clone): Always works, recommended by GitHub's own blog for any history-dependent operation. Performance cost scales with repo size.
- **Iterative deepening**: The `rmacklin/fetch-through-merge-base` and `fulcrumgenomics/fetch-through-merge-base` actions call `git fetch --deepen=N` in a loop until `git merge-base` succeeds. Default step size is 10 commits. Most efficient for large repos.
- **Treeless clones** (`--filter=tree:0`): Fetch full commit graph without file trees. `git merge-base` works, but `git diff` triggers on-demand blob fetching. Not yet natively supported by `actions/checkout` (issue #1152).

**Diff passing must use files, never environment variables.** Large diffs cause "Argument list too long" errors with env vars (OS-level `ARG_MAX` ~2MB on Linux). `GITHUB_OUTPUT` breaks with multiline content. The GrantBirki/git-diff-action documentation explicitly warns against env var-based diff passing and recommends file outputs. For cross-job sharing, use `actions/upload-artifact` / `actions/download-artifact`.

## Evaluating the proposed fix

The proposed approach — (a) two-dot fallback when three-dot fails, and (b) saving `gh pr diff` output and passing via `--diff-file` — is architecturally sound but should be reordered and augmented.

**The recommended fallback chain is API-first, not API-last:**

1. **`gh pr diff {number}` to file** (API diff): Most robust for typical PRs. Server computes merge base, works for forks, no clone depth dependency. Fails only for very large PRs (>20K lines).
2. **`git diff HEAD^1 HEAD^2`** (merge commit parents): Works with `fetch-depth: 2`, no merge-base computation needed. Only works when checkout is the merge commit (default `pull_request` trigger).
3. **`git diff origin/{base}...HEAD`** (three-dot local): Requires sufficient fetch depth for merge-base. Most semantically correct for PR review.
4. **`git diff origin/{base}..HEAD`** (two-dot local): Always works if base ref is fetched. Different semantics (includes base branch changes) but better than nothing.

The `--diff-file` approach has three pitfalls to handle. First, **API size limits**: validate that `gh pr diff` succeeded (check exit code and HTTP status) before relying on the file. For PRs exceeding the limit, fall through to local git. Second, **empty diff detection**: verify the file is non-empty and starts with `diff --git` before passing downstream. Third, **format compatibility**: while API and local git diffs are both standard unified format, rename detection may differ — if the downstream tool relies on exact `rename from`/`rename to` headers, test with both sources.

The format differences between `gh pr diff` and local `git diff` are minor enough that any standard unified diff parser handles both correctly. Both include `diff --git` headers, `a/`/`b/` path prefixes, `index` lines with abbreviated hashes, `@@` hunk headers, and `\ No newline at end of file` markers. The meaningful differences are: rename detection thresholds may vary, `index` line hash abbreviation length differs, and the API diff is always three-dot while local `git diff A..B` is two-dot.

## Conclusion

The failure pattern described — "no merge base" cascading to empty diff and 0% recall — is the most common diff-related CI failure across the ecosystem, affecting Danger, reviewdog, super-linter, and dozens of other tools. The root cause is **Git 2.28's deliberate removal of silent degradation** combined with **shallow clones being the universal CI default**.

The key insight from studying mature tools is that **API-based diff acquisition should be the primary strategy, not the fallback**. `gh pr diff` bypasses all local git topology issues because GitHub's server always has the full history and can always compute the merge base. The 20,000-line API limit is the only scenario where local git diff becomes necessary, and for that case, `fetch-depth: 0` combined with a three-dot to two-dot fallback chain covers the remaining surface. Pre-computing the diff once as a file and passing it downstream via `--diff-file` is exactly what GrantBirki/git-diff-action and other production tools recommend — it eliminates redundant computation, avoids env var size limits, and decouples diff acquisition from diff consumption.
