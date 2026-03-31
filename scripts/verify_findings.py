#!/usr/bin/env python3
"""
verify_findings.py — Deterministic finding verification for deep-review Phase 4.

Usage:
    python3 verify_findings.py <findings_json> [--base-branch main] [--diff-file path]

Input JSON schema:
    {
        "findings": [
            {
                "id": "bug-1",
                "dimension": "bug",
                "severity": "high",
                "confidence": 75,
                "file": "src/foo.py",
                "line_start": 42,
                "line_end": 45,
                "title": "...",
                "description": "...",
                "evidence": "...",
                "suggestion": "...",
                "suggested_fix_code": null,
                "cross_file_refs": []
            }
        ],
        "base_branch": "main",
        "head_sha": "abc123",
        "pr_number": 42,
        "owner": "org",
        "repo": "name"
    }

Output JSON schema:
    {
        "verified": [...],
        "eliminated": [...],
        "batches": [[...], ...],
        "stats": {
            "total": N,
            "new": N,
            "surfaced": N,
            "eliminated": N
        }
    }

    Each finding in "verified" has an added "origin" field:
        "new"       — line was written in the current PR/branch diff
        "surfaced"  — line predates the current diff (pre-existing issue exposed by change)

    Each finding in "eliminated" has an added "elimination_reason" field explaining
    why it was removed (e.g., "line not in diff", "evidence mismatch", etc.).

No external Python dependencies — stdlib only.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    print(f"WARNING: {msg}", file=sys.stderr)


def run(cmd, check=False):
    """Run a subprocess command. Returns (stdout, stderr, returncode)."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        die(
            f"Command failed (exit {result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def get_diff(base_branch, diff_file=None):
    """
    Return the unified diff text between base_branch and HEAD.

    If diff_file is provided, read from it instead of running git diff.
    Returns the diff string, or None on failure.
    """
    if diff_file:
        try:
            with open(diff_file) as fh:
                return fh.read()
        except OSError as e:
            warn(f"Could not read diff file '{diff_file}': {e}")
            return None

    stdout, stderr, rc = run(["git", "diff", f"{base_branch}...HEAD"])
    if rc != 0:
        warn(
            f"git diff failed (exit {rc}): {stderr.strip()}. "
            "Falling back to git diff HEAD (unstaged changes)."
        )
        stdout, stderr, rc = run(["git", "diff", "HEAD"])
        if rc != 0:
            warn("git diff HEAD also failed. Diff validation will be skipped.")
            return None
    return stdout


def parse_diff_lines(diff_text):
    """
    Parse a unified diff and return a set of (filepath, line_number) tuples
    representing lines present in the diff (added or context lines).
    Line numbers are from the new (head) version.
    """
    if not diff_text:
        return None

    valid_lines = set()
    current_file = None
    new_line = 0

    for raw_line in diff_text.splitlines():
        # New file header: +++ b/path/to/file
        file_match = re.match(r"^\+\+\+ b/(.+)$", raw_line)
        if file_match:
            current_file = file_match.group(1)
            new_line = 0
            continue

        # Hunk header: @@ -old_start[,old_count] +new_start[,new_count] @@
        hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
        if hunk_match:
            new_line = int(hunk_match.group(1))
            continue

        if current_file is None:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            valid_lines.add((current_file, new_line))
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            # Removed line — does not advance new_line
            pass
        elif not raw_line.startswith("\\"):
            # Context line
            valid_lines.add((current_file, new_line))
            new_line += 1

    return valid_lines


def is_line_in_diff(valid_lines, filepath, line):
    """Check whether (filepath, line) appears in the parsed diff."""
    if valid_lines is None:
        return True  # diff validation skipped — pass through
    if (filepath, line) in valid_lines:
        return True
    # Strip leading path component variations
    stripped = re.sub(r"^[ab]/", "", filepath)
    return (stripped, line) in valid_lines


# ---------------------------------------------------------------------------
# Stub functions — implemented in follow-on tasks
# ---------------------------------------------------------------------------

def classify_blame(finding, base_branch):
    """
    Classify a finding as "new" or "surfaced" using git blame.

    "new"       — the finding's lines were introduced by the current branch
                  (blame shows a commit reachable from HEAD but not base_branch)
    "surfaced"  — the finding's lines predate the current branch
                  (blame shows a commit also reachable from base_branch)

    Side effects:
    - Sets finding["blame_metadata"] with classification, author, date, and
      original_severity.
    - Downgrades finding["severity"] by one level for "surfaced" findings:
      critical→high, high→medium, medium→low, low stays low.

    Returns: "new" | "surfaced"
    """
    _SEVERITY_DOWNGRADE = {
        "critical": "high",
        "high": "medium",
        "medium": "low",
        "low": "low",
    }

    filepath = finding.get("file", "")
    line_start = finding.get("line_start", 1)
    line_end = finding.get("line_end") or line_start
    original_severity = finding.get("severity", "")
    cross_file_refs = finding.get("cross_file_refs") or []

    # Cross-file impact findings (about code outside the diff) → always "surfaced"
    if cross_file_refs:
        classification = "surfaced"
        finding["blame_metadata"] = {
            "classification": classification,
            "author": None,
            "date": None,
            "original_severity": original_severity,
        }
        if original_severity in _SEVERITY_DOWNGRADE:
            finding["severity"] = _SEVERITY_DOWNGRADE[original_severity]
        return classification

    # File not found on disk → skip (return "new" to keep finding, conservative)
    if not os.path.exists(filepath):
        warn(
            f"classify_blame: file not found '{filepath}' — classifying as 'new' (conservative)."
        )
        finding["blame_metadata"] = {
            "classification": "new",
            "author": None,
            "date": None,
            "original_severity": original_severity,
        }
        return "new"

    # Obtain the set of commits reachable from HEAD but not base_branch (i.e. PR commits)
    pr_stdout, pr_stderr, pr_rc = run(
        ["git", "log", "--format=%H", f"{base_branch}..HEAD"]
    )
    if pr_rc != 0:
        warn(
            f"classify_blame: git log failed for base '{base_branch}': {pr_stderr.strip()}"
            " — classifying as 'new' (conservative)."
        )
        finding["blame_metadata"] = {
            "classification": "new",
            "author": None,
            "date": None,
            "original_severity": original_severity,
        }
        return "new"

    pr_commits = set(pr_stdout.strip().splitlines())

    # Run git blame on the finding's line range
    blame_cmd = ["git", "blame", f"-L{line_start},{line_end}", "--", filepath]
    blame_stdout, blame_stderr, blame_rc = run(blame_cmd)

    if blame_rc != 0:
        err_lower = blame_stderr.lower()
        # Binary files produce a specific error from git blame
        if "binary" in err_lower:
            warn(
                f"classify_blame: binary file '{filepath}' — classifying as 'new' (conservative)."
            )
        else:
            warn(
                f"classify_blame: git blame failed for '{filepath}': {blame_stderr.strip()}"
                " — classifying as 'new' (conservative)."
            )
        finding["blame_metadata"] = {
            "classification": "new",
            "author": None,
            "date": None,
            "original_severity": original_severity,
        }
        return "new"

    # Parse blame output lines.
    # Standard porcelain format (short): "^SHA (Author Date HH:MM:SS +TZ LINE) code"
    # Short format: "SHA (Author YYYY-MM-DD HH:MM:SS +TZ LINE) code"
    blame_sha_re = re.compile(r"^\^?([0-9a-f]{7,40})\s+\((.+?)\s+(\d{4}-\d{2}-\d{2})")

    blamed_shas = set()
    first_author = None
    first_date = None

    for line in blame_stdout.splitlines():
        m = blame_sha_re.match(line)
        if not m:
            continue
        sha_prefix = m.group(1)
        author = m.group(2).strip()
        date = m.group(3)
        blamed_shas.add(sha_prefix)
        if first_author is None:
            first_author = author
            first_date = date

    if not blamed_shas:
        # Could not parse any blame output — conservative
        warn(
            f"classify_blame: could not parse blame output for '{filepath}' lines "
            f"{line_start}-{line_end} — classifying as 'new' (conservative)."
        )
        finding["blame_metadata"] = {
            "classification": "new",
            "author": None,
            "date": None,
            "original_severity": original_severity,
        }
        return "new"

    # A blamed SHA may be a short prefix; check if any blamed commit is a PR commit.
    # PR commits are full SHAs; blamed SHAs may be short (7+ chars).
    def sha_in_pr(short_sha, pr_set):
        for full_sha in pr_set:
            if full_sha.startswith(short_sha) or short_sha.startswith(full_sha):
                return True
        return False

    has_pr_commit = any(sha_in_pr(s, pr_commits) for s in blamed_shas)

    # "new" if any blamed commit is in the PR branch; otherwise "surfaced"
    if has_pr_commit:
        classification = "new"
    else:
        classification = "surfaced"

    finding["blame_metadata"] = {
        "classification": classification,
        "author": first_author,
        "date": first_date,
        "original_severity": original_severity,
    }

    # Downgrade severity for surfaced findings
    if classification == "surfaced" and original_severity in _SEVERITY_DOWNGRADE:
        finding["severity"] = _SEVERITY_DOWNGRADE[original_severity]

    return classification


def verify_factual(finding):
    """
    Verify that the finding's evidence field matches the actual file content
    at the reported line range.

    Reads finding["file"] lines [line_start, line_end] from disk and checks
    whether the evidence text appears in that range (partial match accepted).

    Returns: True if plausible, False if the evidence clearly does not match.

    Stub: always returns True until full verification logic is implemented.
    """
    # TODO(T02.3): implement file content read + evidence matching
    return True


def validate_diff_lines(finding, valid_lines):
    """
    Validate that the finding's reported line is present in the diff.

    Uses valid_lines set from parse_diff_lines().  A finding that points to
    a line not in the diff is likely stale or fabricated and should be
    eliminated.

    Returns: True if line is in diff (or diff validation is skipped),
             False if line is definitively absent from the diff.

    Stub: delegates to is_line_in_diff() — already functional.
    """
    filepath = finding.get("file", "")
    line_start = finding.get("line_start", 0)
    return is_line_in_diff(valid_lines, filepath, line_start)


def batch_findings(findings, batch_size=10):
    """
    Partition a list of findings into batches for Phase 5 agent dispatch.

    Each batch is a list of findings that can be processed in parallel by a
    single Phase 5 agent instance.  Batching by file first keeps related
    findings together and reduces per-agent context load.

    Returns: list of lists (batches), each containing at most batch_size items.

    Stub: returns simple sequential batches of batch_size until smarter
    grouping (by file / by dimension) is implemented.
    """
    # TODO(T02.4): implement file-grouped batching for Phase 5
    return [findings[i:i + batch_size] for i in range(0, len(findings), batch_size)]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def load_input(findings_json_path):
    """Load and validate the input JSON file."""
    try:
        with open(findings_json_path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        die(f"Findings file not found: {findings_json_path}")
    except json.JSONDecodeError as e:
        die(f"Invalid JSON in findings file: {e}")

    if not isinstance(data, dict):
        die("Input JSON must be an object with a 'findings' key.")
    if "findings" not in data:
        die("Input JSON is missing required 'findings' array.")
    if not isinstance(data["findings"], list):
        die("'findings' must be an array.")

    return data


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic finding verification for deep-review Phase 4. "
            "Takes Phase 3 agent findings JSON, classifies new vs. surfaced via "
            "git blame, verifies factual accuracy against file content, validates "
            "line references against the diff, and batches results for Phase 5."
        )
    )
    parser.add_argument(
        "findings_json",
        help="Path to input findings JSON (Phase 3 agent outputs merged).",
    )
    parser.add_argument(
        "--base-branch",
        default="main",
        metavar="BRANCH",
        help=(
            "Base branch for blame comparison. "
            "Default: %(default)s. "
            "Override with the PR base branch name (e.g. 'develop')."
        ),
    )
    parser.add_argument(
        "--diff-file",
        default=None,
        metavar="PATH",
        help=(
            "Path to a pre-fetched unified diff file. "
            "If omitted, the script runs 'git diff <base-branch>...HEAD'."
        ),
    )
    args = parser.parse_args()

    # Phase 1: Load
    data = load_input(args.findings_json)
    findings = data["findings"]
    base_branch = data.get("base_branch") or args.base_branch
    total = len(findings)
    print(f"Loaded {total} finding(s) from {args.findings_json}", file=sys.stderr)

    # Phase 2: Classify (blame)
    print(f"Classifying findings against base branch '{base_branch}'...", file=sys.stderr)
    for f in findings:
        f["origin"] = classify_blame(f, base_branch)

    # Phase 3: Verify (factual)
    print("Verifying factual accuracy...", file=sys.stderr)
    verified = []
    eliminated = []
    for f in findings:
        if verify_factual(f):
            verified.append(f)
        else:
            f["elimination_reason"] = "evidence does not match file content"
            eliminated.append(f)

    # Phase 4: Validate diff lines
    print("Validating finding line numbers against diff...", file=sys.stderr)
    diff_text = get_diff(base_branch, args.diff_file)
    valid_lines = parse_diff_lines(diff_text)
    if valid_lines is None:
        warn("Diff validation skipped — all findings passed through.")

    still_verified = []
    for f in verified:
        if validate_diff_lines(f, valid_lines):
            still_verified.append(f)
        else:
            f["elimination_reason"] = (
                f"line {f.get('line_start')} of {f.get('file')} not found in diff"
            )
            eliminated.append(f)
    verified = still_verified

    # Phase 5: Batch
    print(f"Batching {len(verified)} verified finding(s)...", file=sys.stderr)
    batches = batch_findings(verified)

    # Build stats
    new_count = sum(1 for f in verified if f.get("origin") == "new")
    surfaced_count = sum(1 for f in verified if f.get("origin") == "surfaced")
    stats = {
        "total": total,
        "new": new_count,
        "surfaced": surfaced_count,
        "eliminated": len(eliminated),
    }

    output = {
        "verified": verified,
        "eliminated": eliminated,
        "batches": batches,
        "stats": stats,
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))

    # Summary to stderr
    print(
        f"Done: {len(verified)} verified ({new_count} new, {surfaced_count} surfaced), "
        f"{len(eliminated)} eliminated, {len(batches)} batch(es).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
