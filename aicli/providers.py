"""Model provider layer for the AI CLI agent.

This module contains abstractions over different providers that can
generate shell/Git commands from free‑form natural language prompts.
Providers are responsible for interfacing with a local large language
model (LLM) or, in the case of the mock provider, returning
pre‑defined commands from a heuristic dataset.  All providers
implement the ``BaseProvider`` interface with a ``generate_command``
method that accepts a prompt and returns a string containing one or
more shell commands.

Supported providers:

* ``MockProvider`` – returns commands from the dataset loaded via
  :mod:`aicli.training`.  Used when no LLM is configured or
  available.
* ``OllamaProvider`` – wraps the ``ollama`` command line tool to run
  local models.  The ``generate_command`` implementation calls
  ``ollama run`` with the specified model name.  If Ollama is not
  installed or the model does not exist, errors are caught and
  surfaced to the caller.
* ``LMStudioProvider`` – a stub provider included for completeness.
  LM Studio exposes a similar HTTP interface for local models, but
  integration is optional.  If configured, the user must supply an
  endpoint in their config file.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .training import load_examples


class ProviderError(Exception):
    """Raised when a provider fails to generate a command."""


class BaseProvider:
    """Abstract base class for all providers."""

    def generate_command(self, prompt: str) -> str:
        """Return a shell/Git command for the given prompt.

        Subclasses must implement this method.  If a provider is
        unable to handle the prompt (e.g. due to missing models or an
        internal error) it should raise :class:`ProviderError`.
        """
        raise NotImplementedError

    def list_models(self) -> List[str]:
        """Return a list of available model names for this provider.

        The default implementation returns an empty list.  Providers
        that can enumerate models (e.g. Ollama) should override this
        method.  Errors are propagated as exceptions.
        """
        return []


class MockProvider(BaseProvider):
    """Provider that serves commands from a heuristic dataset.

    The mock provider loads a set of examples at initialisation time
    and looks up commands by matching the provided prompt.  Matching
    logic is intentionally simple: it first tries an exact
    case‑insensitive match against the prompt keys, and if none is
    found then performs a substring search across all prompt entries.
    If a unique match is found it returns the associated command;
    otherwise it raises :class:`ProviderError`.
    """

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        # Load examples once at init.  This merges built‑in and user
        # examples.  The structure is a list of dicts with keys
        # ``prompt`` and ``command``.
        self.examples = load_examples()
        # Build a mapping for exact lookups.
        self.prompt_to_command: Dict[str, str] = {
            e["prompt"].strip().lower(): e["command"]
            for e in self.examples
        }

    def generate_command(self, prompt: str) -> str:
        """Return a command from the dataset matching the prompt.

        :param prompt: Free‑form natural language request.
        :returns: Shell/Git command string.
        :raises ProviderError: When no suitable command is found.
        """
        normalized = prompt.strip().lower()
        if not normalized:
            raise ProviderError("Empty prompt provided")
        # Exact match
        if normalized in self.prompt_to_command:
            return self.prompt_to_command[normalized]
        # Substring match: collect all commands whose prompt appears
        # within the input prompt.  Using case‑insensitive comparison.
        matches = []
        for example in self.examples:
            p_norm = example["prompt"].strip().lower()
            if p_norm and p_norm in normalized:
                matches.append(example["command"])
        # If one unique match is found use it.
        if len(matches) == 1:
            return matches[0]
        # Fallback: simple heuristics for common Git/Bash patterns.
        # For example, stage and commit with a given message.
        # We look for keywords in the prompt and build commands.
        try:
            fallback = self._heuristic_generate(normalized)
            if fallback:
                return fallback
        except Exception:
            # Ignore heuristic errors and fall through
            pass
        raise ProviderError("No matching command found in dataset")

    def _heuristic_generate(self, prompt: str) -> Optional[str]:
        """Generate a command using simple keyword heuristics.

        This helper is invoked when no exact or substring match is
        found.  It handles a handful of common instructions that are
        easily parsed via keyword detection.  The goal is not to
        replace a proper language model but to cover some frequent
        patterns without invoking external providers.
        """
        # GitHub repository creation workflows
        if any(keyword in prompt for keyword in ["github", "repository", "repo"]) and any(keyword in prompt for keyword in ["create", "initialize", "init", "set up", "start"]):
            if any(keyword in prompt for keyword in ["push", "publish", "upload"]):
                return "git init && git add . && git commit -m \"Initial commit\" && git branch -M main && git remote add origin REPO_URL && git push -u origin main"
            else:
                return "git init"
        
        # Stage all changes and commit
        if "commit" in prompt and "message" in prompt:
            # Extract the quoted message if present
            msg = None
            if '"' in prompt:
                parts = prompt.split('"')
                if len(parts) >= 3:
                    msg = parts[1]
            if msg:
                return f"git add . && git commit -m \"{msg}\""
            return "git add . && git commit -m \"commit\""
        if "stage all" in prompt or ("stage" in prompt and "all" in prompt):
            return "git add ."
        if "status" in prompt:
            return "git status"
        if "push" in prompt:
            # Default push to origin and current branch
            branch = "$(git rev-parse --abbrev-ref HEAD)"
            return f"git push origin {branch}"
        if "pull" in prompt:
            return "git pull"
        if "init" in prompt:
            return "git init"
        if "clone" in prompt:
            # Assume last word is repo URL
            parts = prompt.split()
            url = parts[-1]
            return f"git clone {shlex.quote(url)}"
        return None

    def list_models(self) -> List[str]:
        """The mock provider has no models to list."""
        return []


class OllamaProvider(BaseProvider):
    """Provider that interfaces with the Ollama CLI.

    Ollama (https://ollama.ai/) allows running large language models
    locally via a simple command line interface.  This provider uses
    ``subprocess`` to invoke the ``ollama`` binary.  It supports
    listing installed models and generating commands by asking the
    model to translate the prompt into a shell/Git command.  If the
    Ollama CLI or the specified model is unavailable, a
    :class:`ProviderError` is raised.
    """

    def __init__(self, model_name: str, endpoint: Optional[str] = None) -> None:
        self.model_name = model_name
        self.endpoint = endpoint

    def _check_ollama(self) -> None:
        """Ensure the ollama CLI is installed and executable."""
        from shutil import which
        if which("ollama") is None:
            raise ProviderError(
                "Ollama CLI not found. Please install Ollama or configure another provider."
            )

    def list_models(self) -> List[str]:
        """Return a list of models installed via Ollama."""
        self._check_ollama()
        try:
            proc = subprocess.run(
                ["ollama", "list", "--json"],
                capture_output=True,
                text=True,
                check=True,
            )
            # Ollama returns JSON array of objects with name and size
            # (see https://github.com/jmorganca/ollama).  Parse names.
            data = json.loads(proc.stdout)
            return [item["name"] for item in data]
        except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            raise ProviderError(f"Failed to list models via Ollama: {exc}")

    def generate_command(self, prompt: str) -> str:
        """Generate a shell command using the configured Ollama model.

        This method constructs a prompt instructing the model to
        output only the command(s) and returns the response.  It
        includes some context to steer the model away from including
        explanations or markdown.  If the call fails, a
        :class:`ProviderError` is raised.
        """
        self._check_ollama()
        if not prompt.strip():
            raise ProviderError("Empty prompt provided")
        # Compose the system and user messages for a chat prompt.  We
        # instruct the model to be concise and output only the commands.
        # Since Ollama's CLI currently expects a plain text prompt, we
        # include directives inline.
        # Example: ``Translate the following request into a bash command: ...``
        system_prompt = (
            "Translate the following request into a valid bash or git command. "
            "Return only the command(s) without backticks, markdown or explanation. "
            "If multiple commands are required, separate them with ' && '."
        )
        full_prompt = f"{system_prompt}\n{prompt.strip()}"
        # Invoke the model via ollama run.  We request raw text output.
        try:
            proc = subprocess.run(
                ["ollama", "run", self.model_name, full_prompt],
                capture_output=True,
                text=True,
                check=True,
            )
            response = proc.stdout.strip()
            # Ollama may echo the prompt or include additional
            # formatting; attempt to take only the last non‑empty line.
            lines = [line.strip() for line in response.splitlines() if line.strip()]
            if not lines:
                raise ProviderError("Model returned no output")
            # Return last line as the command.
            return lines[-1]
        except subprocess.CalledProcessError as exc:
            raise ProviderError(f"Failed to call Ollama model: {exc}")


class LMStudioProvider(BaseProvider):
    """Provider stub for LM Studio.

    This class is included for completeness.  LM Studio runs local
    models behind an HTTP API.  To use it, the user must specify an
    endpoint in their config (e.g. http://localhost:1234).  If no
    endpoint is provided, attempts to generate commands will fail.
    """

    def __init__(self, model_name: str, endpoint: Optional[str] = None) -> None:
        self.model_name = model_name
        self.endpoint = endpoint

    def list_models(self) -> List[str]:
        # LM Studio's API may not provide a model listing endpoint; return empty.
        return []

    def generate_command(self, prompt: str) -> str:
        raise ProviderError(
            "LM Studio provider is not implemented. Please configure a supported provider or use mock."
        )


def get_provider(provider_name: str, model_name: str, endpoint: Optional[str] = None) -> BaseProvider:
    """Factory function to instantiate the appropriate provider.

    :param provider_name: Name of the provider ('ollama', 'lmstudio', 'mock').
    :param model_name: Name of the model to use.
    :param endpoint: Optional endpoint for HTTP‑based providers.
    :returns: A provider instance.
    :raises ValueError: If the provider name is unknown.
    """
    name = provider_name.lower().strip()
    if name == "ollama":
        return OllamaProvider(model_name, endpoint)
    if name == "lmstudio":
        return LMStudioProvider(model_name, endpoint)
    if name == "mock":
        return MockProvider(model_name)
    raise ValueError(f"Unknown provider: {provider_name}")