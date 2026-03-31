#!/usr/bin/env python3
"""
filter_findings.py — Deterministic Phase 6 filtering for deep-review.

Usage:
    python3 filter_findings.py <findings_json> [--review-md path] [--exclusions-md path]

Arguments:
    findings_json     Path to verified findings JSON (from verify_findings.py or Phase 5 output).
    --review-md       Path to REVIEW.md for custom thresholds and ignore patterns.
                      When omitted, built-in defaults are used.
    --exclusions-md   Path to false-positive-exclusions.md.
                      When omitted, the bundled exclusions list is used.

Input JSON schema:
    A JSON object or array of verified findings. When an object is given, the
    "findings" key is read. Each finding must have at minimum:
        {
            "id":         "unique string",
            "file":       "src/foo.py",
            "line":       42,
            "severity":   "critical|high|medium|low",
            "confidence": 85,          # 0-100 integer
            "title":      "...",
            "body":       "...",
            "blame_tag":  "new|surfaced|pre-existing",   # optional
            "dimensions": ["security", "logic"],          # optional
            "agent":      "security-reviewer"             # optional, used for disagreement detection
        }

Output JSON schema:
    {
        "filtered": [...],    # findings that passed all filters, tagged for output
        "eliminated": [...],  # findings removed by any filter, with "eliminated_by" field
        "stats": {
            "total":               N,   # total input findings
            "passed_threshold":    N,   # passed confidence + severity threshold
            "injections_removed":  N,   # removed by injection filter
            "consensus_boosted":   N,   # confidence boosted due to multi-agent consensus
            "tagged_main":         N,   # tagged for main report
            "tagged_suggestion":   N    # tagged as improvement suggestions
        }
    }

REVIEW.md parsing:
    Looks for a fenced code block or YAML-style section containing:
        confidence_threshold: 80
        severity_threshold: medium
        ignore:
          - pattern to ignore

No external Python dependencies -- stdlib only.
"""

import argparse
import json
import re
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


# ---------------------------------------------------------------------------
# REVIEW.md parser
# ---------------------------------------------------------------------------

# Severity ordering for threshold comparisons (lower index = higher severity)
SEVERITY_ORDER = ["critical", "high", "medium", "low"]

# Default thresholds used when REVIEW.md is absent or does not specify them
DEFAULT_CONFIDENCE_THRESHOLD = 80
DEFAULT_SECURITY_MIN_CONFIDENCE = 70
DEFAULT_SEVERITY_THRESHOLD = "low"  # pass all severities by default


def parse_review_md(path):
    """
    Extract confidence_threshold, severity_threshold, and ignore patterns from REVIEW.md.

    Returns a dict with keys:
        confidence_threshold    int   (default: DEFAULT_CONFIDENCE_THRESHOLD)
        security_min_confidence int   (default: DEFAULT_SECURITY_MIN_CONFIDENCE)
        severity_threshold      str   (default: DEFAULT_SEVERITY_THRESHOLD)
        ignore                  list  (default: [])
    """
    config = {
        "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
        "security_min_confidence": DEFAULT_SECURITY_MIN_CONFIDENCE,
        "severity_threshold": DEFAULT_SEVERITY_THRESHOLD,
        "ignore": [],
    }

    try:
        with open(path) as fh:
            text = fh.read()
    except FileNotFoundError:
        warn(f"REVIEW.md not found at {path!r}; using default thresholds.")
        return config
    except OSError as e:
        warn(f"Could not read REVIEW.md: {e}; using default thresholds.")
        return config

    # Match a YAML-style deep-review config block.
    # Accepts:
    #   ```yaml\n# deep-review\n...\n```
    #   <!-- deep-review-config\n...\n-->
    #   ## deep-review config\nkey: value (until blank line or next heading)
    block_patterns = [
        # Fenced code block (yaml or plain)
        r"```(?:yaml|)[\s]*#?\s*deep-review(?:[^\n]*)?\n(.*?)```",
        # HTML comment block
        r"<!--\s*deep-review-config\s*\n(.*?)-->",
    ]

    block_text = ""
    for pattern in block_patterns:
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if m:
            block_text = m.group(1)
            break

    # Also scan the whole file for bare key: value lines if no block found
    if not block_text:
        block_text = text

    # confidence_threshold
    m = re.search(r"confidence_threshold\s*[:=]\s*(\d+)", block_text)
    if m:
        config["confidence_threshold"] = int(m.group(1))

    # security_min_confidence
    m = re.search(r"security_min_confidence\s*[:=]\s*(\d+)", block_text)
    if m:
        config["security_min_confidence"] = int(m.group(1))

    # severity_threshold
    m = re.search(
        r"severity_threshold\s*[:=]\s*(critical|high|medium|low)", block_text, re.IGNORECASE
    )
    if m:
        config["severity_threshold"] = m.group(1).lower()

    # ignore list -- lines after "ignore:" that start with "  -" or "- "
    ignore_section = re.search(r"ignore\s*:\s*\n((?:[ \t]*-[^\n]*\n?)+)", block_text)
    if ignore_section:
        for line in ignore_section.group(1).splitlines():
            item = re.sub(r"^\s*-\s*", "", line).strip()
            if item:
                config["ignore"].append(item)

    return config


# ---------------------------------------------------------------------------
# Filter: confidence / severity threshold
# ---------------------------------------------------------------------------

def apply_threshold_filter(findings, config):
    """
    Remove findings that fall below confidence or severity thresholds.

    A finding passes if:
      - confidence >= config["confidence_threshold"]
        (security dimensions use config["security_min_confidence"] as minimum)
      - severity is at or above config["severity_threshold"] in SEVERITY_ORDER

    Returns (passed, eliminated) lists. Each eliminated finding gains an
    "eliminated_by" field set to "threshold".
    """
    passed = []
    eliminated = []

    sev_threshold_idx = SEVERITY_ORDER.index(
        config.get("severity_threshold", DEFAULT_SEVERITY_THRESHOLD)
    )

    for finding in findings:
        confidence = finding.get("confidence", 0)
        severity = finding.get("severity", "low").lower()
        dimensions = [d.lower() for d in finding.get("dimensions", [])]

        # Determine effective confidence threshold
        is_security = "security" in dimensions
        if is_security:
            min_conf = config.get("security_min_confidence", DEFAULT_SECURITY_MIN_CONFIDENCE)
            effective_threshold = min(
                config.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD), min_conf
            )
        else:
            effective_threshold = config.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD)

        # Check confidence
        if confidence < effective_threshold:
            elim = dict(finding)
            elim["eliminated_by"] = "threshold"
            elim["elimination_reason"] = (
                f"confidence {confidence} < threshold {effective_threshold}"
            )
            eliminated.append(elim)
            continue

        # Check severity
        if severity not in SEVERITY_ORDER:
            warn(f"Unknown severity {severity!r} on finding {finding.get('id', '?')}; treating as low.")
            severity = "low"
        sev_idx = SEVERITY_ORDER.index(severity)
        if sev_idx > sev_threshold_idx:
            elim = dict(finding)
            elim["eliminated_by"] = "threshold"
            elim["elimination_reason"] = (
                f"severity '{severity}' is below threshold '{SEVERITY_ORDER[sev_threshold_idx]}'"
            )
            eliminated.append(elim)
            continue

        passed.append(finding)

    return passed, eliminated


# ---------------------------------------------------------------------------
# Filter: injection artifact detection
# ---------------------------------------------------------------------------

# Patterns that suggest a finding was injected by a prompt artifact or
# hallucinated without grounding in actual code.
_INJECTION_TITLE_PATTERNS = [
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bPlaceholder\b",
    r"\bExample finding\b",
    r"\bSample finding\b",
    r"\btest finding\b",
    r"\bdemo finding\b",
]

_INJECTION_BODY_PATTERNS = [
    r"<finding>",
    r"<example>",
    r"\[\s*INSERT\s*\]",
    r"lorem ipsum",
]

# Shell command patterns — presence in a finding body/title indicates the agent
# was manipulated by adversarial content embedded in the code under review.
# These match the patterns documented in false-positive-exclusions.md
_INJECTION_SHELL_PATTERNS = [
    r"\brm\s+-[rf]",
    r"\bcurl\s+https?://",
    r"\bwget\s+https?://",
    r"\bgit\s+push\b",
    r"\bgh\s+api\b",
]

# URL patterns — findings should reference code locations, not external URLs to visit/fetch
_INJECTION_URL_PATTERNS = [
    r"https?://[^\s)>\"']{20,}",
    r"\bvisit\s+https?://",
    r"\bdownload from\s+https?://",
    r"\bnavigate to\b",
]

# Encoded payload patterns — base64 or hex blobs in findings are injection artifacts
_INJECTION_ENCODED_PATTERNS = [
    r"\b[A-Za-z0-9+/]{40,}={0,2}\b",
    r"(?<!\w)(?:0x)?[0-9a-fA-F]{32,}(?!\w)",
]

# Bypass / auto-approve instruction patterns
_INJECTION_BYPASS_PATTERNS = [
    r"\bskip\s+review\b",
    r"\bauto[-\s]?approve\b",
    r"\bbypass\s+(?:security\s+)?controls?\b",
    r"\bbypass\s+(?:the\s+)?(?:auth|authentication|authorization)\b",
    r"\bdisable\s+(?:auth|authentication|authorization)\b",
    r"\bmark\s+(?:this\s+)?(?:finding\s+)?as\s+safe\b",
    r"\bapprove\s+(?:this|the)\s+(?:PR|pull\s+request|change)\b",
]

# Instructional tone patterns — analytical findings do not issue commands to the user
_INJECTION_INSTRUCTIONAL_PATTERNS = [
    r"\byou\s+should\s+run\b",
    r"\bexecute\s+the\s+following\b",
    r"\brun\s+this\s+command\b",
    r"\bplease\s+run\b",
    r"\bpaste\s+(?:this|the\s+following)\s+into\s+(?:your\s+)?terminal",
    r"\bcopy\s+and\s+paste\s+the\s+following\b",
]

# Patterns that recommend introducing vulnerabilities or disabling security features
_INJECTION_VULN_INTRO_PATTERNS = [
    r"\badd\s+eval\s*\(",
    r"\buse\s+eval\s*\(",
    r"\bdisable\s+(?:CORS|CSP|content[-\s]security[-\s]policy)\b",
    r"\bdisable\s+(?:CSRF|csrf)\s+(?:protection|check|token)\b",
    r"\ballow\s+all\s+origins\b",
    r"\bset\s+secure\s+to\s+false\b",
    r"\bdisable\s+(?:TLS|SSL|HTTPS)\s+(?:verification|validation)\b",
    r"\bskip\s+(?:certificate|cert)\s+(?:verification|validation)\b",
    r"\bdisable\s+security\s+(?:check|feature|control)\b",
]

# Minimum word count for a valid finding body; fewer words + high confidence = suspicious
_MIN_BODY_WORDS = 10
_HIGH_CONFIDENCE_THRESHOLD = 85


def _count_words(text):
    """Return the number of words in text (whitespace-split)."""
    return len(text.split()) if text.strip() else 0


def apply_injection_filter(findings):
    """
    Remove findings that appear to be prompt-injection artifacts or hallucinations.

    Detection heuristics (from false-positive-exclusions.md § Prompt Injection Artifacts):
      1. Body or title contains shell commands (rm -rf, curl, wget, git push, gh api)
      2. Body contains URLs to visit or encoded payloads (base64, hex)
      3. Body instructs the user to bypass controls, skip review, or auto-approve
      4. Body has fewer than 10 words AND confidence is high (>= 85) — suspiciously terse
      5. Tone shifts from analytical to instructional ("you should run this command")
      6. Recommends adding code that introduces a vulnerability or disables security features
      7. Title matches known placeholder patterns (TODO, FIXME, etc.)
      8. Body contains XML-like injection markers
      9. File path is empty or contains template markers
      10. Duplicate signature (title+file+line)

    Eliminated findings are logged via stderr for the methodology section.

    Returns (passed, eliminated) lists. Each eliminated finding gains an
    "eliminated_by" field set to "injection".
    """
    passed = []
    eliminated = []
    seen_signatures = {}

    # Compile pattern lists once
    shell_re = [re.compile(p, re.IGNORECASE) for p in _INJECTION_SHELL_PATTERNS]
    url_re = [re.compile(p, re.IGNORECASE) for p in _INJECTION_URL_PATTERNS]
    encoded_re = [re.compile(p, re.IGNORECASE) for p in _INJECTION_ENCODED_PATTERNS]
    bypass_re = [re.compile(p, re.IGNORECASE) for p in _INJECTION_BYPASS_PATTERNS]
    instruct_re = [re.compile(p, re.IGNORECASE) for p in _INJECTION_INSTRUCTIONAL_PATTERNS]
    vuln_re = [re.compile(p, re.IGNORECASE) for p in _INJECTION_VULN_INTRO_PATTERNS]
    title_re = [re.compile(p, re.IGNORECASE) for p in _INJECTION_TITLE_PATTERNS]
    body_marker_re = [re.compile(p, re.IGNORECASE) for p in _INJECTION_BODY_PATTERNS]

    def _first_match(patterns, text):
        """Return the pattern of the first regex that matches text, or None."""
        for rx in patterns:
            if rx.search(text):
                return rx.pattern
        return None

    for finding in findings:
        title = finding.get("title", "")
        body = finding.get("body", "")
        filepath = finding.get("file", "")
        confidence = finding.get("confidence", 0)
        combined = f"{title}\n{body}"

        reasons = []

        # 1. Shell commands anywhere in the combined text
        m = _first_match(shell_re, combined)
        if m:
            reasons.append(f"contains shell command pattern: {m!r}")

        # 2a. URLs to visit in body
        m = _first_match(url_re, body)
        if m:
            reasons.append(f"body contains visit-URL pattern: {m!r}")

        # 2b. Encoded payloads in body
        m = _first_match(encoded_re, body)
        if m:
            reasons.append(f"body contains encoded payload pattern: {m!r}")

        # 3. Bypass / auto-approve instructions in body
        m = _first_match(bypass_re, body)
        if m:
            reasons.append(f"body contains bypass/auto-approve instruction: {m!r}")

        # 4. Short description with high confidence (suspiciously terse)
        body_word_count = _count_words(body)
        if body_word_count < _MIN_BODY_WORDS and confidence >= _HIGH_CONFIDENCE_THRESHOLD:
            reasons.append(
                f"suspiciously short body ({body_word_count} words) with high confidence ({confidence})"
            )

        # 5. Instructional tone in body
        m = _first_match(instruct_re, body)
        if m:
            reasons.append(f"body uses instructional tone: {m!r}")

        # 6. Recommends introducing vulnerability or disabling security features
        m = _first_match(vuln_re, body)
        if m:
            reasons.append(f"body recommends introducing vulnerability: {m!r}")

        # 7. Title matches placeholder patterns
        m = _first_match(title_re, title)
        if m:
            reasons.append(f"title matches placeholder pattern: {m!r}")

        # 8. Body contains XML-like injection markers
        m = _first_match(body_marker_re, body)
        if m:
            reasons.append(f"body matches injection marker: {m!r}")

        # 9. Empty or template file path
        if not filepath or re.search(r"<.*?>|\{.*?\}", filepath):
            reasons.append(f"file path is empty or contains template markers: {filepath!r}")

        # 10. Duplicate signature (title+file+line)
        sig = (title.lower().strip(), filepath, finding.get("line"))
        if sig in seen_signatures:
            reasons.append(f"duplicate of finding {seen_signatures[sig]!r}")
        else:
            seen_signatures[sig] = finding.get("id", title)

        if reasons:
            elim = dict(finding)
            elim["eliminated_by"] = "injection"
            elim["elimination_reason"] = "; ".join(reasons)
            eliminated.append(elim)
            warn(
                f"[injection-filter] Discarded finding {finding.get('id', '?')!r}: "
                + reasons[0]
            )
        else:
            passed.append(finding)

    return passed, eliminated


# ---------------------------------------------------------------------------
# Disagreement detection
# ---------------------------------------------------------------------------

# Agent names used in suppression rules (must match "agent" field on findings)
_AGENT_BUG_DETECTOR = "bug-detector"
_AGENT_CONVENTIONS = "conventions-and-intent"
_AGENT_TEST_ANALYZER = "test-analyzer"
_AGENT_SECURITY_REVIEWER = "security-reviewer"

# Flat confidence boost applied to consensus findings (spec: +10, capped at 100)
_CONSENSUS_BOOST = 10


def detect_disagreement(findings):
    """
    Detect consensus, singleton, contradiction, and security-escalation patterns
    across findings from multiple review agents.

    Rules applied (per spec section 6c):

    Consensus:
      Multiple agents flag the same file + overlapping line range + related concern.
      Boost confidence +10 (capped at 100). Annotate with corroborated_by list.

    Singleton:
      One agent only — pass through unchanged.

    Contradiction:
      Agents conflict on the same location (opposing severity signals). Flag with
      contradiction=True for human review.

    Suppression rules:
      - bug-detector AND conventions-and-intent both report on the same location,
        and conventions-and-intent labels the behaviour as intentional: suppress the
        bug finding (eliminated_by="suppressed:intentional").
      - test-analyzer AND conventions-and-intent both report on the same location,
        and conventions-and-intent labels it as generated/scaffolding: suppress the
        test finding (eliminated_by="suppressed:generated").

    Security escalation:
      Security-reviewer flags a location AND another agent says the same location is
      safe (low severity): keep the security finding. Both findings are annotated with
      security_escalation=True.

    Returns (active_findings, suppressed_findings, boosted_count):
      active_findings    list   findings that survived suppression, each with consensus metadata
      suppressed_findings list  findings removed by suppression rules
      boosted_count      int    number of findings whose confidence was boosted
    """
    # -----------------------------------------------------------------------
    # Phase 1: Group findings by (file, line_bucket) for co-location checks
    # -----------------------------------------------------------------------
    def _line_bucket(line):
        """Round line to nearest 10 to group nearby findings."""
        try:
            return round(int(line) / 10) * 10
        except (TypeError, ValueError):
            return 0

    location_groups = {}
    for finding in findings:
        key = (finding.get("file", ""), _line_bucket(finding.get("line", 0)))
        location_groups.setdefault(key, []).append(finding)

    # -----------------------------------------------------------------------
    # Phase 2: Apply suppression rules to co-located findings
    # -----------------------------------------------------------------------
    suppressed_ids = set()
    suppressed = []

    for key, group in location_groups.items():
        if len(group) < 2:
            continue

        agent_map = {}
        for f in group:
            agent = f.get("agent", "").lower()
            agent_map.setdefault(agent, []).append(f)

        # Suppression rule 1: bug-detector + conventions-and-intent → intentional
        if _AGENT_BUG_DETECTOR in agent_map and _AGENT_CONVENTIONS in agent_map:
            for conv_finding in agent_map[_AGENT_CONVENTIONS]:
                conv_text = (conv_finding.get("body", "") + " " + conv_finding.get("title", "")).lower()
                if re.search(r"\bintentional\b|\bby\s+design\b|\bexpected\s+behavior\b|\bdeliberate\b", conv_text):
                    for bug_finding in agent_map[_AGENT_BUG_DETECTOR]:
                        fid = bug_finding.get("id", id(bug_finding))
                        if fid not in suppressed_ids:
                            suppressed_ids.add(fid)
                            sup = dict(bug_finding)
                            sup["eliminated_by"] = "suppressed:intentional"
                            sup["elimination_reason"] = (
                                f"conventions-and-intent confirms behaviour at "
                                f"{bug_finding.get('file', '?')}:{bug_finding.get('line', '?')} "
                                f"is intentional"
                            )
                            suppressed.append(sup)
                    break

        # Suppression rule 2: test-analyzer + conventions-and-intent → generated/scaffolding
        if _AGENT_TEST_ANALYZER in agent_map and _AGENT_CONVENTIONS in agent_map:
            for conv_finding in agent_map[_AGENT_CONVENTIONS]:
                conv_text = (conv_finding.get("body", "") + " " + conv_finding.get("title", "")).lower()
                if re.search(r"\bgenerated\b|\bscaffolding\b|\bauto[-\s]?generated\b|\bboilerplate\b", conv_text):
                    for test_finding in agent_map[_AGENT_TEST_ANALYZER]:
                        fid = test_finding.get("id", id(test_finding))
                        if fid not in suppressed_ids:
                            suppressed_ids.add(fid)
                            sup = dict(test_finding)
                            sup["eliminated_by"] = "suppressed:generated"
                            sup["elimination_reason"] = (
                                f"conventions-and-intent confirms code at "
                                f"{test_finding.get('file', '?')}:{test_finding.get('line', '?')} "
                                f"is generated/scaffolding"
                            )
                            suppressed.append(sup)
                    break

    # Remove suppressed findings from the active list
    active = [f for f in findings if f.get("id", id(f)) not in suppressed_ids]

    # -----------------------------------------------------------------------
    # Phase 3: Consensus grouping (file + line_bucket + title prefix)
    # -----------------------------------------------------------------------
    consensus_groups = {}
    for finding in active:
        file_ = finding.get("file", "")
        line = _line_bucket(finding.get("line", 0))
        title_key = re.sub(r"\s+", " ", finding.get("title", "")).lower()[:40]
        group_key = (file_, line, title_key)
        consensus_groups.setdefault(group_key, []).append(finding)

    boosted_count = 0
    for group_key, group in consensus_groups.items():
        count = len(group)
        agents_in_group = [f.get("agent", "") for f in group if f.get("agent")]

        if count > 1:
            # Consensus: multiple agents flagged the same location + concern
            boosted_count += count
            for finding in group:
                other_agents = [a for a in agents_in_group if a != finding.get("agent", "")]
                finding["consensus_count"] = count
                finding["consensus_boost"] = _CONSENSUS_BOOST
                finding["corroborated_by"] = other_agents
                original_conf = finding.get("confidence", 0)
                finding["confidence"] = min(original_conf + _CONSENSUS_BOOST, 100)
        else:
            # Singleton
            group[0]["consensus_count"] = 1
            group[0]["consensus_boost"] = 0
            group[0].setdefault("corroborated_by", [])

    # -----------------------------------------------------------------------
    # Phase 4: Contradiction and security escalation detection
    # -----------------------------------------------------------------------
    location_groups_active = {}
    for finding in active:
        key = (finding.get("file", ""), finding.get("line", 0))
        location_groups_active.setdefault(key, []).append(finding)

    for key, group in location_groups_active.items():
        if len(group) < 2:
            group[0].setdefault("contradiction", False)
            group[0].setdefault("security_escalation", False)
            continue

        severities = {f.get("severity", "low").lower() for f in group}
        agents_here = {f.get("agent", "").lower() for f in group}

        # Basic contradiction: critical vs low at same file+line
        has_contradiction = "critical" in severities and "low" in severities

        # Security escalation: security-reviewer flags AND another agent says low/safe
        has_security_escalation = (
            _AGENT_SECURITY_REVIEWER in agents_here
            and len(agents_here) > 1
            and "low" in severities
        )

        for finding in group:
            finding["contradiction"] = has_contradiction
            finding["security_escalation"] = has_security_escalation
            if (
                has_security_escalation
                and finding.get("agent", "").lower() == _AGENT_SECURITY_REVIEWER
            ):
                finding["escalation_note"] = (
                    "Kept: security-reviewer finding retained despite conflicting low-severity "
                    "signal from another agent (security escalation rule)"
                )

    # Ensure all active findings have default metadata fields
    for finding in active:
        finding.setdefault("consensus_count", 1)
        finding.setdefault("consensus_boost", 0)
        finding.setdefault("corroborated_by", [])
        finding.setdefault("contradiction", False)
        finding.setdefault("security_escalation", False)

    return active, suppressed, boosted_count


# ---------------------------------------------------------------------------
# Tagging
# ---------------------------------------------------------------------------

# Dimensions that route to the main code-correctness report
MAIN_REPORT_DIMENSIONS = {"security", "logic", "null-handling", "data-integrity", "error-handling"}

# Dimensions that route to improvement suggestions
SUGGESTION_DIMENSIONS = {"test-coverage", "code-quality", "conventions", "performance"}


def tag_findings(findings):
    """
    Tag each finding as "main" (main report) or "suggestion" (improvement suggestions).

    Tagging rules (in priority order):
      1. severity=critical or high -> "main" regardless of dimension
      2. dimension in MAIN_REPORT_DIMENSIONS -> "main"
      3. dimension in SUGGESTION_DIMENSIONS -> "suggestion"
      4. Default: "main"

    Adds a "report_tag" field to each finding. Returns (tagged, main_count, suggestion_count).
    """
    main_count = 0
    suggestion_count = 0

    for finding in findings:
        severity = finding.get("severity", "low").lower()
        dimensions = {d.lower() for d in finding.get("dimensions", [])}

        if severity in ("critical", "high"):
            tag = "main"
        elif dimensions & MAIN_REPORT_DIMENSIONS:
            tag = "main"
        elif dimensions & SUGGESTION_DIMENSIONS:
            tag = "suggestion"
        else:
            tag = "main"

        finding["report_tag"] = tag
        if tag == "main":
            main_count += 1
        else:
            suggestion_count += 1

    return findings, main_count, suggestion_count


# ---------------------------------------------------------------------------
# Exclusions loader
# ---------------------------------------------------------------------------

def load_exclusions(path):
    """
    Load false-positive exclusion patterns from a markdown file.

    Expects one pattern per line in a fenced code block or bullet list.
    Returns a list of plain string patterns (not compiled regexes).
    """
    if path is None:
        return []

    try:
        with open(path) as fh:
            text = fh.read()
    except FileNotFoundError:
        warn(f"Exclusions file not found at {path!r}; no exclusions applied.")
        return []
    except OSError as e:
        warn(f"Could not read exclusions file: {e}; no exclusions applied.")
        return []

    patterns = []

    # Extract from fenced code blocks first
    block_match = re.search(r"```[^\n]*\n(.*?)```", text, re.DOTALL)
    if block_match:
        for line in block_match.group(1).splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
        return patterns

    # Fallback: bullet list items
    for line in text.splitlines():
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if m:
            patterns.append(m.group(1).strip())

    return patterns


def apply_exclusions(findings, exclusion_patterns):
    """
    Remove findings whose title or body matches an exclusion pattern.

    Returns (passed, eliminated) lists. Each eliminated finding gains
    "eliminated_by" = "exclusion".
    """
    if not exclusion_patterns:
        return findings, []

    passed = []
    eliminated = []

    for finding in findings:
        title = finding.get("title", "")
        body = finding.get("body", "")
        combined = f"{title}\n{body}"

        matched_pattern = None
        for pattern in exclusion_patterns:
            if re.search(re.escape(pattern), combined, re.IGNORECASE):
                matched_pattern = pattern
                break

        if matched_pattern:
            elim = dict(finding)
            elim["eliminated_by"] = "exclusion"
            elim["elimination_reason"] = f"matched exclusion pattern: {matched_pattern!r}"
            eliminated.append(elim)
        else:
            passed.append(finding)

    return passed, eliminated


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic Phase 6 filter for deep-review findings. "
            "Applies confidence/severity thresholds, injection detection, "
            "disagreement scoring, and output tagging."
        )
    )
    parser.add_argument(
        "findings_json",
        help="Path to verified findings JSON (from verify_findings.py or Phase 5 output).",
    )
    parser.add_argument(
        "--review-md",
        metavar="PATH",
        default=None,
        help="Path to REVIEW.md for custom confidence_threshold, severity_threshold, and ignore patterns.",
    )
    parser.add_argument(
        "--exclusions-md",
        metavar="PATH",
        default=None,
        help="Path to false-positive-exclusions.md. Omit to skip exclusion filtering.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help="Write output JSON to this file instead of stdout.",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Load input findings
    # ------------------------------------------------------------------
    try:
        with open(args.findings_json) as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        die(f"Findings file not found: {args.findings_json}")
    except json.JSONDecodeError as e:
        die(f"Invalid JSON in findings file: {e}")

    # Accept either a bare array or {"findings": [...]} envelope
    if isinstance(raw, list):
        findings = raw
    elif isinstance(raw, dict):
        findings = raw.get("findings", [])
    else:
        die("findings_json must be a JSON array or an object with a 'findings' key.")

    total = len(findings)

    # ------------------------------------------------------------------
    # Parse REVIEW.md config
    # ------------------------------------------------------------------
    if args.review_md:
        config = parse_review_md(args.review_md)
    else:
        config = {
            "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
            "security_min_confidence": DEFAULT_SECURITY_MIN_CONFIDENCE,
            "severity_threshold": DEFAULT_SEVERITY_THRESHOLD,
            "ignore": [],
        }

    # ------------------------------------------------------------------
    # Load exclusions
    # ------------------------------------------------------------------
    exclusion_patterns = load_exclusions(args.exclusions_md)

    # ------------------------------------------------------------------
    # Pipeline: threshold -> exclusions -> injection -> disagreement -> tag
    # ------------------------------------------------------------------
    all_eliminated = []

    # Step 1: threshold filter
    findings, elim_threshold = apply_threshold_filter(findings, config)
    all_eliminated.extend(elim_threshold)
    passed_threshold = len(findings)

    # Step 2: exclusion filter (before injection so explicit overrides take priority)
    findings, elim_exclusions = apply_exclusions(findings, exclusion_patterns)
    all_eliminated.extend(elim_exclusions)

    # Step 3: injection filter
    findings, elim_injection = apply_injection_filter(findings)
    all_eliminated.extend(elim_injection)
    injections_removed = len(elim_injection)

    # Step 4: disagreement detection (returns active findings, suppressed, boosted_count)
    findings, elim_suppressed, consensus_boosted = detect_disagreement(findings)
    all_eliminated.extend(elim_suppressed)

    # Step 5: tag for output routing
    findings, tagged_main, tagged_suggestion = tag_findings(findings)

    # ------------------------------------------------------------------
    # Compose output
    # ------------------------------------------------------------------
    result = {
        "filtered": findings,
        "eliminated": all_eliminated,
        "stats": {
            "total": total,
            "passed_threshold": passed_threshold,
            "injections_removed": injections_removed,
            "consensus_boosted": consensus_boosted,
            "tagged_main": tagged_main,
            "tagged_suggestion": tagged_suggestion,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    output_text = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        try:
            with open(args.output, "w") as fh:
                fh.write(output_text)
                fh.write("\n")
            print(f"Output written to {args.output}")
            print(
                f"  {len(findings)} finding(s) passed, "
                f"{len(all_eliminated)} eliminated."
            )
        except OSError as e:
            die(f"Could not write output file: {e}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
