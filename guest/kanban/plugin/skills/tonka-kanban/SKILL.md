---
name: tonka-kanban
description: Report task progress to the tonka kanban board by writing .tonka/status.md in the worktree. Use at the start of every task in a tonka kanban session, whenever progress or the plan changes, before asking the user a question, and before ending a turn.
---

# Reporting progress to the tonka kanban board

This session runs inside the tonka kanban board. The board shows one card per
project. It builds the card from `.tonka/status.md` at the root of the worktree.
Git ignores the `.tonka/` directory. Never commit it.

The board detects on its own whether you are working or waiting for the user.
The status file tells the user what you have done, what you are doing now, and
why you stopped.

## File format

```
status: working
pr: https://github.com/org/repo/pull/123

- [x] Reproduce the bug
- [x] Write a regression test
- [ ] Fix the parser
- [ ] Open a PR

Fixing the off-by-one error in the parser. The regression test fails as expected.
```

- `status:` is one of:
  - `working`: you are making progress or you have finished a turn normally.
  - `needs-input`: you need a decision or an answer from the user.
  - `review`: a PR is open and you are waiting for reviewers or CI. The user does not need to act.
  - `done`: every PR for the task is merged and no work remains.
- `pr:` lines list PR URLs, one per line. The board finds PRs for the worktree's
  own branch automatically. List PRs here when they come from other branches or repos.
- The checklist has 3 to 8 items. Each item has at most 6 words. Check items off
  as you complete them. Rewrite the list when the plan changes.
- The message after the checklist has at most 3 short sentences. It says what you
  are doing now, or what you need from the user.

## When to write the file

- Before you start the task, write the file with your plan as the checklist.
- After you complete a checklist item or change the plan.
- Before you ask the user a question. Set `status: needs-input` and put the question in the message.
- Before you end a turn.
- When you learn that every PR has merged and nothing remains, set `status: done`.
  The board then offers to delete the project.

Overwrite the whole file each time. Keep it short: the card is narrow.
