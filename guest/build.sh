#!/bin/bash
# Runs a headless Claude session for `tonka build` inside the VM.
# Usage: build.sh <project>
# Expects the prompt at /tmp/tonka-build/<project>.prompt; writes the raw
# stream-json log to /tmp/tonka-build/<project>.log.
set -o pipefail

project="${1:?usage: build.sh <project>}"
dir="$HOME/projects/$project"
export TONKA_BUILD_PROMPT_FILE="/tmp/tonka-build/$project.prompt"
log="/tmp/tonka-build/$project.log"

[[ -f "$TONKA_BUILD_PROMPT_FILE" ]] || { echo "build.sh: missing prompt file $TONKA_BUILD_PROMPT_FILE" >&2; exit 1; }
cd "$dir" || exit 1

# The interactive login shell is what puts ~/.local/bin and toolchains on PATH
# (see claude_remote_cmd in tonka). stdin is /dev/null so `claude -p` doesn't
# try to read a prompt from it.
"$SHELL" -i -l -c 'if [ -f ~/.claude.env ]; then set -a; . ~/.claude.env; set +a; fi
    exec ~/.local/bin/claude -p --dangerously-skip-permissions --verbose --output-format stream-json "$(cat "$TONKA_BUILD_PROMPT_FILE")"' \
    </dev/null \
    | tee "$log" \
    | jq -r --unbuffered '
        if .type == "assistant" then
            .message.content[]?
            | if .type == "text" then .text
              elif .type == "tool_use" then
                  "▶ \(.name): \((.input.command // .input.file_path // .input.skill // .input.description // .input.prompt // .input.pattern // "") | tostring | gsub("\n"; " ") | .[0:160])"
              else empty end
        elif .type == "user" then
            .message.content[]?
            | select(.type == "tool_result" and .is_error == true)
            | "✗ tool error: \((.content | if type == "string" then . else map(.text // "") | join("") end) | gsub("\n"; " ") | .[0:200])"
        elif .type == "result" then
            "── claude finished: \(.subtype), \(.num_turns // "?") turns, $\((.total_cost_usd // 0) * 100 | round / 100)"
        else empty end'
