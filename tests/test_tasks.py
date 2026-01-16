"""Tests for task parsing."""

import tempfile
from pathlib import Path

import pytest

from pluribus.tasks import TaskParser, task_to_branch_name, task_to_slug


@pytest.fixture
def todo_file():
    """Create a temporary todo.md file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("""# Tasks

## Add database migration system
This task involves creating a migration framework.

## Add JWT authentication
Implement JWT-based auth for the API.

## Refactor logging
Move from printf to structured JSON logging.
""")
        f.flush()
        yield Path(f.name)

    Path(f.name).unlink()


def test_parse_tasks(todo_file):
    """Test parsing tasks from todo.md."""
    parser = TaskParser(todo_file)
    tasks = parser.parse()

    assert len(tasks) == 3
    assert tasks[0][0] == "Add database migration system"
    assert "migration framework" in tasks[0][1]
    assert tasks[1][0] == "Add JWT authentication"
    assert tasks[2][0] == "Refactor logging"


def test_get_task_by_name(todo_file):
    """Test getting a specific task by name."""
    parser = TaskParser(todo_file)

    name, desc = parser.get_task_by_name("database")
    assert name == "Add database migration system"
    assert "migration" in desc


def test_get_task_not_found(todo_file):
    """Test getting nonexistent task raises error."""
    parser = TaskParser(todo_file)

    with pytest.raises(ValueError):
        parser.get_task_by_name("nonexistent")


def test_task_to_branch_name():
    """Test converting task names to branch names."""
    assert task_to_branch_name("Add database migration system") == "pluribus/add-database-migration-system"
    assert task_to_branch_name("Fix bug!") == "pluribus/fix-bug"
    assert task_to_branch_name("Test (urgent)") == "pluribus/test-urgent"


def test_task_to_slug():
    """Test converting task names to slugs."""
    slug = task_to_slug("Add database migration system")
    assert slug == "add-database-migration-system"

    slug = task_to_slug("Refactor config/setup")
    assert "refactor" in slug
    assert "config" in slug


def test_parse_empty_file():
    """Test parsing empty todo.md."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("# Tasks\n")
        f.flush()
        path = Path(f.name)

    try:
        parser = TaskParser(path)
        tasks = parser.parse()
        assert len(tasks) == 0
    finally:
        path.unlink()


def test_parse_nonexistent_file():
    """Test parsing nonexistent file."""
    parser = TaskParser(Path("/tmp/nonexistent-todo-12345.md"))
    tasks = parser.parse()

    assert len(tasks) == 0
