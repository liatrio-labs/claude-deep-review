#!/usr/bin/env python3
"""
PreToolUse hook: validate_bash_subagent

Restricts Bash usage in subagents to the finding-emission echo-append pattern only:
  echo ... >> $TMPDIR/deep-review-*

Reads hook input JSON from stdin. Checks:
- agent_id: if missing/null (orchestrator), allow all commands
- command: must match echo-append pattern for subagents
- path: must be $TMPDIR/deep-review-*

Exit 0: command allowed
Exit 2: command blocked (with stderr feedback)
"""

import json
import re
import sys


def validate_bash_command(hook_input):
    """
    Validate a bash command for subagent execution.

    Args:
        hook_input (dict): Hook input with 'agent_id' and 'command'

    Returns:
        tuple: (allowed: bool, message: str)
    """
    agent_id = hook_input.get("agent_id")
    command = hook_input.get("command", "").strip()

    # Orchestrator (no agent_id) is allowed all commands
    if not agent_id:
        return True, "Orchestrator allowed"

    # Subagent: validate command is echo-append to $TMPDIR/deep-review-*
    if not command:
        return False, "Empty command not allowed for subagents"

    # Reject shell operators: pipes, semicolons, and other command chaining
    forbidden_operators = ["|", ";", "&&", "||"]
    for op in forbidden_operators:
        if op in command:
            return False, f"Shell operators not allowed in subagents"

    # Reject single > (overwrite) unless it's part of >> (append)
    # Simple approach: replace all >> with placeholder, then check for remaining >
    cmd_without_append = command.replace(">>", "")
    if ">" in cmd_without_append:
        return False, "echo command must use >> (append) not > (overwrite)"

    # Reject forbidden commands
    forbidden_commands = ["grep", "cat", "git", "find"]
    for forbidden in forbidden_commands:
        if forbidden in command.split()[0] if command.split() else False:
            return False, f"Command '{forbidden}' not allowed in subagents"

    # Validate echo-append pattern: echo ... >> $TMPDIR/deep-review-*
    pattern = r"^\s*echo\s+.+\s+>>\s+\$TMPDIR/deep-review-[a-zA-Z0-9_.-]+$"

    if re.match(pattern, command):
        return True, "Valid echo-append pattern"

    # If we got here, check what part is wrong
    if "echo" not in command:
        return False, f"Command not allowed: {command}"

    if "$TMPDIR/deep-review-" not in command:
        return False, "echo command must append to $TMPDIR/deep-review-*"

    return False, f"Command does not match valid echo-append pattern: {command}"


def main():
    """
    Read hook input from stdin and validate bash command.

    Returns:
        0 if command is allowed
        2 if command is blocked
    """
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"ERROR: Invalid JSON input: {e}\n")
        sys.exit(2)
    except Exception as e:
        sys.stderr.write(f"ERROR: Failed to read hook input: {e}\n")
        sys.exit(2)

    allowed, message = validate_bash_command(hook_input)

    if allowed:
        sys.exit(0)
    else:
        sys.stderr.write(f"BASH_COMMAND_BLOCKED: {message}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
