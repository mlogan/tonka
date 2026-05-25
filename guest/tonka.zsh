# tonka.zsh — sourced by /etc/zshrc so users get an `add` shell function.
#
# A function (not an alias) is required: `tonka-add` is a child script and
# cannot `cd` its parent shell. The function passes a TONKA_ADD_CD_FILE
# path; if `tonka-add` writes a directory into it on success, the function
# cd's the caller there. stdout and stderr pass through unmodified so git
# clone/push progress is visible live.
#
# If a user's dotfiles redefine `add`, theirs wins (loaded after /etc/zshrc).
# In that case `tonka-add` remains directly callable, just without auto-cd.

add() {
    # Absolute path: /usr/local/bin is not always in PATH for non-login zsh
    # invocations (path_helper runs from /etc/zprofile, not /etc/zshrc).
    local _tonka_bin=/usr/local/bin/tonka-add
    if [[ ! -x "$_tonka_bin" ]]; then
        echo "add: $_tonka_bin not installed. Run 'tonka start' on the host." >&2
        return 127
    fi
    local _tonka_cd_file _tonka_rc _tonka_target
    _tonka_cd_file=$(mktemp -t tonka-add.XXXXXX)
    TONKA_ADD_CD_FILE="$_tonka_cd_file" "$_tonka_bin" "$@"
    _tonka_rc=$?
    _tonka_target=$(cat "$_tonka_cd_file" 2>/dev/null)
    rm -f "$_tonka_cd_file"
    if [[ $_tonka_rc -eq 0 && -n "$_tonka_target" && -d "$_tonka_target" ]]; then
        cd "$_tonka_target"
    fi
    return $_tonka_rc
}
