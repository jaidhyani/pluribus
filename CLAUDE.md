# Pluribus Development Guide

## Project Overview

Pluribus is a Python CLI tool for managing multiple parallel Claude Code instances working on different tasks within a single Git repository. It uses Git worktrees to isolate work on each task and manages their lifecycle from creation through PR submission and cleanup.

## Development Workflow

### Setup

**Option 1: Development with uv sync** (local development, no global installation)
```bash
cd /home/jai/Desktop/pluribus

# Install dependencies
uv sync

# Verify installation
uv run pluribus --help

# Run tests
uv run pytest
```

**Option 2: Development with editable install** (install globally, run `pluribus` from anywhere)
```bash
cd /home/jai/Desktop/pluribus

# Install in editable mode
uv pip install -e .

# Verify installation (run from anywhere)
pluribus --help
pluribus init /path/to/repo
```

### Making Changes
1. Edit source files in `src/pluribus/`
2. Test locally with `uv run pluribus <command>` or `pluribus <command>` (if installed editable)
3. Run tests with `uv run pytest` or `pytest` (if installed editable)
4. Commit changes with clear messages
5. Push to remote

### Testing

**With uv sync:**
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_tasks.py

# Run with coverage
uv run pytest --cov=pluribus tests/

# Test a specific command
uv run pluribus init /path/to/test-repo

# Test the full workflow in a sandbox directory
mkdir /tmp/pluribus-test
cd /tmp/pluribus-test
uv run pluribus init https://github.com/user/test-repo.git
```

**With editable install:**
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_tasks.py

# Run with coverage
pytest --cov=pluribus tests/

# Test a specific command
pluribus init /path/to/test-repo

# Test the full workflow in a sandbox directory
mkdir /tmp/pluribus-test
cd /tmp/pluribus-test
pluribus init https://github.com/user/test-repo.git
```

### Code Style
- Follow the principles in `/home/jai/.claude/CLAUDE.md`: write for human brains, not machines
- Use clear variable names and early returns
- Minimal comments; only "why", not "what"
- Keep functions/modules focused and deep, not shallow
- Avoid over-engineering; stick to what's needed

## Architecture

Key modules:
- **`cli.py`** – Command routing and argument parsing
- **`commands/`** – Individual command implementations
- **`worktree.py`** – Git worktree operations
- **`status_file.py`** – Status file reading/writing
- **`tasks.py`** – Task parsing from `todo.md`
- **`prompt.py`** – Claude prompt generation
- **`display.py`** – CLI output formatting
- **`watcher.py`** – File system watching for `pluribus watch`

## Key Design Decisions

- **Python for first draft** – Fast iteration, good ecosystem for CLI tools and file I/O
- **File watching for live updates** – Use inotify (or watchdog library) so `pluribus watch` updates in real-time as `.pluribus/status` changes
- **Simple task format** – `todo.md` with just `##` headings; no metadata required initially
- **Passive monitoring** – No active process checking; rely on filesystem timestamps and user updates
- **gh CLI for PRs** – Use GitHub CLI (assumed pre-configured); future: configurable merge strategy

## Status File Format

Location: `worktrees/<task-slug>/.pluribus/status`

JSON format with required fields:
```json
{
  "task_id": "add-database-migration-system",
  "status": "in_progress",
  "phase": "implementation",
  "progress_percent": 45,
  "last_update": "2026-01-16T14:30:00Z",
  "claude_instance_active": true,
  "pr_url": null,
  "blocker": null,
  "notes": "Working on schema validation"
}
```

Status enum: `pending`, `in_progress`, `blocked`, `ready_for_pr`, `pr_open`, `done`

## Commands to Implement

- `pluribus init <repo-url>` – Initialize workspace
- `pluribus workon [task-name]` – Start work on a task (interactive if no name given)
- `pluribus resume <task-name>` – Resume work on existing task
- `pluribus delete <task-name>` – Clean up completed task
- `pluribus status` – Show table of all tasks
- `pluribus watch [--interval 10]` – Live-update status table
- `pluribus list-tasks` – List all tasks from `todo.md`
- `pluribus details <task-name>` – Show full status + git info

## Committing Changes

Commit early and often with clear, descriptive messages. Example:
```bash
git add -A
git commit -m "Add worktree management module"
```

Push to remote regularly:
```bash
git push origin main
```

## Notes

- This is a first draft; we can iterate on UX/features based on real usage
- Language may change later once we have a working prototype
- Focus on simplicity and correctness over features
- The filesystem is the source of truth; keep designs simple and observable
