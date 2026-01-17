"""Integration tests for the complete agent loop workflow."""

import json
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime, timezone

from pluribus.status_file import StatusFile
from pluribus.post_run import process_completed_agent_run
from pluribus.tasks import TaskParser, task_to_slug, generate_unique_suffix
from pluribus.worktree import Worktree
from pluribus.config import Config


def setup_test_workspace(tmp_path: Path):
    """Set up a complete pluribus workspace with a test repository."""
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    # Create repo
    repo_path = workspace_root / "test-repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Initial commit
    (repo_path / "README.md").write_text("# Test Repo\n")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create pluribus workspace
    (workspace_root / "worktrees").mkdir()

    # Create todo.md
    todo_file = workspace_root / "todo.md"
    todo_file.write_text("""# Tasks

## Implement user authentication
Add JWT-based authentication system.

## Add database migration tool
Create tool for managing database schema changes.
""")

    # Create config
    config = Config(workspace_root)
    config.save({"repo_path": str(repo_path)})

    return workspace_root, repo_path


def create_mock_agent_run(
    worktree_path: Path,
    session_id: str,
    progress: int,
    phase: str,
    has_interventions: bool = False,
    has_error: bool = False,
):
    """Create a mock agent output simulating a completed run."""
    pluribus_dir = worktree_path / ".pluribus"
    pluribus_dir.mkdir(parents=True, exist_ok=True)

    if has_error:
        result_text = "Failed to complete task due to permission issues."
        output_data = {
            "session_id": session_id,
            "error": "Permission denied: cannot write to database",
        }
    else:
        # Build result with progress and phase indicators
        result_parts = [
            f"Completed {progress}% of the task.",
        ]

        # Add phase indicator with keywords that match the regex patterns
        if phase == "implementation":
            result_parts.append("Currently building and implementing the core features.")
        elif phase == "testing":
            result_parts.append("Running tests and debugging issues.")
        else:
            result_parts.append(f"In {phase} phase.")

        if has_interventions:
            result_parts.extend([
                "I found these tasks in the backlog. Should I execute them?",
                "Can you confirm that I should proceed with this database schema?"
            ])

        result_text = " ".join(result_parts)
        output_data = {
            "session_id": session_id,
            "result": result_text,
        }

    with open(pluribus_dir / "agent-output.json", "w") as f:
        json.dump(output_data, f)


def test_complete_agent_loop_workflow():
    """Test the complete workflow: create plurb, run agent, process output, detect interventions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        workspace_root, repo_path = setup_test_workspace(tmp_path)

        # Step 1: Create a worktree (simulating pluribus workon)
        parser = TaskParser(workspace_root / "todo.md")
        task_name, task_desc = parser.parse()[0]

        unique_suffix = generate_unique_suffix()
        task_slug = task_to_slug(task_name, unique_suffix)

        worktree_manager = Worktree(repo_path, workspace_root / "worktrees")
        branch_name = f"pluribus/{task_slug}"
        worktree_path = worktree_manager.create(branch_name, task_slug)

        # Step 2: Initialize status file
        status_file = StatusFile(worktree_path)
        status_file.create(task_slug)

        # Verify initial status
        status = status_file.load()
        assert status["status"] == "pending"
        assert status["progress_percent"] == 0
        assert status["interventions"] == []
        assert status["blockers"] is None

        # Step 3: Simulate agent running (mark as active, update with session ID)
        session_id = "sess_test_workflow_123"
        status_file.update({
            "status": "in_progress",
            "claude_instance_active": True,
            "session_id": session_id,
            "agent_pid": 12345,
        })

        # Step 4: Create mock agent output
        create_mock_agent_run(
            worktree_path,
            session_id=session_id,
            progress=45,
            phase="implementation",
            has_interventions=True,
        )

        # Step 5: Process completed agent run
        process_completed_agent_run(worktree_path)

        # Step 6: Verify status was updated
        updated_status = status_file.load()
        assert updated_status["progress_percent"] == 45
        assert updated_status["phase"] == "implementation"
        assert updated_status["claude_instance_active"] is False
        assert len(updated_status["interventions"]) >= 1
        assert updated_status["status"] == "awaiting_input"

        # Verify interventions contain expected data
        interventions = updated_status["interventions"]
        assert any(i["type"] == "ask_user_question" for i in interventions)
        for intervention in interventions:
            assert "timestamp" in intervention
            assert "answered" in intervention
            assert intervention["answered"] is False

        print("✓ Complete agent loop workflow test passed")


def test_error_handling_in_agent_loop():
    """Test that errors are properly captured and status marked as blocked."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        workspace_root, repo_path = setup_test_workspace(tmp_path)

        # Create worktree
        parser = TaskParser(workspace_root / "todo.md")
        task_name, task_desc = parser.parse()[0]

        unique_suffix = generate_unique_suffix()
        task_slug = task_to_slug(task_name, unique_suffix)

        worktree_manager = Worktree(repo_path, workspace_root / "worktrees")
        branch_name = f"pluribus/{task_slug}"
        worktree_path = worktree_manager.create(branch_name, task_slug)

        status_file = StatusFile(worktree_path)
        status_file.create(task_slug)

        # Simulate agent with error
        session_id = "sess_error_test_456"
        status_file.update({
            "status": "in_progress",
            "claude_instance_active": True,
            "session_id": session_id,
        })

        create_mock_agent_run(
            worktree_path,
            session_id=session_id,
            progress=30,
            phase="implementation",
            has_error=True,
        )

        # Process output
        process_completed_agent_run(worktree_path)

        # Verify error handling
        updated_status = status_file.load()
        assert updated_status["status"] == "blocked"
        assert updated_status["blockers"] is not None
        assert updated_status["blockers"]["type"] == "agent_error"
        assert "Permission denied" in updated_status["blockers"]["message"]
        assert updated_status["claude_instance_active"] is False

        print("✓ Error handling in agent loop test passed")


def test_session_resumption_with_status():
    """Test that session ID is preserved for resumption and interventions are tracked."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        workspace_root, repo_path = setup_test_workspace(tmp_path)

        # Create and process a plurb
        parser = TaskParser(workspace_root / "todo.md")
        task_name, task_desc = parser.parse()[1]  # Use second task

        unique_suffix = generate_unique_suffix()
        task_slug = task_to_slug(task_name, unique_suffix)

        worktree_manager = Worktree(repo_path, workspace_root / "worktrees")
        branch_name = f"pluribus/{task_slug}"
        worktree_path = worktree_manager.create(branch_name, task_slug)

        status_file = StatusFile(worktree_path)
        status_file.create(task_slug)

        session_id = "sess_resume_test_789"
        status_file.update({
            "status": "in_progress",
            "claude_instance_active": True,
            "session_id": session_id,
        })

        create_mock_agent_run(
            worktree_path,
            session_id=session_id,
            progress=60,
            phase="testing",
            has_interventions=True,
        )

        process_completed_agent_run(worktree_path)

        # Verify resumption data
        resumed_status = status_file.load()
        assert resumed_status["session_id"] == session_id
        assert len(resumed_status["interventions"]) >= 1

        # Verify interventions can be displayed for user interaction
        interventions = resumed_status["interventions"]
        for interv in interventions:
            # These fields should be present for user interaction
            assert "type" in interv
            assert "question" in interv or "description" in interv
            assert "blocking" in interv
            assert "answered" in interv

        print("✓ Session resumption with status test passed")


def test_status_file_backward_compatibility():
    """Test that old status files without new fields still work."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        worktree_path = tmp_path / "test-worktree"
        worktree_path.mkdir()

        # Create an old-style status file (without interventions, blockers, work_summary)
        old_status = {
            "task_id": "test-task",
            "status": "in_progress",
            "phase": "implementation",
            "progress_percent": 50,
            "last_update": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "claude_instance_active": True,
            "agent_pid": 9999,
            "session_id": "sess_old",
            "pr_url": None,
            "blocker": None,
            "notes": "Old status file",
        }

        pluribus_dir = worktree_path / ".pluribus"
        pluribus_dir.mkdir(parents=True, exist_ok=True)
        with open(pluribus_dir / "status", "w") as f:
            json.dump(old_status, f)

        # Load with StatusFile and verify it works
        status_file = StatusFile(worktree_path)
        status = status_file.load()

        assert status["task_id"] == "test-task"
        assert status["progress_percent"] == 50
        assert status.get("interventions") is None  # Old file doesn't have this
        assert status.get("work_summary") is None  # Old file doesn't have this

        # Update with new fields
        status_file.update({
            "interventions": [{"type": "ask_user_question", "question": "Continue?"}],
            "work_summary": "Made progress on implementation",
        })

        # Verify update preserved old fields
        updated = status_file.load()
        assert updated["task_id"] == "test-task"
        assert updated["progress_percent"] == 50
        assert len(updated["interventions"]) == 1
        assert "Made progress" in updated["work_summary"]

        print("✓ Status file backward compatibility test passed")


if __name__ == "__main__":
    print("\n🧪 Running agent loop integration tests...\n")

    test_complete_agent_loop_workflow()
    test_error_handling_in_agent_loop()
    test_session_resumption_with_status()
    test_status_file_backward_compatibility()

    print("\n✅ All integration tests passed!\n")
