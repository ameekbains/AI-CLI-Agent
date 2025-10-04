"""Command line interface for the AI CLI agent.

This module defines the ``ai`` command using the ``click`` library.
It exposes several subcommands:

``ai configure``
    Configure the model provider and model name.  Writes
    ``~/.aicli/config.yaml``.

``ai list-models``
    List available models for the configured provider.  If none are
    found or the provider is unavailable, the mock provider is used
    and a recommendation is printed.

``ai run <prompt>``
    Generate, validate and optionally execute commands for the given
    prompt.  Supports ``--yes`` to skip confirmation and editing when
    the command is valid.

``ai history``
    Display previously executed commands.  Shows the index,
    prompt and command.  Use ``ai ! <n>`` to re‑run a command.

``ai ! <n>``
    Re‑run the command at index ``n`` from the history.  The same
    confirmation and validation logic applies.

``ai serve``
    Launch a FastAPI server exposing a JSON API for external
    integrations.  The server listens on port 5005 by default.
"""

from __future__ import annotations

import datetime as _datetime
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click
import yaml

from . import providers
from .providers import get_provider, ProviderError
from .validator import validate_command
from .training import load_history, save_history_entry, load_examples, save_example
from .state import detect_state_error, suggest_followup


DEFAULT_CONFIG = {
    "model": {
        "provider": "mock",
        "name": "mock",
        "endpoint": None,
    },
    "safe_mode": True,
    "history": True,
}


def _config_file() -> Path:
    """Return the path to the configuration file (~/.aicli/config.yaml)."""
    from .training import _config_dir  # reuse helper

    return _config_dir() / "config.yaml"


def load_config() -> dict:
    """Load YAML configuration, returning defaults if missing or malformed."""
    cfg_path = _config_file()
    if cfg_path.exists():
        try:
            with cfg_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    # Fallback to defaults
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Persist configuration to disk."""
    cfg_path = _config_file()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)


def _display_history():
    history = load_history()
    if not history:
        click.echo("No history available.")
        return
    for idx, entry in enumerate(history, start=1):
        prompt = entry.get("prompt", "").strip()
        cmd = entry.get("edited_command", entry.get("command", "")).strip()
        click.echo(f"{idx}: {cmd}  ←  {prompt}")


def _execute_command(command: str) -> tuple:
    """Execute a shell command and return (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as exc:
        return 1, "", str(exc)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """AI CLI agent – translate natural language into shell/Git commands."""
    pass


@cli.command()
@click.option("--provider", required=True, type=str, help="Model provider (ollama, lmstudio, mock)")
@click.option("--name", required=True, type=str, help="Model name (e.g. llama2, qwen2.5-coder:7b)")
@click.option("--endpoint", type=str, default=None, help="Endpoint for HTTP based providers")
def configure(provider: str, name: str, endpoint: Optional[str]) -> None:
    """Configure the model provider and model name."""
    config = load_config()
    config.setdefault("model", {})
    config["model"]["provider"] = provider
    config["model"]["name"] = name
    config["model"]["endpoint"] = endpoint
    save_config(config)
    click.echo(f"Configuration updated. Provider={provider}, Name={name}")


@cli.command(name="list-models")
def list_models() -> None:
    """List available models for the configured provider."""
    config = load_config()
    provider_name = config.get("model", {}).get("provider", "mock")
    model_name = config.get("model", {}).get("name", "mock")
    endpoint = config.get("model", {}).get("endpoint")
    try:
        provider = get_provider(provider_name, model_name, endpoint)
    except ValueError as exc:
        click.echo(f"Unknown provider: {exc}")
        return
    try:
        models = provider.list_models()
        if models:
            for m in models:
                click.echo(m)
        else:
            # Fallback: no models found
            click.echo(
                "No models found for provider '{0}'. You can download models using the provider's CLI. "
                "We recommend pulling 'qwen2.5-coder:7b' for coding tasks.".format(provider_name)
            )
    except ProviderError as exc:
        click.echo(str(exc))


@cli.command(name="run")
@click.argument("prompt", nargs=-1, type=str)
@click.option("--yes", "auto_yes", is_flag=True, help="Automatically accept and run a valid command without prompting.")
def run_prompt(prompt: tuple[str, ...], auto_yes: bool) -> None:
    """Generate, validate and optionally execute commands for the given prompt."""
    # Join prompt parts into a single string (to allow multiple words)
    prompt_text = " ".join(prompt).strip()
    if not prompt_text:
        click.echo("Please provide a prompt, e.g. ai run \"stage all changes and commit\"")
        return
    config = load_config()
    model_cfg = config.get("model", {})
    safe_mode = bool(config.get("safe_mode", True))
    provider_name = model_cfg.get("provider", "mock")
    model_name = model_cfg.get("name", "mock")
    endpoint = model_cfg.get("endpoint")
    try:
        provider = get_provider(provider_name, model_name, endpoint)
    except (ValueError, ProviderError) as exc:
        # If provider is unknown or fails to initialise, fallback to mock
        click.echo(f"Warning: {exc}. Falling back to mock provider.")
        provider = get_provider("mock", "mock")
    original_command = None
    try:
        original_command = provider.generate_command(prompt_text)
    except ProviderError as exc:
        # Fallback to mock provider when generation fails
        click.echo(f"Provider failed: {exc}. Using mock dataset.")
        try:
            provider = get_provider("mock", "mock")
            original_command = provider.generate_command(prompt_text)
        except ProviderError as exc2:
            click.echo(f"Unable to generate command: {exc2}")
            return
    # Validate output
    valid, reason = validate_command(original_command)
    edited_command = original_command
    if not valid:
        click.echo(f"Generated command is invalid: {reason}")
    # Interactive editing when not auto_yes
    if not auto_yes:
        # Show the command and allow editing
        click.echo("Command to execute. Press Enter to accept or edit:")
        click.echo(f"{original_command}")
        user_input = click.prompt("", default=original_command, show_default=False)
        edited_command = user_input.strip() or original_command
        # Revalidate after editing
        v2, reason2 = validate_command(edited_command)
        if not v2:
            click.echo(f"Edited command is invalid: {reason2}")
            # Do not run invalid commands
            if not auto_yes:
                click.echo("Cannot execute invalid command. Aborting.")
                # Log history and exit
                entry = {
                    "timestamp": _datetime.datetime.utcnow().isoformat(),
                    "prompt": prompt_text,
                    "command": original_command,
                    "edited_command": edited_command,
                    "executed": False,
                    "returncode": None,
                    "stdout": "",
                    "stderr": reason2,
                    "satisfied": None,
                }
                save_history_entry(entry)
                return
    else:
        # auto_yes: still require that the command is valid
        if not valid:
            click.echo("Cannot auto‑execute invalid command. Use without --yes to edit.")
            entry = {
                "timestamp": _datetime.datetime.utcnow().isoformat(),
                "prompt": prompt_text,
                "command": original_command,
                "edited_command": original_command,
                "executed": False,
                "returncode": None,
                "stdout": "",
                "stderr": reason,
                "satisfied": None,
            }
            save_history_entry(entry)
            return
    # Confirmation unless auto_yes or safe_mode disabled
    proceed = True
    if not auto_yes and safe_mode:
        confirm = click.prompt("Run this command? [y/N]", default="n")
        if confirm.lower() not in ("y", "yes"):
            proceed = False
    elif safe_mode and auto_yes:
        # In safe mode with auto_yes we still ask for confirmation
        confirm = click.prompt("Run this command? [y/N]", default="n")
        if confirm.lower() not in ("y", "yes"):
            proceed = False
    # Execute or skip
    executed = False
    returncode = None
    stdout = ""
    stderr = ""
    if proceed:
        executed = True
        returncode, stdout, stderr = _execute_command(edited_command)
        if stdout:
            click.echo(stdout.rstrip())
        if stderr:
            click.echo(stderr.rstrip(), err=True)
        # Suggest follow‑up actions based on errors
        advice = detect_state_error(stderr)
        if advice:
            click.echo(advice)
            followups = suggest_followup(stderr)
            if followups:
                click.echo("Suggested follow‑up commands:")
                for cmd in followups:
                    click.echo(f"  {cmd}")
    else:
        click.echo("Command not executed.")
    # Ask for feedback if not auto_yes
    satisfied = None
    feedback_cmd = None
    if not auto_yes:
        sat_input = click.prompt("Were you satisfied with the output? [Y/n]", default="Y")
        satisfied = sat_input.lower() in ("y", "yes", "")
        if not satisfied:
            feedback_cmd = click.prompt("Please provide the correct command that should have been generated")
            if feedback_cmd.strip():
                save_example(prompt_text, feedback_cmd.strip())
    # Save history entry
    entry = {
        "timestamp": _datetime.datetime.utcnow().isoformat(),
        "prompt": prompt_text,
        "command": original_command,
        "edited_command": edited_command,
        "executed": executed,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "satisfied": satisfied,
        "feedback_command": feedback_cmd,
    }
    save_history_entry(entry)


@cli.command(name="history")
def history_cmd() -> None:
    """Show previously executed commands."""
    _display_history()


@cli.command(name="!")
@click.argument("index", type=int)
@click.option("--yes", "auto_yes", is_flag=True, help="Automatically run the command without prompting.")
def rerun(index: int, auto_yes: bool) -> None:
    """Re‑run a command from history by its index (1‑based)."""
    history = load_history()
    if index < 1 or index > len(history):
        click.echo(f"Invalid history index {index}")
        return
    entry = history[index - 1]
    prompt_text = entry.get("prompt", "")
    original_command = entry.get("edited_command", entry.get("command", ""))
    if not original_command:
        click.echo("No command found in history entry.")
        return
    # Validate and optionally prompt user
    valid, reason = validate_command(original_command)
    if not valid:
        click.echo(f"Stored command is invalid: {reason}")
        if not auto_yes:
            new_cmd = click.prompt("Command to execute", default=original_command)
            edited_command = new_cmd.strip() or original_command
            valid, reason2 = validate_command(edited_command)
            if not valid:
                click.echo(f"Edited command is invalid: {reason2}")
                return
        else:
            click.echo("Cannot auto‑execute invalid command from history. Use without --yes to edit.")
            return
    else:
        edited_command = original_command
    # Confirmation
    config = load_config()
    safe_mode = bool(config.get("safe_mode", True))
    proceed = True
    if not auto_yes and safe_mode:
        confirm = click.prompt("Run this command? [y/N]", default="n")
        if confirm.lower() not in ("y", "yes"):
            proceed = False
    elif auto_yes and safe_mode:
        confirm = click.prompt("Run this command? [y/N]", default="n")
        if confirm.lower() not in ("y", "yes"):
            proceed = False
    executed = False
    returncode = None
    stdout = ""
    stderr = ""
    if proceed:
        executed = True
        returncode, stdout, stderr = _execute_command(edited_command)
        if stdout:
            click.echo(stdout.rstrip())
        if stderr:
            click.echo(stderr.rstrip(), err=True)
        advice = detect_state_error(stderr)
        if advice:
            click.echo(advice)
            followups = suggest_followup(stderr)
            if followups:
                click.echo("Suggested follow‑up commands:")
                for cmd in followups:
                    click.echo(f"  {cmd}")
    else:
        click.echo("Command not executed.")
    # Record rerun history (but do not ask satisfaction) – mark source index
    new_entry = {
        "timestamp": _datetime.datetime.utcnow().isoformat(),
        "prompt": prompt_text,
        "command": original_command,
        "edited_command": edited_command,
        "executed": executed,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "satisfied": None,
        "feedback_command": None,
        "source_history_index": index,
    }
    save_history_entry(new_entry)


@cli.command(name="serve")
@click.option("--host", default="0.0.0.0", help="Bind address for the MCP server")
@click.option("--port", default=5005, help="Port for the MCP server")
def serve(host: str, port: int) -> None:
    """Run the MCP server exposing a JSON API for generating commands."""
    # Import fastapi lazily to avoid mandatory dependency for CLI users
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        import uvicorn
    except ImportError:
        click.echo("FastAPI and uvicorn are required to run the server. Please install them with pip.")
        return

    app = FastAPI(title="AI CLI MCP Server", version="1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/generate_command")
    async def generate_command(request: dict) -> dict:
        prompt_text = request.get("input") or request.get("prompt")
        auto_yes = bool(request.get("auto_yes", False))
        if not prompt_text or not isinstance(prompt_text, str):
            raise HTTPException(status_code=400, detail="'input' field must be a non‑empty string")
        config = load_config()
        model_cfg = config.get("model", {})
        provider_name = model_cfg.get("provider", "mock")
        model_name = model_cfg.get("name", "mock")
        endpoint = model_cfg.get("endpoint")
        try:
            provider = get_provider(provider_name, model_name, endpoint)
        except Exception:
            provider = get_provider("mock", "mock")
        try:
            cmd = provider.generate_command(prompt_text)
        except ProviderError as exc:
            # Fallback to mock
            try:
                provider = get_provider("mock", "mock")
                cmd = provider.generate_command(prompt_text)
            except ProviderError:
                raise HTTPException(status_code=500, detail=str(exc))
        valid, reason = validate_command(cmd)
        if not valid:
            raise HTTPException(status_code=400, detail=f"Invalid command: {reason}")
        # Do not execute; just return the command
        return {"command": cmd}

    click.echo(f"MCP server running on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()