"""
Setuptools build script for the AI CLI agent.

This file allows installation of the ``aicli`` package via
``pip install .``.  It declares the required dependencies and
registers a console script entry point named ``ai``.  When
installed, users can invoke the CLI with ``ai`` from their shell.

See the ``README`` or requirements document for details.
"""

from setuptools import setup, find_packages

setup(
    name="aicli",
    version="0.1.0",
    description="AI-powered CLI tool translating natural language to shell/Git commands",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "click>=7.0",
        "PyYAML>=5.4",
        "fastapi>=0.80",
        "uvicorn>=0.20",
    ],
    entry_points={
        "console_scripts": [
            "ai=aicli.cli:main",
        ],
    },
    include_package_data=True,
    package_data={"aicli": ["data/examples.json"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)