"""Top-level package for AI CLI agent.

This package contains the implementation of a command line tool named
``ai`` which converts natural language instructions into validated
shell or Git commands.  The core logic lives in the ``cli.py``
module, while helper modules handle model provider abstraction,
command validation, training data management, session history and
state detection.  See the documentation in ``Requirements & Design
Document for AI CLI Agent with Enhanced Features`` for a detailed
overview of the design.

When this package is installed via pip you can invoke the CLI from
your shell using the ``ai`` entry point.  Alternatively you can run
``python -m aicli.cli`` from this directory for local development.
"""

__all__ = [
    "cli",
    "providers",
    "validator",
    "training",
    "state",
]