"""Agent management for Pluribus."""

import json
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
            command="claude",
            args=["-p"],
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

    # Build command, adding JSON output format for headless-claude-code
    cmd = [agent.command] + agent.args
    if agent.name == "headless-claude-code" and "--output-format" not in agent.args:
        cmd.extend(["--output-format", "json"])

    # For headless-claude-code, pass the prompt as a command argument instead of stdin
    # This avoids issues with detached processes and stdin
    if agent.name == "headless-claude-code" and task_description:
        cmd.append(task_description)

    # Setup output capture for session ID extraction
    pluribus_dir = worktree_dir / ".pluribus"
    pluribus_dir.mkdir(parents=True, exist_ok=True)
    output_file = pluribus_dir / "agent-output.json"

    # Spawn process
    try:
        with open(output_file, "w") as out_f:
            process = subprocess.Popen(
                cmd,
                stdout=out_f,
                stderr=subprocess.STDOUT,
                cwd=worktree_dir,
                env=env,
                text=True,
                start_new_session=True,  # Detach from parent process
            )

        return process.pid
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Failed to start agent: command not found: {agent.command}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Failed to spawn agent: {e}") from e


def try_get_session_id(worktree_dir: Path, timeout_seconds: float = 5.0) -> Optional[str]:
    """Try to extract session ID from agent output.

    Polls the agent output file for up to timeout_seconds to extract the session ID
    from the JSON output. Returns None if not available within timeout.

    Args:
        worktree_dir: Path to worktree directory
        timeout_seconds: Maximum seconds to wait for session ID

    Returns:
        Session ID string if found, None otherwise
    """
    import time

    output_file = worktree_dir / ".pluribus" / "agent-output.json"
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        if not output_file.exists():
            time.sleep(0.1)
            continue

        try:
            with open(output_file) as f:
                content = f.read().strip()

            if not content:
                time.sleep(0.1)
                continue

            # Try to parse as JSON
            data = json.loads(content)
            if "session_id" in data:
                return data["session_id"]

            # If we got valid JSON but no session_id, stop waiting
            return None
        except (json.JSONDecodeError, OSError):
            time.sleep(0.1)
            continue

    return None


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
