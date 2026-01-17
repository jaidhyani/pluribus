"""Main CLI entry point for Pluribus."""

import subprocess
import sys
from pathlib import Path
from typing import Optional

import click

from .agents import (
    load_agents_from_config,
    resolve_agent,
    spawn_agent,
    try_get_session_id,
    get_agent_metadata,
)
from .config import Config
from .status_file import StatusFile
from .tasks import TaskParser, task_to_branch_name, task_to_slug, generate_unique_suffix
from .worktree import Worktree, WorktreeError
from .prompt import generate_task_prompt
from .display import format_status_table, get_task_status_data, print_task_details


def find_workspace_root(start_path: Path = None) -> Optional[Path]:
    """Find the pluribus workspace root by looking for pluribus.config."""
    if start_path is None:
        start_path = Path.cwd()

    current = Path(start_path).resolve()
    while current != current.parent:
        if (current / "pluribus.config").exists():
            return current
        current = current.parent

    return None


def _parse_repo_input(repo_input: str) -> str:
    """Parse repo input and convert GitHub format to URL if needed.

    Returns:
        Either a URL starting with http/https/git@ or a local path.

    Logic:
        - http/https/git@ URLs are returned as-is
        - Paths starting with / or . are treated as local paths
        - <string>/<string> that don't exist are treated as GitHub repos
        - Otherwise treated as local paths (may not exist yet)
    """
    # Already a URL
    if repo_input.startswith(("http://", "https://", "git@")):
        return repo_input

    # Absolute or relative path (starts with / or .)
    if repo_input.startswith(("/", ".")):
        return repo_input

    # Check if it's a local path that exists
    potential_path = Path(repo_input).resolve()
    if potential_path.exists():
        return str(potential_path)

    # Check if it looks like owner/repo (GitHub format) - has slash but not a path prefix
    if "/" in repo_input:
        return f"https://github.com/{repo_input}.git"

    # Otherwise treat as a bare path (error will be caught if it doesn't exist)
    return repo_input


@click.group()
def cli():
    """Pluribus: Manage multiple parallel Claude instances."""
    pass


@cli.command()
@click.argument("repo_input", required=False)
@click.option(
    "--path",
    default=".",
    help="Directory to initialize workspace in (default: current directory)",
)
def init(repo_input: Optional[str], path: str):
    """Initialize a new Pluribus workspace."""
    workspace_root = Path(path).resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)

    config_file = workspace_root / "pluribus.config"
    if config_file.exists():
        click.echo("❌ Workspace already initialized (pluribus.config exists)")
        sys.exit(1)

    # Create directory structure
    (workspace_root / "worktrees").mkdir(exist_ok=True)

    # Create todo.md if it doesn't exist
    todo_file = workspace_root / "todo.md"
    if not todo_file.exists():
        todo_file.write_text("# Tasks\n\n## Example Task\nDescribe what needs to be done.\n")

    # If no repo provided, prompt for it
    if not repo_input:
        click.echo("\n📦 Repository source:")
        repo_input = click.prompt(
            "Enter path/local repo, GitHub repo (owner/repo), or git URL"
        )

    # Convert GitHub repo format to URL if needed
    repo_url_or_path = _parse_repo_input(repo_input)  # type: ignore

    # Determine if it's a URL or path
    if repo_url_or_path.startswith(("http://", "https://", "git@")):
        # Clone the repo
        repo_path = workspace_root / "myrepo"
        try:
            subprocess.run(
                ["git", "clone", repo_url_or_path, str(repo_path)],
                check=True,
            )
            click.echo(f"✓ Cloned repository to {repo_path}")
        except subprocess.CalledProcessError as e:
            click.echo(f"❌ Failed to clone repository: {e}")
            sys.exit(1)

        config = Config(workspace_root)
        config.save({"repo_url": repo_url_or_path, "repo_path": str(repo_path)})
    else:
        # Use existing repo path
        repo_path = Path(repo_url_or_path).resolve()
        if not repo_path.exists():
            click.echo(f"❌ Repository path does not exist: {repo_path}")
            sys.exit(1)

        config = Config(workspace_root)
        config.save({"repo_path": str(repo_path)})

    click.echo(f"✅ Initialized Pluribus workspace at {workspace_root}")
    click.echo(f"   Configuration: {config_file}")
    click.echo(f"   Tasks: {todo_file}")
    click.echo(f"   Repository: {repo_path}")


@cli.command()
@click.argument("task_name", required=False)
@click.option(
    "--agent",
    default=None,
    help="Agent to use for this task (overrides config)",
)
@click.option(
    "--agent-arg",
    multiple=True,
    type=str,
    help="Agent-specific arguments (format: key=value)",
)
def workon(task_name: Optional[str], agent: Optional[str], agent_arg: tuple):
    """Start working on a task (creates a new plurb with unique identifier)."""
    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace (no pluribus.config found)")
        sys.exit(1)

    config_obj = Config(workspace_root)
    config_dict = config_obj.load()
    repo_path = config_obj.get_repo_path()
    if not repo_path or not repo_path.exists():
        click.echo("❌ Repository not configured or does not exist")
        sys.exit(1)

    todo_path = workspace_root / "todo.md"
    if not todo_path.exists():
        click.echo("❌ todo.md not found")
        sys.exit(1)

    parser = TaskParser(todo_path)
    all_tasks = parser.parse()

    if not all_tasks:
        click.echo("❌ No tasks defined in todo.md")
        sys.exit(1)

    # Select task
    if task_name:
        try:
            task_name, task_desc = parser.get_task_by_name(task_name)
        except ValueError as e:
            click.echo(f"❌ {e}")
            sys.exit(1)
    else:
        # Interactive selection
        click.echo("\n📝 Available tasks:")
        for i, (name, _) in enumerate(all_tasks, 1):
            click.echo(f"   {i}. {name}")

        choice = click.prompt("Which task? (1-{})".format(len(all_tasks)))
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(all_tasks):
                task_name, task_desc = all_tasks[idx]
            else:
                click.echo("❌ Invalid choice")
                sys.exit(1)
        except ValueError:
            click.echo("❌ Invalid input")
            sys.exit(1)

    # Generate unique suffix for this task instance
    unique_suffix = generate_unique_suffix()

    # Create task slug and check if already exists
    task_slug = task_to_slug(task_name, unique_suffix)
    worktree_manager = Worktree(repo_path, workspace_root / "worktrees")

    # Note: with unique suffixes, we won't have collisions, but keep the check
    # in case the same random suffix is generated (extremely unlikely)
    if worktree_manager.exists(task_slug):
        click.echo(f"⚠️  Rare collision detected (same random suffix). Retrying...")
        unique_suffix = generate_unique_suffix()
        task_slug = task_to_slug(task_name, unique_suffix)

    # Create worktree
    branch_name = task_to_branch_name(task_name, unique_suffix)
    try:
        worktree_path = worktree_manager.create(branch_name, task_slug)
        click.echo(f"✓ Created worktree at {worktree_path}")
    except WorktreeError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)

    # Initialize status file
    status_file = StatusFile(worktree_path)
    status_file.create(task_slug)
    click.echo(f"✓ Initialized status file")

    # Parse agent arguments
    agent_args_dict = {}
    for arg in agent_arg:
        if "=" not in arg:
            click.echo(f"❌ Invalid agent argument format: '{arg}' (expected key=value)")
            sys.exit(1)
        key, value = arg.split("=", 1)
        agent_args_dict[key] = value

    # Resolve agent
    config_agents = load_agents_from_config(config_dict)
    default_agent = config_dict.get("default_agent")

    try:
        agent_config = resolve_agent(agent, config_agents, default_agent)
        if not agent_config:
            click.echo("❌ No agent configured or available")
            sys.exit(1)
    except ValueError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)

    # Spawn agent
    try:
        agent_pid = spawn_agent(
            agent_config,
            task_id=task_slug,
            task_name=task_name,
            task_description=task_desc,
            worktree_dir=worktree_path,
            repo_root=repo_path,
            agent_args=agent_args_dict if agent_args_dict else None,
        )
        click.echo(f"✓ Spawned {agent_config.name} (PID: {agent_pid})")

        # Update status file with agent info
        agent_metadata = get_agent_metadata(agent_config)
        status_file.update({
            "agent_pid": agent_pid,
            "agent": agent_metadata,
            "status": "in_progress",
            "claude_instance_active": True,
        })

        # Try to capture session ID for resumption (non-blocking)
        session_id = try_get_session_id(worktree_path, timeout_seconds=3.0)
        if session_id:
            status_file.update({"session_id": session_id})
            click.echo(f"✓ Captured session ID for resumption")

        click.echo(f"\n✅ Task worktree ready with agent running")
        click.echo(f"   Task: {task_name}")
        click.echo(f"   Worktree: {worktree_path}")
        click.echo(f"   Agent: {agent_config.name}")
        click.echo(f"\n   To monitor progress: pluribus watch")
        click.echo(f"   To resume manually: pluribus resume '{task_name}'")

    except (FileNotFoundError, RuntimeError) as e:
        click.echo(f"❌ {e}")
        sys.exit(1)


@cli.command()
@click.argument("identifier")
def resume(identifier: str):
    """Resume work on an existing plurb.

    IDENTIFIER can be:
    - A task name from todo.md (e.g., "Add database migration")
    - A plurb-id (directory name with suffix, e.g., "add-database-migration-abc12")

    If multiple plurbs exist for a task name, you'll be prompted to choose which one.
    """
    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace")
        sys.exit(1)

    config = Config(workspace_root)
    repo_path = config.get_repo_path()
    if not repo_path or not repo_path.exists():
        click.echo("❌ Repository not configured")
        sys.exit(1)

    worktree_manager = Worktree(repo_path, workspace_root / "worktrees")
    worktrees_dir = workspace_root / "worktrees"

    # First, check if identifier is an exact plurb-id (directory exists)
    plurb_id = None
    task_name = None
    task_desc = None

    if (worktrees_dir / identifier).is_dir():
        plurb_id = identifier
        # For display purposes, try to find the task name from status file
        status_file = StatusFile(worktrees_dir / plurb_id)
        status = status_file.load()
        task_name = status.get("task_id", plurb_id) if status else plurb_id
    else:
        # Try to resolve it as a task name from todo.md
        todo_path = workspace_root / "todo.md"
        parser = TaskParser(todo_path)

        try:
            full_task_name, task_desc = parser.get_task_by_name(identifier)
        except ValueError as e:
            click.echo(f"❌ {e}")
            sys.exit(1)

        task_name = full_task_name

        # Find all plurbs (instances) for this task
        task_base_slug = task_to_slug(full_task_name, "")
        matching_plurbs = sorted(
            [d.name for d in worktrees_dir.iterdir()
             if d.is_dir() and d.name.startswith(task_base_slug)]
        )

        if not matching_plurbs:
            click.echo(f"❌ No plurbs found for task '{full_task_name}'")
            sys.exit(1)

        if len(matching_plurbs) == 1:
            plurb_id = matching_plurbs[0]
        else:
            # Multiple plurbs - let user choose
            click.echo(f"\n📋 Multiple instances found for '{full_task_name}':")
            for i, p in enumerate(matching_plurbs, 1):
                status_file = StatusFile(worktrees_dir / p)
                status = status_file.load() or {}
                progress = status.get("progress_percent", "-")
                click.echo(f"  [{i}] {p} (progress: {progress}%)")

            try:
                choice = click.prompt("Choose which to resume (number)", type=int)
                if 1 <= choice <= len(matching_plurbs):
                    plurb_id = matching_plurbs[choice - 1]
                else:
                    click.echo("❌ Invalid choice")
                    sys.exit(1)
            except click.Abort:
                click.echo("Cancelled")
                return

    worktree_path = worktree_manager.get_path(plurb_id)
    if not task_desc:
        # If we resolved by plurb_id, we may not have task_desc. Fetch from status if available.
        status_file = StatusFile(worktree_path)
        status = status_file.load()
        task_desc = status.get("notes", "") if status else ""
    prompt = generate_task_prompt(task_name, task_desc, worktree_path)

    # Check if we have a session ID to resume
    status_file = StatusFile(worktree_path)
    status = status_file.load()
    session_id = status.get("session_id") if status else None

    click.echo(f"🚀 Resuming work on: {task_name}\n")
    try:
        if session_id:
            # Resume specific session
            subprocess.run(
                ["claude", "--resume", session_id],
                cwd=worktree_path,
            )
        else:
            # Open worktree in new session
            subprocess.run(
                ["claude", str(worktree_path)],
                cwd=worktree_path,
            )
        click.echo(f"\n✓ Work session ended for '{task_name}'")
    except FileNotFoundError:
        click.echo("⚠️  Claude CLI not found. Starting with prompt instead...\n")
        click.echo("📋 Here's your task prompt:\n")
        click.echo(prompt)
        click.echo("\n" + "="*60)
        click.echo("To work on this task with Claude, run:")
        click.echo(f"  cd {worktree_path}")
        click.echo("  claude")
        click.echo("="*60)
        click.echo(f"\n✓ Ready to resume at: {worktree_path}")


@cli.command()
def status():
    """Show status of all plurbs."""
    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace")
        sys.exit(1)

    worktrees_root = workspace_root / "worktrees"
    if not worktrees_root.exists():
        click.echo("No tasks yet")
        return

    # Collect all task data
    task_data = []
    for task_dir in sorted(worktrees_root.iterdir()):
        if task_dir.is_dir() and (task_dir / ".git").exists():
            task_slug = task_dir.name
            data = get_task_status_data(task_slug, task_dir)
            task_data.append(data)

    if not task_data:
        click.echo("No tasks")
        return

    click.echo("\n" + format_status_table(task_data))


@cli.command()
@click.option("--interval", default=5, help="Refresh interval in seconds")
def watch(interval: int):
    """Watch plurb status for live updates."""
    import time
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace")
        sys.exit(1)

    worktrees_root = workspace_root / "worktrees"
    if not worktrees_root.exists():
        click.echo("No worktrees to watch")
        return

    class StatusChangeHandler(FileSystemEventHandler):
        def __init__(self):
            self.should_refresh = True

        def on_modified(self, event):
            if event.src_path.endswith("status"):
                self.should_refresh = True

    handler = StatusChangeHandler()
    observer = Observer()
    observer.schedule(handler, str(worktrees_root), recursive=True)
    observer.start()

    try:
        while True:
            # Collect and display current status
            task_data = []
            for task_dir in sorted(worktrees_root.iterdir()):
                if task_dir.is_dir() and (task_dir / ".git").exists():
                    task_slug = task_dir.name
                    data = get_task_status_data(task_slug, task_dir)
                    task_data.append(data)

            # Clear screen and display
            click.clear()
            click.echo("📊 Pluribus Task Status (Ctrl+C to exit)\n")
            if task_data:
                click.echo(format_status_table(task_data))
            else:
                click.echo("No tasks")

            time.sleep(interval)
    except KeyboardInterrupt:
        click.echo("\n✓ Stopped watching")
    finally:
        observer.stop()
        observer.join()


@cli.command()
@click.argument("identifier")
def details(identifier: str):
    """Show detailed information about a plurb.

    IDENTIFIER can be:
    - A task name from todo.md (e.g., "Add database migration")
    - A plurb-id (directory name with suffix, e.g., "add-database-migration-abc12")

    If multiple plurbs exist for a task name, you'll be prompted to choose which one.
    """
    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace")
        sys.exit(1)

    config = Config(workspace_root)
    repo_path = config.get_repo_path()
    worktree_manager = Worktree(repo_path, workspace_root / "worktrees")
    worktrees_dir = workspace_root / "worktrees"

    # First, check if identifier is an exact plurb-id (directory exists)
    plurb_id = None
    if (worktrees_dir / identifier).is_dir():
        plurb_id = identifier
    else:
        # Try to resolve it as a task name from todo.md
        todo_path = workspace_root / "todo.md"
        parser = TaskParser(todo_path)

        try:
            full_task_name, _ = parser.get_task_by_name(identifier)
        except ValueError as e:
            click.echo(f"❌ {e}")
            sys.exit(1)

        # Find all plurbs (instances) for this task
        task_base_slug = task_to_slug(full_task_name, "")
        matching_plurbs = sorted(
            [d.name for d in worktrees_dir.iterdir()
             if d.is_dir() and d.name.startswith(task_base_slug)]
        )

        if not matching_plurbs:
            click.echo(f"❌ No plurbs found for task '{full_task_name}'")
            sys.exit(1)

        if len(matching_plurbs) == 1:
            plurb_id = matching_plurbs[0]
        else:
            # Multiple plurbs - let user choose
            click.echo(f"\n📋 Multiple instances found for '{full_task_name}':")
            for i, p in enumerate(matching_plurbs, 1):
                status_file = StatusFile(worktrees_dir / p)
                status = status_file.load() or {}
                progress = status.get("progress_percent", "-")
                click.echo(f"  [{i}] {p} (progress: {progress}%)")

            try:
                choice = click.prompt("Choose which to view (number)", type=int)
                if 1 <= choice <= len(matching_plurbs):
                    plurb_id = matching_plurbs[choice - 1]
                else:
                    click.echo("❌ Invalid choice")
                    sys.exit(1)
            except click.Abort:
                click.echo("Cancelled")
                return

    worktree_path = worktree_manager.get_path(plurb_id)
    print_task_details(plurb_id, worktree_path, worktree_manager)


@cli.command()
@click.argument("identifier")
@click.option("--force", is_flag=True, help="Force delete even with uncommitted changes")
def delete(identifier: str, force: bool):
    """Delete a completed plurb's worktree (branch remains for cleanup).

    IDENTIFIER can be:
    - A task name from todo.md (e.g., "Add database migration")
    - A plurb-id (directory name with suffix, e.g., "add-database-migration-abc12")

    If multiple plurbs exist for a task name, you'll be prompted to choose which one.

    Note: This removes only the worktree directory. The branch is left in place and can be
    cleaned up later with 'pluribus git-cleanup'.
    """
    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace")
        sys.exit(1)

    config = Config(workspace_root)
    repo_path = config.get_repo_path()
    worktree_manager = Worktree(repo_path, workspace_root / "worktrees")
    worktrees_dir = workspace_root / "worktrees"

    # First, check if identifier is an exact plurb-id (directory exists)
    plurb_id = None
    if (worktrees_dir / identifier).is_dir():
        plurb_id = identifier
    else:
        # Try to resolve it as a task name from todo.md
        todo_path = workspace_root / "todo.md"
        parser = TaskParser(todo_path)

        try:
            full_task_name, _ = parser.get_task_by_name(identifier)
        except ValueError as e:
            click.echo(f"❌ {e}")
            sys.exit(1)

        # Find all plurbs (instances) for this task
        task_base_slug = task_to_slug(full_task_name, "")
        matching_plurbs = sorted(
            [d.name for d in worktrees_dir.iterdir()
             if d.is_dir() and d.name.startswith(task_base_slug)]
        )

        if not matching_plurbs:
            click.echo(f"❌ No plurbs found for task '{full_task_name}'")
            sys.exit(1)

        if len(matching_plurbs) == 1:
            plurb_id = matching_plurbs[0]
        else:
            # Multiple plurbs - let user choose
            click.echo(f"\n📋 Multiple instances found for '{full_task_name}':")
            for i, p in enumerate(matching_plurbs, 1):
                status_file = StatusFile(worktrees_dir / p)
                status = status_file.load() or {}
                progress = status.get("progress_percent", "-")
                click.echo(f"  [{i}] {p} (progress: {progress}%)")

            try:
                choice = click.prompt("Choose which to delete (number)", type=int)
                if 1 <= choice <= len(matching_plurbs):
                    plurb_id = matching_plurbs[choice - 1]
                else:
                    click.echo("❌ Invalid choice")
                    sys.exit(1)
            except click.Abort:
                click.echo("Cancelled")
                return

    # Check for uncommitted changes
    if worktree_manager.has_uncommitted_changes(plurb_id):
        if not force:
            click.echo(f"⚠️  Plurb has uncommitted changes")
            if not click.confirm("Delete anyway?"):
                click.echo("Cancelled")
                return

    if worktree_manager.has_unpushed_commits(plurb_id):
        if not force:
            click.echo(f"⚠️  Plurb has unpushed commits")
            if not click.confirm("Delete anyway?"):
                click.echo("Cancelled")
                return

    # Delete the worktree
    try:
        worktree_manager.delete(plurb_id)
        click.echo(f"✓ Deleted plurb '{plurb_id}'")
    except WorktreeError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)


@cli.command()
def list_tasks():
    """List all tasks from todo.md."""
    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace")
        sys.exit(1)

    todo_path = workspace_root / "todo.md"
    if not todo_path.exists():
        click.echo("❌ todo.md not found")
        sys.exit(1)

    parser = TaskParser(todo_path)
    tasks = parser.parse()

    if not tasks:
        click.echo("No tasks defined")
        return

    click.echo("\n📋 Tasks:")
    for task_name, desc in tasks:
        click.echo(f"\n   {task_name}")
        if desc:
            for line in desc.split('\n')[:2]:
                if line.strip():
                    click.echo(f"      {line.strip()}")


@cli.command("git-cleanup")
@click.option("--force", is_flag=True, help="Delete orphaned branches without confirmation")
def git_cleanup(force: bool):
    """Delete orphaned pluribus branches (worktree was deleted but branch remains)."""
    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace")
        sys.exit(1)

    config = Config(workspace_root)
    repo_path = config.get_repo_path()
    if not repo_path or not repo_path.exists():
        click.echo("❌ Repository not configured")
        sys.exit(1)

    worktree_manager = Worktree(repo_path, workspace_root / "worktrees")

    # Prune stale worktree entries to avoid conflicts when deleting branches
    try:
        worktree_manager.prune_worktrees()
    except WorktreeError as e:
        click.echo(f"⚠️  Warning: {e}")

    orphaned = worktree_manager.get_orphaned_branches()

    if not orphaned:
        click.echo("✓ No orphaned branches found")
        return

    click.echo(f"\n🌿 Found {len(orphaned)} orphaned branch(es):\n")
    for branch in orphaned:
        click.echo(f"   {branch}")

    if not force:
        if not click.confirm("\nDelete these branches?"):
            click.echo("Cancelled")
            return

    click.echo()
    deleted_count = 0
    for branch in orphaned:
        try:
            worktree_manager.delete_branch(branch)
            click.echo(f"✓ Deleted {branch}")
            deleted_count += 1
        except WorktreeError as e:
            click.echo(f"⚠️  Failed to delete {branch}: {e}")

    click.echo(f"\n✓ Cleaned up {deleted_count}/{len(orphaned)} branches")


def main():
    """Entry point for the CLI."""
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\n⏸️  Interrupted")
        sys.exit(0)
    except Exception as e:
        click.echo(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
