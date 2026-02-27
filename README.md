# Tonka

*Making sandboxes fun*

![Tonka Truck](tonka.webp)

Ephemeral tart-based sandboxes for running Claude Code with `--dangerously-skip-permissions`.

## Features

- **No shared volumes** - Code lives entirely inside the VM for complete isolation
- **Automatic sync** of Claude settings, credentials, and plugins
- **GitHub credentials** synced via `gh` CLI
- **Dotfiles support** - Installs your dotfiles repo automatically
- **Configurable tools** - Install Rust, Go, Node.js, Python, and your brew packages

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

# Rebuild base VM (after config changes)
tonka rebuild-base
```

## How It Works

1. **Base VM**: Created once with your dotfiles, tools, and Claude CLI installed
2. **Tonka VM**: Cloned from base, contains your repos and project worktrees
3. **Git Auth**: Uses `gh` CLI credential helper (synced from host)

## Configuration

Config file: `~/.tonka.conf` (sourced as shell script)

Variables (can be set in config file or environment):
- `TONKA_BASE_IMAGE` - Tart image to use for base VM (default: `ghcr.io/cirruslabs/macos-tahoe-xcode:latest`)
- `TONKA_DOTFILES_REPO` - Git URL of your dotfiles repo (should have `setup.sh` at root)
- `TONKA_TOOLS` - Space-separated list of tools to install: `rust`, `go`, `nodejs`, `python`
- `GITHUB_TOKEN` - Passed to VM for GitHub CLI authentication (auto-detected from `gh auth token` if not set)
