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
- `a` queues quick notes, one per line, in `~/.tonka/kanban/queue.json`. They show in a Queue column
  (drawn only when non-empty). Enter on a note runs the `n` flow with the note as the starting text;
  the note is removed when the project is confirmed.

## Done
- guest/kanban: start.sh, board.sh, agent.sh, tmux.conf, kanban.py, plugin (tonka-kanban skill + state hooks)
- cmd_kanban in tonka (installs tmux, copies files, ssh -t into start.sh); tmux added to install.sh
- start.sh marks ~/projects as trusted in ~/.claude.json; otherwise new agents stop at the trust prompt
- Docs: README.md, TONKA_FOR_DUMMIES.md
- Tested in the VM: board scan of 42 projects with PR states; new project via claude -p (repo + name);
  skill writes status.md; hooks drive working -> waiting -> exited; Enter on an exited card resumes
  with --continue; Ctrl-\ returns to the board (real tmux client); done card -> delete with force
  prompt; `tonka kanban` from the host attaches and `q` detaches.

- Startup stage inference: open PR -> In review, all PRs merged -> done; Claude processes outside the
  board are found by cwd (ps + lsof) and their state read from the transcript tail
  (`system/turn_duration` or `end_turn` = waiting). PR polling is parallel and cached in pr-cache.json.
  Checked against the VM's 39 projects: 14 Needs input / 1 Working / 12 In review / 11 Idle.
- Windows follow the attaching terminal's size; host terminfo (e.g. xterm-ghostty) is installed in the VM.
- Project queue (`a`). Tested on a separate tmux server in the VM: multi-line entry, bullet stripping,
  wrapping, removal with `d`, Esc at the confirm dialog keeps the note, and creating a project from a
  note removes it.
- getkey decodes Home/End/Delete sequences that tmux sends but the inner terminfo (xterm-256color from
  ~/.tmux.conf) does not list; before, they arrived as Esc and cancelled dialogs.

## Remaining
- Not tested: a card reaching "done" through merged PRs (only `status: done` was tested), and the
  In review column with a real PR.
- Possible follow-ups: kill orphaned agent windows after `tonka rm`; PR polling uses one gh call per
  project every 3 minutes, which could become one call per repo.
- A branch name reused from an old merged PR makes a new project look done.
