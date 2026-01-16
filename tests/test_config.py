"""Tests for configuration management."""

import tempfile
from pathlib import Path

import pytest

from pluribus.config import Config


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_save_and_load_config(temp_workspace):
    """Test saving and loading config."""
    config = Config(temp_workspace)
    config.save({
        "repo_url": "https://github.com/user/repo.git",
        "repo_path": "/path/to/repo",
    })

    loaded = config.load()
    assert loaded["repo_url"] == "https://github.com/user/repo.git"
    assert loaded["repo_path"] == "/path/to/repo"


def test_get_repo_url(temp_workspace):
    """Test getting repo URL from config."""
    config = Config(temp_workspace)
    config.save({"repo_url": "https://github.com/test/repo.git"})

    assert config.get_repo_url() == "https://github.com/test/repo.git"


def test_get_repo_path(temp_workspace):
    """Test getting repo path from config."""
    config = Config(temp_workspace)
    config.save({"repo_path": "/home/user/repo"})

    assert config.get_repo_path() == Path("/home/user/repo")


def test_load_nonexistent_config(temp_workspace):
    """Test loading nonexistent config returns empty dict."""
    config = Config(temp_workspace)
    loaded = config.load()

    assert loaded == {}


def test_get_repo_missing(temp_workspace):
    """Test getting missing repo info returns None."""
    config = Config(temp_workspace)

    assert config.get_repo_url() is None
    assert config.get_repo_path() is None
