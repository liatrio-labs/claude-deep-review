# Phase 8 Delivery Reference

Full UX orchestration flow for Phase 8: report delivery, PR comment selection, task board, and dismissed findings.

---

## Stage 0: Generate Report (Internal)

> **Do NOT output the report to the user here.** Generate internally; delivery stages below use the method(s) selected in Phase 1.

Read `references/report-format.md` for the full template and PR comment format.

The report includes: executive summary with finding counts (no verdict), severity-grouped findings, surfaced findings section, improvement suggestions section, per-dimension summary, and a **required** Review Methodology section documenting agents dispatched, model tier, validation stats, challenge results, and failures.

### Permalinks

Use platform-appropriate full-SHA permalink format:
- **GitHub:** `https://github.com/{owner}/{repo}/blob/{full_sha}/{path}#L{start}-L{end}`
- **GitLab:** `https://gitlab.com/{group}/{project}/-/blob/{full_sha}/{path}#L{start}-L{end}`

Always use the full 40-character SHA from `git rev-parse HEAD`.

---

## Stage 1: Deliver the Report

**Re-check eligibility** — verify the PR is still open. If closed/merged: deliver via chat/markdown only.

Deliver using the method(s) selected in Phase 1, in this order:

**Step A. Chat** — if selected, output the full report per `references/report-format.md`.

**Step B. PR comments** — if selected, run the PR comment selection flow before posting.

> **MANDATORY GATE: Do not post PR comments without completing this selection flow.**

```
AskUserQuestion(
  questions: [{
    question: "Which findings should I post as PR comments?",
    header: "PR Comments",
    multiSelect: false,
    options: [
      { label: "Default — top 6 by severity", description: "Post the highest-severity findings as inline comments" },
      { label: "Let me pick", description: "Walk through each finding and choose" }
    ]
  }]
)
```

- **"Default"** → top 6 main-report findings by severity then confidence. Improvement Suggestions excluded.
- **"Let me pick"** → run the **interactive finding walkthrough** (see below). Includes Improvement Suggestions. All selected findings posted — no cap.

Track which findings were selected (**pr_comment_set**) for Stage 2 shortcut.

Read `references/delivery-guide.md` for PR comment posting details (batched review event, platform-specific API, comment body format, findings metadata footer).

**Step C. Markdown file** — if selected, write to `./deep-review-{date}.md`.

---

## Stage 2: Task Board — MANDATORY GATE

> **STOP: You MUST ask this before finishing.** The user decides whether to create tasks.

**If pr_comment_set exists:**
```
AskUserQuestion(
  questions: [{
    question: "Would you like to add any findings to the task board?",
    header: "Task Board",
    multiSelect: false,
    options: [
      { label: "Yes — from my PR comments", description: "Create a task for each finding I posted as a PR comment" },
      { label: "Yes — let me pick from all findings", description: "Walk through the full list and choose" },
      { label: "No — done", description: "Finish the review" }
    ]
  }]
)
```

**If no pr_comment_set:**
```
AskUserQuestion(
  questions: [{
    question: "Would you like to add any findings to the task board?",
    header: "Task Board",
    multiSelect: false,
    options: [
      { label: "Yes — walk me through them", description: "I'll show each finding and you decide" },
      { label: "No — done", description: "Finish the review" }
    ]
  }]
)
```

Create FIX tasks for all included findings using the task creation flow in `references/delivery-guide.md` (metadata per `references/fix-task-metadata.md`). After creating: "Created N tasks from review findings."

---

## Stage 3: Dismissed Findings

After delivery, ask if findings should be suppressed in future reviews. See `references/delivery-guide.md` for the full dismissed findings flow (AskUserQuestion template, proposed entries preview, REVIEW.md write logic).

---

## Interactive Finding Walkthrough

Reusable selection pattern for both PR comment selection (Stage 1 Step B) and task board selection (Stage 2).

Walk the user through findings one at a time, grouped by severity (critical first). For each finding:

```
AskUserQuestion(
  questions: [{
    question: "{emoji} {id}: {title}\n{file}#{lines} | Confidence: {N}%",
    header: "{emoji} {Severity} ({M} of {N})",
    multiSelect: false,
    options: [
      { label: "Include" },
      { label: "Don't include" },
      { label: "Include all {Severity} findings" },
      { label: "Skip remaining {Severity} findings" }
    ]
  }]
)
```

Emojis: critical=🔴, high=🟠, medium=🟡, low=💡. Bulk options apply to current severity group then advance to next. When transitioning to a new severity group, add a fifth option: **"Done — skip everything else"** for early exit.
