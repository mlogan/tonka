#!/bin/bash
# rust-setup.sh - Configure cargo in the VM to use a shared sccache.
# Idempotent; tonka runs it over ssh when the script changes.
#
# Environment variables:
#   TONKA_SCCACHE_SIZE - Cache size cap, e.g. 200G (defaults to 200G)

set -euo pipefail

SIZE="${TONKA_SCCACHE_SIZE:-200G}"
BREW=/opt/homebrew/bin/brew
SCCACHE=/opt/homebrew/bin/sccache
CACHE_DIR="$HOME/Library/Caches/Mozilla.sccache"
SCCACHE_CONFIG="$HOME/Library/Application Support/Mozilla.sccache/config"
CARGO_CONFIG="$HOME/.cargo/config.toml"
MARKER="# managed by tonka"

if [[ ! -x "$SCCACHE" ]]; then
    echo "Installing sccache..."
    "$BREW" install sccache
fi

size_bytes() {
    local n="${1%[KkMmGgTt]}" unit="${1: -1}"
    case "$unit" in
        K|k) echo $(( n * 1024 )) ;;
        M|m) echo $(( n * 1024 ** 2 )) ;;
        G|g) echo $(( n * 1024 ** 3 )) ;;
        T|t) echo $(( n * 1024 ** 4 )) ;;
        *) echo "$1" ;;
    esac
}

# A config file (rather than SCCACHE_* env vars) applies to every cargo
# invocation, including non-interactive shells that skip shell rc files.
mkdir -p "$(dirname "$SCCACHE_CONFIG")"
cat > "$SCCACHE_CONFIG" <<EOF
$MARKER
[cache.disk]
dir = "$CACHE_DIR"
size = $(size_bytes "$SIZE")
EOF

# build.incremental overrides profile settings in each project's Cargo.toml.
# sccache cannot cache incremental compilations, so it must be off.
mkdir -p "$(dirname "$CARGO_CONFIG")"
if [[ ! -f "$CARGO_CONFIG" ]] || head -1 "$CARGO_CONFIG" | grep -qF "$MARKER"; then
    cat > "$CARGO_CONFIG" <<EOF
$MARKER
[build]
rustc-wrapper = "$SCCACHE"
incremental = false
EOF
else
    echo "Warning: $CARGO_CONFIG is not managed by tonka; add these lines to its [build] section:" >&2
    echo "  rustc-wrapper = \"$SCCACHE\"" >&2
    echo "  incremental = false" >&2
fi

# The size cap is the primary bound: sccache evicts least-recently-used entries
# once the cache exceeds it. The daily job below handles low disk space.
mkdir -p "$HOME/.tonka"
GC_SCRIPT="$HOME/.tonka/sccache-gc.sh"
cat > "$GC_SCRIPT" <<EOF
#!/bin/bash
# Wipe the sccache cache when the data volume is at least 85% full.
used=\$(df -P /System/Volumes/Data | awk 'NR==2 {sub("%", "", \$5); print \$5}')
echo "\$(date): data volume \${used}% used"
if (( used >= 85 )); then
    echo "Clearing sccache cache"
    # Stop the server first so its size accounting does not go stale.
    "$SCCACHE" --stop-server >/dev/null 2>&1 || true
    rm -rf "$CACHE_DIR"
fi
EOF
chmod +x "$GC_SCRIPT"

GC_CRON="30 4 * * * $GC_SCRIPT >> $HOME/.tonka/sccache-gc.log 2>&1"
existing=$(crontab -l 2>/dev/null | grep -v "sccache-gc.sh" || true)
printf "%s\n%s\n" "$existing" "$GC_CRON" | grep -v "^$" | crontab -

# Restart the server so a running one picks up the new config.
"$SCCACHE" --stop-server >/dev/null 2>&1 || true
echo "sccache configured: $CACHE_DIR, cap $SIZE"
