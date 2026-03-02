# Tonka for Dummies

A beginner's guide to running Claude Code in an ephemeral macOS sandbox.

---

## 1. What Is Tonka?

Tonka creates ephemeral macOS virtual machines using [Tart](https://tart.run/) so you can run Claude Code with `--dangerously-skip-permissions` without any risk to your host machine. Code lives entirely inside the VM — nothing can escape.

**The mental model:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ tonka-base (template)                                               │
│   Your dotfiles, tools, Homebrew packages, and Claude CLI           │
│   Built once. Never touched directly.                               │
│                                                                     │
│   ┌───────────────────────────────────────────────────────────────┐ │
│   │ tonka-vm (your workspace)                                     │ │
│   │   Cloned from tonka-base. Contains your repos and projects.   │ │
│   │                                                               │ │
│   │   ~/repos/myproject          ← bare repo clone                │ │
│   │   ~/projects/my-feature      ← git worktree (you work here)   │ │
│   │   ~/projects/fix-bug         ← another worktree               │ │
│   └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

`tonka-base` is a template VM built once with all your tools baked in. `tonka-vm` is cloned from the base and is where your actual work happens. Projects are git worktrees — lightweight, disposable branches that Claude operates on independently.

---

## 2. Prerequisites

You need:

- **macOS with Apple Silicon** — Tart only runs on M-series Macs
- **Tart** — the VM manager:
  ```bash
  brew install cirruslabs/cli/tart
  ```
- **sshpass** — needed during base VM setup for initial SSH with default credentials:
  ```bash
  brew install hudochenkov/sshpass/sshpass
  ```
- **GitHub CLI** — authenticated on your host machine:
  ```bash
  brew install gh
  gh auth login
  ```
- **(Optional) A dotfiles repo on GitHub** — with a `setup.sh` at the root

---

## 3. Configuration

Create a configuration file at `~/.tonka.conf`:

```bash
# Required if you want dotfiles installed in the VM
# Both SSH and HTTPS URLs work — SSH URLs are auto-converted to HTTPS for cloning
TONKA_DOTFILES_REPO="git@github.com:yourusername/dotfiles.git"

# Optional: language toolchains to install inside the VM
# Choices: rust, go, nodejs, python (space-separated)
TONKA_TOOLS="nodejs rust"
```

### All Configuration Variables

| Variable | Default | Description |
|---|---|---|
| `TONKA_BASE_IMAGE` | `ghcr.io/cirruslabs/macos-tahoe-xcode:latest` | Tart image to clone for the base VM |
| `TONKA_DOTFILES_REPO` | *(none)* | Git URL of your dotfiles repo (should have `setup.sh` at root) |
| `TONKA_TOOLS` | *(none)* | Space-separated list: `rust`, `go`, `nodejs`, `python` |
| `GITHUB_TOKEN` | *(auto-detected from `gh auth token`)* | GitHub token for authentication inside the VM |

You can also set these as environment variables instead of putting them in `~/.tonka.conf`. The config file is simply sourced as a shell script.

---

## 4. Getting Tonka on Your PATH

Clone the repo and make `tonka` accessible. Pick one approach:

**Option A — Symlink (recommended):**
```bash
git clone https://github.com/yourusername/tonka.git ~/tonka
ln -s ~/tonka/tonka /usr/local/bin/tonka
```

**Option B — Add to PATH:**
```bash
git clone https://github.com/yourusername/tonka.git ~/tonka
echo 'export PATH="$HOME/tonka:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Verify it works:
```bash
tonka --help
```

---

## 5. Building Your First Base VM

```bash
tonka rebuild-base
```

This takes a while (downloading a macOS image, installing Homebrew, etc.). Here's what happens behind the scenes:

1. **Downloads a macOS image** from the configured `TONKA_BASE_IMAGE` (a macOS Tahoe + Xcode image by default)
2. **Creates a user** matching your host username (so file paths feel familiar)
3. **Installs Homebrew** and every formula/cask you have installed on your host Mac
4. **Installs language toolchains** from `TONKA_TOOLS` (if configured)
5. **Installs the Claude CLI** (`~/.local/bin/claude`)
6. **Copies your Claude settings** (settings.json, skills) into the VM
7. **Configures GitHub auth** using your `gh` token so `git clone/push` work inside the VM
8. **Clones your dotfiles** to `~/.dotfiles` and runs `setup.sh` (if `TONKA_DOTFILES_REPO` is set) — SSH URLs are automatically converted to HTTPS so cloning uses the `gh` credential helper instead of SSH keys
9. **Shuts down** — the base VM is now a frozen template

You only need to run `rebuild-base` once, or when you change your config.

---

## 6. Adding a Repo

To work on a project, first add its repo to the VM:

```bash
tonka new-repo ~/dev/myproject
```

What this does:
- Reads the `origin` remote URL from your local repo
- Converts SSH remotes (`git@github.com:...`) to HTTPS (needed for the `gh` credential helper)
- Clones the repo into `~/repos/myproject` inside the VM

> **Note:** This clones the remote, not your local copy. Any unpushed local changes won't be in the VM. Push first!

You can add multiple repos:
```bash
tonka new-repo ~/dev/project-alpha
tonka new-repo ~/dev/project-beta
```

---

## 7. Creating a Project & Launching Claude

Now create a project (a git worktree) and launch Claude:

```bash
tonka new my-feature myproject
```

This:
1. Ensures the VM is running (starts it if needed)
2. Syncs your latest Claude settings, skills, plugins, and credentials to the VM
3. Creates a git worktree at `~/projects/my-feature` (branched from `myproject`)
4. SSHs into the VM and launches `claude --dangerously-skip-permissions`

Claude runs in full autonomous mode. When Claude exits, you stay in the VM shell — explore, run tests, inspect files. Press **Ctrl-D** to leave the VM.

If the repo name is omitted and you only have one repo, Tonka picks it automatically:
```bash
tonka new my-feature
```

---

## 8. Day-to-Day Commands

| Command | Description |
|---|---|
| `tonka` | Launch Claude in a project (prompts to select if multiple) |
| `tonka cl <project>` | Launch Claude in a specific project |
| `tonka sh [project]` | SSH into the VM (optionally into a project directory) |
| `tonka new <project> [repo]` | Create a new worktree + launch Claude |
| `tonka new-repo <path>` | Clone a local repo's remote into the VM |
| `tonka list` | List all repos and projects in the VM |
| `tonka cleanup` | Prune merged worktrees |
| `tonka start` | Start the VM (if stopped) |
| `tonka stop` | Stop the VM |
| `tonka rebuild-base` | Rebuild the base VM from scratch |

### Typical workflow

```bash
# One-time setup
tonka rebuild-base
tonka new-repo ~/dev/myproject

# Daily work
tonka new fix-login-bug myproject   # new worktree + Claude
# ... Claude does its thing ...
# Ctrl-D to leave

tonka cl fix-login-bug              # re-enter the same project later
tonka                               # or just pick from a list

# Housekeeping
tonka cleanup                       # remove merged worktrees
tonka stop                          # stop the VM when done for the day
```

---

## 9. Writing a `setup.sh` for Your Dotfiles

If you set `TONKA_DOTFILES_REPO`, Tonka clones it to `~/.dotfiles` inside the VM and runs `setup.sh`. This section explains how to write one that works with Tonka.

### Execution Context

When `setup.sh` runs:
- **Shell**: `/bin/bash` (macOS bash 3.2 — **not** zsh, not bash 5)
- **User**: Your user (not root — but `sudo` is available with NOPASSWD)
- **Working directory**: `~/.dotfiles` (the root of your cloned dotfiles repo)
- **What's already installed**: Homebrew, `git`, `gh`, your host brew packages, Claude CLI, and any `TONKA_TOOLS`
- **What's NOT available**: GUI apps aren't usable (VM runs headless with `--no-graphics`)

### Generalized Template

```bash
#!/bin/bash
# setup.sh — Dotfiles setup script for Tonka VMs (and anywhere else)
# Runs under bash 3.2 on macOS. No bashisms beyond 3.2!

set -euo pipefail

DOTFILES_DIR="$HOME/.dotfiles"

# ─── Helper: back up existing file/symlink, then create symlink ───
backup_and_link() {
    local source="$1"
    local target="$2"

    # If target already points to the right place, skip
    if [ -L "$target" ] && [ "$(readlink "$target")" = "$source" ]; then
        return
    fi

    # Back up existing file (not symlinks)
    if [ -e "$target" ] && [ ! -L "$target" ]; then
        echo "  Backing up $target → ${target}.bak"
        mv "$target" "${target}.bak"
    fi

    # Remove stale symlink
    if [ -L "$target" ]; then
        rm "$target"
    fi

    echo "  Linking $source → $target"
    ln -s "$source" "$target"
}

# ─── Create directories ───
echo "Creating directories..."
mkdir -p "$HOME/.config"
# Add any other directories your dotfiles expect:
# mkdir -p "$HOME/.config/nvim"
# mkdir -p "$HOME/.config/starship"

# ─── Symlink dotfiles ───
echo "Linking dotfiles..."

# Shell
backup_and_link "$DOTFILES_DIR/zshrc"     "$HOME/.zshrc"
backup_and_link "$DOTFILES_DIR/zprofile"  "$HOME/.zprofile"

# Git
backup_and_link "$DOTFILES_DIR/gitconfig" "$HOME/.gitconfig"
backup_and_link "$DOTFILES_DIR/gitignore" "$HOME/.gitignore_global"

# Editor (uncomment what you use)
# backup_and_link "$DOTFILES_DIR/vimrc"             "$HOME/.vimrc"
# backup_and_link "$DOTFILES_DIR/config/nvim"       "$HOME/.config/nvim"

# Add your own files here:
# backup_and_link "$DOTFILES_DIR/tmux.conf"  "$HOME/.tmux.conf"
# backup_and_link "$DOTFILES_DIR/starship.toml" "$HOME/.config/starship.toml"

echo "Done!"
```

### Key Rules

**DO:**
- Use `[ ... ]` instead of `[[ ... ]]` if you want maximum portability (though `[[ ]]` works in bash 3.2)
- Make the script **idempotent** — running it twice should produce the same result. This matters because `rebuild-base` runs it every time.
- Use the `backup_and_link` pattern to avoid overwriting files that already exist.
- Keep it fast — this runs during `rebuild-base`, which is already slow.

**DON'T:**
- **Don't install packages** — Homebrew and your host packages are already installed by Tonka before `setup.sh` runs.
- **Don't use `sudo`** — it's available but you shouldn't need it. Dotfiles are user-level.
- **Don't change the login shell** — the VM uses whatever macOS defaults to. Configure your shell via dotfiles instead (e.g., source zsh config from bash if needed).
- **Don't use bash 4+ features** — no associative arrays (`declare -A`), no `${var,,}` lowercasing, no `mapfile`/`readarray`. macOS ships bash 3.2.

### Why Idempotency Matters

Every time you run `tonka rebuild-base`, Tonka:
1. Deletes the old base VM
2. Creates a fresh one from the macOS image
3. Runs your `setup.sh` again from scratch

If your script isn't idempotent, things break on re-runs. The `backup_and_link` helper above handles this correctly — it checks if the symlink already points to the right place before doing anything.

---

## 10. Rebuilding & Troubleshooting

### When to Rebuild

Run `tonka rebuild-base` when you:
- Change `~/.tonka.conf` (new tools, different base image, etc.)
- Update your dotfiles and want a fresh base with the latest version
- Install or remove brew packages on your host (they mirror into the VM)
- Something is broken and you want a clean slate

### What Rebuilding Destroys

| What | Destroyed? |
|---|---|
| `tonka-base` | Always (rebuilt from scratch) |
| `tonka-vm` | Only if you say "yes" at the prompt |
| Repos in `~/repos/` | Only if tonka-vm is rebuilt |
| Projects in `~/projects/` | Only if tonka-vm is rebuilt |
| Code pushed to GitHub | Never — it's on the remote |

**Always push your work before rebuilding** if there's any chance you'll rebuild `tonka-vm`.

### Common Issues

**SSH timeout during `rebuild-base`**
The VM takes ~30 seconds to boot. If SSH can't connect after 60 seconds, the build fails. This usually means the Tart image is very slow to boot or the VM didn't start properly. Try:
```bash
tart delete tonka-base
tonka rebuild-base
```

**Brew install failures**
Some host packages can't be installed in the VM (architecture differences, macOS version mismatches, etc.). Tonka uses `|| true` so these failures don't stop the build, but you'll see warnings. The important tools (`git`, `gh`) are installed separately and won't be affected.

**"No repos found"**
You need to add a repo before creating a project:
```bash
tonka new-repo ~/dev/myproject
```

**Claude won't start / credentials missing**
Tonka syncs credentials from your host every time you run `tonka new` or `tonka cl`. Make sure your host has valid credentials:
```bash
# On your host:
gh auth status          # GitHub CLI should be authenticated
claude --version        # Claude CLI should be installed
```

**VM IP changes after restart**
This is normal. Tonka looks up the IP dynamically with `tart ip`. You don't need to track it manually.

**Dotfiles `setup.sh` failed**
SSH into the VM and debug:
```bash
tonka sh
cd ~/.dotfiles
bash -x setup.sh       # run with debug tracing
```
