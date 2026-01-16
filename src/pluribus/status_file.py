"""Status file management for tracking task progress."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class StatusFile:
    """Manages .pluribus/status files."""

    def __init__(self, worktree_path: Path):
        self.worktree_path = Path(worktree_path)
        self.status_path = self.worktree_path / ".pluribus" / "status"

    def create(self, task_id: str) -> None:
        """Create initial status file for a task."""
        self.status_path.parent.mkdir(parents=True, exist_ok=True)

        initial_status = {
            "task_id": task_id,
            "status": "pending",
            "phase": "starting",
            "progress_percent": 0,
            "last_update": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "claude_instance_active": False,
            "pr_url": None,
            "blocker": None,
            "notes": "",
        }

        self.save(initial_status)

    def load(self) -> Optional[dict]:
        """Load status from file. Returns None if file doesn't exist."""
        if not self.status_path.exists():
            return None

        with open(self.status_path) as f:
            return json.load(f)

    def save(self, status: dict) -> None:
        """Save status to file."""
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.status_path, 'w') as f:
            json.dump(status, f, indent=2)

    def update(self, updates: dict) -> None:
        """Update specific fields in status file."""
        status = self.load() or {}
        status.update(updates)
        status["last_update"] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        self.save(status)

    def get_status(self) -> Optional[str]:
        """Get current status value (e.g., 'in_progress')."""
        status = self.load()
        return status.get("status") if status else None

    def is_active(self) -> bool:
        """Check if Claude instance is active."""
        status = self.load()
        return status.get("claude_instance_active", False) if status else False

    def get_last_update_age_seconds(self) -> Optional[float]:
        """Get seconds since last update."""
        status = self.load()
        if not status:
            return None

        last_update_str = status.get("last_update", "")
        try:
            last_update = datetime.fromisoformat(last_update_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            return (now - last_update).total_seconds()
        except (ValueError, TypeError):
            return None
