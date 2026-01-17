"""Handle post-run processing after agent completes."""

from pathlib import Path
from .status_file import StatusFile
from .agent_output import process_agent_output


def process_completed_agent_run(worktree_path: Path) -> None:
    """Process agent output after run completes and update status file.

    Args:
        worktree_path: Path to worktree directory
    """
    status_file = StatusFile(worktree_path)

    # Parse agent output
    output_data = process_agent_output(worktree_path)

    # Build updates for status file
    updates = {
        "claude_instance_active": False,
        "progress_percent": output_data["progress_percent"],
        "phase": output_data["phase"],
        "work_summary": output_data["work_summary"],
    }

    # Add or update session_id if found
    if output_data["session_id"]:
        updates["session_id"] = output_data["session_id"]

    # Add interventions if found
    if output_data["interventions"]:
        updates["interventions"] = output_data["interventions"]

    # Handle errors
    if output_data["error"]:
        updates["status"] = "blocked"
        updates["blockers"] = output_data["error"]
    else:
        # If no error and interventions detected, mark as awaiting_input
        if output_data["interventions"]:
            updates["status"] = "awaiting_input"
        # Otherwise assume ready or let previous state stand
        current_status = status_file.get_status()
        if current_status == "in_progress":
            # Keep it as in_progress, caller can override if needed
            pass

    status_file.update(updates)
