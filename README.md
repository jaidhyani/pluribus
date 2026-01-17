# Pluribus

Pluribus is a CLI tool for managing multiple parallel Claude instances working on different tasks within a single Git repository. It uses Git worktrees to create isolated, independent work environments (called "plurbs") for each task instance and keeps them coordinated via a simple filesystem-based status system.

## Why Pluribus?

Imagine you have a project with 3 issues to tackle. Instead of:
- Sequentially working through them one at a time
- Manually creating branches and switching contexts
- Managing multiple local git worktrees yourself

You can:
- Define tasks in a simple `todo.md` file
- Spin up multiple Claude instances with `pluribus workon`
- Each instance works independently in its own plurb (worktree + branch + agent)
- Monitor all progress in real-time with `pluribus watch`
- Clean up completed plurbs with `pluribus delete`

All coordinated through the filesystem as a single source of truth.

## Installation

### Prerequisites
- Python 3.9+
- Git (with support for `git worktree`)
- GitHub CLI (`gh`) configured with your credentials
- Claude CLI installed

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

Pluribus will show available tasks and prompt you to choose one. It then creates a **plurb** (an isolated instance of that task):
- Generates a unique identifier combining task name and random suffix (e.g., `add-database-migration-abc12`)
- Creates a new branch (`pluribus/add-database-migration-abc12`)
- Creates an isolated Git worktree at `worktrees/add-database-migration-abc12/`
- Initializes a `.pluribus/status` file to track progress
- Starts Claude in that directory with context about the task

Multiple plurbs can work on the same task simultaneously with independent branches and worktrees.

### 4. Monitor progress

In another terminal:

```bash
pluribus watch
```

This displays a live-updating table of all plurbs and their status:

```
Task                          | Branch                    | Status       | Progress | Last Update
Add database migration system | pluribus/add-database-... | in_progress  | 40%      | 2026-01-16 14:30
Add JWT authentication...     | pluribus/add-jwt-auth-... | in_progress  | 20%      | 2026-01-16 14:32
Refactor logging...           | -                         | pending      | -        | -
```

### 5. Create a PR

When Claude finishes work on a plurb, it will:
- Push commits to its branch
- Create a PR via `gh pr create`
- Update the status file with the PR URL

You can then review and merge the PR on GitHub.

### 6. Clean up

Once a plurb is complete and the PR is merged:

```bash
pluribus delete "Add database migration system"
```

This removes that plurb's worktree directory. If multiple plurbs exist for the task, you'll be prompted to choose which one to delete.

**Note**: The Git branch is left in place. To clean up orphaned branches later:

```bash
pluribus git-cleanup
```

This finds all `pluribus/*` branches that have no corresponding worktree and prompts you to delete them. Use `--force` to skip the confirmation.

## Commands

### Terminology
- **task**: An item from `todo.md` (e.g., "Add database migration")
- **plurb-id**: An isolated instance with unique identifier (e.g., `add-database-migration-abc12`)
- **identifier**: Either a task name or plurb-id

### Command Reference

- **`pluribus init <repo-url>`** – Initialize a new Pluribus workspace
- **`pluribus workon [task-name]`** – Start working on a task (creates a new plurb with unique ID; interactive selection if no name given)
  - `--agent=<name>` – Specify agent to use (overrides config)
  - `--agent-arg key=value` – Pass arguments to agent (repeatable)
- **`pluribus resume <identifier>`** – Resume work on an existing plurb (accepts task name or plurb-id; prompts if multiple plurbs exist)
- **`pluribus status`** – Display current status of all plurbs
- **`pluribus watch [--interval 10]`** – Live-update status table
- **`pluribus list-tasks`** – List all tasks from `todo.md`
- **`pluribus details <identifier>`** – Show full status, recent commits, and uncommitted changes (accepts task name or plurb-id; prompts if multiple plurbs exist)
- **`pluribus delete <identifier>`** – Remove a plurb's worktree (accepts task name or plurb-id; prompts if multiple plurbs exist)
  - `--force` – Skip confirmation prompts for uncommitted changes
  - Note: Branch is left in place; use `git-cleanup` to remove it later
- **`pluribus git-cleanup`** – Delete orphaned `pluribus/*` branches (branches with no corresponding worktree)
  - `--force` – Delete without confirmation

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

Each plurb has a `.pluribus/status` file (at `worktrees/<plurb-id>/.pluribus/status`) that tracks its state:

```json
{
  "task_id": "add-database-migration-system",
  "status": "in_progress",
  "phase": "implementation",
  "progress_percent": 45,
  "last_update": "2026-01-16T14:30:00Z",
  "claude_instance_active": true,
  "agent_pid": 12345,
  "agent": {
    "name": "headless-claude-code",
    "started_at": "2026-01-16T14:25:00Z",
    "metadata": {}
  },
  "session_id": "sess_abc123xyz",
  "pr_url": null,
  "blocker": null,
  "notes": "Working on schema validation"
}
```

Claude instances update this file as they progress. Pluribus reads these files to provide visibility without needing to monitor processes.

### Plurbs and Worktrees

Each plurb gets its own Git worktree, completely isolated from others. This means:
- Multiple Claude instances can work on the same task in parallel without conflicts
- Each plurb has its own branch and worktree directory
- Changes in one plurb don't affect others
- Easy to delete a plurb when done without affecting the main repo or other instances

### Live Watching

`pluribus watch` uses filesystem watchers (inotify on Linux, FSEvents on macOS) to detect when `.pluribus/status` files change. When a Claude instance updates a status file, the watch display updates immediately—no polling.

## Configuration

Pluribus uses a `pluribus.config` file (YAML format) to configure agents and workspace settings.

### Agent Configuration

By default, Pluribus spawns a headless Claude instance to work on tasks. You can configure custom agents or change the default behavior:

```yaml
# pluribus.config

# Repository configuration
repo_path: /path/to/repo

# Default agent to use (optional, defaults to headless-claude-code)
default_agent: default

# Agent definitions
agents:
  default:
    name: headless-claude-code
    command: claude
    args:
      - -p
    setup: null

  interactive:
    name: interactive-claude
    command: claude
    args:
      - -p
      - --interactive
    setup: |
      uv sync

  custom-agent:
    name: my-custom-agent
    command: /path/to/custom-agent.sh
    args:
      - --verbose
    setup: |
      npm install
      npm run build
```

### Using Custom Agents

Specify an agent when starting a task:

```bash
# Use a specific configured agent
pluribus workon --agent=interactive "My Task"

# Pass agent-specific arguments
pluribus workon --agent=custom-agent --agent-arg timeout=300 --agent-arg mode=debug "My Task"

# Use default agent
pluribus workon "My Task"
```

**Agent Precedence**: CLI arguments (`--agent`) override `pluribus.config`, which overrides the built-in default.

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
