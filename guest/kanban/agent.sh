#!/bin/bash
# Runs Claude for one project in its tmux window.
# Usage: agent.sh <project> [--continue | --prompt-file <file>]
dir="$(cd "$(dirname "$0")" && pwd)"
project="$1"
shift

cd "$HOME/projects/$project" || { echo "No such project: $project"; read -r; exit 1; }
if [ -f ~/.claude.env ]; then set -a; . ~/.claude.env; set +a; fi

args=(
    --dangerously-skip-permissions
    --plugin-dir "$dir/plugin"
    --name "$project"
    --append-system-prompt "This Claude Code session runs inside the tonka kanban board. Follow the tonka-kanban skill: keep .tonka/status.md at the root of the worktree up to date as you work, and update it before you end each turn."
)
case "${1:-}" in
    --continue) args=(--continue "${args[@]}") ;;
    --prompt-file)
        args+=("$(cat "$2")")
        rm -f "$2"
        ;;
esac

~/.local/bin/claude "${args[@]}"
echo
echo "Claude exited. This window is now a shell; press Ctrl-\\ to return to the board."
exec "$SHELL" -l
