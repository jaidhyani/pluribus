"""Task parsing and management from todo.md files."""

import re
from pathlib import Path
from typing import List, Tuple


class TaskParser:
    """Parses tasks from todo.md files."""

    def __init__(self, todo_path: Path):
        self.todo_path = Path(todo_path)

    def parse(self) -> List[Tuple[str, str]]:
        """
        Parse tasks from todo.md. Returns list of (task_name, description).
        Tasks are defined by ## headings.
        """
        if not self.todo_path.exists():
            return []

        with open(self.todo_path) as f:
            content = f.read()

        tasks = []
        current_task = None
        current_desc = []

        for line in content.split('\n'):
            if line.startswith('## '):
                if current_task:
                    description = '\n'.join(current_desc).strip()
                    tasks.append((current_task, description))
                current_task = line[3:].strip()
                current_desc = []
            elif current_task and line.strip() and not line.startswith('#'):
                current_desc.append(line)

        if current_task:
            description = '\n'.join(current_desc).strip()
            tasks.append((current_task, description))

        return tasks

    def get_task_by_name(self, name: str) -> Tuple[str, str]:
        """Get a specific task by (partial) name. Returns (full_name, description)."""
        tasks = self.parse()

        for task_name, description in tasks:
            if name.lower() in task_name.lower():
                return (task_name, description)

        raise ValueError(f"Task '{name}' not found in {self.todo_path}")


def task_to_branch_name(task_name: str) -> str:
    """Convert task name to a valid git branch name."""
    # Replace spaces and special chars with hyphens, keep alphanumeric
    branch = re.sub(r'[^\w\s-]', '', task_name.lower())
    branch = re.sub(r'[\s]+', '-', branch)
    branch = re.sub(r'-+', '-', branch)
    branch = branch.strip('-')
    return f"pluribus/{branch}"


def task_to_slug(task_name: str) -> str:
    """Convert task name to a filesystem-safe slug."""
    return re.sub(r'[^\w-]', '', task_to_branch_name(task_name).replace('pluribus/', ''))
