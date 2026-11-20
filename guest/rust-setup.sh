#!/bin/bash
# rust-setup.sh - Configure cargo in the VM to use a shared kache store.
# Idempotent; tonka runs it over ssh when the script changes.
#
# Environment variables:
#   TONKA_KACHE_SIZE - Cache size cap, e.g. 200G (defaults to 200G)

set -euo pipefail

SIZE="${TONKA_KACHE_SIZE:-200G}"
BREW=/opt/homebrew/bin/brew
KACHE=/opt/homebrew/bin/kache
CACHE_DIR="$HOME/Library/Caches/kache"
KACHE_CONFIG="$HOME/.config/kache/config.toml"
CARGO_CONFIG="$HOME/.cargo/config.toml"
MARKER="# managed by tonka"

if [[ ! -x "$KACHE" ]]; then
    echo "Installing kache..."
    "$BREW" install kunobi-ninja/kunobi/kache
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

# A config file (rather than KACHE_* env vars) applies to every cargo
# invocation, including non-interactive shells that skip shell rc files.
mkdir -p "$(dirname "$KACHE_CONFIG")"
cat > "$KACHE_CONFIG" <<EOF
$MARKER
[cache]
local_store = "$CACHE_DIR"
local_max_size = $(size_bytes "$SIZE")
EOF

# kache handles incremental compilation itself, so build.incremental is left
# at cargo's default. `kache init` is not used because it also edits shell rc
# files and installs C/C++ compiler shims.
mkdir -p "$(dirname "$CARGO_CONFIG")"
if [[ ! -f "$CARGO_CONFIG" ]] || head -1 "$CARGO_CONFIG" | grep -qF "$MARKER"; then
    cat > "$CARGO_CONFIG" <<EOF
$MARKER
[build]
rustc-wrapper = "$KACHE"
EOF
else
    echo "Warning: $CARGO_CONFIG is not managed by tonka; add this line to its [build] section:" >&2
    echo "  rustc-wrapper = \"$KACHE\"" >&2
fi

# Remove the sccache setup that earlier versions of this script installed.
if [[ -x /opt/homebrew/bin/sccache ]]; then
    /opt/homebrew/bin/sccache --stop-server >/dev/null 2>&1 || true
fi
rm -rf "$HOME/Library/Caches/Mozilla.sccache" \
    "$HOME/Library/Application Support/Mozilla.sccache" \
    "$HOME/.tonka/sccache-gc.sh"

# The size cap is the primary bound: the kache daemon evicts entries once the
# store exceeds it. The daily job below handles low disk space.
mkdir -p "$HOME/.tonka"
GC_SCRIPT="$HOME/.tonka/kache-gc.sh"
cat > "$GC_SCRIPT" <<EOF
#!/bin/bash
# Empty the kache store when the data volume is at least 85% full.
used=\$(df -P /System/Volumes/Data | awk 'NR==2 {sub("%", "", \$5); print \$5}')
echo "\$(date): data volume \${used}% used"
if (( used >= 85 )); then
    echo "Clearing kache store"
    "$KACHE" clean --cache --yes
fi
EOF
chmod +x "$GC_SCRIPT"

GC_CRON="30 4 * * * $GC_SCRIPT >> $HOME/.tonka/kache-gc.log 2>&1"
existing=$(crontab -l 2>/dev/null | grep -v -e "sccache-gc.sh" -e "kache-gc.sh" || true)
printf "%s\n%s\n" "$existing" "$GC_CRON" | grep -v "^$" | crontab -

# Stop the daemon so the next compile starts one with the new config.
"$KACHE" daemon stop >/dev/null 2>&1 || true
echo "kache configured: $CACHE_DIR, cap $SIZE"
