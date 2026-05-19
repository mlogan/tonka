#!/bin/bash
# install.sh - Base VM setup script
# Run on the base VM to install all required tools and configure the user
#
# Environment variables:
#   TONKA_USER - Username to create (defaults to tonka)
#   TONKA_DOTFILES_REPO - Git URL of dotfiles repo (must have setup.sh at root)
#   GITHUB_TOKEN - GitHub token for git authentication
#   TONKA_TOOLS - Space-separated list of tools to install (rust, go, nodejs, python)
#   BREW_FORMULAE - Space-separated list of brew formulae from host
#   BREW_CASKS - Space-separated list of brew casks from host

set -euo pipefail

TUSER="${TONKA_USER:-tonka}"
DOTFILES_REPO="${TONKA_DOTFILES_REPO:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
TONKA_TOOLS="${TONKA_TOOLS:-}"
BREW_FORMULAE="${BREW_FORMULAE:-}"
BREW_CASKS="${BREW_CASKS:-}"

echo "=== Tonka Base VM Setup ==="

# Create user (idempotent — skip if a user with this name already exists on
# the base image)
if id -u "$TUSER" &>/dev/null; then
    echo "User $TUSER already exists, skipping creation"
else
    echo "Creating user $TUSER..."
    sudo sysadminctl -addUser "$TUSER" -fullName "Tonka User" -password tonka -admin
fi

# Set up SSH directory for user
echo "Configuring SSH access..."
sudo mkdir -p /Users/$TUSER/.ssh
sudo chmod 700 /Users/$TUSER/.ssh

# Copy SSH keys
if [[ -f /tmp/tonka.pub ]]; then
    sudo cp /tmp/tonka.pub /Users/$TUSER/.ssh/authorized_keys
    sudo chmod 600 /Users/$TUSER/.ssh/authorized_keys
fi
if [[ -f /tmp/tonka_key ]]; then
    sudo cp /tmp/tonka_key /Users/$TUSER/.ssh/id_ed25519
    sudo cp /tmp/tonka.pub /Users/$TUSER/.ssh/id_ed25519.pub
    sudo chmod 600 /Users/$TUSER/.ssh/id_ed25519
    sudo chmod 644 /Users/$TUSER/.ssh/id_ed25519.pub
fi
sudo chown -R "$TUSER:staff" /Users/$TUSER/.ssh

# Add github.com to known_hosts
sudo -u "$TUSER" -H bash -c 'ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null'

# Enable passwordless sudo for user
echo "Enabling passwordless sudo for $TUSER..."
echo "$TUSER ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/tonka

# Install Homebrew as tonka user
echo "Installing Homebrew..."
sudo -u "$TUSER" -H /bin/bash -c 'NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'

# Add brew to path for subsequent commands
export PATH="/opt/homebrew/bin:$PATH"

# Install essential tools via brew
echo "Installing essential tools..."
sudo -u "$TUSER" -H /opt/homebrew/bin/brew install git gh jq

# Install host brew formulae
if [[ -n "$BREW_FORMULAE" ]]; then
    echo "Installing host brew formulae..."
    # shellcheck disable=SC2086
    sudo -u "$TUSER" -H /opt/homebrew/bin/brew install $BREW_FORMULAE || true
fi

# Install host brew casks
if [[ -n "$BREW_CASKS" ]]; then
    echo "Installing host brew casks..."
    # shellcheck disable=SC2086
    sudo -u "$TUSER" -H /opt/homebrew/bin/brew install --cask $BREW_CASKS || true
fi

# Install TONKA_TOOLS
for tool in $TONKA_TOOLS; do
    case "$tool" in
        rust)
            echo "Installing Rust..."
            sudo -u "$TUSER" -H bash -c 'curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y'
            ;;
        go)
            echo "Installing Go..."
            sudo -u "$TUSER" -H /opt/homebrew/bin/brew install go
            ;;
        nodejs|node)
            echo "Installing Node.js..."
            sudo -u "$TUSER" -H /opt/homebrew/bin/brew install node
            ;;
        python)
            echo "Installing Python..."
            sudo -u "$TUSER" -H /opt/homebrew/bin/brew install python
            ;;
        *)
            echo "Unknown tool: $tool"
            ;;
    esac
done

# Install Claude CLI
echo "Installing Claude CLI..."
sudo -u "$TUSER" -H bash -c 'curl -fsSL https://claude.ai/install.sh | bash'

# Copy Claude settings if provided
if [[ -f /tmp/claude_settings.json ]]; then
    echo "Configuring Claude settings..."
    sudo mkdir -p /Users/$TUSER/.claude
    sudo cp /tmp/claude_settings.json /Users/$TUSER/.claude/settings.json
    sudo chown -R "$TUSER:staff" /Users/$TUSER/.claude
fi
if [[ -d /tmp/claude_skills ]]; then
    echo "Configuring Claude skills..."
    sudo mkdir -p /Users/$TUSER/.claude
    sudo cp -r /tmp/claude_skills /Users/$TUSER/.claude/skills
    sudo chown -R "$TUSER:staff" /Users/$TUSER/.claude
fi

# Enable Remote Login (SSH)
echo "Enabling SSH..."
sudo systemsetup -setremotelogin on

# Pin git's credential helper to gh at the system level (/etc/gitconfig).
# Putting it system-wide means it survives the dotfiles symlinking the
# user's ~/.gitconfig: credential.helper is multi-valued, so git tries
# the user-level entry (if any) AND the system-level one. Most dotfiles
# .gitconfigs don't define credential.helper at all, in which case the
# system-level setting is the only one in effect — exactly what we want.
echo "Configuring git credential helper..."
sudo git config --system --unset-all credential.helper 2>/dev/null || true
sudo git config --system --add credential.helper "/opt/homebrew/bin/gh auth git-credential"

# Install the in-guest `tonka-add` helper + `add` shell function so users
# can pull in additional repos / scratch folders from inside a `tonka sh`
# session without leaving the VM. The companion host-side
# `ensure_guest_helpers` in `tonka` keeps these in sync on every command
# so already-built VMs gain the feature without `tonka rebuild-base`.
if [[ -f /tmp/tonka-add ]]; then
    echo "Installing tonka-add helper..."
    sudo install -m 0755 -o root -g wheel /tmp/tonka-add /usr/local/bin/tonka-add
fi
if [[ -f /tmp/tonka.zsh ]]; then
    echo "Installing tonka.zsh shell function..."
    sudo mkdir -p /usr/local/etc
    sudo install -m 0644 -o root -g wheel /tmp/tonka.zsh /usr/local/etc/tonka.zsh
    # Source it from /etc/zshrc behind a marker so updates are idempotent
    # and we never duplicate the sourcing line on re-runs of install.sh.
    if ! sudo grep -q 'TONKA-SHELL-HOOK' /etc/zshrc 2>/dev/null; then
        echo "Wiring tonka.zsh into /etc/zshrc..."
        sudo tee -a /etc/zshrc >/dev/null <<'EOF'

# TONKA-SHELL-HOOK (managed by tonka — do not edit this block)
[ -r /usr/local/etc/tonka.zsh ] && . /usr/local/etc/tonka.zsh
# END-TONKA-SHELL-HOOK
EOF
    fi
fi

# If the host forwarded a token, also seed the guest's gh auth state so the
# dotfiles clone in this same script can authenticate immediately. Pipe the
# token via stdin so it is never interpolated into a shell string — same
# quote-safe pattern used for the Keychain credential write on the host.
if [[ -n "$GITHUB_TOKEN" ]]; then
    echo "Seeding GitHub CLI authentication with host token..."
    printf '%s\n' "$GITHUB_TOKEN" | sudo -u "$TUSER" -H /opt/homebrew/bin/gh auth login --with-token
else
    echo "No GITHUB_TOKEN forwarded — guest gh auth will be populated on first sync_claude_settings via hosts.yml. Dotfiles clone may fail if dotfiles repo is private."
fi

# Helper to convert SSH URLs to HTTPS so the gh credential helper can serve
# them. Handles: git@host:path, ssh://[user@]host[:port]/path. Already-HTTPS
# URLs pass through unchanged. SSH host aliases from the host's ~/.ssh/config
# (e.g. github.com-work) are rewritten verbatim — they won't resolve inside
# the VM, but the resulting "could not resolve hostname" error is more
# diagnostic than letting git attempt the SSH protocol with a missing key.
ssh_to_https() {
    local url="$1"
    # ssh://[user@]host[:port]/path   →   https://host/path
    if [[ "$url" =~ ^ssh://(([^@]+)@)?([^:/]+)(:[0-9]+)?/(.+)$ ]]; then
        echo "https://${BASH_REMATCH[3]}/${BASH_REMATCH[5]}"
        return
    fi
    # git@host:path                   →   https://host/path
    if [[ "$url" =~ ^git@([^:]+):(.+)$ ]]; then
        echo "https://${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
        return
    fi
    # Already HTTPS or any other shape — pass through.
    echo "$url"
}

# Clone and run dotfiles if specified. Failures here are warned about but
# do NOT abort the base build — a private dotfiles repo combined with a
# token-less host (web-flow / passkey-only gh auth) would otherwise kill
# the install before Phase D ever runs. The user can re-run setup.sh
# later with: tonka sh && cd ~/.dotfiles && ./setup.sh
#
# Both git invocations inherit GIT_CONFIG_* env vars that transparently
# rewrite git@github.com:… URLs to https://github.com/… via git's
# `url.<base>.insteadOf` mechanism. This is needed because the user's
# dotfiles repo commonly has SSH-based submodules whose URLs we can't see
# in advance (they're inside .gitmodules), and the VM only has the
# tonka-specific SSH key (not the host SSH key authorized at GitHub) —
# so SSH clones would fail with "Permission denied (publickey)". Routing
# through HTTPS uses the gh credential helper that was just configured
# above, which works for any repo the host's token has access to.
# The env-var approach (GIT_CONFIG_COUNT) is scoped to these two git
# invocations only — it does NOT pollute ~/.gitconfig, so work repos
# cloned later via `tonka new-repo` keep their original SSH URLs.
if [[ -n "$DOTFILES_REPO" ]]; then
    DOTFILES_URL=$(ssh_to_https "$DOTFILES_REPO")
    echo "Setting up dotfiles from: $DOTFILES_URL"
    if sudo -u "$TUSER" -H /bin/bash -c '
        export GIT_CONFIG_COUNT=1
        export GIT_CONFIG_KEY_0="url.https://github.com/.insteadOf"
        export GIT_CONFIG_VALUE_0="git@github.com:"
        git clone "$1" "$2"
    ' bash "$DOTFILES_URL" "/Users/$TUSER/.dotfiles"; then
        if [[ -f /Users/$TUSER/.dotfiles/setup.sh ]]; then
            echo "Running dotfiles setup.sh..."
            if ! sudo -u "$TUSER" -H /bin/bash -c '
                export GIT_CONFIG_COUNT=1
                export GIT_CONFIG_KEY_0="url.https://github.com/.insteadOf"
                export GIT_CONFIG_VALUE_0="git@github.com:"
                cd ~/.dotfiles && ./setup.sh
            '; then
                echo "Warning: dotfiles setup.sh failed. Re-run with: tonka sh && cd ~/.dotfiles && ./setup.sh"
            fi
        else
            echo "Warning: No setup.sh found in dotfiles repo"
        fi
    else
        echo "Warning: dotfiles clone failed (auth not yet established?)."
        echo "After base build, run 'gh auth login' on host, then 'tonka sh' and clone manually:"
        echo "  git clone $DOTFILES_URL ~/.dotfiles && cd ~/.dotfiles && ./setup.sh"
    fi
else
    echo "No TONKA_DOTFILES_REPO set, skipping dotfiles setup"
fi

# Clean up
echo "Cleaning up..."
rm -f /tmp/tonka.pub /tmp/tonka_key /tmp/install.sh /tmp/tonka-add /tmp/tonka.zsh

echo "=== Base VM setup complete ==="
