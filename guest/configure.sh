#!/bin/bash
# configure.sh - Project VM configuration script
# Run on a project VM to clone the repo and set up the project environment

set -euo pipefail

echo "=== Tonka Project Configuration ==="

# Environment variables expected:
# - GIT_REMOTE: The real git remote URL
# - PROJECT_NAME: Name of the project

PROJECT_NAME="${PROJECT_NAME:-project}"
GIT_REMOTE="${GIT_REMOTE:-}"

# The host project is mounted at /Volumes/My Shared Files/hostproject
HOST_PROJECT="/Volumes/My Shared Files/hostproject"

# Clone from the mounted host directory (fast local copy)
echo "Cloning project from host..."
if [[ -d "$HOST_PROJECT" ]]; then
    git clone "$HOST_PROJECT" ~/project
else
    echo "Warning: Host project not found at $HOST_PROJECT"
    mkdir -p ~/project
fi

# Set the real remote URL
if [[ -n "$GIT_REMOTE" && -d ~/project/.git ]]; then
    echo "Setting remote origin to: $GIT_REMOTE"
    cd ~/project
    git remote set-url origin "$GIT_REMOTE"
    # Fetch to ensure we have the latest refs
    git fetch origin 2>/dev/null || echo "Note: Could not fetch from remote (SSH agent may not be forwarded)"
fi

# Store project name for reference
echo "$PROJECT_NAME" > ~/.tonka-project

# Configure GitHub CLI if GITHUB_TOKEN is available
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    echo "Configuring GitHub CLI..."
    echo "$GITHUB_TOKEN" | gh auth login --with-token
fi

echo "=== Project configuration complete ==="
echo "Project directory: ~/project"
