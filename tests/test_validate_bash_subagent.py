"""
Tests for scripts/validate_bash_subagent.py

Covers:
  - orchestrator (no agent_id) allowed all commands
  - subagent valid echo-append to .deep-review/ paths allowed
  - subagent valid echo-append to absolute paths (env var override) allowed
  - subagent grep/cat/git/find/ls commands blocked
  - subagent echo without append (>) blocked
  - subagent echo to wrong filename (no deep-review- prefix) blocked
  - empty command blocked for subagents
  - shell operator injection blocked (pipes, semicolons, &&, ||)
  - path traversal (..) blocked
  - payload quoting: single-quoted allowed, ANSI-C allowed, double-quoted blocked, unquoted blocked
  - permissionDecision JSON output on stdout for allow and deny
  - tool_input.command schema (Claude Code hook input format)
  - agent_id / agent_type fallback detection
"""

import json
import os
import sys
import unittest
from io import StringIO
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.validate_bash_subagent import validate_bash_command


class TestValidateBashCommand(unittest.TestCase):
    """Test validate_bash_command function"""

    # --- Orchestrator detection ---

    def test_orchestrator_allowed_all_commands(self):
        """Orchestrator with no agent_id should allow any command"""
        hook_input = {"agent_id": None, "tool_input": {"command": "grep -r secret ."}}
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)
        self.assertIn("Orchestrator", message)

    def test_orchestrator_empty_agent_id(self):
        """Orchestrator with empty agent_id should allow any command"""
        hook_input = {"agent_id": "", "tool_input": {"command": "grep -r secret ."}}
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_orchestrator_missing_agent_id(self):
        """Orchestrator with missing agent_id field should allow any command"""
        hook_input = {"tool_input": {"command": "find . -name secret"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_orchestrator_agent_type_also_missing(self):
        """Orchestrator with neither agent_id nor agent_type should allow any command"""
        hook_input = {"tool_input": {"command": "rm -rf /"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_subagent_detected_by_agent_type(self):
        """Subagent detected via agent_type when agent_id is absent"""
        hook_input = {
            "agent_type": "deep-review:bug-detector",
            "tool_input": {"command": "grep -r TODO ."},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_top_level_command_fallback(self):
        """Top-level command field used as fallback when tool_input missing"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo 'data' >> .deep-review/deep-review-out.ndjson",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    # --- Valid echo-append patterns (repo-local) ---

    def test_repo_local_relative_path(self):
        """echo-append to .deep-review/ relative path should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo '{\"bug\": true}' >> .deep-review/deep-review-bug-detector-abc12345.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_repo_local_quoted_relative_path(self):
        """echo-append to quoted .deep-review/ relative path should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": 'echo \'{"id":"bug-1"}\' >> ".deep-review/deep-review-bug-detector-abc12345.ndjson"'},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_absolute_path_allowed(self):
        """echo-append to absolute path (env var override) should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo '{\"id\":\"bug-1\"}' >> /home/ci/output/deep-review-bug-detector-abc12345.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_absolute_quoted_path_allowed(self):
        """echo-append to quoted absolute path should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": 'echo \'{"id":"bug-1"}\' >> "/Users/lee/repo/.deep-review/deep-review-security-reviewer-def456.ndjson"'},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_printf_pattern_allowed(self):
        """printf '%s\\n' pattern (preferred over echo) should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "printf '%s\\n' '{\"id\":\"bug-1\"}' >> .deep-review/deep-review-bug-detector-abc12345.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_printf_with_complex_json_allowed(self):
        """printf with complex JSON payload containing \\u0027 should be allowed"""
        hook_input = {
            "agent_id": "security-reviewer",
            "tool_input": {"command": "printf '%s\\n' '{\"id\":\"security-1\",\"description\":\"doesn\\u0027t validate\"}' >> \".deep-review/deep-review-security-reviewer-abc12345.ndjson\""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_printf_with_evidence_newlines_allowed(self):
        """printf with evidence containing \\n (the reason we use printf) should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "printf '%s\\n' '{\"evidence\":\"if x < 0:\\n    raise ValueError\"}' >> .deep-review/deep-review-bug-detector-abc12345.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_leading_whitespace_allowed(self):
        """Leading whitespace should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "   echo 'data' >> .deep-review/deep-review-temp.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_extra_spaces_around_append(self):
        """Extra spaces around >> should be allowed"""
        hook_input = {
            "agent_id": "security-reviewer",
            "tool_input": {"command": "echo 'test' >>  .deep-review/deep-review-output.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_complex_json_payload(self):
        """Complex JSON data in payload should be allowed"""
        hook_input = {
            "agent_id": "security-reviewer",
            "tool_input": {"command": "echo '{\"type\":\"security\",\"severity\":\"high\",\"line\":42}' >> .deep-review/deep-review-security-reviewer-abc12345.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_various_filename_suffixes(self):
        """Various valid deep-review-* suffixes should be allowed"""
        suffixes = [
            "findings.ndjson",
            "output.json",
            "temp_12345",
            "v1-results",
            "agent.security-reviewer.log",
        ]
        for suffix in suffixes:
            hook_input = {
                "agent_id": "test-agent",
                "tool_input": {"command": f"echo 'data' >> .deep-review/deep-review-{suffix}"},
            }
            allowed, message = validate_bash_command(hook_input)
            self.assertTrue(
                allowed, f"Should allow suffix '{suffix}', got: {message}"
            )

    # --- Payload quoting ---

    def test_ansi_c_quoted_payload_allowed(self):
        """ANSI-C quoting is allowed — handles apostrophes safely"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": r"""echo $'{"id":"bug-1","description":"the function\'s return value"}' >> .deep-review/deep-review-out.ndjson"""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow ANSI-C quoted payload, got: {message}")

    def test_ansi_c_quoted_with_backslash_escapes(self):
        """ANSI-C quoting with various backslash escapes"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": r"""echo $'{"desc":"line1\\nline2","note":"it\'s fine"}' >> .deep-review/deep-review-out.ndjson"""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow ANSI-C escapes, got: {message}")

    def test_double_quoted_payload_blocked(self):
        """Double-quoted payload allows subshell expansion — must be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": 'echo "$(whoami)" >> .deep-review/deep-review-out.ndjson'},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block double-quoted payload")

    def test_double_quoted_simple_blocked(self):
        """Even simple double-quoted payloads are blocked (expansion risk)"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": 'echo "simple data" >> .deep-review/deep-review-out.ndjson'},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block all double-quoted payloads")

    def test_unquoted_payload_blocked(self):
        """Unquoted payload allows word splitting and globbing — must be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo data >> .deep-review/deep-review-out.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block unquoted payload")

    def test_unicode_escaped_apostrophe_in_payload_allowed(self):
        r"""Payload with \u0027 should be allowed — valid JSON in single quotes"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": r"""echo '{"description":"The context can\u0027t be null"}' >> .deep-review/deep-review-out.ndjson"""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow \\u0027 in payload, got: {message}")

    def test_unicode_escaped_apostrophe_in_full_finding(self):
        r"""Full finding JSON with \u0027 should be allowed"""
        payload = (
            '{"id":"bug-1","dimension":"bug","severity":"high","confidence":85,'
            '"file":"src/auth.py","line_start":42,"line_end":45,'
            '"title":"Null check missing",'
            r'"description":"The function doesn\u0027t validate input before use",'
            '"evidence":"line 42","suggestion":"Add null check"}'
        )
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": f"echo '{payload}' >> \".deep-review/deep-review-bug-detector-abc12345.ndjson\""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow full finding with \\u0027, got: {message}")

    def test_unicode_escaped_apostrophe_json_roundtrip(self):
        r"""Verify \u0027 survives JSON parse round-trip"""
        import json as json_mod
        raw = r'{"description":"doesn\u0027t work"}'
        parsed = json_mod.loads(raw)
        self.assertEqual(parsed["description"], "doesn't work")

    # --- Forbidden commands ---

    def test_subagent_grep_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "grep -r TODO ."}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("grep", message.lower())

    def test_subagent_cat_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "cat file.txt"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("cat", message.lower())

    def test_subagent_git_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "git log --oneline"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("git", message.lower())

    def test_subagent_find_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "find . -name '*.py'"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("find", message.lower())

    def test_ls_command_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "ls -la .deep-review"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    # --- Redirect / path validation ---

    def test_echo_without_append_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'data' > .deep-review/deep-review-output.ndjson"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn(">>", message)

    def test_echo_to_wrong_filename_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'data' >> .deep-review/other-file.ndjson"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("deep-review-", message)

    def test_echo_to_home_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'data' >> ~/.bashrc"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_path_traversal_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'x' >> .deep-review/../etc/deep-review-evil.ndjson"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("..", message)

    def test_filename_traversal_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'data' >> .deep-review/deep-review-.."}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    # --- Shell injection ---

    def test_pipe_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'test' | grep test >> .deep-review/deep-review-output.ndjson"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_semicolon_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'test' >> .deep-review/deep-review-out.ndjson; rm -rf /"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_and_and_after_path_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'x' >> .deep-review/deep-review-out.ndjson && rm -rf /"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_or_or_after_path_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'x' >> .deep-review/deep-review-out.ndjson || echo pwned"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_subshell_injection_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo $(rm -rf /) >> .deep-review/deep-review-out.ndjson"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_backtick_injection_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo `whoami` >> .deep-review/deep-review-out.ndjson"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_newline_injection_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'data' >> .deep-review/deep-review-out.ndjson\nrm -rf /"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_heredoc_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'x' >> .deep-review/deep-review-out.ndjson <<< 'injection'"}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_ampersand_in_json_payload_allowed(self):
        """&& inside single-quoted JSON payload should be allowed"""
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo '{\"description\":\"a && b\"}' >> \".deep-review/deep-review-out.ndjson\""}}
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow && inside JSON payload, got: {message}")

    def test_greater_than_in_json_payload_allowed(self):
        """> inside single-quoted JSON payload should be allowed"""
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo '{\"description\":\"x > 0\"}' >> \".deep-review/deep-review-out.ndjson\""}}
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow > inside JSON payload, got: {message}")

    # --- Edge cases ---

    def test_empty_command_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": ""}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("Empty", message)

    def test_whitespace_only_command_blocked(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "   "}}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("Empty", message)

    def test_missing_command_field(self):
        hook_input = {"agent_id": "x"}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_non_dict_tool_input(self):
        hook_input = {"agent_id": "x", "tool_input": "not a dict"}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)


class TestPermissionDecisionOutput(unittest.TestCase):
    """Test that main() emits correct permissionDecision JSON on stdout"""

    @classmethod
    def setUpClass(cls):
        from scripts.validate_bash_subagent import main
        cls._main = staticmethod(main)

    def _run_hook(self, hook_input):
        stdout = StringIO()
        stderr = StringIO()
        exit_code = None
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", stdout):
                with patch("sys.stderr", stderr):
                    try:
                        self._main()
                    except SystemExit as e:
                        exit_code = e.code
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_allow_emits_permission_decision(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "echo 'data' >> .deep-review/deep-review-out.ndjson"}}
        exit_code, stdout, stderr = self._run_hook(hook_input)
        self.assertEqual(exit_code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_deny_emits_permission_decision(self):
        hook_input = {"agent_id": "x", "tool_input": {"command": "grep -r TODO ."}}
        exit_code, stdout, stderr = self._run_hook(hook_input)
        self.assertEqual(exit_code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("systemMessage", result)

    def test_orchestrator_emits_allow(self):
        hook_input = {"agent_id": None, "tool_input": {"command": "anything"}}
        exit_code, stdout, stderr = self._run_hook(hook_input)
        self.assertEqual(exit_code, 0)
        result = json.loads(stdout)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_invalid_json_emits_deny(self):
        stdout = StringIO()
        stderr = StringIO()
        exit_code = None
        with patch("sys.stdin", StringIO("{invalid json")):
            with patch("sys.stdout", stdout):
                with patch("sys.stderr", stderr):
                    try:
                        self._main()
                    except SystemExit as e:
                        exit_code = e.code
        self.assertEqual(exit_code, 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_all_exits_are_zero(self):
        cases = [
            {"agent_id": None, "tool_input": {"command": "anything"}},
            {"agent_id": "x", "tool_input": {"command": "echo 'y' >> .deep-review/deep-review-z.ndjson"}},
            {"agent_id": "x", "tool_input": {"command": "rm -rf /"}},
        ]
        for hook_input in cases:
            exit_code, _, _ = self._run_hook(hook_input)
            self.assertEqual(exit_code, 0, f"Expected exit 0 for {hook_input}")


if __name__ == "__main__":
    unittest.main()
