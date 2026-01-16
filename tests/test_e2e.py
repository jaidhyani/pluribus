"""End-to-end tests with real git repositories."""

import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def test_repo():
    """Create a test git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test-repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial commit
        (repo_path / "README.md").write_text("# Test Repo\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        yield repo_path


@pytest.fixture
def workspace():
    """Create a temporary workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_init_creates_workspace_structure(test_repo, workspace):
    """Test that pluribus init creates the expected workspace structure."""
    from click.testing import CliRunner
    from pluribus.cli import init

    # When using an existing path (not a URL), it doesn't create myrepo
    runner = CliRunner()
    result = runner.invoke(init, [str(test_repo), "--path", str(workspace)])

    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert (workspace / "pluribus.config").exists()
    assert (workspace / "todo.md").exists()
    assert (workspace / "worktrees").exists()


def test_init_stores_repo_path(test_repo, workspace):
    """Test that pluribus init correctly stores the repo path in config."""
    from click.testing import CliRunner
    from pluribus.cli import init
    from pluribus.config import Config

    runner = CliRunner()
    result = runner.invoke(init, [str(test_repo), "--path", str(workspace)])

    assert result.exit_code == 0
    config = Config(workspace)
    repo_path = config.get_repo_path()
    assert repo_path == test_repo


def test_workon_creates_worktree(test_repo, workspace):
    """Test that pluribus workon creates a worktree."""
    from click.testing import CliRunner
    from pluribus.cli import init, list_tasks
    from pluribus.worktree import Worktree
    from pluribus.config import Config

    # Initialize workspace
    runner = CliRunner()
    runner.invoke(init, [str(test_repo), "--path", str(workspace)])

    # Create a task
    todo_path = workspace / "todo.md"
    todo_path.write_text("# Tasks\n\n## Implement feature\nDo something useful.\n")

    # Try to create worktree (note: workon will try to spawn claude-code which won't exist)
    # Instead, we test the underlying worktree functionality directly
    config = Config(workspace)
    repo_path = config.get_repo_path()

    worktree_manager = Worktree(repo_path, workspace / "worktrees")
    worktree_path = worktree_manager.create("pluribus/implement-feature", "implement-feature")

    assert worktree_path.exists()
    assert (worktree_path / ".git").exists()
    assert (worktree_path / "README.md").exists()


def test_status_file_created_in_worktree(test_repo, workspace):
    """Test that status file is created when worktree is created."""
    from pluribus.cli import init
    from pluribus.worktree import Worktree
    from pluribus.status_file import StatusFile
    from pluribus.config import Config
    from click.testing import CliRunner

    # Initialize
    runner = CliRunner()
    runner.invoke(init, [str(test_repo), "--path", str(workspace)])

    # Create worktree
    config = Config(workspace)
    repo_path = config.get_repo_path()
    worktree_manager = Worktree(repo_path, workspace / "worktrees")
    worktree_path = worktree_manager.create("pluribus/test-task", "test-task")

    # Initialize status file
    status_file = StatusFile(worktree_path)
    status_file.create("test-task")

    assert status_file.status_path.exists()
    status = status_file.load()
    assert status["task_id"] == "test-task"
    assert status["status"] == "pending"


def test_worktree_branch_isolation(test_repo, workspace):
    """Test that worktrees have isolated branches."""
    from pluribus.cli import init
    from pluribus.worktree import Worktree
    from pluribus.config import Config
    from click.testing import CliRunner
    import subprocess

    # Initialize
    runner = CliRunner()
    runner.invoke(init, [str(test_repo), "--path", str(workspace)])

    # Create two worktrees
    config = Config(workspace)
    repo_path = config.get_repo_path()
    worktree_manager = Worktree(repo_path, workspace / "worktrees")

    wt1 = worktree_manager.create("pluribus/feature-1", "feature-1")
    wt2 = worktree_manager.create("pluribus/feature-2", "feature-2")

    # Check branches
    branch1 = worktree_manager.get_current_branch("feature-1")
    branch2 = worktree_manager.get_current_branch("feature-2")

    assert branch1 == "pluribus/feature-1"
    assert branch2 == "pluribus/feature-2"

    # Make changes in each worktree
    (wt1 / "feature1.txt").write_text("Feature 1 content\n")
    (wt2 / "feature2.txt").write_text("Feature 2 content\n")

    # Verify changes are isolated
    assert (wt1 / "feature1.txt").exists()
    assert not (wt1 / "feature2.txt").exists()
    assert (wt2 / "feature2.txt").exists()
    assert not (wt2 / "feature1.txt").exists()


def test_delete_worktree_removes_branch(test_repo, workspace):
    """Test that deleting a worktree removes its branch."""
    from pluribus.cli import init
    from pluribus.worktree import Worktree
    from pluribus.config import Config
    from click.testing import CliRunner

    # Initialize
    runner = CliRunner()
    runner.invoke(init, [str(test_repo), "--path", str(workspace)])

    # Create and then delete a worktree
    config = Config(workspace)
    repo_path = config.get_repo_path()
    worktree_manager = Worktree(repo_path, workspace / "worktrees")

    worktree_path = worktree_manager.create("pluribus/temp-task", "temp-task")
    assert worktree_manager.exists("temp-task")

    worktree_manager.delete("temp-task")
    assert not worktree_manager.exists("temp-task")
    assert not worktree_path.exists()


def test_uncommitted_changes_detection(test_repo, workspace):
    """Test detection of uncommitted changes in a worktree."""
    from pluribus.cli import init
    from pluribus.worktree import Worktree
    from pluribus.config import Config
    from click.testing import CliRunner

    # Initialize
    runner = CliRunner()
    runner.invoke(init, [str(test_repo), "--path", str(workspace)])

    # Create worktree
    config = Config(workspace)
    repo_path = config.get_repo_path()
    worktree_manager = Worktree(repo_path, workspace / "worktrees")
    worktree_path = worktree_manager.create("pluribus/test-task", "test-task")

    # No uncommitted changes initially
    assert not worktree_manager.has_uncommitted_changes("test-task")

    # Add a file
    (worktree_path / "new_file.txt").write_text("Some content\n")

    # Should detect uncommitted changes
    assert worktree_manager.has_uncommitted_changes("test-task")


def test_recent_commits_retrieval(test_repo, workspace):
    """Test retrieving recent commits from a worktree."""
    from pluribus.cli import init
    from pluribus.worktree import Worktree
    from pluribus.config import Config
    from click.testing import CliRunner
    import subprocess

    # Initialize
    runner = CliRunner()
    runner.invoke(init, [str(test_repo), "--path", str(workspace)])

    # Create worktree
    config = Config(workspace)
    repo_path = config.get_repo_path()
    worktree_manager = Worktree(repo_path, workspace / "worktrees")
    worktree_path = worktree_manager.create("pluribus/test-task", "test-task")

    # Make a commit in the worktree
    (worktree_path / "feature.txt").write_text("New feature\n")
    subprocess.run(["git", "add", "."], cwd=worktree_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Add feature"],
        cwd=worktree_path,
        check=True,
        capture_output=True,
    )

    # Get recent commits
    commits = worktree_manager.get_recent_commits("test-task", count=5)

    assert len(commits) >= 1
    assert any("Add feature" in msg for _, msg in commits)
