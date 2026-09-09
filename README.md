# Tonka

*Making sandboxes fun*

![Tonka Truck](tonka.webp)

Ephemeral tart-based sandboxes for running Claude Code with `--dangerously-skip-permissions`.

## Features

- **No shared volumes** - Code lives entirely inside the VM
- **Automatic sync** of
  - Claude settings, credentials, and plugins
  - GitHub credentials for `gh` and `git`
- **Dotfiles support** - Installs your dotfiles repo automatically
- **Brew** - Automatically `brew install`s everything you have installed on the host OS
- **Tools** - Easy install of Rust, Go, Node.js, Python if you need them.

## Prerequisites

- [Tart](https://tart.run/) - macOS VM manager
- `sshpass` - For initial VM setup (`brew install hudochenkov/sshpass/sshpass`)
- A dotfiles repo with a `setup.sh` script (optional but recommended)

## Setup

Create a config file at `~/.tonka.conf`:

```bash
TONKA_DOTFILES_REPO="git@github.com:yourusername/dotfiles.git"
```

Or set the environment variable:

```bash
export TONKA_DOTFILES_REPO="git@github.com:yourusername/dotfiles.git"
```

Your dotfiles repo should have a `setup.sh` script at the root that sets up your shell, editor, etc.

## Usage

```bash
# Add a repo to the VM
tonka new-repo ~/dev/myproject

# Create a project worktree and launch Claude
tonka new my-feature myproject

# Build a feature end-to-end without supervision: worktree -> Claude -> PR
tonka build "Add a --json flag to the status command"

# Launch Claude in a project (or select from list)
tonka
tonka cl my-feature

# SSH into a project
tonka sh my-feature

# Start/stop VM
tonka start
tonka stop

# List repos and projects
tonka list

# Clean up merged worktrees
tonka cleanup

# Rebuild base VM (after config changes)
tonka rebuild-base
```

## Building a feature end-to-end

`tonka build` runs the whole loop unattended:

```bash
tonka build "Add a --json flag to the status command"
tonka build --repo myproject --name json-flag "Add a --json flag ..."
tonka build - < prompt.txt          # read the prompt from stdin
```

It creates a fresh worktree off the default branch, runs Claude headlessly in
it with your prompt, and expects Claude to commit, push, and open a PR. The
prompt tells Claude to read every skill in the repo's `.claude/skills` directory
and invoke the relevant ones (tests, review, PR creation, ...). Progress is
streamed to your terminal; the raw session log is kept at
`/tmp/tonka-build/<project>.log` in the VM.

When a PR exists for the branch, tonka prints its URL, pushes any commits that
did not make it to origin, and removes the worktree and local branch. Pass
`--keep` to keep the worktree. If no PR was created, the worktree is kept and
tonka prints how to inspect it, resume the Claude session, or discard it.

Options:
- `--repo <repo>` - repo to build in (default: `TONKA_DEFAULT_REPO` or first repo)
- `--name <project>` - worktree/branch name (default: `build-<slug of prompt>`)
- `--keep` - keep the worktree after the PR is created

## How It Works

1. **Base VM**: Created once with your dotfiles, tools, and Claude CLI installed
2. **Tonka VM**: Cloned from base, contains your repos and project worktrees
3. **Git Auth**: Uses `gh` CLI credential helper (synced from host)

## Configuration

Config file: `~/.tonka.conf` (sourced as shell script)

Variables (can be set in config file or environment):
- `TONKA_BASE_IMAGE` - Tart image to use for base VM (default: `ghcr.io/cirruslabs/macos-tahoe-xcode:latest`)
- `TONKA_CPU` - Number of VM CPUs (default: host CPU count)
- `TONKA_MEMORY` - VM memory in MB (default: 5/8 of host memory)
- `TONKA_DISK_SIZE` - VM disk size in GB (e.g., `512`)
- `TONKA_DOTFILES_REPO` - Git URL of your dotfiles repo (should have `setup.sh` at root)
- `TONKA_DEFAULT_REPO` - Name of the repo to use when `tonka new` / `tonka pr` is invoked without a repo argument (default: first repo alphabetically)
- `TONKA_TOOLS` - Space-separated list of tools to install: `rust`, `go`, `nodejs`, `python`
- `GITHUB_TOKEN` - Passed to VM for GitHub CLI authentication (auto-detected from `gh auth token` if not set)

## Troubleshooting

### "SSH not ready after 60 seconds" on `tonka rebuild-base` or first `tonka` command

On macOS Sequoia and later, your terminal app (iTerm, Terminal.app, Ghostty, etc.) needs **Local Network** privacy permission to reach VMs on the tart bridge. If it's denied, every connection to a LAN address is silently dropped — ARP works, but TCP/ICMP fail with "No route to host" — and tonka's SSH wait loop will time out even though the VM is healthy.

**Fix:**

1. Open **System Settings → Privacy & Security → Local Network**
2. Enable your terminal app
3. **Quit (Cmd+Q) and reopen** the terminal — child processes of the old instance inherit the denied state
4. Verify with `ping <vm-ip>` (e.g. `ping 192.168.64.2`) before retrying

You can confirm this is the cause by running `ping <vm-ip>` from your shell while the VM is running. If it fails with `No route to host` while `arp -a` shows the VM's MAC, it's the privacy block.
