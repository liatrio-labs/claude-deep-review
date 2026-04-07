"""
Tests for scripts/validate_bash_subagent.py

Covers:
  - orchestrator (no agent_id) allowed all commands
  - subagent valid echo-append pattern to $TMPDIR/deep-review-* allowed
  - subagent grep/cat/git/find commands blocked
  - subagent echo without append (>) blocked
  - subagent echo to wrong path blocked
  - empty command blocked for subagents
  - whitespace handling and variations
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
        hook_input = {"agent_id": None, "command": "grep -r secret ."}
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)
        self.assertIn("Orchestrator", message)

    def test_orchestrator_empty_agent_id(self):
        """Orchestrator with empty agent_id should allow any command"""
        hook_input = {"agent_id": "", "command": "grep -r secret ."}
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_orchestrator_missing_agent_id(self):
        """Orchestrator with missing agent_id field should allow any command"""
        hook_input = {"command": "find . -name secret"}
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_subagent_valid_echo_append(self):
        """Subagent valid echo-append pattern should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo '[{\"bug\": true}]' >> $TMPDIR/deep-review-findings",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_subagent_valid_echo_append_with_spaces(self):
        """Subagent valid echo-append with extra spaces should be allowed"""
        hook_input = {
            "agent_id": "security-reviewer",
            "command": "echo 'test' >>  $TMPDIR/deep-review-output.json",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_subagent_valid_echo_append_with_leading_whitespace(self):
        """Subagent valid echo-append with leading whitespace should be allowed"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "   echo 'data' >> $TMPDIR/deep-review-temp",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_subagent_valid_echo_append_complex_data(self):
        """Subagent valid echo-append with complex JSON data should be allowed"""
        hook_input = {
            "agent_id": "security-reviewer",
            "command": """echo '{"type":"security","severity":"high","line":42}' >> $TMPDIR/deep-review-security""",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed)

    def test_subagent_grep_blocked(self):
        """Subagent grep command should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "grep -r TODO .",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("grep", message.lower())

    def test_subagent_cat_blocked(self):
        """Subagent cat command should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "cat file.txt",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("cat", message.lower())

    def test_subagent_git_blocked(self):
        """Subagent git command should be blocked"""
        hook_input = {
            "agent_id": "security-reviewer",
            "command": "git log --oneline",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("git", message.lower())

    def test_subagent_find_blocked(self):
        """Subagent find command should be blocked"""
        hook_input = {
            "agent_id": "type-reviewer",
            "command": "find . -name '*.py'",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("find", message.lower())

    def test_subagent_echo_without_append_blocked(self):
        """Subagent echo with > (overwrite) instead of >> (append) should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo 'data' > $TMPDIR/deep-review-output",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn(">>", message)

    def test_subagent_echo_to_wrong_path_blocked(self):
        """Subagent echo to non-deep-review path should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo 'data' >> /tmp/other-file",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("$TMPDIR/deep-review", message)

    def test_subagent_echo_to_home_blocked(self):
        """Subagent echo to home directory should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo 'data' >> ~/.bashrc",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_subagent_empty_command_blocked(self):
        """Subagent with empty command should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("Empty", message)

    def test_subagent_whitespace_only_command_blocked(self):
        """Subagent with whitespace-only command should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "   ",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)
        self.assertIn("Empty", message)

    def test_subagent_command_with_pipe_blocked(self):
        """Subagent with piped commands should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo 'test' | grep test >> $TMPDIR/deep-review-output",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_subagent_echo_with_semicolon_blocked(self):
        """Subagent with command chaining should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo 'test' >> $TMPDIR/deep-review-out; rm -rf /",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed)

    def test_various_tmpdir_suffixes_allowed(self):
        """Various valid $TMPDIR/deep-review-* suffixes should be allowed"""
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
                "command": f"echo 'data' >> $TMPDIR/deep-review-{suffix}",
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

    # --- Adversarial pattern tests ---

    def test_double_quoted_path_allowed(self):
        """Double-quoted $TMPDIR path should be allowed (agents may quote the path)"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": 'echo \'{"id":"bug-1"}\' >> "$TMPDIR/deep-review-bug-detector-abc.ndjson"',
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow double-quoted path, got: {message}")

    def test_ampersand_in_json_payload_allowed(self):
        """&& inside single-quoted JSON payload should be allowed (not a shell operator)"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo '{\"description\":\"a && b\"}' >> \"$TMPDIR/deep-review-out.ndjson\"",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow && inside JSON payload, got: {message}")

    def test_greater_than_in_json_payload_allowed(self):
        """> inside single-quoted JSON payload should be allowed (not a redirect)"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo '{\"description\":\"x > 0\"}' >> \"$TMPDIR/deep-review-out.ndjson\"",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertTrue(allowed, f"Should allow > inside JSON payload, got: {message}")

    def test_subshell_injection_blocked(self):
        """Subshell injection via $() should be blocked (payload must be single-quoted)"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo $(rm -rf /) >> $TMPDIR/deep-review-out.ndjson",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block subshell injection")

    def test_backtick_injection_blocked(self):
        """Backtick injection should be blocked (payload must be single-quoted)"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo `whoami` >> $TMPDIR/deep-review-out.ndjson",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block backtick injection")

    def test_newline_injection_blocked(self):
        """Embedded newline in command should be blocked"""
        hook_input = {
            "agent_id": "bug-detector",
            "command": "echo 'data' >> $TMPDIR/deep-review-out.ndjson\nrm -rf /",
        }
        allowed, message = validate_bash_command(hook_input)
        self.assertFalse(allowed, "Should block command with embedded newline")


class TestValidateBashHookIntegration(unittest.TestCase):
    """Test the full hook integration with stdin/stdout/stderr"""

    def test_orchestrator_allowed_via_stdin(self):
        """Test orchestrator allowed via stdin input"""
        hook_input = {"agent_id": None, "command": "grep -r secret ."}
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit) as context:
                    # Simulate calling main()
                    from scripts.validate_bash_subagent import main

                    main()
                self.assertEqual(context.exception.code, 0)

    def test_subagent_blocked_via_stdin(self):
        """Test subagent blocked via stdin input"""
        hook_input = {"agent_id": "bug-detector", "command": "grep -r TODO ."}
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit) as context:
                    from scripts.validate_bash_subagent import main

                    main()
                self.assertEqual(context.exception.code, 2)
                self.assertIn("BASH_COMMAND_BLOCKED", mock_stderr.getvalue())

    def test_invalid_json_input(self):
        """Test invalid JSON input"""
        invalid_json = "{invalid json"
        with patch("sys.stdin", StringIO(invalid_json)):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with self.assertRaises(SystemExit) as context:
                    from scripts.validate_bash_subagent import main

                    main()
                self.assertEqual(context.exception.code, 2)
                self.assertIn("Invalid JSON", mock_stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
