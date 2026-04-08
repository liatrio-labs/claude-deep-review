"""
Tests for scripts/validate_bash_subagent.py

Covers:
  - orchestrator (no agent_id) allowed all commands
  - subagent valid echo-append to literal temp path deep-review-* allowed
  - $TMPDIR structurally blocked with corrective guidance
  - subagent grep/cat/git/find commands blocked
  - subagent echo without append (>) blocked
  - subagent echo to wrong path blocked
  - empty command blocked for subagents
  - whitespace handling and variations
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
            "command": "echo 'data' >> /tmp/deep-review-out",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_subagent_valid_echo_append(self):
        """Subagent valid echo-append pattern should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo '[{\"bug\": true}]' >> /tmp/deep-review-findings"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_subagent_valid_echo_append_with_spaces(self):
        """Subagent valid echo-append with extra spaces should be allowed"""
        hook_input = {
            "agent_id": "security-reviewer",
            "tool_input": {"command": "echo 'test' >>  /tmp/deep-review-output.json"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_subagent_valid_echo_append_with_leading_whitespace(self):
        """Subagent valid echo-append with leading whitespace should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "   echo 'data' >> /tmp/deep-review-temp"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_subagent_valid_echo_append_complex_data(self):
        """Subagent valid echo-append with complex JSON data should be allowed"""
        hook_input = {
            "agent_id": "security-reviewer",
            "tool_input": {"command": """echo '{"type":"security","severity":"high","line":42}' >> /tmp/deep-review-security"""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_tmpdir_variable_blocked(self):
        """$TMPDIR usage is structurally blocked — agents must use literal paths"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'data' >> $TMPDIR/deep-review-out"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("$TMPDIR is not allowed", message)
        self.assertIn("literal path", message)

    def test_tmpdir_in_payload_not_false_positive(self):
        """$TMPDIR inside single-quoted JSON payload must NOT be blocked.
        A finding about a $TMPDIR bug has the text in the payload, not the path."""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command":
                "echo '{\"description\":\"the code uses $TMPDIR without checking if set\"}' "
                ">> /tmp/deep-review-bug-detector-abc.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow $TMPDIR inside payload, got: {message}")

    def test_subagent_grep_blocked(self):
        """Subagent grep command should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "grep -r TODO ."},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("grep", message.lower())

    def test_subagent_cat_blocked(self):
        """Subagent cat command should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "cat file.txt"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("cat", message.lower())

    def test_subagent_git_blocked(self):
        """Subagent git command should be blocked"""
        hook_input = {
            "agent_id": "security-reviewer",
            "tool_input": {"command": "git log --oneline"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("git", message.lower())

    def test_subagent_find_blocked(self):
        """Subagent find command should be blocked"""
        hook_input = {
            "agent_id": "type-reviewer",
            "tool_input": {"command": "find . -name '*.py'"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("find", message.lower())

    def test_subagent_echo_without_append_blocked(self):
        """Subagent echo with > (overwrite) instead of >> (append) should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'data' > /tmp/deep-review-output"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn(">>", message)

    def test_subagent_echo_to_wrong_path_blocked(self):
        """Subagent echo to non-deep-review path should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'data' >> /tmp/other-file"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("/deep-review-", message)

    def test_subagent_echo_to_home_blocked(self):
        """Subagent echo to home directory should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'data' >> ~/.bashrc"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_subagent_empty_command_blocked(self):
        """Subagent with empty command should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": ""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("Empty", message)

    def test_subagent_whitespace_only_command_blocked(self):
        """Subagent with whitespace-only command should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "   "},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("Empty", message)

    def test_subagent_command_with_pipe_blocked(self):
        """Subagent with piped commands should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'test' | grep test >> /tmp/deep-review-output"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_subagent_echo_with_semicolon_blocked(self):
        """Subagent with command chaining should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'test' >> /tmp/deep-review-out; rm -rf /"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_various_tmpdir_suffixes_allowed(self):
        """Various valid literal path deep-review-* suffixes should be allowed"""
        suffixes = [
            "findings",
            "output.json",
            "temp_12345",
            "v1-results",
            "agent.security-reviewer.log",
        ]
        for suffix in suffixes:
            hook_input = {
                "agent_id": "test-agent",
                "tool_input": {"command": f"echo 'data' >> /tmp/deep-review-{suffix}"},
            }
            allowed, message = validate_bash_command(hook_input)
            self.assertTrue(
                allowed, f"Should allow suffix '{suffix}', got: {message}"
            )

    def test_missing_command_field(self):
        """Missing command field should be treated as empty command"""
        hook_input = {"agent_id": "bug-detector"}
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    # --- Literal path tests (resolved $TMPDIR) ---

    def test_literal_path_allowed(self):
        """Literal absolute path (resolved TMPDIR) should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo '{\"id\":\"bug-1\"}' >> /var/folders/dn/abc123/T/deep-review-bug-detector-abc12345.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow literal path, got: {message}")

    def test_literal_path_quoted_allowed(self):
        """Double-quoted literal path should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": 'echo \'{"id":"bug-1"}\' >> "/private/tmp/deep-review-security-reviewer-def456.ndjson"'},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow quoted literal path, got: {message}")

    def test_literal_path_tmp_allowed(self):
        """Simple /tmp literal path should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'data' >> /tmp/deep-review-test-analyzer-abc.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow /tmp literal path, got: {message}")

    def test_literal_path_traversal_blocked(self):
        """Literal path with traversal should be blocked by post-match check"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'data' >> /var/folders/../etc/deep-review-out.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        # Dots are valid regex chars; traversal is caught by post-match ".." check
        self.assertFalse(allowed)

    def test_literal_path_dangerous_directory_blocked(self):
        """Literal path to non-temp directory should be blocked"""
        for path in ["/etc/deep-review-evil", "/bin/deep-review-evil",
                     "/usr/local/bin/deep-review-evil", "/home/user/deep-review-evil"]:
            hook_input = {
                "agent_id": "bug-detector",
                "tool_input": {"command": f"echo 'data' >> {path}"},
            }
            allowed, message = validate_bash_command(hook_input)
            self.assertFalse(allowed, f"Should block write to {path}, got: {message}")

    def test_literal_path_filename_traversal_blocked(self):
        """deep-review-.. as filename should be blocked by post-match check"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'data' >> /tmp/deep-review-.."},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    # --- Adversarial pattern tests ---

    def test_double_quoted_literal_path_allowed(self):
        """Double-quoted literal path should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": 'echo \'{"id":"bug-1"}\' >> "/tmp/deep-review-bug-detector-abc.ndjson"'},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow double-quoted literal path, got: {message}")

    def test_ampersand_in_json_payload_allowed(self):
        """&& inside single-quoted JSON payload should be allowed (not a shell operator)"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo '{\"description\":\"a && b\"}' >> \"/tmp/deep-review-out.ndjson\""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow && inside JSON payload, got: {message}")

    def test_greater_than_in_json_payload_allowed(self):
        """> inside single-quoted JSON payload should be allowed (not a redirect)"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo '{\"description\":\"x > 0\"}' >> \"/tmp/deep-review-out.ndjson\""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow > inside JSON payload, got: {message}")

    def test_subshell_injection_blocked(self):
        """Subshell injection via $() should be blocked (payload must be single-quoted)"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo $(rm -rf /) >> /tmp/deep-review-out.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block subshell injection")

    def test_backtick_injection_blocked(self):
        """Backtick injection should be blocked (payload must be single-quoted)"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo `whoami` >> /tmp/deep-review-out.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block backtick injection")

    def test_newline_injection_blocked(self):
        """Embedded newline in command should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'data' >> /tmp/deep-review-out.ndjson\nrm -rf /"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block command with embedded newline")

    def test_double_quoted_payload_blocked(self):
        """Double-quoted payload allows subshell expansion — must be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": 'echo "$(whoami)" >> /tmp/deep-review-out.ndjson'},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block double-quoted payload (allows $() expansion)")

    def test_double_quoted_simple_blocked(self):
        """Even simple double-quoted payloads are blocked (expansion risk)"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": 'echo "simple data" >> /tmp/deep-review-out.ndjson'},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block all double-quoted payloads")

    def test_ansi_c_quoted_payload_allowed(self):
        """ANSI-C quoting ($'...') is allowed — handles apostrophes safely"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": r"""echo $'{"id":"bug-1","description":"the function\'s return value"}' >> /tmp/deep-review-out.ndjson"""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow ANSI-C quoted payload, got: {message}")

    def test_ansi_c_quoted_with_backslash_escapes(self):
        """ANSI-C quoting with various backslash escapes"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": r"""echo $'{"desc":"line1\\nline2","note":"it\'s fine"}' >> /tmp/deep-review-out.ndjson"""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow ANSI-C escapes, got: {message}")

    def test_unquoted_payload_blocked(self):
        """Unquoted payload allows word splitting and globbing — must be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo data >> /tmp/deep-review-out.ndjson"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block unquoted payload")

    def test_unicode_escaped_apostrophe_in_payload_allowed(self):
        r"""Payload with \u0027 (escaped apostrophe) should be allowed — valid JSON in single quotes"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": r"""echo '{"description":"The context can\u0027t be null"}' >> /tmp/deep-review-out.ndjson"""},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow \\u0027 in payload, got: {message}")

    def test_ls_command_blocked(self):
        """ls command should be blocked for subagents"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "ls -la /tmp"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block ls command")

    def test_and_and_after_path_blocked(self):
        """&& after valid path should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'x' >> /tmp/deep-review-out && rm -rf /"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block && after path")

    def test_and_and_no_space_after_path_blocked(self):
        """&& without space after valid path should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'x' >> /tmp/deep-review-out.ndjson&&rm -rf /"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block && without space after path")

    def test_or_or_after_path_blocked(self):
        """|| after valid path should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'x' >> /tmp/deep-review-out || echo pwned"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block || after path")

    def test_heredoc_blocked(self):
        """Heredoc should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'x' >> /tmp/deep-review-out <<< 'injection'"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block heredoc")

    def test_path_traversal_blocked(self):
        """Path traversal via ../ should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "tool_input": {"command": "echo 'x' >> /tmp/deep-review-../../etc/passwd"},
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block path traversal")


class TestValidateBashHookIntegration(unittest.TestCase):
    """Test the full hook integration with stdin/stdout/stderr"""

    @classmethod
    def setUpClass(cls):
        from scripts.validate_bash_subagent import main
        cls._main = staticmethod(main)

    def test_orchestrator_allowed_via_stdin(self):
        """Test orchestrator allowed via stdin input"""
        hook_input = {"agent_id": None, "tool_input": {"command": "grep -r secret ."}}
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stderr", new_callable=StringIO):
                with self.assertRaises(SystemExit) as context:
                    self._main()
                self.assertEqual(context.exception.code, 0)

    def test_subagent_blocked_via_stdin(self):
        """Test subagent blocked via stdin input"""
        hook_input = {"agent_id": "bug-detector", "tool_input": {"command": "grep -r TODO ."}}
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit) as context:
                    self._main()
                self.assertEqual(context.exception.code, 2)
                self.assertIn("BASH_COMMAND_BLOCKED", mock_stderr.getvalue())

    def test_invalid_json_input(self):
        """Test invalid JSON input"""
        invalid_json = "{invalid json"
        with patch("sys.stdin", StringIO(invalid_json)):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit) as context:
                    self._main()
                self.assertEqual(context.exception.code, 2)
                self.assertIn("Invalid JSON", mock_stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
