"""Generate Claude Code prompts for tasks."""

from pathlib import Path


def generate_task_prompt(
    task_name: str,
    task_description: str,
    worktree_path: Path,
) -> str:
    """Generate the Claude Code prompt for working on a task."""

    status_file_path = worktree_path / ".pluribus" / "status"

    prompt = f"""You are working on the following task for the Pluribus project:

## Task: {task_name}

{task_description}

## Your Environment

Repository: {worktree_path}
Your branch: pluribus/* (see git status)
Status file: {status_file_path}

## Your Responsibilities

1. Work on this task until complete
2. Commit regularly with clear messages (`git commit -m "..."`)
3. Push commits to your branch frequently (`git push origin <your-branch>`)
4. Update the .pluribus/status file at regular intervals:
   - After completing major milestones
   - When you hit blockers (set status to "blocked", add blocker description)
   - When ready to submit PR (set status to "ready_for_pr", progress_percent to ~100)
   - Once you've submitted the PR (set status to "pr_open", add pr_url)
5. Create a pull request via GitHub CLI (`gh pr create`) when ready
6. Keep notes updated in the status file for visibility

## Status File Updates

The status file is JSON at: {status_file_path}

Example status update after implementing your changes:
```json
{{
  "status": "ready_for_pr",
  "phase": "testing",
  "progress_percent": 90,
  "pr_url": null,
  "claude_instance_active": true,
  "notes": "Implementation complete. Ready to create PR."
}}
```

When you create a PR and it's merged, update:
```json
{{
  "status": "done",
  "pr_url": "https://github.com/user/repo/pull/123",
  "notes": "PR created and merged successfully"
}}
```

## Important Notes

- Always keep your branch up-to-date with main (`git pull origin main`)
- If you hit a blocker, update status with a clear description and wait for assistance
- Keep commits atomic and well-documented
- Test your changes before creating a PR

Begin working on the task now. Good luck!
"""

    return prompt
