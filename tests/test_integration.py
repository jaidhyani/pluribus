"""Integration tests for complete workflows."""

import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def repos_and_workspace():
    """Create test repos and workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create main repo
        main_repo = tmpdir / "main-repo"
        main_repo.mkdir()
        subprocess.run(["git", "init"], cwd=main_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=main_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=main_repo,
            capture_output=True,
            check=True,
        )

        (main_repo / "README.md").write_text("# Main Repo\n")
        subprocess.run(["git", "add", "."], cwd=main_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=main_repo,
            capture_output=True,
            check=True,
        )

        # Create workspace
        workspace = tmpdir / "workspace"
        workspace.mkdir()

        yield main_repo, workspace


def test_full_workflow(repos_and_workspace):
    """Test a full pluribus workflow from init to delete."""
    from click.testing import CliRunner
    from pluribus.cli import init, list_tasks, delete, status
    from pluribus.config import Config
    from pluribus.worktree import Worktree
    from pluribus.status_file import StatusFile

    main_repo, workspace = repos_and_workspace

    # Initialize
    runner = CliRunner()
    result = runner.invoke(init, [str(main_repo), "--path", str(workspace)])
    assert result.exit_code == 0

    # Add tasks
    (workspace / "todo.md").write_text(
        "# Tasks\n\n## Feature A\nBuild A.\n\n## Feature B\nBuild B.\n"
    )

    # List tasks (change to workspace directory)
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(workspace)
        result = runner.invoke(list_tasks, [])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "Feature A" in result.output
        assert "Feature B" in result.output
    finally:
        os.chdir(original_cwd)

    # Create worktrees manually (can't spawn Claude Code)
    config = Config(workspace)
    repo_path = config.get_repo_path()
    worktree_mgr = Worktree(repo_path, workspace / "worktrees")

    from pluribus.tasks import task_to_branch_name, task_to_slug

    wt1_slug = task_to_slug("Feature A")
    wt2_slug = task_to_slug("Feature B")

    wt1 = worktree_mgr.create(task_to_branch_name("Feature A"), wt1_slug)
    wt2 = worktree_mgr.create(task_to_branch_name("Feature B"), wt2_slug)

    # Initialize status files with task names
    status1 = StatusFile(wt1)
    status1.create(wt1_slug)
    status1.update({
        "status": "in_progress",
        "progress_percent": 50,
        "task_name": "Feature A"
    })

    status2 = StatusFile(wt2)
    status2.create(wt2_slug)
    status2.update({
        "status": "in_progress",
        "progress_percent": 75,
        "task_name": "Feature B"
    })

    # Check status
    import os
    original_cwd = os.getcwd()
    try:
        os.chdir(workspace)
        result = runner.invoke(status, [])
        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
        assert "Feature A" in result.output
        assert "Feature B" in result.output

        # Delete one worktree
        result = runner.invoke(delete, ["Feature A", "--force"])
        assert result.exit_code == 0, f"Delete failed: {result.output}"

        # Verify it's gone
        assert not worktree_mgr.exists(wt1_slug)
        assert worktree_mgr.exists(wt2_slug)

        # Status should show only one task
        result = runner.invoke(status, [])
        assert result.exit_code == 0
    finally:
        os.chdir(original_cwd)


def test_task_parsing_with_complex_names(repos_and_workspace):
    """Test that tasks with complex names are handled correctly."""
    from pluribus.tasks import TaskParser, task_to_slug, task_to_branch_name

    main_repo, workspace = repos_and_workspace

    # Create todo.md with various task names
    (workspace / "todo.md").write_text(
        """# Tasks

## Fix bug in (urgent) parser
Priority bug with special handling.

## Refactor config/setup logic
Multiple path components.

## Add API v2.0 endpoints
Version numbers.

## Test: Edge cases!!!
Multiple special characters.
"""
    )

    parser = TaskParser(workspace / "todo.md")
    tasks = parser.parse()

    assert len(tasks) == 4

    # Verify slugs are filesystem-safe
    for task_name, _ in tasks:
        slug = task_to_slug(task_name)
        branch = task_to_branch_name(task_name)

        # Slug and branch should not contain problematic characters
        assert "/" not in slug, f"Slug contains /: {slug}"
        assert "\\" not in slug, f"Slug contains backslash: {slug}"
        assert ":" not in slug, f"Slug contains colon: {slug}"

        # Branch should start with pluribus/
        assert branch.startswith("pluribus/"), f"Branch doesn't start with pluribus/: {branch}"


def test_error_handling_invalid_task(repos_and_workspace):
    """Test error handling when task doesn't exist."""
    from click.testing import CliRunner
    from pluribus.cli import init, delete
    import os

    main_repo, workspace = repos_and_workspace

    # Initialize
    runner = CliRunner()
    runner.invoke(init, [str(main_repo), "--path", str(workspace)])

    # Add a task
    (workspace / "todo.md").write_text("# Tasks\n\n## Existing Task\nDo something.\n")

    # Try to delete nonexistent task
    original_cwd = os.getcwd()
    try:
        os.chdir(workspace)
        result = runner.invoke(delete, ["nonexistent"])
        assert result.exit_code == 1
        # Should either not find the task or fail
    finally:
        os.chdir(original_cwd)


def test_workspace_detection(repos_and_workspace):
    """Test that workspace root is correctly found."""
    from pluribus.cli import init, find_workspace_root
    from click.testing import CliRunner

    main_repo, workspace = repos_and_workspace

    # Initialize
    runner = CliRunner()
    runner.invoke(init, [str(main_repo), "--path", str(workspace)])

    # Change to workspace directory and verify detection
    import os

    original_cwd = os.getcwd()
    try:
        os.chdir(workspace)
        found_root = find_workspace_root()
        assert found_root == workspace

        # Change to subdirectory and try again
        worktrees_dir = workspace / "worktrees"
        worktrees_dir.mkdir(exist_ok=True)
        os.chdir(worktrees_dir)
        found_root = find_workspace_root()
        assert found_root == workspace
    finally:
        os.chdir(original_cwd)
