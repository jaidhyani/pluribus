#!/bin/bash
# Manual test script to verify pluribus workflow

set -e

source /tmp/pluribus-env/bin/activate

# Create test directories
TEST_DIR="/tmp/pluribus-manual-test-$$"
mkdir -p "$TEST_DIR"

echo "📦 Creating test repository..."
REPO_DIR="$TEST_DIR/test-repo"
mkdir -p "$REPO_DIR"
cd "$REPO_DIR"
git init
git config user.email "test@example.com"
git config user.name "Test User"
echo "# Test Repo" > README.md
git add .
git commit -m "Initial commit"

echo "✅ Created test repo at $REPO_DIR"

# Initialize pluribus workspace
WORKSPACE_DIR="$TEST_DIR/workspace"
echo ""
echo "🚀 Initializing pluribus workspace..."
cd "$WORKSPACE_DIR" 2>/dev/null || mkdir -p "$WORKSPACE_DIR"
pluribus init "$REPO_DIR" --path "$WORKSPACE_DIR"

echo "✅ Initialized workspace"

# Check structure
echo ""
echo "📋 Checking workspace structure..."
ls -la "$WORKSPACE_DIR/" | grep -E "pluribus.config|todo.md|worktrees"

# Add some tasks
echo ""
echo "📝 Adding tasks to todo.md..."
cat > "$WORKSPACE_DIR/todo.md" <<'EOF'
# Tasks

## Implement feature A
Create a new widget that does something useful.

## Fix critical bug
Address the memory leak in the parser.

## Refactor logging
Move to structured JSON logging.
EOF

cat "$WORKSPACE_DIR/todo.md"

# List tasks
echo ""
echo "📌 Listing tasks..."
cd "$WORKSPACE_DIR"
pluribus list-tasks

# Check status (should be empty)
echo ""
echo "📊 Checking initial status..."
pluribus status || echo "No tasks yet"

# Try creating a worktree manually (can't spawn Claude Code in test)
echo ""
echo "🔧 Testing worktree creation directly..."
WORKSPACE_PID="$$"
python3 << PYTHON_EOF
import os
from pathlib import Path
from pluribus.config import Config
from pluribus.worktree import Worktree
from pluribus.status_file import StatusFile

workspace = Path("/tmp/pluribus-manual-test-$WORKSPACE_PID")
config = Config(workspace)
repo_path = config.get_repo_path()

worktree_mgr = Worktree(repo_path, workspace / "worktrees")

# Create first worktree
print("Creating worktree for feature-a...")
wt1 = worktree_mgr.create("pluribus/implement-feature-a", "implement-feature-a")
print(f"✓ Created at {wt1}")

# Initialize status
status = StatusFile(wt1)
status.create("implement-feature-a")
print(f"✓ Initialized status file")

# Update status
status.update({
    "status": "in_progress",
    "phase": "analysis",
    "progress_percent": 10,
    "notes": "Analyzed requirements"
})
print(f"✓ Updated status")

# Create second worktree
print("\nCreating worktree for bug-fix...")
wt2 = worktree_mgr.create("pluribus/fix-critical-bug", "fix-critical-bug")
print(f"✓ Created at {wt2}")

status2 = StatusFile(wt2)
status2.create("fix-critical-bug")
status2.update({"status": "in_progress", "progress_percent": 50})
print(f"✓ Initialized status file")

# Verify isolation
print("\n✓ Worktrees are isolated:")
print(f"  - Branch 1: {worktree_mgr.get_current_branch('implement-feature-a')}")
print(f"  - Branch 2: {worktree_mgr.get_current_branch('fix-critical-bug')}")

os.chdir(workspace)
PYTHON_EOF

# Show status
echo ""
echo "📊 Current pluribus status..."
cd "$WORKSPACE_DIR"
pluribus status

# Cleanup
echo ""
echo "🧹 Cleaning up test directory..."
rm -rf "$TEST_DIR"
echo "✓ Done!"
