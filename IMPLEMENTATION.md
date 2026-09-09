# tonka build — implementation notes

Branch: `mlogan-build-cmd`

## Done
- `guest/build.sh`: headless runner (claude -p, stream-json -> readable progress via jq, raw log kept in VM:/tmp/tonka-build/<project>.log)
- `cmd_build` in `tonka`: args (--repo, --name, --keep, `-` for stdin), worktree creation, skill discovery from `.claude/skills`, prompt composition, PR check, push-if-needed, worktree + branch removal
- `create_worktree_from_branch` helper shared with `tonka new`
- usage text + dispatcher

## Remaining
- Docs: README.md, TONKA_FOR_DUMMIES.md
- Dry-run test in VM (no-PR path)
- Full PR-path run (creates a real PR; left for the user)
