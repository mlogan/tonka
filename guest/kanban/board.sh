#!/bin/bash
# Runs the board in the tmux "board" window. Exit status 0 means "reload".
dir="$(cd "$(dirname "$0")" && pwd)"
while true; do
    python3 "$dir/kanban.py" && continue
    echo
    echo "The board exited with an error. Press Enter to restart it."
    read -r
done
