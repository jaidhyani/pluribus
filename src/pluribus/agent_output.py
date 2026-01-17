"""Parse agent output to detect interventions and progress."""

import json
import re
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone


def extract_session_id_from_json(worktree_path: Path) -> Optional[str]:
    """Extract session_id from agent-output.json file.

    Args:
        worktree_path: Path to worktree directory

    Returns:
        Session ID if found in JSON, None otherwise
    """
    output_file = worktree_path / ".pluribus" / "agent-output.json"

    if not output_file.exists():
        return None

    try:
        with open(output_file) as f:
            data = json.load(f)
        return data.get("session_id")
    except (json.JSONDecodeError, OSError):
        return None


def extract_result_from_json(worktree_path: Path) -> Optional[str]:
    """Extract result field from agent-output.json file.

    Args:
        worktree_path: Path to worktree directory

    Returns:
        Result text if found in JSON, None otherwise
    """
    output_file = worktree_path / ".pluribus" / "agent-output.json"

    if not output_file.exists():
        return None

    try:
        with open(output_file) as f:
            data = json.load(f)
        return data.get("result")
    except (json.JSONDecodeError, OSError):
        return None


def extract_error_from_output(worktree_path: Path) -> Optional[dict]:
    """Extract error information if agent failed.

    Args:
        worktree_path: Path to worktree directory

    Returns:
        Dict with error info if error occurred, None otherwise
    """
    output_file = worktree_path / ".pluribus" / "agent-output.json"

    if not output_file.exists():
        return None

    try:
        with open(output_file) as f:
            data = json.load(f)

        # Check for error field
        if "error" in data:
            return {
                "type": "agent_error",
                "message": data.get("error", "Unknown error"),
                "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            }
    except (json.JSONDecodeError, OSError):
        pass

    return None


def detect_interventions(result_text: Optional[str]) -> list[dict]:
    """Detect user intervention points from Claude's output.

    Args:
        result_text: The 'result' field from Claude Code's JSON output

    Returns:
        List of intervention dicts with type, question/description, options, blocking, answered
    """
    if not result_text:
        return []

    interventions = []

    # Pattern 1: AskUserQuestion - generic confirmation
    ask_patterns = [
        r"I found these tasks in (.+?)\. Should I execute them\?",
        r"Can you confirm (.+?)\?",
        r"Should I proceed with (.+?)\?",
        r"I need permission to (.+?)\.",
    ]

    for pattern in ask_patterns:
        matches = re.finditer(pattern, result_text, re.IGNORECASE)
        for match in matches:
            question_text = match.group(1)
            interventions.append({
                "type": "ask_user_question",
                "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                "question": question_text,
                "options": [],
                "blocking": False,
                "answered": False,
            })

    # Pattern 2: Permission grant requests
    permission_patterns = [
        r"Please grant permission to (.+?)\.",
        r"I cannot (.+?)\. Permission denied\.",
        r"Permission required: (.+?)",
    ]

    for pattern in permission_patterns:
        matches = re.finditer(pattern, result_text, re.IGNORECASE)
        for match in matches:
            perm_text = match.group(1)
            interventions.append({
                "type": "permission_grant",
                "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                "description": perm_text,
                "blocking": True,
                "answered": False,
            })

    # Remove duplicates (same question text within short time)
    seen = set()
    unique_interventions = []
    for interv in interventions:
        key = (interv.get("question") or interv.get("description"), interv["type"])
        if key not in seen:
            seen.add(key)
            unique_interventions.append(interv)

    return unique_interventions


def extract_progress_signals(result_text: Optional[str]) -> dict:
    """Extract progress indicators from result text.

    Args:
        result_text: The 'result' field from Claude Code's JSON output

    Returns:
        Dict with 'progress_percent', 'phase', 'work_summary'
    """
    signals = {
        "progress_percent": 0,
        "phase": "in_progress",
        "work_summary": "",
    }

    if not result_text:
        return signals

    # Look for progress percentage (e.g., "50%", "50% complete", "Completed 50%")
    progress_match = re.search(r"(?:^|\s|Completed\s)(\d+)%", result_text, re.IGNORECASE | re.MULTILINE)
    if progress_match:
        signals["progress_percent"] = int(progress_match.group(1))

    # Look for phase indicators (more specific patterns, checked in priority order)
    phase_patterns = [
        ("complete", r"\bcomplete\b|\bdone\b|\bfinish\b"),
        ("testing", r"\btest\b|\bdebug\b|\bverif"),
        ("implementation", r"\bimplement\b|\bbuilding\b|\bcoding\b|\bwriting\b"),
        ("planning", r"\bplanning\b|\bdesign\b|\barchitecture\b|\bspec\b"),
    ]

    for phase_name, pattern in phase_patterns:
        if re.search(pattern, result_text, re.IGNORECASE):
            signals["phase"] = phase_name
            break

    # Extract work summary (first 200 chars of useful content)
    lines = result_text.split('\n')
    summary_lines = []
    for line in lines:
        line = line.strip()
        if line and len(' '.join(summary_lines) + ' ' + line) < 200:
            summary_lines.append(line)
        else:
            break

    signals["work_summary"] = ' '.join(summary_lines)[:200]

    return signals


def process_agent_output(worktree_path: Path) -> dict:
    """Process agent output and extract all relevant data.

    Args:
        worktree_path: Path to worktree directory

    Returns:
        Dict with keys: session_id, interventions, progress_percent, phase,
                       work_summary, error (if any)
    """
    result = {
        "session_id": extract_session_id_from_json(worktree_path),
        "interventions": [],
        "progress_percent": 0,
        "phase": "in_progress",
        "work_summary": "",
        "error": None,
    }

    # Check for errors
    error = extract_error_from_output(worktree_path)
    if error:
        result["error"] = error
        return result

    # Extract result text
    result_text = extract_result_from_json(worktree_path)

    # Detect interventions
    result["interventions"] = detect_interventions(result_text)

    # Extract progress signals
    progress = extract_progress_signals(result_text)
    result.update(progress)

    return result
