"""Tests for status file management."""

import tempfile
from pathlib import Path

import pytest

from pluribus.status_file import StatusFile


@pytest.fixture
def temp_worktree():
    """Create a temporary worktree directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_create_status_file(temp_worktree):
    """Test creating a new status file."""
    status_file = StatusFile(temp_worktree)
    status_file.create("test-task")

    assert status_file.status_path.exists()
    status = status_file.load()

    assert status["task_id"] == "test-task"
    assert status["status"] == "pending"
    assert status["progress_percent"] == 0
    assert status["claude_instance_active"] is False


def test_save_and_load(temp_worktree):
    """Test saving and loading status."""
    status_file = StatusFile(temp_worktree)

    test_status = {
        "task_id": "my-task",
        "status": "in_progress",
        "progress_percent": 50,
        "notes": "Working on it",
    }

    status_file.save(test_status)
    loaded = status_file.load()

    assert loaded["task_id"] == "my-task"
    assert loaded["status"] == "in_progress"
    assert loaded["progress_percent"] == 50


def test_update_status(temp_worktree):
    """Test updating specific fields in status."""
    status_file = StatusFile(temp_worktree)
    status_file.create("test-task")

    status_file.update({
        "status": "in_progress",
        "progress_percent": 75,
        "notes": "Making progress",
    })

    loaded = status_file.load()
    assert loaded["status"] == "in_progress"
    assert loaded["progress_percent"] == 75
    assert loaded["notes"] == "Making progress"


def test_get_status(temp_worktree):
    """Test getting current status value."""
    status_file = StatusFile(temp_worktree)
    status_file.create("test-task")

    assert status_file.get_status() == "pending"

    status_file.update({"status": "in_progress"})
    assert status_file.get_status() == "in_progress"


def test_is_active(temp_worktree):
    """Test checking if Claude instance is active."""
    status_file = StatusFile(temp_worktree)
    status_file.create("test-task")

    assert status_file.is_active() is False

    status_file.update({"claude_instance_active": True})
    assert status_file.is_active() is True


def test_load_nonexistent(temp_worktree):
    """Test loading nonexistent status file."""
    status_file = StatusFile(temp_worktree)
    assert status_file.load() is None
