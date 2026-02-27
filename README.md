# Tonka

Ephemeral tart-based sandboxes for running Claude Code with `--dangerously-skip-permissions`.

Unlike shared-directory approaches, Tonka clones the git repo *inside* the VM for complete isolation. SSH agent forwarding allows git operations from within the VM.

## Prerequisites

- [Tart](https://tart.run/) - macOS VM manager
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

Your dotfiles repo must have a `setup.sh` script at the root that installs Claude Code and any other tools you need.

## Usage

```bash
# Create new project sandbox from a local git repo
tonka new ~/dev/myproject

# Create with explicit name
tonka new ~/dev/myproject myproject-feature

# Start/stop/delete
tonka start myproject
tonka stop myproject
tonka delete myproject

# Connect
tonka shell myproject     # SSH into VM
tonka claude myproject    # Run Claude in project directory

# List projects
tonka list

# Rebuild base VM (after dotfiles changes)
tonka rebuild-base
```

## How It Works

1. **Base VM**: Created once from `ghcr.io/cirruslabs/macos-sequoia-vanilla`, with your dotfiles installed
2. **Project VMs**: Cloned from base VM, with the git repo cloned from a temporary host mount
3. **SSH Agent Forwarding**: `-A` flag passes your SSH agent for git authentication
4. **GitHub Token**: Pass `GITHUB_TOKEN` env var for GitHub CLI authentication

## Configuration

Config file: `~/.tonka.conf` (sourced as shell script)

Variables (can be set in config file or environment):
- `TONKA_DOTFILES_REPO` - Git URL of your dotfiles repo (must have `setup.sh` at root)
- `GITHUB_TOKEN` - Passed to VM for GitHub CLI authentication (auto-detected from `gh auth token` if not set)
