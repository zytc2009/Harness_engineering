"""Shared fixtures for harness-runtime tests."""

import json
import os
import tempfile

import pytest


@pytest.fixture
def sandbox_dir(tmp_path):
    """Provides a temporary sandbox directory for tool tests."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    return str(sandbox)


@pytest.fixture
def memory_file(tmp_path):
    """Provides a temporary memory.json path."""
    return str(tmp_path / "memory.json")


@pytest.fixture
def env_vars():
    """Context manager to temporarily set environment variables."""
    original = {}

    def _set(**kwargs):
        for key, value in kwargs.items():
            original[key] = os.environ.get(key)
            os.environ[key] = value

    yield _set

    for key, orig_value in original.items():
        if orig_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig_value
