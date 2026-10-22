#!/usr/bin/env python3
"""Kanban board for the projects in ~/projects.

Runs in the "board" window of the kanban tmux session inside the tonka VM.
Each project's Claude runs in its own window of the same session.
"""

import curses
import json
import locale
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

HOME = os.path.expanduser("~")
PROJECTS = os.path.join(HOME, "projects")
REPOS = os.path.join(HOME, "repos")
KANBAN_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(KANBAN_DIR, "prompts")
PR_CACHE = os.path.join(KANBAN_DIR, "pr-cache.json")
STATUS_FILE = os.path.join(".tonka", "status.md")
STATE_FILE = os.path.join(".tonka", "agent-state")
BOARD_WINDOW = "board"
MODEL = os.environ.get("TONKA_KANBAN_MODEL", "sonnet")
PR_POLL_SECONDS = 180  # one gh call per project per poll; keep well under the API rate limit
SCAN_SECONDS = 1.0
PROCESS_SCAN_SECONDS = 5.0
# A mid-turn transcript that has not changed for this long is probably blocked on the user.
STALE_TURN_SECONDS = 30 * 60

NEEDS_INPUT, WORKING, REVIEW, IDLE = range(4)
COLUMNS = ["Needs input", "Working", "In review", "Idle"]
MESSAGE_LINES = 6

CHECK_RE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.*)$")
HEADER_RE = re.compile(r"^([A-Za-z][\w-]*):\s*(.*)$")


def run(cmd, cwd=None, timeout=60):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def tool(name):
    for path in (shutil.which(name), f"/opt/homebrew/bin/{name}", os.path.join(HOME, ".local/bin", name)):
        if path and os.access(path, os.X_OK):
            return path
    return name


GH = tool("gh")
CLAUDE = tool("claude")
TMUX = tool("tmux")


def tmux(*args):
    return run([TMUX, *args], timeout=10)


def read_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def parse_status(text):
    """Parses .tonka/status.md into (status, pr urls, checklist, message)."""
    status, prs, checklist, message = "", [], [], []
    in_header = True
    for line in text.splitlines():
        stripped = line.strip()
        m = CHECK_RE.match(line)
        if m:
            in_header = False
            checklist.append((m.group(1) != " ", m.group(2).strip()))
            continue
        if in_header:
            h = HEADER_RE.match(stripped)
            if h and h.group(1).lower() in ("status", "pr"):
                if h.group(1).lower() == "status":
                    status = h.group(2).strip().lower()
                elif h.group(2).strip():
                    prs.append(h.group(2).strip())
                continue
            if not stripped:
                continue
            in_header = False
        stripped = stripped.lstrip("#>").strip()
        if stripped:
            message.append(stripped)
    return status, prs, checklist, " ".join(message)


def git_dirs(worktree):
    """Returns (gitdir, common dir) for a worktree, or None if it is not a git checkout."""
    dotgit = os.path.join(worktree, ".git")
    if os.path.isdir(dotgit):
        return dotgit, dotgit
    text = read_file(dotgit)
    if not text or not text.startswith("gitdir:"):
        return None
    gitdir = os.path.normpath(os.path.join(worktree, text[len("gitdir:"):].strip()))
    common = read_file(os.path.join(gitdir, "commondir"))
    common = os.path.normpath(os.path.join(gitdir, common.strip())) if common else gitdir
    return gitdir, common


def repo_dir_of(common_dir):
    return os.path.dirname(common_dir) if os.path.basename(common_dir) == ".git" else common_dir


excluded_repos = set()


def ensure_excluded(common_dir):
    """Keeps .tonka/ out of git status for every worktree of the repo."""
    if common_dir in excluded_repos:
        return
    path = os.path.join(common_dir, "info", "exclude")
    existing = read_file(path) or ""
    if "/.tonka/" not in existing.split():
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write("/.tonka/\n")
        except OSError:
            return
    excluded_repos.add(common_dir)


def default_branch(repo_dir):
    for b in ("main", "master"):
        if run(["git", "-C", repo_dir, "rev-parse", "--verify", "-q", f"origin/{b}"]).returncode == 0:
            return b
    return None


def transcript_dir(path):
    # Claude Code stores transcripts under a directory named after the path with
    # every non-alphanumeric character replaced by '-'.
    return os.path.join(HOME, ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", path))


def has_claude_session(path):
    try:
        return any(n.endswith(".jsonl") for n in os.listdir(transcript_dir(path)))
    except OSError:
        return False


def newest_transcript(path):
    d = transcript_dir(path)
    try:
        files = [os.path.join(d, n) for n in os.listdir(d) if n.endswith(".jsonl")]
        return max(files, key=os.path.getmtime) if files else None
    except OSError:
        return None


def transcript_state(transcript):
    """Infers "working" or "waiting" from the end of a Claude transcript."""
    try:
        with open(transcript, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 256 * 1024))
            tail = f.read().decode("utf-8", errors="replace").splitlines()
        age = time.time() - os.path.getmtime(transcript)
    except OSError:
        return "waiting"
    for line in reversed(tail):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        kind = entry.get("type")
        # Claude Code records the duration of every turn when the turn ends.
        if kind == "system" and entry.get("subtype") == "turn_duration":
            return "waiting"
        if kind not in ("user", "assistant") or entry.get("isMeta"):
            continue
        message = entry.get("message") or {}
        if kind == "assistant" and message.get("stop_reason") == "end_turn":
            return "waiting"
        content = message.get("content")
        text = content if isinstance(content, str) else " ".join(
            c.get("text", "") for c in content or [] if isinstance(c, dict))
        if kind == "user" and text.startswith("[Request interrupted"):
            return "waiting"
        return "working" if age < STALE_TURN_SECONDS else "waiting"
    return "waiting"


def claude_cwds():
    """Returns the working directories of every Claude process in the VM."""
    r = run(["ps", "-A", "-o", "pid=,comm="])
    pids = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and os.path.basename(parts[1].strip()) == "claude":
            pids.append(parts[0])
    if not pids:
        return set()
    r = run(["lsof", "-a", "-d", "cwd", "-p", ",".join(pids), "-Fn"])
    return {line[1:] for line in r.stdout.splitlines() if line.startswith("n")}


def window_name(project):
    return project + "-project" if project == BOARD_WINDOW else project


class Card:
    def __init__(self, name):
        self.name = name
        self.path = os.path.join(PROJECTS, name)
        self.repo = ""
        self.branch = ""
        self.common_dir = ""
        self.status = ""
        self.listed_prs = []
        self.checklist = []
        self.message = ""
        self.prs = {}  # url -> state, from gh; replaced wholesale by the poller thread
        self.agent_state = ""
        self.window = None
        self.external = False  # Claude runs for this project outside the board
        self.external_state = ""
        self.status_mtime = None

    def refresh(self):
        dirs = git_dirs(self.path)
        if dirs is None:
            return False
        gitdir, self.common_dir = dirs
        self.repo = os.path.basename(repo_dir_of(self.common_dir))
        head = (read_file(os.path.join(gitdir, "HEAD")) or "").strip()
        self.branch = head[len("ref: refs/heads/"):] if head.startswith("ref: refs/heads/") else head[:10]
        ensure_excluded(self.common_dir)

        status_path = os.path.join(self.path, STATUS_FILE)
        try:
            mtime = os.stat(status_path).st_mtime
        except OSError:
            mtime = None
        if mtime != self.status_mtime:
            self.status_mtime = mtime
            text = read_file(status_path) if mtime is not None else None
            self.status, self.listed_prs, self.checklist, self.message = parse_status(text or "")
        self.agent_state = (read_file(os.path.join(self.path, STATE_FILE)) or "").strip()
        return True

    def all_prs(self):
        prs = dict(self.prs)
        for url in self.listed_prs:
            prs.setdefault(url, "")
        return prs

    def done(self):
        if self.status == "done":
            return True
        states = self.all_prs().values()
        return (bool(states) and all(s == "MERGED" for s in states)
                and all(ok for ok, _ in self.checklist))

    def has_open_pr(self):
        return "OPEN" in self.all_prs().values()

    def board_agent(self):
        return self.window is not None and self.agent_state != "exited"

    def column(self):
        if self.done():
            return NEEDS_INPUT
        if self.board_agent():
            # An empty state means Claude is still starting up.
            state = self.agent_state or "working"
        elif self.external:
            state = self.external_state
        else:
            return REVIEW if self.has_open_pr() or self.status == "review" else IDLE
        if state == "working":
            return WORKING
        if self.status == "review" or (self.has_open_pr() and self.status != "needs-input"):
            return REVIEW
        return NEEDS_INPUT


def fetch_prs(card):
    """Returns {url: state} for the card's branch PRs and listed PRs, or None on error."""
    prs = {}
    if card.branch and card.branch not in ("main", "master"):
        r = run([GH, "pr", "list", "--head", card.branch, "--state", "all", "--json", "url,state"], cwd=card.path)
        if r.returncode != 0:
            return None
        try:
            for pr in json.loads(r.stdout):
                prs[pr["url"]] = pr["state"]
        except (ValueError, KeyError, TypeError):
            return None
    for url in card.listed_prs:
        if url in prs:
            continue
        r = run([GH, "pr", "view", url, "--json", "state"], cwd=card.path)
        try:
            prs[url] = json.loads(r.stdout)["state"] if r.returncode == 0 else ""
        except (ValueError, KeyError, TypeError):
            prs[url] = ""
    return prs


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return "-".join(slug.split("-")[:5])[:40].strip("-") or "task"


def list_repos():
    try:
        return sorted(n for n in os.listdir(REPOS) if os.path.isdir(os.path.join(REPOS, n, ".git")))
    except OSError:
        return []


def suggest_project(desc, repos, taken):
    """Asks Claude which repo the task belongs in and what to name the worktree."""
    blocks = []
    for repo in repos:
        d = os.path.join(REPOS, repo)
        url = run(["git", "-C", d, "remote", "get-url", "origin"]).stdout.strip()
        readme = ""
        for n in ("README.md", "README", "readme.md", "README.rst"):
            readme = read_file(os.path.join(d, n)) or ""
            if readme:
                break
        readme = "\n".join(l for l in readme.splitlines() if l.strip())[:800]
        blocks.append(f"## {repo}\norigin: {url}\n{readme}")
    prompt = f"""Pick the repository and a git worktree/branch name for a new coding task.

# Task

{desc}

# Repositories

{chr(10).join(blocks)}

# Existing worktree names (do not reuse)

{', '.join(sorted(taken)) or '(none)'}

Choose the repository the task most likely belongs in. Choose a short name for the worktree and its branch: lowercase letters, digits and hyphens, at most 40 characters. If your instructions define a branch naming convention, follow it.
Reply with JSON only, in the form {{"repo": "<repo>", "name": "<name>"}}."""
    schema = {"type": "object", "required": ["repo", "name"],
              "properties": {"repo": {"type": "string", "enum": repos}, "name": {"type": "string"}}}
    r = run([CLAUDE, "-p", "--model", MODEL, "--output-format", "json",
             "--json-schema", json.dumps(schema), prompt], cwd=HOME, timeout=180)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:200] or f"claude exited {r.returncode}")
    data = json.loads(r.stdout)
    obj = data.get("structured_output")
    if not isinstance(obj, dict):
        m = re.search(r"\{.*\}", data.get("result", ""), re.S)
        if not m:
            raise RuntimeError("Claude did not return JSON")
        obj = json.loads(m.group(0))
    repo, name = obj.get("repo"), obj.get("name") or ""
    if repo not in repos:
        raise RuntimeError(f"Claude picked an unknown repo: {repo}")
    return repo, name


def clean_name(name):
    return re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-.")[:60] or "task"


def unique_name(name, repo):
    base, n = name, 2
    while (os.path.exists(os.path.join(PROJECTS, name)) or
           run(["git", "-C", os.path.join(REPOS, repo), "rev-parse", "--verify", "-q",
                f"refs/heads/{name}"]).returncode == 0):
        name = f"{base}-{n}"
        n += 1
    return name


def disp_width(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def clip(s, width):
    out, w = [], 0
    for c in s:
        cw = 2 if unicodedata.east_asian_width(c) in "WF" else 1
        if w + cw > width:
            break
        out.append(c)
        w += cw
    return "".join(out)


def wrap(text, width, first_prefix="", prefix=""):
    """Word-wraps text, breaking words longer than the line (such as URLs)."""
    width = max(width, 4)
    lines, cur = [], first_prefix
    cur_prefix = first_prefix
    for word in text.split():
        sep = "" if cur == cur_prefix else " "
        if disp_width(cur + sep + word) <= width:
            cur += sep + word
            continue
        if cur != cur_prefix:
            lines.append(cur)
            cur = cur_prefix = prefix
        while disp_width(cur + word) > width:
            room = width - disp_width(cur)
            piece = clip(word, room)
            lines.append(cur + piece)
            word = word[len(piece):]
            cur = cur_prefix = prefix
        cur += word
    if cur != cur_prefix or not lines:
        lines.append(cur)
    return lines


class Pending:
    """A project whose worktree is being created; shown as a placeholder card."""

    def __init__(self, name, repo):
        self.name = name
        self.repo = repo


class Board:
    def __init__(self, scr):
        self.scr = scr
        self.cards = {}
        self.pending = []
        self.selected = None
        self.want_selected = None  # a card to select once it appears
        self.sel_col, self.sel_idx = NEEDS_INPUT, 0
        self.offsets = [0] * len(COLUMNS)
        self.last_scan = 0
        self.notice = ""
        self.notice_time = 0
        self.waiting_shown = None
        self.session = tmux("display-message", "-p", "#S").stdout.strip() if os.environ.get("TMUX") else ""
        self.last_process_scan = 0
        try:
            with open(PR_CACHE) as f:
                self.pr_cache = json.load(f)
        except (OSError, ValueError):
            self.pr_cache = {}
        self.pr_wake = threading.Event()
        threading.Thread(target=self.poll_prs, daemon=True).start()
        self.init_colors()

    def init_colors(self):
        curses.curs_set(0)
        self.attr = {"dim": curses.A_DIM, "bold": curses.A_BOLD, "green": curses.A_BOLD,
                     "yellow": curses.A_BOLD, "sel": curses.A_BOLD, "red": curses.A_BOLD}
        if curses.has_colors():
            curses.start_color()
            try:
                curses.use_default_colors()
                bg = -1
            except curses.error:
                bg = curses.COLOR_BLACK
            for i, color in enumerate((curses.COLOR_GREEN, curses.COLOR_YELLOW, curses.COLOR_CYAN,
                                       curses.COLOR_RED), start=1):
                curses.init_pair(i, color, bg)
            self.attr.update(green=curses.color_pair(1), yellow=curses.color_pair(2) | curses.A_BOLD,
                             sel=curses.color_pair(3) | curses.A_BOLD, red=curses.color_pair(4))

    def say(self, text):
        self.notice, self.notice_time = text, time.time()

    # --- state -------------------------------------------------------------

    def scan(self):
        self.last_scan = time.time()
        try:
            names = sorted(os.listdir(PROJECTS))
        except OSError:
            names = []
        seen = set()
        for name in names:
            if not os.path.isdir(os.path.join(PROJECTS, name)):
                continue
            card = self.cards.get(name) or Card(name)
            if card.refresh():
                if name not in self.cards:
                    card.prs = self.pr_cache.get(name, {})
                    self.cards[name] = card
                    self.pr_wake.set()
                seen.add(name)
        for name in list(self.cards):
            if name not in seen:
                del self.cards[name]
        self.pending = [p for p in self.pending if p.name not in self.cards]

        windows = {}
        if self.session:
            out = tmux("list-windows", "-t", self.session, "-F", "#{window_id}\t#{window_name}").stdout
            for line in out.splitlines():
                wid, _, wname = line.partition("\t")
                windows[wname] = wid
        for card in self.cards.values():
            card.window = windows.get(window_name(card.name))

        if time.time() - self.last_process_scan >= PROCESS_SCAN_SECONDS:
            self.last_process_scan = time.time()
            cwds = claude_cwds()
            for card in self.cards.values():
                prefix = card.path + os.sep
                card.external = not card.board_agent() and any(
                    c == card.path or c.startswith(prefix) for c in cwds)
                if card.external:
                    t = newest_transcript(card.path)
                    card.external_state = transcript_state(t) if t else "working"

        waiting = sum(1 for c in self.cards.values() if c.column() == NEEDS_INPUT)
        if self.session and waiting != self.waiting_shown:
            self.waiting_shown = waiting
            tmux("set-option", "-g", "@tonka-waiting", str(waiting) if waiting else "")

    def poll_prs(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            while True:
                cards = list(self.cards.values())
                for card, prs in zip(cards, pool.map(fetch_prs, cards)):
                    if prs is not None:
                        card.prs = prs
                        self.pr_cache[card.name] = prs
                try:
                    with open(PR_CACHE + ".tmp", "w") as f:
                        json.dump(self.pr_cache, f)
                    os.replace(PR_CACHE + ".tmp", PR_CACHE)
                except OSError:
                    pass
                self.pr_wake.wait(PR_POLL_SECONDS)
                self.pr_wake.clear()

    def layout(self):
        cols = [[] for _ in COLUMNS]
        for card in self.cards.values():
            cols[card.column()].append(card)
        for col in cols:
            col.sort(key=lambda c: (c.done(), c.name))
        return cols

    def fix_selection(self, cols):
        if self.want_selected in self.cards:
            self.selected, self.want_selected = self.want_selected, None
        for ci, col in enumerate(cols):
            for i, card in enumerate(col):
                if card.name == self.selected:
                    self.sel_col, self.sel_idx = ci, i
                    return
        # The selected card is gone; select its neighbour, or the first card anywhere.
        order = [self.sel_col] + [c for c in range(len(COLUMNS)) if c != self.sel_col]
        for ci in order:
            if cols[ci]:
                self.sel_col = ci
                self.sel_idx = min(self.sel_idx, len(cols[ci]) - 1) if ci == order[0] else 0
                self.selected = cols[ci][self.sel_idx].name
                return
        self.selected = None

    def current(self):
        return self.cards.get(self.selected) if self.selected else None

    # --- drawing -----------------------------------------------------------

    def put(self, y, x, text, attr=0, width=None):
        h, w = self.scr.getmaxyx()
        if y < 0 or y >= h or x >= w:
            return
        width = min(width if width is not None else w - x, w - x)
        if y == h - 1:
            width = min(width, w - x - 1)  # writing the bottom-right cell raises
        if width <= 0:
            return
        try:
            self.scr.addstr(y, x, clip(text, width), attr)
        except curses.error:
            pass

    def card_lines(self, card, width):
        a = self.attr
        lines = [(card.name, a["bold"])]
        sub = card.repo if card.branch == card.name else f"{card.repo} · {card.branch}"
        lines.append((sub, a["dim"]))
        if card.done():
            lines.append(("✔ Complete. Enter deletes it.", a["green"]))
        elif card.window is not None and card.agent_state == "exited":
            lines.append(("○ Claude exited", a["dim"]))
        elif card.column() == NEEDS_INPUT:
            lines.append(("● Waiting for you", a["yellow"]))
        if card.external and not card.done():
            lines.append(("◆ Claude is running in another terminal", a["dim"]))
        for ok, text in card.checklist:
            for line in wrap(text, width, "☑ " if ok else "☐ ", "  "):
                lines.append((line, a["dim"] if ok else 0))
        if card.message:
            msg = wrap(card.message, width)
            if len(msg) > MESSAGE_LINES:
                msg = msg[:MESSAGE_LINES - 1] + [clip(msg[MESSAGE_LINES - 1], width - 1) + "…"]
            if card.checklist:
                lines.append(("", 0))
            lines += [(m, 0) for m in msg]
        for url, state in sorted(card.all_prs().items()):
            attr = {"MERGED": a["green"], "CLOSED": a["red"]}.get(state, a["yellow"] if state else 0)
            label = f"{url} ({state.lower()})" if state else url
            lines += [(l, attr) for l in wrap(label, width)]
        return lines

    def draw_box(self, y, x, h, w, attr, top, bottom):
        """Draws a box whose rows outside [top, bottom) are skipped."""
        for row in range(y, y + h):
            if row < top or row >= bottom:
                continue
            if row == y or row == y + h - 1:
                l, r = ("┌", "┐") if row == y else ("└", "┘")
                self.put(row, x, l + "─" * (w - 2) + r, attr)
            else:
                self.put(row, x, "│", attr)
                self.put(row, x + w - 1, "│", attr)

    def draw(self):
        self.scr.erase()
        h, w = self.scr.getmaxyx()
        a = self.attr
        cols = self.layout()
        self.fix_selection(cols)

        self.put(0, 0, " tonka kanban", a["bold"])
        help_text = "←↑↓→ move  ⏎ open  n new  d delete  r refresh PRs  R reload  q detach  │  Ctrl-\\ returns here"
        self.put(0, max(14, w - disp_width(help_text) - 1), help_text, a["dim"])

        ncol = len(COLUMNS)
        colw = max(12, (w - (ncol - 1)) // ncol)
        top, bottom = 3, h - 1
        for ci, title in enumerate(COLUMNS):
            x = ci * (colw + 1)
            n = len(cols[ci]) + (len(self.pending) if ci == WORKING else 0)
            attr = a["yellow"] if ci == NEEDS_INPUT and n else a["bold"]
            self.put(1, x, f" {title} ({n})", attr, colw)
            self.put(2, x, "─" * colw, a["dim"], colw)

            inner = colw - 4
            entries = []
            if ci == WORKING:
                for p in self.pending:
                    entries.append((None, [(p.name, a["bold"]), (p.repo, a["dim"]),
                                           ("Creating worktree…", a["yellow"])]))
            entries += [(card, self.card_lines(card, inner)) for card in cols[ci]]

            # Scroll the selected column so the selected card is visible.
            ys, y = [], 0
            for _, lines in entries:
                ys.append(y)
                y += len(lines) + 2
            avail = bottom - top
            off = self.offsets[ci]
            if ci == self.sel_col and self.selected:
                for (card, lines), cy in zip(entries, ys):
                    if card is not None and card.name == self.selected:
                        ch = len(lines) + 2
                        if cy < off or ch > avail:
                            off = cy
                        elif cy + ch > off + avail:
                            off = cy + ch - avail
            off = max(0, min(off, max(0, y - avail)))
            self.offsets[ci] = off

            for (card, lines), cy in zip(entries, ys):
                sy = top + cy - off
                if sy >= bottom or sy + len(lines) + 2 <= top:
                    continue
                selected = card is not None and card.name == self.selected
                self.draw_box(sy, x, len(lines) + 2, colw, a["sel"] if selected else a["dim"], top, bottom)
                for i, (text, attr) in enumerate(lines):
                    row = sy + 1 + i
                    if top <= row < bottom:
                        self.put(row, x + 2, text, attr, inner)
            if off > 0:
                self.put(top, x + colw - 2, "↑", a["dim"])
            if y - off > avail:
                self.put(bottom - 1, x + colw - 2, "↓", a["dim"])

        if not self.cards and not self.pending:
            self.put(h // 2, 2, "No projects in ~/projects. Press n to create one.", a["dim"])
        if self.notice and time.time() - self.notice_time < 15:
            self.put(h - 1, 0, " " + self.notice, a["yellow"])

    def tick(self):
        if time.time() - self.last_scan >= SCAN_SECONDS:
            self.scan()
        self.draw()

    # --- dialogs -----------------------------------------------------------

    def dialog_box(self, title, body, width=None):
        """Draws a centred box with a title and a list of (text, attr) lines; returns its origin."""
        h, w = self.scr.getmaxyx()
        bw = min(w - 4, width or 76)
        lines = []
        for text, attr in body:
            lines += [(l, attr) for l in (wrap(text, bw - 4) if text else [""])]
        lines = lines[:max(1, h - 6)]
        bh = len(lines) + 4
        y0, x0 = max(0, (h - bh) // 2), max(0, (w - bw) // 2)
        for row in range(bh):
            self.put(y0 + row, x0, " " * bw)
        self.draw_box(y0, x0, bh, bw, self.attr["sel"], 0, h)
        self.put(y0, x0 + 2, f" {title} ", self.attr["bold"])
        for i, (text, attr) in enumerate(lines):
            self.put(y0 + 2 + i, x0 + 2, text, attr, bw - 4)
        return y0, x0, bw

    def ask(self, title, body, keys, enter):
        """Shows a dialog until one of `keys` (or Enter, meaning `enter`) is pressed; Esc returns None."""
        while True:
            self.tick()
            self.dialog_box(title, body)
            self.scr.refresh()
            ch = self.getkey()
            if ch in ("\n", "\r", curses.KEY_ENTER):
                return enter
            if ch == "\x1b":
                return None
            if isinstance(ch, str) and ch.lower() in keys:
                return ch.lower()

    def edit_text(self, title, initial="", hint="Enter done · Esc cancel"):
        buf, pos = list(initial), len(initial)
        curses.curs_set(1)
        try:
            while True:
                self.tick()
                h, w = self.scr.getmaxyx()
                bw = min(w - 4, 80)
                tw = bw - 4
                rows = ["".join(buf[i:i + tw]) for i in range(0, len(buf) + 1, tw)] or [""]
                crow, ccol = pos // tw, pos % tw
                vis = min(len(rows), max(3, h - 10))
                start = max(0, crow - vis + 1)
                body = [(r, 0) for r in rows[start:start + vis]]
                body += [("", 0)] * (3 - len(body)) + [("", 0), (hint, self.attr["dim"])]
                y0, x0, _ = self.dialog_box(title, body, 80)
                try:
                    self.scr.move(y0 + 2 + crow - start, x0 + 2 + ccol)
                except curses.error:
                    pass
                self.scr.refresh()
                ch = self.getkey()
                if ch is None:
                    continue
                if ch in ("\n", "\r", curses.KEY_ENTER):
                    # A newline followed immediately by more input is part of a paste.
                    self.scr.timeout(20)
                    try:
                        nxt = self.scr.get_wch()
                    except curses.error:
                        nxt = None
                    finally:
                        self.scr.timeout(500)
                    if nxt is None:
                        return "".join(buf).strip()
                    curses.unget_wch(nxt)
                    buf.insert(pos, " ")
                    pos += 1
                elif ch == "\x1b":
                    return None
                elif ch in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    if pos > 0:
                        pos -= 1
                        del buf[pos]
                elif ch == curses.KEY_DC:
                    if pos < len(buf):
                        del buf[pos]
                elif ch == curses.KEY_LEFT:
                    pos = max(0, pos - 1)
                elif ch == curses.KEY_RIGHT:
                    pos = min(len(buf), pos + 1)
                elif ch in (curses.KEY_HOME, "\x01"):
                    pos = 0
                elif ch in (curses.KEY_END, "\x05"):
                    pos = len(buf)
                elif ch == "\x15":
                    del buf[:pos]
                    pos = 0
                elif ch == "\x17":
                    start_w = pos
                    while start_w > 0 and buf[start_w - 1] == " ":
                        start_w -= 1
                    while start_w > 0 and buf[start_w - 1] != " ":
                        start_w -= 1
                    del buf[start_w:pos]
                    pos = start_w
                elif isinstance(ch, str) and ch.isprintable():
                    buf.insert(pos, ch)
                    pos += 1
        finally:
            curses.curs_set(0)

    def getkey(self):
        try:
            return self.scr.get_wch()
        except curses.error:
            return None

    # --- actions -----------------------------------------------------------

    def open_card(self, card, prompt_file=None, select=True):
        if card.window and card.agent_state == "exited" and not prompt_file:
            tmux("kill-window", "-t", card.window)
            card.window = None
        if card.window and not prompt_file:
            tmux("select-window", "-t", card.window)
            return
        if not self.session:
            self.say("The board is not running inside tmux; cannot open a terminal.")
            return
        try:
            os.remove(os.path.join(card.path, STATE_FILE))
        except OSError:
            pass
        cmd = [os.path.join(KANBAN_DIR, "agent.sh"), card.name]
        if prompt_file:
            cmd += ["--prompt-file", prompt_file]
        elif has_claude_session(card.path):
            cmd += ["--continue"]
        args = ["new-window", "-P", "-F", "#{window_id}", "-t", self.session + ":",
                "-n", window_name(card.name), "-c", card.path]
        if not select:
            args.append("-d")
        r = tmux(*args, shlex.join(cmd))
        if r.returncode != 0:
            self.say(f"tmux new-window failed: {r.stderr.strip()}")
            return
        card.window = r.stdout.strip()

    def activate(self):
        card = self.current()
        if card is None:
            return
        if card.done():
            choice = self.ask("Project complete",
                              [(f"{card.name}: all work is merged.", 0), ("", 0),
                               ("Enter / y: delete the project (worktree and branch)", 0),
                               ("o: open its terminal instead", 0),
                               ("Esc: cancel", self.attr["dim"])],
                              keys="yno", enter="y")
            if choice == "y":
                self.delete(card, confirmed=True)
            elif choice == "o":
                self.open_card(card)
            return
        if card.external and not card.board_agent():
            # A second Claude would resume the same conversation as the running one.
            self.say(f"Claude for {card.name} is running in another terminal; switch to it there.")
            return
        self.open_card(card)

    def delete(self, card, confirmed=False):
        repo_dir = repo_dir_of(card.common_dir)
        if not confirmed:
            body = [(f"Delete {card.name}? This removes the worktree and the local branch {card.branch}.", 0)]
            unpushed = run(["git", "-C", card.path, "rev-list", "--count", "HEAD", "--not", "--remotes"])
            if unpushed.returncode == 0 and unpushed.stdout.strip() not in ("", "0"):
                body.append((f"⚠ {unpushed.stdout.strip()} commit(s) are not on any remote and will be lost.",
                             self.attr["red"]))
            body += [("", 0), ("y delete · Enter, n or Esc keep", self.attr["dim"])]
            if self.ask("Delete project", body, keys="yn", enter="n") != "y":
                return
        r = run(["git", "-C", repo_dir, "worktree", "remove", card.path])
        if r.returncode != 0:
            status = run(["git", "-C", card.path, "status", "--short"]).stdout.strip().splitlines()
            body = [(r.stderr.strip() or "git worktree remove failed", self.attr["red"]), ("", 0)]
            body += [(line, 0) for line in status[:10]]
            body += [("", 0), ("f force removal · Enter or Esc keep", self.attr["dim"])]
            if self.ask("Worktree has changes", body, keys="f", enter=None) != "f":
                return
            r = run(["git", "-C", repo_dir, "worktree", "remove", "--force", card.path])
            if r.returncode != 0:
                self.say(f"Removal failed: {r.stderr.strip()}")
                return
        if card.window:
            tmux("kill-window", "-t", card.window)
        if card.branch and card.branch not in ("main", "master"):
            run(["git", "-C", repo_dir, "branch", "-D", card.branch])
        self.cards.pop(card.name, None)
        self.say(f"Deleted {card.name}.")

    def new_project(self):
        desc = self.edit_text("New project: describe the task")
        if not desc:
            return
        repos = list_repos()
        if not repos:
            self.say("No repos in ~/repos. Add one from the host with: tonka new-repo <path>")
            return

        result = {}

        def work():
            try:
                result["value"] = suggest_project(desc, repos, set(self.cards))
            except Exception as e:  # any failure falls back to a local guess
                result["error"] = str(e)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        i = 0
        while t.is_alive():
            self.tick()
            self.dialog_box("New project", [("Asking Claude which repo to use and what to name the project "
                                             + spinner[i % len(spinner)], 0), ("", 0),
                                            ("Esc: skip and choose by hand", self.attr["dim"])])
            self.scr.refresh()
            i += 1
            self.scr.timeout(120)
            ch = self.getkey()
            self.scr.timeout(500)
            if ch == "\x1b":
                result["error"] = "skipped"
                break

        if "value" in result:
            repo, name = result["value"]
        else:
            repo = os.environ.get("TONKA_DEFAULT_REPO") if os.environ.get("TONKA_DEFAULT_REPO") in repos else repos[0]
            name = slugify(desc)
        name = unique_name(clean_name(name), repo)

        while True:
            body = [(desc if len(desc) < 300 else desc[:300] + "…", self.attr["dim"]), ("", 0),
                    (f"Repo:  {repo}", self.attr["bold"]), (f"Name:  {name}", self.attr["bold"]), ("", 0)]
            if "error" in result and result["error"] != "skipped":
                body.append((f"Claude could not suggest a project: {result['error']}", self.attr["red"]))
                body.append(("", 0))
            body.append(("Enter create · Tab next repo · e edit name · Esc cancel", self.attr["dim"]))
            choice = self.ask("New project", body, keys="e\t", enter="create")
            if choice is None:
                return
            if choice == "\t":
                repo = repos[(repos.index(repo) + 1) % len(repos)]
                name = unique_name(name, repo)
            elif choice == "e":
                edited = self.edit_text("Project name", name)
                if edited:
                    name = unique_name(clean_name(edited), repo)
            elif choice == "create":
                break

        pending = Pending(name, repo)
        self.pending.append(pending)
        self.want_selected = name
        threading.Thread(target=self.create_project, args=(pending, desc), daemon=True).start()

    def drop_pending(self, pending):
        if pending in self.pending:
            self.pending.remove(pending)

    def create_project(self, pending, desc):
        """Runs on a background thread, so it leaves self.cards to scan() on the main thread."""
        name, repo = pending.name, pending.repo
        repo_dir = os.path.join(REPOS, repo)
        path = os.path.join(PROJECTS, name)
        base = default_branch(repo_dir)
        if base is None:
            self.drop_pending(pending)
            self.say(f"{repo}: neither origin/main nor origin/master exists.")
            return
        steps = [["git", "-C", repo_dir, "fetch", "-q", "origin", base],
                 ["git", "-C", repo_dir, "worktree", "add", "-q", path, "-b", name, f"origin/{base}"]]
        os.makedirs(PROJECTS, exist_ok=True)
        for cmd in steps:
            r = run(cmd, timeout=600)
            if r.returncode != 0:
                self.drop_pending(pending)
                self.say(f"Creating {name} failed: {r.stderr.strip()[:200]}")
                return

        os.makedirs(os.path.join(path, ".tonka"), exist_ok=True)
        with open(os.path.join(path, STATUS_FILE), "w") as f:
            f.write(f"status: working\n\n{desc[:200]}\n")
        os.makedirs(PROMPTS, exist_ok=True)
        prompt_file = os.path.join(PROMPTS, f"{name}.txt")
        with open(prompt_file, "w") as f:
            f.write(f"""{desc}

---
You are working in the git worktree ~/projects/{name} on branch '{name}', which was just created from origin/{base} of the {repo} repository. Do all work on this branch.
This session is tracked on the tonka kanban board. Follow the tonka-kanban skill, and write .tonka/status.md with your plan before you start the task.
""")
        card = Card(name)
        if card.refresh():
            self.open_card(card, prompt_file=prompt_file, select=False)
        self.drop_pending(pending)
        self.say(f"Created {name} in {repo}. Press Enter to open it.")

    # --- main loop ---------------------------------------------------------

    def move(self, dcol, drow):
        cols = self.layout()
        self.fix_selection(cols)
        if drow:
            col = cols[self.sel_col]
            if col:
                self.sel_idx = max(0, min(len(col) - 1, self.sel_idx + drow))
                self.selected = col[self.sel_idx].name
        if dcol:
            ci = self.sel_col + dcol
            while 0 <= ci < len(COLUMNS) and not cols[ci]:
                ci += dcol
            if 0 <= ci < len(COLUMNS):
                self.sel_col = ci
                self.sel_idx = min(self.sel_idx, len(cols[ci]) - 1)
                self.selected = cols[ci][self.sel_idx].name

    def loop(self):
        self.scr.timeout(500)
        self.scan()
        while True:
            self.tick()
            self.scr.refresh()
            ch = self.getkey()
            if ch is None or ch == curses.KEY_RESIZE:
                continue
            if ch in (curses.KEY_LEFT, "h"):
                self.move(-1, 0)
            elif ch in (curses.KEY_RIGHT, "l"):
                self.move(1, 0)
            elif ch in (curses.KEY_UP, "k"):
                self.move(0, -1)
            elif ch in (curses.KEY_DOWN, "j"):
                self.move(0, 1)
            elif ch in ("\n", "\r", curses.KEY_ENTER):
                self.activate()
            elif ch == "n":
                self.new_project()
            elif ch == "d" and self.current():
                self.delete(self.current())
            elif ch == "r":
                self.pr_wake.set()
                self.say("Refreshing PRs…")
            elif ch == "R":
                return
            elif ch == "q":
                if self.session:
                    tmux("detach-client")
                else:
                    return


def main():
    locale.setlocale(locale.LC_ALL, "")
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(lambda scr: Board(scr).loop())


if __name__ == "__main__":
    sys.exit(main())
