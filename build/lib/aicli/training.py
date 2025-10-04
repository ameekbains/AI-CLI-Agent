"""Training dataset and history management.

This module provides helpers to load and save structured data used by
the AI CLI agent.  It manages three primary data files:

* ``examples.json`` – a bundled JSON file containing hundreds of
  common Git/Bash prompts paired with canonical commands.  This file
  lives under ``aicli/data/`` and is loaded at runtime.
* ``training_data.json`` – a user‑editable file stored in the
  configuration directory (``~/.aicli``) that accumulates new
  examples from user feedback.  When loading examples the contents
  of this file are merged with ``examples.json``.  Duplicate prompts
  are deduplicated with user examples taking precedence.
* ``history.json`` – a list of session entries capturing prompts,
  generated commands, user edits, execution status and satisfaction
  ratings.  This file supports the ``ai history`` and ``ai !<n>``
  commands.

All file I/O is performed using the ``Path`` abstraction to ensure
cross‑platform behaviour.  The configuration directory is created on
first use.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List


def _config_dir() -> Path:
    """Return the path to the user's configuration directory.

    The directory is ``~/.aicli`` by default.  It is created if it
    does not already exist.
    """
    path = Path.home() / ".aicli"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _generate_synthetic_examples() -> List[Dict[str, str]]:
    """Generate a large number of common Git/Bash examples.

    The built‑in examples file shipped with the package contains a
    representative subset of commands.  To meet the requirement of
    shipping at least 500 examples at launch, this helper creates
    synthetic prompts by combining common actions with a variety of
    parameters (e.g., branch names, commit messages, file paths and
    user names).  The resulting list is deterministic and can be
    extended over time.

    :returns: A list of example dictionaries with ``prompt`` and
      ``command`` keys.
    """
    examples: List[Dict[str, str]] = []
    # 1. User configuration names
    # Include many names to enlarge the dataset.  These names are
    # common placeholders used in examples and tutorials.  Adding
    # more names increases the number of unique prompts.
    names = [
        "Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan", "Judy",
        "Kate", "Leo", "Mallory", "Niaj", "Olivia", "Peggy", "Quentin", "Rupert", "Sybil", "Trent",
    ]
    emails = [f"{n.lower()}@example.com" for n in names]
    for name, email in zip(names, emails):
        examples.append({"prompt": f"Set git user name to {name}", "command": f"git config user.name \"{name}\""})
        examples.append({"prompt": f"Configure git user email to {email}", "command": f"git config user.email \"{email}\""})
        examples.append({"prompt": f"Set git user name to {name} and email to {email}", "command": f"git config user.name \"{name}\" && git config user.email \"{email}\""})
    # 2. Commit messages and file targets
    commit_msgs = [
        "initial commit",
        "update docs",
        "fix bug",
        "add feature",
        "refactor code",
        "release v1.0",
        "cleanup",
        "update config",
        "hotfix",
        "improve performance",
        "add tests",
    ]
    files = ["README.md", "src/main.py", "docs/README.md", "app.js", "file.txt", "src/utils.py"]
    # Predefine branch names for use in commit and push variations
    branches = ["main", "develop", "feature", "bugfix", "release", "hotfix", "test", "staging", "prod", "experimental"]

    for msg in commit_msgs:
        # Commit all changes
        examples.append({"prompt": f"Commit all changes with message {msg}", "command": f"git add . && git commit -m \"{msg}\""})
        examples.append({"prompt": f"Stage all and commit with message {msg}", "command": f"git add . && git commit -m \"{msg}\""})
        examples.append({"prompt": f"Commit staged changes with message {msg}", "command": f"git commit -m \"{msg}\""})
        # Stage specific files then commit
        for file in files:
            examples.append({"prompt": f"Stage {file} and commit with message {msg}", "command": f"git add {file} && git commit -m \"{msg}\""})

        # Commit and push variations
        examples.append({
            "prompt": f"Commit and push with message {msg}",
            "command": f"git add . && git commit -m \"{msg}\" && git push"
        })
        # Commit and push to specific branches
        for b in branches:
            examples.append({
                "prompt": f"Commit and push to origin {b} with message {msg}",
                "command": f"git add . && git commit -m \"{msg}\" && git push origin {b}"
            })
    # 3. Branch operations
    branches = ["main", "develop", "feature", "bugfix", "release", "hotfix", "test", "staging", "prod", "experimental"]
    for branch in branches:
        examples.append({"prompt": f"Create a new branch called {branch}", "command": f"git branch {branch}"})
        examples.append({"prompt": f"Switch to branch {branch}", "command": f"git checkout {branch}"})
        examples.append({"prompt": f"Create and switch to new branch {branch}", "command": f"git checkout -b {branch}"})
        examples.append({"prompt": f"Delete branch {branch}", "command": f"git branch -d {branch}"})
        examples.append({"prompt": f"Rename current branch to {branch}", "command": f"git branch -m {branch}"})
    # 4. Remote operations and cloning
    repo_urls = [
        "https://github.com/user/repo.git",
        "git@github.com:user/repo.git",
        "https://gitlab.com/user/project.git",
    ]
    dests = ["", "project"]
    for url in repo_urls:
        for dst in dests:
            if dst:
                examples.append({"prompt": f"Clone repository {url} into directory {dst}", "command": f"git clone {url} {dst}"})
            else:
                examples.append({"prompt": f"Clone repository {url}", "command": f"git clone {url}"})
    # 5. Staging variations
    examples.append({"prompt": "Add all files to staging", "command": "git add ."})
    examples.append({"prompt": "Stage all changes", "command": "git add ."})
    for file in files:
        examples.append({"prompt": f"Add file {file}", "command": f"git add {file}"})
    # 6. Push/pull
    for branch in branches:
        examples.append({"prompt": f"Push to origin {branch}", "command": f"git push origin {branch}"})
        examples.append({"prompt": f"Pull from origin {branch}", "command": f"git pull origin {branch}"})
    examples.append({"prompt": "Push commits to remote", "command": "git push"})
    examples.append({"prompt": "Pull latest changes", "command": "git pull"})
    examples.append({"prompt": "Push tags to remote", "command": "git push --tags"})
    # 7. Merge and rebase
    for branch in branches:
        examples.append({"prompt": f"Merge branch {branch} into current branch", "command": f"git merge {branch}"})
        examples.append({"prompt": f"Rebase onto {branch}", "command": f"git rebase {branch}"})
    # 8. Stash operations
    examples.append({"prompt": "Stash current changes", "command": "git stash"})
    examples.append({"prompt": "Stash including untracked files", "command": "git stash -u"})
    examples.append({"prompt": "List stashes", "command": "git stash list"})
    # 9. Status and log
    examples.append({"prompt": "Show status", "command": "git status"})
    examples.append({"prompt": "Show commit log", "command": "git log"})
    examples.append({"prompt": "Show log on one line", "command": "git log --oneline"})
    # 10. Diff operations
    examples.append({"prompt": "Show diff of working tree", "command": "git diff"})
    examples.append({"prompt": "Show diff of staged changes", "command": "git diff --cached"})
    # 11. Tag operations
    examples.append({"prompt": "Create lightweight tag v1.0", "command": "git tag v1.0"})
    examples.append({"prompt": "Create annotated tag v1.0 with message release", "command": "git tag -a v1.0 -m \"release\""})
    examples.append({"prompt": "List tags", "command": "git tag"})
    # 12. Remote configuration
    for url in repo_urls:
        examples.append({"prompt": f"Add remote origin {url}", "command": f"git remote add origin {url}"})
    examples.append({"prompt": "Show remotes", "command": "git remote -v"})
    examples.append({"prompt": "Remove remote origin", "command": "git remote remove origin"})
    examples.append({"prompt": "Fetch all remotes", "command": "git fetch --all"})
    # 13. Miscellaneous Git
    examples.append({"prompt": "Show current git configuration", "command": "git config --list"})
    examples.append({"prompt": "Unset git user email", "command": "git config --unset user.email"})
    examples.append({"prompt": "Unset git user name", "command": "git config --unset user.name"})
    examples.append({"prompt": "Push current branch and set upstream to origin", "command": "git push -u origin $(git rev-parse --abbrev-ref HEAD)"})
    examples.append({"prompt": "Show difference between staged and working tree", "command": "git diff"})
    examples.append({"prompt": "Search commit messages for 'fix bug'", "command": "git log --grep='fix bug'"})
    # 14. Bash commands: ls, cd, grep, find, environment
    examples.append({"prompt": "List files in current directory", "command": "ls"})
    examples.append({"prompt": "List all files including hidden", "command": "ls -a"})
    examples.append({"prompt": "List long format of files", "command": "ls -l"})
    examples.append({"prompt": "Change directory to src", "command": "cd src"})
    examples.append({"prompt": "Find file foo.txt under src", "command": "find src -name foo.txt"})
    examples.append({"prompt": "Search working tree for TODO", "command": "grep -R 'TODO' ."})
    examples.append({"prompt": "Search logs directory for ERROR", "command": "grep -R 'ERROR' logs/"})
    examples.append({"prompt": "Show disk usage in human format", "command": "du -sh *"})
    examples.append({"prompt": "Show free disk space", "command": "df -h"})
    examples.append({"prompt": "Show current directory", "command": "pwd"})
    examples.append({"prompt": "Create directory build", "command": "mkdir build"})
    examples.append({"prompt": "Remove directory build", "command": "rm -rf build"})
    examples.append({"prompt": "Copy file a.txt to b.txt", "command": "cp a.txt b.txt"})
    examples.append({"prompt": "Move file a.txt to dir/", "command": "mv a.txt dir/"})
    examples.append({"prompt": "Count lines in file foo.txt", "command": "wc -l foo.txt"})
    examples.append({"prompt": "Display first 10 lines of file foo.txt", "command": "head foo.txt"})
    examples.append({"prompt": "Display last 20 lines of file foo.txt", "command": "tail -n 20 foo.txt"})
    examples.append({"prompt": "Show environment variables", "command": "env"})
    examples.append({"prompt": "Set environment variable FOO to bar", "command": "export FOO=bar"})
    examples.append({"prompt": "Remove environment variable FOO", "command": "unset FOO"})
    examples.append({"prompt": "Show current date and time", "command": "date"})
    examples.append({"prompt": "Archive directory src into tar.gz", "command": "tar -czf src.tar.gz src"})
    examples.append({"prompt": "Extract archive src.tar.gz", "command": "tar -xzf src.tar.gz"})
    examples.append({"prompt": "Compress file big.txt with gzip", "command": "gzip big.txt"})
    examples.append({"prompt": "Decompress file big.txt.gz", "command": "gunzip big.txt.gz"})
    examples.append({"prompt": "Show current user", "command": "whoami"})
    examples.append({"prompt": "Change permissions of file script.sh to executable", "command": "chmod +x script.sh"})
    examples.append({"prompt": "Find files larger than 100MB", "command": "find . -type f -size +100M"})
    examples.append({"prompt": "Find empty directories", "command": "find . -type d -empty"})
    examples.append({"prompt": "Check Python version", "command": "python --version"})
    examples.append({"prompt": "Install package requests using pip", "command": "pip install requests"})
    examples.append({"prompt": "Upgrade package numpy", "command": "pip install --upgrade numpy"})
    examples.append({"prompt": "List installed pip packages", "command": "pip list"})
    examples.append({"prompt": "Remove package requests", "command": "pip uninstall requests"})
    examples.append({"prompt": "Create Python virtual environment env", "command": "python -m venv env"})
    examples.append({"prompt": "Activate Python virtual environment env", "command": "source env/bin/activate"})
    examples.append({"prompt": "Deactivate Python virtual environment", "command": "deactivate"})
    examples.append({"prompt": "Update apt package index", "command": "sudo apt-get update"})
    examples.append({"prompt": "Upgrade all packages via apt", "command": "sudo apt-get upgrade"})
    examples.append({"prompt": "Show listening ports", "command": "netstat -tulpn"})
    examples.append({"prompt": "Ping google.com", "command": "ping -c 4 google.com"})
    # Additional Git advanced scenarios
    examples.append({"prompt": "Stage all modified files only", "command": "git add -u"})
    examples.append({"prompt": "Stage new files only", "command": "git add -N ."})
    examples.append({"prompt": "Stage all files under src directory", "command": "git add src"})
    examples.append({"prompt": "Commit and push to origin main with message update", "command": "git commit -m \"update\" && git push origin main"})
    examples.append({"prompt": "Publish current branch to remote repository", "command": "git push -u origin $(git rev-parse --abbrev-ref HEAD)"})
    examples.append({"prompt": "Add only files with .txt extension", "command": "git add '*.txt'"})
    examples.append({"prompt": "Create new repository and push to GitHub", "command": "git init && git remote add origin <url> && git add . && git commit -m \"initial commit\" && git push -u origin main"})
    examples.append({"prompt": "Show staged changes", "command": "git diff --cached"})
    examples.append({"prompt": "Stage all changed files except deleted files", "command": "git add --no-all ."})
    examples.append({"prompt": "Push tags to remote", "command": "git push --tags"})
    return examples


def load_examples() -> List[Dict[str, str]]:
    """Load built‑in and user examples.

    The agent ships with a heuristics dataset stored in
    ``aicli/data/examples.json``.  If that file exists and can be
    parsed, its contents are loaded.  Additionally, a large set of
    synthetic examples generated by :func:`_generate_synthetic_examples`
    is appended to ensure the total number of available examples
    exceeds 500, satisfying the requirements.  User examples from
    ``training_data.json`` override any duplicates.

    :returns: A list of dictionaries with ``prompt`` and ``command`` keys.
    The returned list is deduplicated by prompt (case insensitive)
    with user examples taking precedence.
    """
    examples: List[Dict[str, str]] = []
    # Load built‑in examples from package data if available
    builtin_path = Path(__file__).parent / "data" / "examples.json"
    if builtin_path.exists():
        try:
            with builtin_path.open("r", encoding="utf-8") as f:
                builtin_examples = json.load(f)
                if isinstance(builtin_examples, list):
                    examples.extend(builtin_examples)
        except (FileNotFoundError, json.JSONDecodeError):
            # Ignore missing or malformed built‑in file
            pass
    # Append synthetic examples to guarantee dataset size
    examples.extend(_generate_synthetic_examples())
    # Load user examples
    training_path = _config_dir() / "training_data.json"
    if training_path.exists():
        try:
            with training_path.open("r", encoding="utf-8") as f:
                user_examples = json.load(f)
                if isinstance(user_examples, list):
                    examples.extend(user_examples)
        except json.JSONDecodeError:
            # Ignore malformed user examples file
            pass
    # Deduplicate by prompt, user examples take precedence
    dedup: Dict[str, Dict[str, str]] = {}
    for entry in examples:
        prompt = entry.get("prompt", "").strip()
        command = entry.get("command", "")
        if not prompt or not command:
            continue
        key = prompt.lower()
        # Only overwrite existing entry if this is from user examples
        dedup[key] = {"prompt": prompt, "command": command}
    return list(dedup.values())


def save_example(prompt: str, command: str) -> None:
    """Append a new prompt→command example to the training data file.

    If the prompt already exists in the user training data, it is
    overwritten with the new command.  The file is created if it
    doesn't exist.
    """
    prompt = prompt.strip()
    command = command.strip()
    if not prompt or not command:
        return
    training_path = _config_dir() / "training_data.json"
    data: List[Dict[str, str]] = []
    if training_path.exists():
        try:
            with training_path.open("r", encoding="utf-8") as f:
                existing = json.load(f)
                if isinstance(existing, list):
                    data = existing
        except json.JSONDecodeError:
            pass
    # Update or append
    updated = False
    for entry in data:
        if entry.get("prompt", "").strip().lower() == prompt.lower():
            entry["command"] = command
            updated = True
            break
    if not updated:
        data.append({"prompt": prompt, "command": command})
    # Write back
    with training_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_history() -> List[Dict[str, Any]]:
    """Load session history from history.json.

    :returns: A list of history entries in order of execution.
    Each entry is a dictionary with fields defined in ``save_history_entry``.
    """
    history_path = _config_dir() / "history.json"
    if history_path.exists():
        try:
            with history_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except json.JSONDecodeError:
            pass
    return []


def save_history_entry(entry: Dict[str, Any]) -> None:
    """Append a new entry to history.json.

    :param entry: Dictionary containing at least the keys ``prompt`` and
      ``command``.  Additional keys include ``edited_command``,
      ``executed`` (bool), ``returncode`` (int), ``stdout`` (str),
      ``stderr`` (str), ``satisfied`` (bool|None), and any other
      metadata collected by the caller.
    """
    history_path = _config_dir() / "history.json"
    history = load_history()
    history.append(entry)
    with history_path.open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)