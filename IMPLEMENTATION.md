# tonka build — implementation notes

Branch: `mlogan-build-cmd`

## Done
- `guest/build.sh`: headless runner (claude -p, stream-json -> readable progress via jq, raw log kept in VM:/tmp/tonka-build/<project>.log)
- `cmd_build` in `tonka`: args (--repo, --name, --keep, `-` for stdin), worktree creation, skill discovery from `.claude/skills`, prompt composition, PR check, push-if-needed, worktree + branch removal
- `create_worktree_from_branch` helper shared with `tonka new`
- usage text + dispatcher

- Docs: README.md, TONKA_FOR_DUMMIES.md
- Dry-run test in VM (sui repo, prompt forbade commits/PR): worktree creation, skill discovery, prompt delivery, progress stream, and the no-PR path all verified; teardown state check verified by hand (unpushed/dirty)

## Remaining
- Full PR-path run (creates a real PR; left for the user)
