"""Shared pytest fixtures.

Adds the source dir to sys.path (the package uses bare imports) and points
the memory system at a temp directory so tests never touch real user data.
"""

import os
import sys
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "operatorone"
sys.path.insert(0, str(SRC))


@pytest.fixture
def temp_data(tmp_path, monkeypatch):
    """Redirect Paths.* to a temp directory for the duration of a test."""
    import paths

    monkeypatch.setattr(paths.Paths, "get_user_data_dir", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(paths.Paths, "get_learning_file",
                        staticmethod(lambda: str(tmp_path / "learn.json")))
    monkeypatch.setattr(paths.Paths, "get_logs_dir", staticmethod(lambda: tmp_path))
    return tmp_path
