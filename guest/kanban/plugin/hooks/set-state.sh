#!/bin/sh
# Records whether Claude is working, waiting for the user, or has exited.
# The board reads this file to decide which column a card belongs in.
d="${CLAUDE_PROJECT_DIR:-$PWD}/.tonka"
mkdir -p "$d" && printf '%s\n' "$1" > "$d/agent-state"
exit 0
