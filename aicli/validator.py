"""Command validation utilities.

The AI CLI agent must ensure that model outputs are safe and properly
formatted before presenting them to the user.  This module
implements simple heuristics to detect and reject outputs that
include markdown fences, backticks, unresolved placeholders, or
potentially dangerous shell operations.  It also provides a helper
for summarising validation errors.

Validation is conservative by design: if a command contains any
disallowed patterns, it is marked invalid.  The caller must then
prompt the user to edit the command before execution or decline to
run it altogether.
"""

import re
from typing import Tuple


def validate_command(command: str) -> Tuple[bool, str]:
    """Validate the generated command string.

    :param command: Command string returned by the provider.
    :returns: Tuple ``(is_valid, reason)``.  ``is_valid`` is ``True``
      when the command passes all checks.  When ``False``, ``reason``
      describes why the command was rejected.

    Validation criteria:

    * Command must not be empty or whitespace.
    * It must not contain Markdown code fences (````` or triple backticks) or
      backtick delimiters.
    * It must not contain unresolved placeholders of the form ``<...>``.
    * It must not contain embedded newlines that are not clearly
      separating multiple commands; newlines are converted to ``&&`` by
      the caller so they are allowed here.
    * It must not include obviously dangerous patterns such as
      ``rm -rf`` or fork bombs.
    """
    cmd = command.strip()
    if not cmd:
        return False, "Command is empty"
    # Disallow Markdown fences and backticks
    if "```" in cmd or "`" in cmd:
        return False, "Command contains backticks or Markdown fences"
    # Disallow unresolved placeholders <...> but allow REPO_URL placeholder
    if re.search(r"<[^>]+>", cmd):
        return False, "Command contains unresolved placeholders"
    # Allow REPO_URL placeholder as it's meant to be replaced by user
    if "REPO_URL" in cmd:
        # REPO_URL is allowed as a placeholder that users should replace
        pass
    # Disallow certain dangerous patterns
    dangerous_patterns = [
        r"rm\s+-rf",  # destructive recursive remove
        r"sudo\s+rm",  # privileged remove
        r"mkfs",  # format filesystem
        r":\(\)\s*\{\s*:|:\|:&\s*;\s*\}",  # fork bomb
        r"dd\s+if=",  # disk copying may be destructive
        r">\s*/dev/sda",  # redirecting to block devices
        r"shutdown",  # shut down the machine
        r"reboot",  # reboot the machine
        r"halt",  # halt system
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, cmd, flags=re.IGNORECASE):
            return False, "Command contains potentially dangerous operations"
    return True, ""


def is_dangerous(command: str) -> bool:
    """Return True if the command contains destructive operations.

    This function is a simple wrapper around the dangerous pattern
    detection logic.  It is provided to let callers check whether
    additional confirmation should be required even when the overall
    command passes validation (e.g. ``rm -rf`` with explicit
    confirmation).
    """
    valid, reason = validate_command(command)
    if valid:
        # Even if valid overall we want to flag potentially dangerous
        # patterns separately.  Use the same regexes as above.
        return False
    return "dangerous" in reason.lower()