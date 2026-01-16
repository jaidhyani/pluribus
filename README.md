# Pluribus

Pluribus is a CLI tool for managing multiple parallel Claude Code instances working on different tasks within a single Git repository. It uses Git worktrees to create isolated, independent work environments for each task and keeps them coordinated via a simple filesystem-based status system.

## Why Pluribus?

Imagine you have a project with 3 issues to tackle. Instead of:
- Sequentially working through them one at a time
- Manually creating branches and switching contexts
- Managing multiple local git worktrees yourself

You can:
- Define tasks in a simple `todo.md` file
- Spin up multiple Claude Code instances with `pluribus workon`
- Each instance works independently in its own worktree
- Monitor all progress in real-time with `pluribus watch`
- Clean up completed tasks with `pluribus delete`

All coordinated through the filesystem as a single source of truth.

## Installation

### Prerequisites
- Python 3.9+
- Git (with support for `git worktree`)
- GitHub CLI (`gh`) configured with your credentials
- Claude Code CLI installed

### Option 1: Install from PyPI (Recommended)

```bash
uv tool install pluribus-ai

# Now run from anywhere
pluribus --help
```

### Option 2: Development

For developing or contributing to Pluribus:

```bash
git clone https://github.com/jaidhyani/pluribus.git
cd pluribus

# Install dependencies (includes editable install of pluribus)
uv sync

# Run commands
uv run pluribus --help
uv run pytest
```

## Quick Start

*If you installed pluribus as a user utility, just use `pluribus` command. If using local development, use `uv run pluribus` instead.*

### 1. Initialize a workspace

```bash
pluribus init https://github.com/your-org/your-project.git
```

This creates:
```
pluribus-workspace/
├── pluribus.config          # Configuration (minimal)
├── todo.md                  # Your task list
├── myrepo/                  # Clone of your repository
└── worktrees/               # Where work happens (initially empty)
```

### 2. Define tasks

Edit `todo.md` with your tasks (just use `##` headings):

```markdown
# todo.md

## Add database migration system
Brief context about what needs to be done.

## Add JWT authentication to API

## Refactor logging to use structured JSON
```

### 3. Start working on a task

```bash
pluribus workon
```

Pluribus will show available tasks and prompt you to choose one. It then:
- Creates a new branch (`pluribus/<task-name>`)
- Creates an isolated Git worktree at `worktrees/<task-name>/`
- Initializes a `.pluribus/status` file to track progress
- Starts Claude Code in that directory with context about the task

### 4. Monitor progress

In another terminal:

```bash
pluribus watch
```

This displays a live-updating table of all tasks and their status:

```
Task                          | Branch                    | Status       | Progress | Last Update
Add database migration system | pluribus/add-database-... | in_progress  | 40%      | 2026-01-16 14:30
Add JWT authentication...     | pluribus/add-jwt-auth-... | in_progress  | 20%      | 2026-01-16 14:32
Refactor logging...           | -                         | pending      | -        | -
```

### 5. Create a PR

When Claude Code finishes work on a task, it will:
- Push commits to its branch
- Create a PR via `gh pr create`
- Update the status file with the PR URL

You can then review and merge the PR on GitHub.

### 6. Clean up

Once a task is complete and the PR is merged:

```bash
pluribus delete "Add database migration system"
```

This removes the worktree and branch, freeing up space for other work.

## Commands

- **`pluribus init <repo-url>`** – Initialize a new Pluribus workspace
- **`pluribus workon [task-name]`** – Start working on a task (interactive selection if no name given)
- **`pluribus resume <task-name>`** – Resume work on an existing task
- **`pluribus status`** – Display current status of all tasks
- **`pluribus watch [--interval 10]`** – Live-update status table
- **`pluribus list-tasks`** – List all tasks from `todo.md`
- **`pluribus details <task-name>`** – Show full status, recent commits, and uncommitted changes
- **`pluribus delete <task-name>`** – Remove a completed task's worktree and branch

## Workflow Example

This entire workflow takes about 10 minutes:

```bash
# 30 seconds: Initialize
pluribus init https://github.com/my-org/my-project.git

# 30 seconds: Define 3 tasks in todo.md
# (edit file manually)

# 10 seconds: Start first task
pluribus workon
# Choose task 1; Claude starts working

# 10 seconds: Start second task (parallel, in another terminal)
pluribus workon
# Choose task 2; another Claude instance starts

# Monitor live (in another terminal)
pluribus watch

# When first task is done (PR created):
pluribus delete "Add database migration system"

# When other tasks are done, clean them up too
pluribus delete "Add JWT authentication to API"
```

## How It Works

### The Status File

Each task has a `.pluribus/status` file that tracks its state:

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

Claude Code instances update this file as they progress. Pluribus reads these files to provide visibility without needing to monitor processes.

### Worktrees

Each task gets its own Git worktree, completely isolated from others. This means:
- Multiple Claude instances can work in parallel without conflicts
- Each has its own branch
- Changes in one worktree don't affect others
- Easy to delete a worktree when done without affecting the main repo

### Live Watching

`pluribus watch` uses filesystem watchers (inotify on Linux, FSEvents on macOS) to detect when `.pluribus/status` files change. When a Claude instance updates a status file, the watch display updates immediately—no polling.

## Development

For details on contributing and developing Pluribus, see [CLAUDE.md](CLAUDE.md).

## Future Enhancements

- Configurable merge/PR strategies (beyond just `gh pr create`)
- Support for monorepos
- Task dependencies
- Automatic cleanup policies
- Web-based dashboard (optional)

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
