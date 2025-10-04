#!/usr/bin/env bash
# Install script for the AI CLI agent.
#
# This helper automates creation of a Python virtual environment
# and installation of the package along with its dependencies.
# It can be run on Unix-like systems (Linux/macOS).  On Windows
# users can create a virtualenv manually and run ``pip install .``.

set -euo pipefail

PYTHON=${PYTHON:-python3}
VENV_DIR="${VENV_DIR:-.venv}"

echo "Creating virtual environment in $VENV_DIR..."
$PYTHON -m venv "$VENV_DIR"

echo "Activating virtual environment..."
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing package requirements..."
pip install click PyYAML fastapi uvicorn

echo "Installing the aicli package..."
pip install .

echo "\nInstallation complete. To activate the environment, run:\n\tsource $VENV_DIR/bin/activate\nThen invoke the CLI with:\n\tai run \"your prompt\""