# tonka kanban — implementation notes

Branch: `mlogan-kanban`

## Design
- `tonka kanban` (host) ensures the VM is up, installs tmux in the VM if needed,
  copies `guest/kanban/` to `~/.tonka/kanban/` in the VM, and runs `start.sh` over `ssh -t`.
- `start.sh` creates or attaches the tmux session `kanban` on a private socket (`tmux -L tonka`).
  Window `board` runs the board (`board.sh` -> `kanban.py`). Each project with a running agent
  gets its own tmux window, so sessions survive ssh disconnects.
- `C-\` (tmux root binding) returns to the board from any window.
- Card state comes from two files in `<worktree>/.tonka/` (git-excluded via the repo's `info/exclude`):
  - `status.md`: written by Claude per the `tonka-kanban` skill (status, PR links, checklist, message).
  - `agent-state`: written by Claude Code hooks (working / waiting / exited).
- The skill and the hooks ship as a plugin loaded with `claude --plugin-dir`.
- PRs for each branch are detected with `gh pr list --head <branch>` in a background thread.
- Columns: Needs input | Working | In review | Idle. Done cards (status `done`, or all PRs merged
  and the checklist complete) go to Needs input, and Enter offers to delete the project.
- `n` creates a project: the user types a task, `claude -p` picks a repo and a worktree name,
  the user confirms, then the board creates the worktree and starts Claude with the task.

## Done

## Remaining
- guest/kanban files: start.sh, board.sh, agent.sh, tmux.conf, kanban.py, plugin (skill + hooks)
- cmd_kanban in tonka, usage text, tmux in install.sh
- Test in the VM
- Docs: README.md, TONKA_FOR_DUMMIES.md
