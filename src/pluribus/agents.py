"""Agent management for Pluribus."""

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str
    command: str
    args: list = field(default_factory=list)
    setup: Optional[str] = None


def get_default_agents() -> dict[str, AgentConfig]:
    """Return built-in default agents."""
    return {
        "headless-claude-code": AgentConfig(
            name="headless-claude-code",
            command="claude-code",
            args=[],
            setup=None,
        )
    }


def load_agents_from_config(config: dict) -> dict[str, AgentConfig]:
    """Load agent definitions from parsed config dict.

    Args:
        config: Dict with 'agents' key containing agent definitions

    Returns:
        Dict mapping agent names to AgentConfig objects
    """
    agents = {}
    agents_section = config.get("agents", {})

    if not agents_section:
        return agents

    for agent_name, agent_def in agents_section.items():
        if not isinstance(agent_def, dict):
            continue

        agents[agent_name] = AgentConfig(
            name=agent_def.get("name", agent_name),
            command=agent_def.get("command", ""),
            args=agent_def.get("args", []),
            setup=agent_def.get("setup"),
        )

    return agents


def resolve_agent(
    agent_name: Optional[str],
    config_agents: dict[str, AgentConfig],
    default_agent: Optional[str] = None,
) -> Optional[AgentConfig]:
    """Resolve agent by name with fallback to defaults.

    Precedence:
    1. Explicitly provided agent_name
    2. config_agents (from pluribus.config)
    3. Built-in defaults

    Args:
        agent_name: Requested agent name (if any)
        config_agents: Agents loaded from config
        default_agent: Default agent name from config (if any)

    Returns:
        AgentConfig if found, None otherwise

    Raises:
        ValueError: If agent_name is provided but not found
    """
    built_in = get_default_agents()

    # If no agent name requested, use default from config or built-in
    if not agent_name:
        if default_agent and default_agent in config_agents:
            return config_agents[default_agent]
        if default_agent and default_agent in built_in:
            return built_in[default_agent]
        # Fall back to headless-claude-code
        return built_in.get("headless-claude-code")

    # Agent name explicitly requested - must be found
    if agent_name in config_agents:
        return config_agents[agent_name]

    if agent_name in built_in:
        return built_in[agent_name]

    raise ValueError(f"Agent '{agent_name}' not found in config or built-in agents")


def build_env_vars(
    task_id: str,
    task_name: str,
    worktree_dir: Path,
    repo_root: Path,
    agent_args: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Build environment variables for agent.

    Args:
        task_id: Task identifier
        task_name: Human-readable task name
        worktree_dir: Path to worktree directory
        repo_root: Path to repository root
        agent_args: Additional agent-specific arguments

    Returns:
        Dict of environment variables to set
    """
    env = {
        "PLURIBUS_TASK_ID": task_id,
        "PLURIBUS_TASK_NAME": task_name,
        "PLURIBUS_WORKTREE_DIR": str(worktree_dir),
        "PLURIBUS_REPO_ROOT": str(repo_root),
    }

    # Add agent-specific arguments as PLURIBUS_AGENT_ARG_*
    if agent_args:
        for key, value in agent_args.items():
            env_key = f"PLURIBUS_AGENT_ARG_{key.upper()}"
            env[env_key] = value

    return env


def run_setup(setup_script: str, worktree_dir: Path) -> None:
    """Run setup script in worktree directory.

    Args:
        setup_script: Shell commands to execute
        worktree_dir: Working directory for execution

    Raises:
        subprocess.CalledProcessError: If setup fails
    """
    try:
        subprocess.run(
            setup_script,
            shell=True,
            cwd=worktree_dir,
            check=True,
            capture_output=False,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Setup script failed: {e}") from e


def spawn_agent(
    agent: AgentConfig,
    task_id: str,
    task_name: str,
    task_description: str,
    worktree_dir: Path,
    repo_root: Path,
    agent_args: Optional[dict[str, str]] = None,
) -> int:
    """Spawn agent process as long-lived background task.

    Args:
        agent: AgentConfig with command and args
        task_id: Task identifier
        task_name: Human-readable task name
        task_description: Full task description to pipe to stdin
        worktree_dir: Path to worktree directory
        repo_root: Path to repository root
        agent_args: Additional agent-specific arguments

    Returns:
        Process ID of spawned agent

    Raises:
        FileNotFoundError: If agent command not found
        RuntimeError: If agent fails to start
    """
    # Run setup if defined
    if agent.setup:
        run_setup(agent.setup, worktree_dir)

    # Build environment
    env = os.environ.copy()
    env.update(build_env_vars(task_id, task_name, worktree_dir, repo_root, agent_args))

    # Build command
    cmd = [agent.command] + agent.args

    # Spawn process with task description piped to stdin
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=worktree_dir,
            env=env,
            text=True,
            start_new_session=True,  # Detach from parent process
        )

        # Write task description to stdin and close
        try:
            if process.stdin:
                process.stdin.write(task_description)
                process.stdin.close()
        except (BrokenPipeError, OSError):
            pass  # Process may have closed stdin already

        return process.pid
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Failed to start agent: command not found: {agent.command}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Failed to spawn agent: {e}") from e


def get_agent_metadata(agent: AgentConfig) -> dict:
    """Get metadata for agent to store in status file.

    Args:
        agent: AgentConfig

    Returns:
        Dict with agent metadata
    """
    return {
        "name": agent.name,
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "metadata": {},
    }
