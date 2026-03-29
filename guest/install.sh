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

# Create user
echo "Creating user $TUSER..."
sudo sysadminctl -addUser "$TUSER" -fullName "Tonka User" -password tonka -admin

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

# Configure GitHub CLI and git credential helper (needed for dotfiles and work repos)
if [[ -n "$GITHUB_TOKEN" ]]; then
    echo "Configuring GitHub CLI authentication..."
    sudo -u "$TUSER" -H /bin/bash -c "echo '$GITHUB_TOKEN' | /opt/homebrew/bin/gh auth login --with-token"
    # Explicitly set credential helper (clear macOS osxkeychain default)
    sudo -u "$TUSER" -H git config --global --unset-all credential.helper 2>/dev/null || true
    sudo -u "$TUSER" -H git config --global credential.helper ""
    sudo -u "$TUSER" -H git config --global --add credential.helper "/opt/homebrew/bin/gh auth git-credential"
fi

# Helper to convert SSH URLs to HTTPS
ssh_to_https() {
    local url="$1"
    if [[ "$url" =~ ^git@([^:]+):(.+)$ ]]; then
        echo "https://${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
    else
        echo "$url"
    fi
}

# Clone and run dotfiles if specified
if [[ -n "$DOTFILES_REPO" ]]; then
    DOTFILES_URL=$(ssh_to_https "$DOTFILES_REPO")
    echo "Setting up dotfiles from: $DOTFILES_URL"
    sudo -u "$TUSER" -H git clone "$DOTFILES_URL" /Users/$TUSER/.dotfiles
    if [[ -f /Users/$TUSER/.dotfiles/setup.sh ]]; then
        echo "Running dotfiles setup.sh..."
        sudo -u "$TUSER" -H /bin/bash -c 'cd ~/.dotfiles && ./setup.sh'
    else
        echo "Warning: No setup.sh found in dotfiles repo"
    fi
else
    echo "No TONKA_DOTFILES_REPO set, skipping dotfiles setup"
fi

# Clean up
echo "Cleaning up..."
rm -f /tmp/tonka.pub /tmp/tonka_key /tmp/install.sh

echo "=== Base VM setup complete ==="
