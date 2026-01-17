"""End-to-end tests for the redesigned agent loop with interventions."""

import json
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime, timezone


def create_test_repo(tmp_path: Path) -> Path:
    """Create a minimal test repository."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir(parents=True, exist_ok=True)

    # Initialize git repo
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

    # Create initial commit
    (repo_path / "README.md").write_text("# Test Repo\n")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    return repo_path


def create_mock_agent_output(
    worktree_path: Path,
    session_id: str = "sess_test123",
    result_text: str = "",
    has_error: bool = False,
):
    """Create a mock agent-output.json file."""
    pluribus_dir = worktree_path / ".pluribus"
    pluribus_dir.mkdir(parents=True, exist_ok=True)

    output_data = {
        "session_id": session_id,
    }

    if has_error:
        output_data["error"] = "Permission denied: cannot create files"
    else:
        output_data["result"] = result_text or "Completed 50% of the task. Currently implementing core functionality."

    with open(pluribus_dir / "agent-output.json", "w") as f:
        json.dump(output_data, f)


def test_session_id_capture():
    """Test that session IDs are captured from agent output."""
    from pluribus.agent_output import extract_session_id_from_json

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        worktree_path = tmp_path / "test-worktree"
        worktree_path.mkdir()

        create_mock_agent_output(worktree_path, session_id="sess_abc123xyz")

        session_id = extract_session_id_from_json(worktree_path)
        assert session_id == "sess_abc123xyz", f"Expected 'sess_abc123xyz', got '{session_id}'"
        print("✓ Session ID capture test passed")


def test_progress_extraction():
    """Test that progress is extracted from result text."""
    from pluribus.agent_output import extract_progress_signals

    result_text = "Completed 65% of the implementation. Currently coding the database layer. Building the API endpoints and controller methods. Made good progress on the ORM setup."

    signals = extract_progress_signals(result_text)
    assert signals["progress_percent"] == 65, f"Expected 65%, got {signals['progress_percent']}%"
    assert signals["phase"] == "implementation", f"Expected 'implementation', got '{signals['phase']}'"
    assert len(signals["work_summary"]) > 0, "Expected work_summary to be non-empty"
    print("✓ Progress extraction test passed")


def test_intervention_detection():
    """Test that interventions are detected from result text."""
    from pluribus.agent_output import detect_interventions

    result_text = """
    Should I execute the migration?
    I found these tasks in the backlog. Should I execute them?
    Can you confirm that I should proceed with this change?
    """

    interventions = detect_interventions(result_text)
    assert len(interventions) >= 2, f"Expected at least 2 interventions, got {len(interventions)}"
    assert any(i["type"] == "ask_user_question" for i in interventions)
    print(f"✓ Intervention detection test passed ({len(interventions)} interventions found)")


def test_error_detection():
    """Test that errors are detected from output."""
    from pluribus.agent_output import extract_error_from_output

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        worktree_path = tmp_path / "test-worktree"
        worktree_path.mkdir()

        create_mock_agent_output(
            worktree_path,
            has_error=True,
        )

        error = extract_error_from_output(worktree_path)
        assert error is not None, "Expected error to be detected"
        assert error["type"] == "agent_error"
        assert "Permission denied" in error["message"]
        print("✓ Error detection test passed")


def test_status_file_updates():
    """Test that status file is created and updated with new fields."""
    from pluribus.status_file import StatusFile

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        worktree_path = tmp_path / "test-worktree"
        worktree_path.mkdir()

        status_file = StatusFile(worktree_path)
        status_file.create("test-task-123")

        # Load and verify initial state
        status = status_file.load()
        assert status is not None
        assert status["task_id"] == "test-task-123"
        assert "work_summary" in status
        assert "interventions" in status
        assert status["interventions"] == []
        assert "blockers" in status

        # Update with progress and interventions
        status_file.update({
            "progress_percent": 45,
            "phase": "implementation",
            "work_summary": "Building the API layer",
            "interventions": [
                {
                    "type": "ask_user_question",
                    "question": "Should I use REST or GraphQL?",
                    "options": [],
                    "blocking": False,
                    "answered": False,
                }
            ],
        })

        # Verify updates
        updated_status = status_file.load()
        assert updated_status["progress_percent"] == 45
        assert updated_status["phase"] == "implementation"
        assert "Building the API" in updated_status["work_summary"]
        assert len(updated_status["interventions"]) == 1
        assert updated_status["interventions"][0]["type"] == "ask_user_question"

        print("✓ Status file updates test passed")


def test_process_agent_output():
    """Test full post-run processing pipeline."""
    from pluribus.agent_output import process_agent_output

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        worktree_path = tmp_path / "test-worktree"
        worktree_path.mkdir()

        result_text = """
        Completed 72% of the task.
        Currently building the user authentication system.
        I found these tasks in the backlog. Should I execute them?
        Can you confirm that I should proceed with this approach?
        """

        create_mock_agent_output(
            worktree_path,
            session_id="sess_proc123",
            result_text=result_text,
        )

        output_data = process_agent_output(worktree_path)

        # Verify session ID
        assert output_data["session_id"] == "sess_proc123"

        # Verify progress
        assert output_data["progress_percent"] == 72
        assert output_data["phase"] == "implementation"

        # Verify interventions detected
        assert len(output_data["interventions"]) >= 1

        # Verify no error
        assert output_data["error"] is None

        print("✓ Process agent output test passed")


def test_display_alerts():
    """Test that interventions and errors display correctly."""
    from pluribus.display import format_status_table

    task_data = [
        {
            "task_name": "Task 1",
            "branch": "pluribus/task-1-abc",
            "status": "in_progress",
            "progress_percent": 50,
            "last_update": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "claude_instance_active": True,
            "pr_url": None,
            "interventions": [
                {"type": "ask_user_question", "question": "Continue?", "blocking": False, "answered": False}
            ],
        },
        {
            "task_name": "Task 2",
            "branch": "pluribus/task-2-xyz",
            "status": "blocked",
            "progress_percent": 30,
            "last_update": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "claude_instance_active": False,
            "pr_url": None,
            "blockers": {"type": "agent_error", "message": "Permission denied"},
        },
    ]

    table = format_status_table(task_data)
    assert "Alerts" in table
    assert "intervention" in table.lower()
    assert "blocked" in table.lower()
    print("✓ Display alerts test passed")


if __name__ == "__main__":
    print("\n🧪 Running e2e agent loop tests...\n")

    test_session_id_capture()
    test_progress_extraction()
    test_intervention_detection()
    test_error_detection()
    test_status_file_updates()
    test_process_agent_output()
    test_display_alerts()

    print("\n✅ All e2e tests passed!\n")
