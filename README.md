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

# Show host + guest GitHub auth state (useful when clones fail)
tonka auth-status

# Rebuild base VM (after config changes)
tonka rebuild-base
```

## How It Works

1. **Base VM**: Created once with your dotfiles, tools, and Claude CLI installed
2. **Tonka VM**: Cloned from base, contains your repos and project worktrees
3. **Git Auth**: Uses `gh` CLI credential helper inside the VM, with the host's `~/.config/gh/hosts.yml` resynced on every command. SSH remotes use agent forwarding (`ssh -A`) from the host.

### Supported host configurations

The basic workflow (`rebuild-base → new-repo → new`) is designed to work regardless of:

- **`~/.claude` layout**: regular directory, or symlinked into a separate repo (e.g. a dotfiles or `dotclaude-staging` worktree). Leaf files (`settings.json`, `skills/`, `CLAUDE.md`, `plugins/`) may be symlinks individually.
- **Dotfiles manager**: any tool is fine as long as the resulting repo has `setup.sh` at its root (stow, chezmoi, yadm, bare-git, plain symlinks — all work).
- **`gh` / `jq` install location on the host**: any PATH-reachable install works. Inside the VM, Homebrew installs both at `/opt/homebrew/bin/...` by construction.
- **`gh` auth state on the host**: env-only token, on-disk `hosts.yml`, web-flow / passkey. If no auth at all, `tonka` warns once and proceeds — git operations inside the VM may fail until you run `gh auth login` on the host.
- **Token rotation**: a new host token is propagated to the guest on the next command. The host's token is read via `gh auth token` (which works whether the token lives in the macOS keychain or in `hosts.yml`) and reseeded on the guest via `gh auth login --with-token`.
- **Private dotfiles repos with submodules**: SSH-only submodule URLs (`git@github.com:…`) inside the dotfiles tree are transparently rewritten to HTTPS during the base build, so the gh credential helper can serve them.
- **User-scope plugins from SSH URLs**: `claude plugin install` inside the VM ssh-agent-forwards from the host, so plugins whose source URL is `git@github.com:…` clone successfully.

If something looks broken, `tonka auth-status` prints the host + guest auth state for diagnosis.

## Configuration

Config file: `~/.tonka.conf` (sourced as shell script)

Variables (can be set in config file or environment):
- `TONKA_BASE_IMAGE` - Tart image to use for base VM (default: `ghcr.io/cirruslabs/macos-tahoe-xcode:latest`)
- `TONKA_CPU` - Number of VM CPUs (default: host CPU count)
- `TONKA_MEMORY` - VM memory in MB (default: 5/8 of host memory)
- `TONKA_DISK_SIZE` - VM disk size in GB (e.g., `512`)
- `TONKA_DOTFILES_REPO` - Git URL of your dotfiles repo (should have `setup.sh` at root)
- `TONKA_TOOLS` - Space-separated list of tools to install: `rust`, `go`, `nodejs`, `python`
- `GITHUB_TOKEN` - Passed to VM for GitHub CLI authentication (auto-detected from `gh auth token` if not set)
