"""State detection and remedial suggestions.

The agent attempts to identify common failure modes when executing
generated commands and provides follow‑up advice to help the user
reach their desired state.  This module parses stderr output from
shell commands and returns short messages or suggested commands when
a known error pattern is detected.  The logic here is intentionally
simple and covers a handful of frequently encountered Git errors.

For example, if a command fails with ``fatal: not a git repository``,
we suggest running ``git init``.  If pushing fails due to missing
remote, we suggest adding a remote.  Additional patterns can be
added over time as users contribute feedback.
"""

from __future__ import annotations

import re
from typing import List, Optional


def detect_state_error(stderr: str) -> Optional[str]:
    """Inspect stderr for known error patterns and return advice.

    :param stderr: Standard error output from the executed command.
    :returns: A suggestion string or ``None`` if no known pattern is
      matched.
    """
    text = stderr.lower()
    # Not a git repository
    if "not a git repository" in text or "not in a git directory" in text:
        return "It looks like you are not in a Git repository. Try running 'git init' first."
    # No configured user name/email
    if "please tell me who you are" in text or "unable to auto-detect email address" in text:
        # The message includes quotes around placeholders; we use escaped quotes to avoid syntax errors.
        return (
            "Your Git user name and email are not configured. Run "
            "'git config user.name \"<Your Name>\"' and "
            "'git config user.email \"you@example.com\"'."
        )
    # No remote repository configured
    if "no configured push destination" in text or "no upstream branch" in text:
        return "No upstream branch is set. Use 'git push -u origin <branch>' to set the upstream."
    # Authentication or permission denied errors
    if "permission denied" in text and "git" in text:
        return "Permission denied when accessing remote. Ensure you have access rights or SSH keys configured."
    # Untracked files present when switching branches
    if "untracked working tree files would be overwritten" in text:
        return "Some untracked files would be overwritten. Consider stashing or moving them before switching branches."
    return None


def suggest_followup(stderr: str) -> List[str]:
    """Return a list of follow‑up commands based on stderr patterns.

    Suggestions are derived from the same error patterns as
    :func:`detect_state_error`, but return explicit commands instead
    of descriptive messages.  If no known pattern is matched, an
    empty list is returned.
    """
    text = stderr.lower()
    suggestions: List[str] = []
    if "not a git repository" in text or "not in a git directory" in text:
        suggestions.append("git init")
    if "please tell me who you are" in text or "unable to auto-detect email address" in text:
        suggestions.extend([
            'git config user.name "Your Name"',
            'git config user.email "you@example.com"',
        ])
    if "no configured push destination" in text or "no upstream branch" in text:
        suggestions.append("git push -u origin $(git rev-parse --abbrev-ref HEAD)")
    if "permission denied" in text and "git" in text:
        suggestions.append("Check your SSH keys or repository permissions.")
    if "untracked working tree files would be overwritten" in text:
        suggestions.append("git stash --include-untracked")
    return suggestions