"""CLI output formatting and display utilities."""

from pathlib import Path
from datetime import datetime
from typing import List, Optional
from tabulate import tabulate
from .status_file import StatusFile


def format_time_ago(iso_string: Optional[str]) -> str:
    """Format ISO timestamp as 'time ago'."""
    if not iso_string:
        return "-"

    try:
        last_update = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        now = datetime.now(last_update.tzinfo)
        delta = now - last_update

        seconds = int(delta.total_seconds())
        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        elif seconds < 86400:
            return f"{seconds // 3600}h ago"
        else:
            return f"{seconds // 86400}d ago"
    except (ValueError, TypeError):
        return "?"


def format_status_table(task_data: List[dict]) -> str:
    """Format task data as a table for display."""
    rows = []

    for task in task_data:
        last_update_display = format_time_ago(task.get("last_update"))
        active_display = "Y" if task.get("claude_instance_active") else "N"

        rows.append([
            task.get("task_name", "-"),
            task.get("branch", "-"),
            task.get("status", "-"),
            str(task.get("progress_percent", 0)) + "%",
            last_update_display,
            active_display,
            task.get("pr_url", "-") or "-",
        ])

    headers = ["Task", "Branch", "Status", "Progress", "Last Update", "Claude", "PR URL"]
    return tabulate(rows, headers=headers, tablefmt="grid")


def get_task_status_data(task_slug: str, worktree_path: Path) -> dict:
    """Get all relevant data for a task for display."""
    status_file = StatusFile(worktree_path)
    status = status_file.load()

    data = {
        "task_slug": task_slug,
        "task_name": "-",
        "branch": "-",
        "status": "pending",
        "progress_percent": 0,
        "last_update": None,
        "claude_instance_active": False,
        "pr_url": None,
    }

    if status:
        data.update(status)
        # Use task_id as task_name if task_name not explicitly set
        if "task_name" not in status and "task_id" in status:
            data["task_name"] = status["task_id"]

    return data


def print_task_details(task_slug: str, worktree_path: Path, worktree_manager) -> None:
    """Print detailed information about a task."""
    from .status_file import StatusFile

    status_file = StatusFile(worktree_path)
    status = status_file.load()

    print(f"\n📋 Task: {status.get('task_id', task_slug)}")
    print(f"   Status: {status.get('status', 'unknown')}")
    print(f"   Phase: {status.get('phase', '-')}")
    print(f"   Progress: {status.get('progress_percent', 0)}%")
    print(f"   Last Update: {format_time_ago(status.get('last_update'))}")

    if status.get("blocker"):
        print(f"   🚫 Blocker: {status.get('blocker')}")

    if status.get("pr_url"):
        print(f"   🔗 PR: {status.get('pr_url')}")

    print(f"   Notes: {status.get('notes', '-')}\n")

    # Recent commits
    commits = worktree_manager.get_recent_commits(task_slug)
    if commits:
        print("   Recent commits:")
        for hash_val, msg in commits:
            print(f"     {hash_val[:7]} {msg}")
    print()

    # Uncommitted changes
    has_uncommitted = worktree_manager.has_uncommitted_changes(task_slug)
    if has_uncommitted:
        print("   ⚠️  Has uncommitted changes")

    has_unpushed = worktree_manager.has_unpushed_commits(task_slug)
    if has_unpushed:
        print("   ⚠️  Has unpushed commits")
