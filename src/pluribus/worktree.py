"""Git worktree management."""

import subprocess
from pathlib import Path
from typing import Optional


class WorktreeError(Exception):
    """Raised when a worktree operation fails."""

    pass


class Worktree:
    """Manages git worktrees for tasks."""

    def __init__(self, repo_path: Path, worktrees_root: Path):
        self.repo_path = Path(repo_path)
        self.worktrees_root = Path(worktrees_root)

    def create(self, branch_name: str, task_slug: str) -> Path:
        """
        Create a new worktree and branch for a task.
        Returns the path to the new worktree.
        """
        worktree_path = self.worktrees_root / task_slug

        if worktree_path.exists():
            raise WorktreeError(f"Worktree already exists at {worktree_path}")

        self.worktrees_root.mkdir(parents=True, exist_ok=True)

        try:
            # Create worktree with new branch
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise WorktreeError(f"Failed to create worktree: {e.stderr}")

        return worktree_path

    def exists(self, task_slug: str) -> bool:
        """Check if a worktree exists for a task."""
        worktree_path = self.worktrees_root / task_slug
        return worktree_path.exists() and (worktree_path / ".git").exists()

    def get_path(self, task_slug: str) -> Path:
        """Get the path to a worktree."""
        return self.worktrees_root / task_slug

    def delete(self, task_slug: str) -> None:
        """Delete a worktree and its branch."""
        worktree_path = self.worktrees_root / task_slug

        if not worktree_path.exists():
            raise WorktreeError(f"Worktree does not exist at {worktree_path}")

        try:
            # Remove worktree (use --force to handle dirty state)
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=self.repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise WorktreeError(f"Failed to delete worktree: {e.stderr}")

    def get_current_branch(self, task_slug: str) -> Optional[str]:
        """Get the current branch name in a worktree."""
        worktree_path = self.worktrees_root / task_slug

        if not worktree_path.exists():
            return None

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=worktree_path,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def has_uncommitted_changes(self, task_slug: str) -> bool:
        """Check if worktree has uncommitted changes."""
        worktree_path = self.worktrees_root / task_slug

        if not worktree_path.exists():
            return False

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=worktree_path,
                check=True,
                capture_output=True,
                text=True,
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError:
            return False

    def has_unpushed_commits(self, task_slug: str) -> bool:
        """Check if worktree has unpushed commits."""
        worktree_path = self.worktrees_root / task_slug
        branch = self.get_current_branch(task_slug)

        if not worktree_path.exists() or not branch or branch == "HEAD":
            return False

        try:
            result = subprocess.run(
                ["git", "rev-list", "--count", f"origin/{branch}..HEAD"],
                cwd=worktree_path,
                capture_output=True,
                text=True,
            )
            return int(result.stdout.strip() or 0) > 0
        except (subprocess.CalledProcessError, ValueError):
            return False

    def get_recent_commits(self, task_slug: str, count: int = 5) -> list:
        """Get recent commits in a worktree. Returns list of (hash, message) tuples."""
        worktree_path = self.worktrees_root / task_slug

        if not worktree_path.exists():
            return []

        try:
            result = subprocess.run(
                ["git", "log", f"-{count}", "--oneline"],
                cwd=worktree_path,
                check=True,
                capture_output=True,
                text=True,
            )
            commits = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split(' ', 1)
                    if len(parts) == 2:
                        commits.append((parts[0], parts[1]))
            return commits
        except subprocess.CalledProcessError:
            return []
