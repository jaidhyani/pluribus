"""Tests for task parsing."""

import tempfile
from pathlib import Path

import pytest

from pluribus.tasks import (
    TaskParser,
    task_to_branch_name,
    task_to_slug,
    generate_unique_suffix,
)


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
    # Test with explicit suffix for deterministic output
    assert task_to_branch_name("Add database migration system", "abc12") == "pluribus/add-database-migration-system-abc12"
    assert task_to_branch_name("Fix bug!", "xyz99") == "pluribus/fix-bug-xyz99"
    assert task_to_branch_name("Test (urgent)", "test1") == "pluribus/test-urgent-test1"

    # Test that generated suffix is included
    branch = task_to_branch_name("Add database migration system")
    assert branch.startswith("pluribus/add-database-migration-system-")
    assert len(branch) == len("pluribus/add-database-migration-system-") + 5  # 5-char default suffix


def test_task_to_slug():
    """Test converting task names to slugs."""
    # Test with explicit suffix
    slug = task_to_slug("Add database migration system", "abc12")
    assert slug == "add-database-migration-system-abc12"

    slug = task_to_slug("Refactor config/setup", "xyz99")
    assert "refactor" in slug
    assert "config" in slug
    assert slug.endswith("-xyz99")

    # Test that generated suffix is included
    slug = task_to_slug("Add database migration system")
    assert slug.startswith("add-database-migration-system-")
    assert len(slug) == len("add-database-migration-system-") + 5  # 5-char default suffix


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


def test_generate_unique_suffix():
    """Test generating unique suffixes."""
    suffix = generate_unique_suffix()
    assert len(suffix) == 5
    assert suffix.isalnum()
    assert suffix.islower()


def test_generate_unique_suffix_custom_length():
    """Test generating unique suffixes with custom length."""
    suffix = generate_unique_suffix(length=8)
    assert len(suffix) == 8
    assert suffix.isalnum()
    assert suffix.islower()


def test_generate_unique_suffix_uniqueness():
    """Test that generated suffixes are (very likely) unique."""
    suffixes = [generate_unique_suffix() for _ in range(100)]
    # With 5 chars and 36 possible chars (a-z, 0-9), collision probability
    # for 100 draws is negligible
    assert len(set(suffixes)) == 100
