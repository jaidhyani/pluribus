"""Main CLI entry point for Pluribus."""

import subprocess
import sys
from pathlib import Path
from typing import Optional

import click

from .config import Config
from .status_file import StatusFile
from .tasks import TaskParser, task_to_branch_name, task_to_slug
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
    """Pluribus: Manage multiple parallel Claude Code instances."""
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
def workon(task_name: Optional[str]):
    """Start working on a task."""
    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace (no pluribus.config found)")
        sys.exit(1)

    config = Config(workspace_root)
    repo_path = config.get_repo_path()
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

    # Check if task already being worked on
    task_slug = task_to_slug(task_name)
    worktree_manager = Worktree(repo_path, workspace_root / "worktrees")

    if worktree_manager.exists(task_slug):
        click.echo(f"❌ Task '{task_name}' is already being worked on")
        click.echo(f"   Use: pluribus resume '{task_name}'")
        sys.exit(1)

    # Create worktree
    branch_name = task_to_branch_name(task_name)
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

    # Generate and display prompt
    prompt = generate_task_prompt(task_name, task_desc, worktree_path)

    # Start Claude Code
    click.echo(f"\n🚀 Starting Claude Code for: {task_name}\n")
    try:
        subprocess.run(
            ["claude-code", str(worktree_path)],
            cwd=worktree_path,
        )
        click.echo(f"\n✓ Work session ended for '{task_name}'")
    except FileNotFoundError:
        click.echo("⚠️  Claude Code CLI not found. Starting with prompt instead...\n")
        click.echo("📋 Here's your task prompt:\n")
        click.echo(prompt)
        click.echo("\n" + "="*60)
        click.echo("To work on this task with Claude Code, run:")
        click.echo(f"  cd {worktree_path}")
        click.echo("  claude-code")
        click.echo("="*60)
        click.echo(f"\n✓ Worktree ready at: {worktree_path}")


@cli.command()
@click.argument("task_name")
def resume(task_name: str):
    """Resume work on an existing task."""
    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace")
        sys.exit(1)

    config = Config(workspace_root)
    repo_path = config.get_repo_path()
    if not repo_path or not repo_path.exists():
        click.echo("❌ Repository not configured")
        sys.exit(1)

    todo_path = workspace_root / "todo.md"
    parser = TaskParser(todo_path)

    try:
        task_name, task_desc = parser.get_task_by_name(task_name)
    except ValueError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)

    task_slug = task_to_slug(task_name)
    worktree_manager = Worktree(repo_path, workspace_root / "worktrees")

    if not worktree_manager.exists(task_slug):
        click.echo(f"❌ No worktree found for '{task_name}'")
        sys.exit(1)

    worktree_path = worktree_manager.get_path(task_slug)
    prompt = generate_task_prompt(task_name, task_desc, worktree_path)

    click.echo(f"🚀 Resuming work on: {task_name}\n")
    try:
        subprocess.run(
            ["claude-code", str(worktree_path)],
            cwd=worktree_path,
        )
        click.echo(f"\n✓ Work session ended for '{task_name}'")
    except FileNotFoundError:
        click.echo("⚠️  Claude Code CLI not found. Starting with prompt instead...\n")
        click.echo("📋 Here's your task prompt:\n")
        click.echo(prompt)
        click.echo("\n" + "="*60)
        click.echo("To work on this task with Claude Code, run:")
        click.echo(f"  cd {worktree_path}")
        click.echo("  claude-code")
        click.echo("="*60)
        click.echo(f"\n✓ Ready to resume at: {worktree_path}")


@cli.command()
def status():
    """Show status of all tasks."""
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
    """Watch task status for live updates."""
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
@click.argument("task_name")
def details(task_name: str):
    """Show detailed information about a task."""
    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace")
        sys.exit(1)

    todo_path = workspace_root / "todo.md"
    parser = TaskParser(todo_path)

    try:
        full_task_name, _ = parser.get_task_by_name(task_name)
    except ValueError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)

    task_slug = task_to_slug(full_task_name)
    config = Config(workspace_root)
    repo_path = config.get_repo_path()
    worktree_manager = Worktree(repo_path, workspace_root / "worktrees")

    if not worktree_manager.exists(task_slug):
        click.echo(f"❌ No worktree found for '{full_task_name}'")
        sys.exit(1)

    worktree_path = worktree_manager.get_path(task_slug)
    print_task_details(task_slug, worktree_path, worktree_manager)


@cli.command()
@click.argument("task_name")
@click.option("--force", is_flag=True, help="Force delete even with uncommitted changes")
def delete(task_name: str, force: bool):
    """Delete a completed task's worktree and branch."""
    workspace_root = find_workspace_root()
    if not workspace_root:
        click.echo("❌ Not in a Pluribus workspace")
        sys.exit(1)

    todo_path = workspace_root / "todo.md"
    parser = TaskParser(todo_path)

    try:
        full_task_name, _ = parser.get_task_by_name(task_name)
    except ValueError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)

    task_slug = task_to_slug(full_task_name)
    config = Config(workspace_root)
    repo_path = config.get_repo_path()
    worktree_manager = Worktree(repo_path, workspace_root / "worktrees")

    if not worktree_manager.exists(task_slug):
        click.echo(f"❌ No worktree found for '{full_task_name}'")
        sys.exit(1)

    # Check for uncommitted changes
    if worktree_manager.has_uncommitted_changes(task_slug):
        if not force:
            click.echo(f"⚠️  Task has uncommitted changes")
            if not click.confirm("Delete anyway?"):
                click.echo("Cancelled")
                return

    if worktree_manager.has_unpushed_commits(task_slug):
        if not force:
            click.echo(f"⚠️  Task has unpushed commits")
            if not click.confirm("Delete anyway?"):
                click.echo("Cancelled")
                return

    # Delete the worktree
    try:
        worktree_manager.delete(task_slug)
        click.echo(f"✓ Deleted worktree for '{full_task_name}'")
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
