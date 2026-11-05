#!/bin/bash
# Starts the kanban tmux session in the VM, or attaches to it if it is running.
set -euo pipefail

dir="$(cd "$(dirname "$0")" && pwd)"
export LANG="${LANG:-en_US.UTF-8}"
# tmux exits with "missing or unsuitable terminal" when TERM has no terminfo entry.
infocmp "${TERM:-dumb}" >/dev/null 2>&1 || export TERM=xterm-256color
# The tmux server's environment is inherited by the board and every agent window.
if [ -f ~/.claude.env ]; then set -a; . ~/.claude.env; set +a; fi

# Trust ~/projects so agents for new worktrees don't stop at Claude's trust prompt,
# which no hook reports. Trust applies to subdirectories.
jq=/opt/homebrew/bin/jq
if [ -f ~/.claude.json ] && ! "$jq" -e --arg p "$HOME/projects" '.projects[$p].hasTrustDialogAccepted == true' ~/.claude.json >/dev/null; then
    "$jq" --arg p "$HOME/projects" '.projects[$p].hasTrustDialogAccepted = true' ~/.claude.json > ~/.claude.json.tonka-tmp \
        && mv ~/.claude.json.tonka-tmp ~/.claude.json
fi

t=(tmux -L tonka -f "$dir/tmux.conf")

if ! "${t[@]}" has-session -t kanban 2>/dev/null; then
    "${t[@]}" new-session -d -s kanban -n board "$dir/board.sh"
elif ! "${t[@]}" list-windows -t kanban -F '#{window_name}' | grep -qx board; then
    "${t[@]}" new-window -d -t kanban: -n board "$dir/board.sh"
fi
# resize-window pins a window to a fixed size (window-size manual); undo that so
# every window follows the attaching terminal.
for w in $("${t[@]}" list-windows -t kanban -F '#{window_id}'); do
    "${t[@]}" set-option -w -u -t "$w" window-size
done
"${t[@]}" select-window -t 'kanban:=board'
exec "${t[@]}" -u attach -t kanban
