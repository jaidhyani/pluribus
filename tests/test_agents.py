"""Tests for agent configuration and spawning."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pluribus.agents import (
    AgentConfig,
    build_env_vars,
    get_agent_metadata,
    get_default_agents,
    load_agents_from_config,
    resolve_agent,
    spawn_agent,
)


class TestAgentConfig:
    """Test AgentConfig dataclass."""

    def test_agent_config_creation(self):
        """Test creating an agent config."""
        agent = AgentConfig(
            name="test-agent",
            command="test-command",
            args=["--arg1", "--arg2"],
            setup="echo setup",
        )
        assert agent.name == "test-agent"
        assert agent.command == "test-command"
        assert agent.args == ["--arg1", "--arg2"]
        assert agent.setup == "echo setup"

    def test_agent_config_defaults(self):
        """Test agent config with default values."""
        agent = AgentConfig(name="test", command="cmd")
        assert agent.name == "test"
        assert agent.command == "cmd"
        assert agent.args == []
        assert agent.setup is None


class TestGetDefaultAgents:
    """Test built-in default agents."""

    def test_default_agents_exist(self):
        """Test that default agents are available."""
        agents = get_default_agents()
        assert "headless-claude-code" in agents

    def test_headless_claude_code_config(self):
        """Test headless claude code agent configuration."""
        agents = get_default_agents()
        agent = agents["headless-claude-code"]
        assert agent.name == "headless-claude-code"
        assert agent.command == "claude-code"
        assert agent.args == []
        assert agent.setup is None


class TestLoadAgentsFromConfig:
    """Test loading agents from config dict."""

    def test_load_agents_empty_config(self):
        """Test loading from config with no agents."""
        config = {}
        agents = load_agents_from_config(config)
        assert agents == {}

    def test_load_agents_with_agents(self):
        """Test loading agents from config."""
        config = {
            "agents": {
                "custom-agent": {
                    "name": "custom-agent",
                    "command": "custom",
                    "args": ["--verbose"],
                    "setup": "npm install",
                }
            }
        }
        agents = load_agents_from_config(config)
        assert "custom-agent" in agents
        assert agents["custom-agent"].name == "custom-agent"
        assert agents["custom-agent"].command == "custom"
        assert agents["custom-agent"].args == ["--verbose"]
        assert agents["custom-agent"].setup == "npm install"

    def test_load_agents_with_defaults(self):
        """Test loading agents with default values."""
        config = {
            "agents": {
                "minimal": {
                    "command": "minimal-cmd",
                }
            }
        }
        agents = load_agents_from_config(config)
        assert agents["minimal"].command == "minimal-cmd"
        assert agents["minimal"].args == []
        assert agents["minimal"].setup is None

    def test_load_agents_skips_non_dict(self):
        """Test that non-dict agent entries are skipped."""
        config = {
            "agents": {
                "valid": {
                    "command": "cmd",
                },
                "invalid": "not a dict",
            }
        }
        agents = load_agents_from_config(config)
        assert "valid" in agents
        assert "invalid" not in agents


class TestResolveAgent:
    """Test agent resolution with precedence."""

    def test_resolve_explicit_agent(self):
        """Test resolving explicitly requested agent."""
        config_agents = {
            "custom": AgentConfig("custom", "custom-cmd")
        }
        agent = resolve_agent("custom", config_agents)
        assert agent.name == "custom"
        assert agent.command == "custom-cmd"

    def test_resolve_explicit_agent_not_found(self):
        """Test resolving non-existent explicit agent."""
        config_agents = {}
        with pytest.raises(ValueError, match="not found"):
            resolve_agent("nonexistent", config_agents)

    def test_resolve_default_from_config(self):
        """Test resolving default agent from config."""
        config_agents = {
            "my-default": AgentConfig("my-default", "cmd")
        }
        agent = resolve_agent(None, config_agents, "my-default")
        assert agent.name == "my-default"

    def test_resolve_fallback_to_builtin(self):
        """Test falling back to built-in agents."""
        config_agents = {}
        agent = resolve_agent(None, config_agents, "headless-claude-code")
        assert agent.name == "headless-claude-code"

    def test_resolve_no_agent_uses_headless_default(self):
        """Test that no agent specified uses headless claude default."""
        config_agents = {}
        agent = resolve_agent(None, config_agents)
        assert agent.name == "headless-claude-code"

    def test_resolve_config_overrides_builtin(self):
        """Test that config agents override built-in ones."""
        config_agents = {
            "headless-claude-code": AgentConfig(
                "headless-claude-code", "custom-claude-cmd"
            )
        }
        agent = resolve_agent("headless-claude-code", config_agents)
        assert agent.command == "custom-claude-cmd"


class TestBuildEnvVars:
    """Test environment variable building."""

    def test_build_env_vars_basic(self):
        """Test building basic environment variables."""
        env = build_env_vars(
            task_id="task-1",
            task_name="My Task",
            worktree_dir=Path("/path/to/worktree"),
            repo_root=Path("/path/to/repo"),
        )
        assert env["PLURIBUS_TASK_ID"] == "task-1"
        assert env["PLURIBUS_TASK_NAME"] == "My Task"
        assert env["PLURIBUS_WORKTREE_DIR"] == "/path/to/worktree"
        assert env["PLURIBUS_REPO_ROOT"] == "/path/to/repo"

    def test_build_env_vars_with_agent_args(self):
        """Test building env vars with agent-specific arguments."""
        env = build_env_vars(
            task_id="task-1",
            task_name="Task",
            worktree_dir=Path("/work"),
            repo_root=Path("/repo"),
            agent_args={"timeout": "300", "verbose": "true"},
        )
        assert env["PLURIBUS_AGENT_ARG_TIMEOUT"] == "300"
        assert env["PLURIBUS_AGENT_ARG_VERBOSE"] == "true"

    def test_build_env_vars_agent_arg_key_uppercase(self):
        """Test that agent arg keys are uppercased."""
        env = build_env_vars(
            task_id="id",
            task_name="name",
            worktree_dir=Path("/w"),
            repo_root=Path("/r"),
            agent_args={"myArg": "value"},
        )
        assert env["PLURIBUS_AGENT_ARG_MYARG"] == "value"


class TestGetAgentMetadata:
    """Test agent metadata generation."""

    def test_get_agent_metadata(self):
        """Test getting agent metadata."""
        agent = AgentConfig("test-agent", "test-cmd")
        metadata = get_agent_metadata(agent)
        assert metadata["name"] == "test-agent"
        assert "started_at" in metadata
        assert metadata["metadata"] == {}

    def test_agent_metadata_timestamp_format(self):
        """Test that timestamp is ISO format with Z suffix."""
        agent = AgentConfig("test", "cmd")
        metadata = get_agent_metadata(agent)
        timestamp = metadata["started_at"]
        assert timestamp.endswith("Z")
        # Should be parseable as ISO timestamp
        from datetime import datetime
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


class TestSpawnAgent:
    """Test agent spawning."""

    @patch("pluribus.agents.subprocess.Popen")
    def test_spawn_agent_basic(self, mock_popen):
        """Test spawning an agent."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        agent = AgentConfig("test", "test-cmd")
        pid = spawn_agent(
            agent,
            task_id="task-1",
            task_name="My Task",
            task_description="Task description",
            worktree_dir=Path("/work"),
            repo_root=Path("/repo"),
        )

        assert pid == 12345
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args

        # Verify command
        assert call_args[0][0] == ["test-cmd"]

        # Verify env vars
        env = call_args[1]["env"]
        assert env["PLURIBUS_TASK_ID"] == "task-1"
        assert env["PLURIBUS_TASK_NAME"] == "My Task"

        # Verify stdin
        assert call_args[1]["stdin"] == subprocess.PIPE

        # Verify stdin was written to
        mock_process.stdin.write.assert_called_once_with("Task description")
        mock_process.stdin.close.assert_called_once()

    @patch("pluribus.agents.subprocess.run")
    @patch("pluribus.agents.subprocess.Popen")
    def test_spawn_agent_with_setup(self, mock_popen, mock_run):
        """Test spawning agent with setup script."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        agent = AgentConfig("test", "test-cmd", setup="npm install")
        pid = spawn_agent(
            agent,
            task_id="task-1",
            task_name="Task",
            task_description="desc",
            worktree_dir=Path("/work"),
            repo_root=Path("/repo"),
        )

        assert pid == 12345
        # Verify setup was run
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == "npm install"
        assert call_args[1]["cwd"] == Path("/work")

    @patch("pluribus.agents.subprocess.Popen")
    def test_spawn_agent_command_not_found(self, mock_popen):
        """Test spawning agent when command not found."""
        mock_popen.side_effect = FileNotFoundError("command not found")

        agent = AgentConfig("test", "nonexistent-cmd")
        with pytest.raises(FileNotFoundError, match="Failed to start agent"):
            spawn_agent(
                agent,
                task_id="task-1",
                task_name="Task",
                task_description="desc",
                worktree_dir=Path("/work"),
                repo_root=Path("/repo"),
            )

    @patch("pluribus.agents.subprocess.run")
    def test_spawn_agent_setup_fails(self, mock_run):
        """Test agent spawn when setup fails."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")

        agent = AgentConfig("test", "cmd", setup="bad-setup")
        with pytest.raises(RuntimeError, match="Setup script failed"):
            spawn_agent(
                agent,
                task_id="task-1",
                task_name="Task",
                task_description="desc",
                worktree_dir=Path("/work"),
                repo_root=Path("/repo"),
            )

    @patch("pluribus.agents.subprocess.Popen")
    def test_spawn_agent_with_args(self, mock_popen):
        """Test spawning agent with command arguments."""
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        agent = AgentConfig("test", "test-cmd", args=["--arg1", "--arg2"])
        spawn_agent(
            agent,
            task_id="task-1",
            task_name="Task",
            task_description="desc",
            worktree_dir=Path("/work"),
            repo_root=Path("/repo"),
        )

        call_args = mock_popen.call_args
        assert call_args[0][0] == ["test-cmd", "--arg1", "--arg2"]
