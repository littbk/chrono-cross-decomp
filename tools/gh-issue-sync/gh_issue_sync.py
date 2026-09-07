#!/usr/bin/env python3
"""
gh-issue-sync - Markdown <-> GitHub Issues sync tool

Usage:
    gh_issue_sync check  [file]
    gh_issue_sync pull   [file]
    gh_issue_sync push   [file]
    gh_issue_sync sync   [file]

On first run, a config.toml template is created and the tool exits.
Fill in owner, repo, and token, then run again.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

TOOL_DIR = Path(__file__).resolve().parent
CONFIG_PATH = TOOL_DIR / "config.toml"
DEFAULT_FILE = "todo.md"

TODO_HEADER = """\
<!--
# todo.md
#
# Syntax reference (these lines are local-only and never synced):
#
#   [gh] [label1,label2] Title        — create a new GitHub issue
#   [#123] [label] Title              — sync to existing issue #123
#   [ ] / [x]                         — open / request close
#   [closed]                          — confirmed closed (written by tool)
#   > Description line                — synced issue body (top-level only)
#   [c] @user — Comment               — create a new comment
#   [#c987654321] @user — Comment     — sync existing comment
#   >> continuation line               — multi-line comment body
#
# Tokens in [...] before the title can appear in any order.
# Indented lines and list items sync title/labels/state only (no body or comments).
# Local notes below a description block are never synced.
#
# Run: issue-sync push        — push local changes to GitHub
#      issue-sync pull        — refresh from GitHub
#      issue-sync sync        — pull then push (validates first)
#      issue-sync check       — validate syntax only
-->
"""

# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

@dataclass
class Config:
    owner: str
    repo: str
    file: str = DEFAULT_FILE
    token: str = ""
    token_env: str = "GITHUB_TOKEN"
    pull_comments: bool = True
    push_comments: bool = True

    @property
    def resolved_token(self) -> str:
        if self.token:
            return self.token
        t = os.environ.get(self.token_env, "")
        if not t:
            die(
                f"No token found. Set 'token' in {CONFIG_PATH}\n"
                f"or export ${self.token_env} in your environment."
            )
        return t


# ---------------------------------------------------------------------------
# Config definition
# Each section: (section_name | None, header_comment | None, [(key, default, comment)])
# This is the single source of truth for defaults and the generated template.
# ---------------------------------------------------------------------------

CONFIG_SECTIONS: list[tuple] = [
    (None, "# IMPORTANT: Keep this file out of git — add it to .gitignore.", [
        ("owner", "",        "Your GitHub username e.g. jdperos"),
        ("repo",  "",        "Repo name e.g. chrono-cross-decomp"),
        ("file",  "todo.md", "Path to sync file from repo root"),
    ]),
    ("auth", None, [
        ("token",     "", "Paste your GitHub personal access token here.\n# Needs 'repo' scope (or 'public_repo' for public repos)."),
        ("token_env", "GITHUB_TOKEN", "Alternatively, leave token blank and set this env var instead"),
    ]),
    ("sync", None, [
        ("pull_comments", True,  "Fetch comments when pulling"),
        ("push_comments", True,  "Create/update comments when pushing"),
    ]),
]


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        items = ", ".join(f'"{v}"' for v in value)
        return f"[{items}]"
    return f'"{value}"'


def write_default_config(path: Path) -> None:
    lines: list[str] = []
    for section_name, header_comment, fields in CONFIG_SECTIONS:
        if header_comment:
            lines.append(header_comment)
        if section_name:
            lines.append(f"\n[{section_name}]")
        for key, default, comment in fields:
            lines.append(f"# {comment}")
            lines.append(f"{key} = {_toml_value(default)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        TOOL_DIR.mkdir(parents=True, exist_ok=True)
        write_default_config(CONFIG_PATH)
        print(
            f"Created config template at:\n"
            f"  {CONFIG_PATH}\n\n"
            f"Fill in 'owner', 'repo', and 'token', then run again.\n"
            f"Add config.toml to your .gitignore to keep your token out of git."
        )
        sys.exit(0)

    with CONFIG_PATH.open("rb") as f:
        data = tomllib.load(f)

    owner = data.get("owner", "").strip()
    repo  = data.get("repo",  "").strip()

    if not owner or not repo:
        die(
            f"config.toml is missing 'owner' and/or 'repo'.\n"
            f"Edit {CONFIG_PATH} and fill them in."
        )

    auth = data.get("auth", {})
    sync = data.get("sync", {})

    token     = auth.get("token",     "").strip()
    token_env = auth.get("token_env", "GITHUB_TOKEN")

    return Config(
        owner=owner,
        repo=repo,
        file=data.get("file", DEFAULT_FILE),
        token=token,
        token_env=token_env,
        pull_comments=sync.get("pull_comments", True),
        push_comments=sync.get("push_comments", True),
    )


def write_config(owner: str, repo: str, file: str = DEFAULT_FILE) -> None:
    """Legacy helper kept for tests."""
    TOOL_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        f'owner = "{owner}"\n'
        f'repo  = "{repo}"\n'
        f'file  = "{file}"\n'
        f"\n[auth]\n"
        f'token = ""\n'
        f"\n[sync]\n"
        f"pull_comments = true\n"
        f"push_comments = true\n"
    )


# -----------------------------------------------------------------------------
# Tokeniser / Parser
# -----------------------------------------------------------------------------

_TOKEN_RE = re.compile(r'\[([^\]]*)\]')
_LIST_PREFIX_RE = re.compile(r'^(\s*(?:\d+[.)]\s+|[-*+]\s+)|\s+)')


def _strip_list_prefix(line: str) -> tuple[str, str]:
    """Return (prefix, rest). prefix is whitespace + optional list marker."""
    m = _LIST_PREFIX_RE.match(line)
    if m:
        return m.group(1), line[m.end():]
    return "", line


def _classify_token(content: str) -> tuple[str, object]:
    """
    Returns (kind, value).
    Kinds: issue_new | issue_num | state_open | state_close_req | state_closed
           comment_new | comment_id | label
    """
    t = content.strip()
    tl = t.lower()
    if tl == "gh":
        return "issue_new", "gh"
    if tl == "x":
        return "state_close_req", "x"
    if tl in (" ", ""):
        return "state_open", " "
    if tl == "closed":
        return "state_closed", "closed"
    if tl == "c":
        return "comment_new", "c"
    m = re.fullmatch(r'#(\d+)', t)
    if m:
        return "issue_num", int(m.group(1))
    m = re.fullmatch(r'#c(\d+)', t)
    if m:
        return "comment_id", int(m.group(1))
    # Label block
    labels = [lbl.strip() for lbl in t.split(",") if lbl.strip()]
    return "label", labels


@dataclass
class ParsedIssueLine:
    raw: str
    line_no: int
    indent: str
    is_top_level: bool
    issue_marker: object   # "gh" | int
    state: Optional[str]   # None | "open" | "close_requested" | "closed"
    labels: list
    title: str


@dataclass
class ParsedCommentLine:
    raw: str
    line_no: int
    end_line_no: int         # last line (== line_no if single-line)
    comment_marker: object   # "new" | int
    author: Optional[str]
    text: str


@dataclass
class IssueBlock:
    issue_line: ParsedIssueLine
    desc_line_nos: list    # line indices of > lines
    desc_lines: list       # raw content of > lines
    comment_lines: list    # list[ParsedCommentLine], top-level only
    # local trailing lines are everything else between this block and the next;
    # we don't store them explicitly — the rewriter preserves them by default.


def _has_token_kind(line: str, *kinds: str) -> bool:
    _, rest = _strip_list_prefix(line)
    for m in _TOKEN_RE.finditer(rest):
        k, _ = _classify_token(m.group(1))
        if k in kinds:
            return True
    return False


def _parse_issue_line(raw: str, line_no: int) -> Optional[ParsedIssueLine]:
    stripped = raw.rstrip("\n")
    indent, rest = _strip_list_prefix(stripped)
    is_top_level = (indent == "")

    tokens = list(_TOKEN_RE.finditer(rest))
    if not tokens:
        return None

    issue_marker = None
    state = None
    labels = []
    last_end = 0

    for m in tokens:
        k, v = _classify_token(m.group(1))
        last_end = m.end()
        if k == "issue_new":
            issue_marker = "gh"
        elif k == "issue_num":
            if issue_marker is None:
                issue_marker = v
        elif k == "state_open":
            if state is None:
                state = "open"
        elif k == "state_close_req":
            if state != "closed":
                state = "close_requested"
        elif k == "state_closed":
            state = "closed"
        elif k == "label":
            labels.extend(v)

    if issue_marker is None:
        return None

    title = rest[last_end:].strip()

    return ParsedIssueLine(
        raw=raw,
        line_no=line_no,
        indent=indent,
        is_top_level=is_top_level,
        issue_marker=issue_marker,
        state=state,
        labels=labels,
        title=title,
    )


def _parse_comment_line(raw: str, line_no: int) -> Optional[ParsedCommentLine]:
    stripped = raw.rstrip("\n")
    _, rest = _strip_list_prefix(stripped)

    tokens = list(_TOKEN_RE.finditer(rest))
    comment_marker = None
    last_end = 0

    for m in tokens:
        k, v = _classify_token(m.group(1))
        if k in ("comment_new", "comment_id"):
            comment_marker = "new" if k == "comment_new" else v
            last_end = m.end()

    if comment_marker is None:
        return None

    remainder = rest[last_end:].strip()

    # Parse optional @author - text  (em-dash or hyphen accepted)
    author = None
    text = remainder
    m = re.match(r'@(\S+)\s+[—\-]\s+(.*)', remainder, re.DOTALL)
    if m:
        author = m.group(1)
        text = m.group(2).strip()

    return ParsedCommentLine(
        raw=raw,
        line_no=line_no,
        end_line_no=line_no,
        comment_marker=comment_marker,
        author=author,
        text=text,
    )


class ParsedDocument:
    def __init__(self, lines: list[str]):
        self.lines = lines
        self.issue_blocks: list[IssueBlock] = []
        self._parse()

    def _parse(self):
        lines = self.lines
        n = len(lines)
        i = 0
        in_html_comment = False
        current_block: Optional[IssueBlock] = None
        in_desc = False

        while i < n:
            raw = lines[i]

            # HTML comment tracking 
            if in_html_comment:
                if "-->" in raw:
                    in_html_comment = False
                i += 1
                continue
            if "<!--" in raw:
                in_html_comment = True
                if "-->" in raw:
                    in_html_comment = False
                i += 1
                continue

            # Issue line? 
            if _has_token_kind(raw, "issue_new", "issue_num"):
                parsed = _parse_issue_line(raw, i)
                if parsed:
                    block = IssueBlock(
                        issue_line=parsed,
                        desc_line_nos=[],
                        desc_lines=[],
                        comment_lines=[],
                    )
                    self.issue_blocks.append(block)
                    current_block = block
                    in_desc = parsed.is_top_level  # only collect desc for top-level
                    i += 1

                    # Greedily collect description block (top-level only)
                    if parsed.is_top_level:
                        while i < n and lines[i].lstrip().startswith(">"):
                            block.desc_line_nos.append(i)
                            block.desc_lines.append(lines[i])
                            i += 1

                    continue

            # Comment line? 
            if (
                current_block is not None
                and current_block.issue_line.is_top_level
                and _has_token_kind(raw, "comment_new", "comment_id")
            ):
                parsed_c = _parse_comment_line(raw, i)
                if parsed_c:
                    current_block.comment_lines.append(parsed_c)
                    i += 1

                    # Greedily consume >> continuation lines
                    cont_parts = [parsed_c.text]
                    while i < n:
                        cont_raw = lines[i].rstrip("\n")
                        if cont_raw.startswith(">> "):
                            cont_parts.append(cont_raw[3:])
                            parsed_c.end_line_no = i
                            i += 1
                        elif cont_raw.rstrip() == ">>":
                            cont_parts.append("")
                            parsed_c.end_line_no = i
                            i += 1
                        else:
                            break
                    parsed_c.text = "\n".join(cont_parts)

                    continue

            # Everything else is local-only; leave it alone 
            i += 1


# -----------------------------------------------------------------------------
# Rendering
# -----------------------------------------------------------------------------

def render_issue_line(
    indent: str,
    issue_marker: object,
    state: Optional[str],
    labels: list,
    title: str,
) -> str:
    marker = f"[#{issue_marker}]" if isinstance(issue_marker, int) else "[gh]"
    state_tok = {
        "closed": "[closed]",
        "open": "[ ]",
        "close_requested": "[x]",
    }.get(state or "", "")
    label_tok = f"[{','.join(labels)}]" if labels else ""
    parts = [p for p in [marker, state_tok, label_tok] if p]
    tokens = " ".join(parts)
    return f"{indent}{tokens} {title}\n" if title else f"{indent}{tokens}\n"


def render_comment_lines(
    comment_marker: object,
    author: Optional[str],
    text: str,
) -> list[str]:
    """Render a comment as one or more lines.

    Single-line:   [#c123] @user — text
    Multi-line:    [#c123] @user — first line
                   >> second line
                   >>
                   >> fourth line
    """
    marker = f"[#c{comment_marker}]" if isinstance(comment_marker, int) else "[c]"
    author_part = f"@{author} — " if author else ""
    lines = text.split("\n") if "\n" in text else [text]
    result = [f"{marker} {author_part}{lines[0]}\n"]
    for cont in lines[1:]:
        result.append(f">> {cont}\n" if cont else ">>\n")
    return result


def body_to_desc_lines(body: str) -> list[str]:
    """GitHub issue body → list of raw '> ...' lines."""
    if not body:
        return []
    result = []
    for line in body.splitlines():
        result.append(f"> {line}\n" if line else ">\n")
    return result


def desc_lines_to_body(desc_lines: list[str]) -> str:
    """Raw '> ...' lines → GitHub issue body string."""
    out = []
    for raw in desc_lines:
        s = raw.rstrip("\n")
        if s.startswith("> "):
            out.append(s[2:])
        elif s.rstrip() == ">":
            out.append("")
        else:
            out.append(s.lstrip(">").lstrip())
    return "\n".join(out)


# -----------------------------------------------------------------------------
# File Rewriter
# -----------------------------------------------------------------------------

class FileRewriter:
    """
    Applies surgical rewrites to a list of lines.
    Only lines explicitly targeted are changed; everything else is preserved.
    """

    def __init__(self, lines: list[str]):
        self.lines = list(lines)
        # line_no -> str (replace) | list[str] (replace with many) | None (delete)
        self._replacements: dict = {}
        # line_no -> list[str] (insert AFTER this line, even if line is replaced)
        self._after: dict = {}

    def replace(self, line_no: int, new_line: str) -> None:
        self._replacements[line_no] = new_line

    def replace_range(self, start: int, end_exclusive: int, new_lines: list[str]) -> None:
        """Replace lines[start:end_exclusive] with new_lines."""
        if start >= end_exclusive:
            return
        self._replacements[start] = list(new_lines)
        for i in range(start + 1, end_exclusive):
            self._replacements[i] = None

    def insert_after(self, line_no: int, new_lines: list[str]) -> None:
        self._after[line_no] = list(new_lines)

    def get_result(self) -> list[str]:
        result = []
        for i, line in enumerate(self.lines):
            rep = self._replacements.get(i, line)
            if rep is None:
                pass  # deleted
            elif isinstance(rep, list):
                result.extend(rep)
            else:
                result.append(rep)
            if i in self._after:
                result.extend(self._after[i])
        return result


# -----------------------------------------------------------------------------
# GitHub Client
# -----------------------------------------------------------------------------

class GitHubError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")


class GitHub:
    API = "https://api.github.com"

    def __init__(self, token: str, owner: str, repo: str):
        self.token = token
        self.owner = owner
        self.repo = repo
        self._username: Optional[str] = None

    def _req(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        url = f"{self.API}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            try:
                msg = json.loads(raw).get("message", raw)
            except Exception:
                msg = raw
            raise GitHubError(e.code, msg)

    @property
    def username(self) -> str:
        if self._username is None:
            self._username = self._req("GET", "/user")["login"]
        return self._username

    def get_issue(self, number: int) -> dict:
        return self._req("GET", f"/repos/{self.owner}/{self.repo}/issues/{number}")

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        return self._req("POST", f"/repos/{self.owner}/{self.repo}/issues", {
            "title": title, "body": body, "labels": labels,
        })

    def update_issue(
        self, number: int, title: str, body: str, labels: list[str], state: str
    ) -> dict:
        return self._req("PATCH", f"/repos/{self.owner}/{self.repo}/issues/{number}", {
            "title": title, "body": body, "labels": labels, "state": state,
        })

    def get_comment(self, comment_id: int) -> dict:
        return self._req(
            "GET", f"/repos/{self.owner}/{self.repo}/issues/comments/{comment_id}"
        )

    def list_issues(self, state: str = "open") -> list[dict]:
        """Fetch all issues (not PRs), paginated."""
        results = []
        page = 1
        while True:
            batch = self._req(
                "GET",
                f"/repos/{self.owner}/{self.repo}/issues"
                f"?state={state}&per_page=100&page={page}"
            )
            if not batch:
                break
            for item in batch:
                if "pull_request" not in item:  # exclude PRs
                    results.append(item)
            if len(batch) < 100:
                break
            page += 1
        return results

    def list_comments(self, issue_number: int) -> list[dict]:
        """Fetch all comments for an issue, paginated."""
        results = []
        page = 1
        while True:
            batch = self._req(
                "GET",
                f"/repos/{self.owner}/{self.repo}/issues/{issue_number}/comments"
                f"?per_page=100&page={page}"
            )
            if not batch:
                break
            results.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return results

    def create_comment(self, issue_number: int, body: str) -> dict:
        return self._req(
            "POST", f"/repos/{self.owner}/{self.repo}/issues/{issue_number}/comments",
            {"body": body},
        )

    def update_comment(self, comment_id: int, body: str) -> dict:
        return self._req(
            "PATCH", f"/repos/{self.owner}/{self.repo}/issues/comments/{comment_id}",
            {"body": body},
        )


# -----------------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------------

def cmd_check(doc: ParsedDocument) -> list[str]:
    """Validate document. Returns list of human-readable error strings."""
    errors = []
    seen_issues: dict[int, int] = {}   # number -> line_no
    seen_comments: dict[int, int] = {} # id -> line_no

    for block in doc.issue_blocks:
        il = block.issue_line

        # Duplicate numbered issues
        if isinstance(il.issue_marker, int):
            if il.issue_marker in seen_issues:
                errors.append(
                    f"Line {il.line_no + 1}: duplicate issue #{il.issue_marker} "
                    f"(first seen at line {seen_issues[il.issue_marker] + 1})"
                )
            else:
                seen_issues[il.issue_marker] = il.line_no

        # Conflicting [x] and [ ] on same line
        # (The parser resolves close_requested + open by favouring close, so
        #  we'd need to re-examine the raw line to catch this cleanly.)
        raw_tokens = [
            _classify_token(m.group(1))[0]
            for m in _TOKEN_RE.finditer(il.raw)
        ]
        if "state_close_req" in raw_tokens and "state_open" in raw_tokens:
            errors.append(
                f"Line {il.line_no + 1}: conflicting state markers [x] and [ ]"
            )

        # [gh] and [#N] on same line
        if "issue_new" in raw_tokens and "issue_num" in raw_tokens:
            errors.append(
                f"Line {il.line_no + 1}: conflicting issue markers [gh] and [#N]"
            )

        # Duplicate comment IDs
        for c in block.comment_lines:
            if isinstance(c.comment_marker, int):
                if c.comment_marker in seen_comments:
                    errors.append(
                        f"Line {c.line_no + 1}: duplicate comment id #c{c.comment_marker} "
                        f"(first seen at line {seen_comments[c.comment_marker] + 1})"
                    )
                else:
                    seen_comments[c.comment_marker] = c.line_no

    return errors


def cmd_pull(doc: ParsedDocument, cfg: Config, gh: GitHub, path: Path) -> None:
    rw = FileRewriter(doc.lines)
    refreshed = 0
    new_issues = 0
    new_comments = 0

    # Build a set of issue numbers already tracked locally
    local_issue_numbers: set[int] = {
        b.issue_line.issue_marker
        for b in doc.issue_blocks
        if isinstance(b.issue_line.issue_marker, int)
    }

    # Refresh existing tracked issues 
    for block in doc.issue_blocks:
        il = block.issue_line
        if not isinstance(il.issue_marker, int):
            continue

        number = il.issue_marker

        try:
            remote = gh.get_issue(number)
        except GitHubError as e:
            warn(f"Could not fetch issue #{number}: {e.message}")
            continue

        remote_title  = remote["title"]
        remote_body   = remote.get("body") or ""
        remote_labels = [lbl["name"] for lbl in remote.get("labels", [])]
        remote_closed = remote["state"] == "closed"

        # Determine new local state
        new_state = il.state
        if remote_closed and il.state not in ("close_requested", "closed"):
            new_state = "closed"
            print(
                f"Issue #{number} was closed on GitHub. "
                f"Local block marked [closed] — safe to delete."
            )
        elif not remote_closed and il.state == "closed":
            new_state = None  # reopened remotely

        rw.replace(il.line_no, render_issue_line(
            il.indent, number, new_state, remote_labels, remote_title
        ))
        refreshed += 1

        # Description (top-level only)
        if il.is_top_level:
            new_desc = body_to_desc_lines(remote_body)
            if block.desc_line_nos:
                rw.replace_range(
                    block.desc_line_nos[0],
                    block.desc_line_nos[-1] + 1,
                    new_desc,
                )
            elif new_desc:
                rw.insert_after(il.line_no, new_desc)

        # Comments (top-level only, if pull_comments enabled)
        if not il.is_top_level or not cfg.pull_comments:
            continue

        try:
            remote_comments = gh.list_comments(number)
        except GitHubError as e:
            warn(f"Could not fetch comments for #{number}: {e.message}")
            continue

        # Build map of locally known comment IDs
        local_comment_ids: set[int] = {
            c.comment_marker
            for c in block.comment_lines
            if isinstance(c.comment_marker, int)
        }

        # Refresh already-tracked comments
        for c in block.comment_lines:
            if not isinstance(c.comment_marker, int):
                continue
            match = next((r for r in remote_comments if r["id"] == c.comment_marker), None)
            if match is None:
                warn(f"Comment #{c.comment_marker} no longer exists on GitHub.")
                continue
            rw.replace_range(c.line_no, c.end_line_no + 1, render_comment_lines(
                c.comment_marker,
                match["user"]["login"],
                match["body"],
            ))

        # Append new remote comments not yet tracked locally
        new_remote = [r for r in remote_comments if r["id"] not in local_comment_ids]
        if new_remote:
            # Find the line to insert after: last comment line (end), or last desc line,
            # or the issue line itself — whichever is latest.
            if block.comment_lines:
                insert_after = block.comment_lines[-1].end_line_no
            elif block.desc_line_nos:
                insert_after = block.desc_line_nos[-1]
            else:
                insert_after = il.line_no

            lines_to_add = []
            for r in new_remote:
                lines_to_add.extend(render_comment_lines(
                    r["id"], r["user"]["login"], r["body"]
                ))
                new_comments += 1
                print(f"    New comment #{r['id']} from @{r['user']['login']} on #{number}")

            rw.insert_after(insert_after, lines_to_add)

    # Append new remote issues not tracked locally 
    try:
        all_remote = gh.list_issues(state="open")
    except GitHubError as e:
        warn(f"Could not list remote issues: {e.message}")
        all_remote = []

    unseen = [r for r in all_remote if r["number"] not in local_issue_numbers]

    if unseen:
        append_lines: list[str] = []
        if doc.lines and not doc.lines[-1].endswith("\n"):
            append_lines.append("\n")  # ensure clean separation
        if doc.lines:
            append_lines.append("\n")  # blank line before new block

        for r in sorted(unseen, key=lambda x: x["number"]):
            number     = r["number"]
            title      = r["title"]
            labels     = [lbl["name"] for lbl in r.get("labels", [])]
            body       = r.get("body") or ""
            closed     = r["state"] == "closed"
            state      = "closed" if closed else None

            append_lines.append(render_issue_line("", number, state, labels, title))

            if body:
                append_lines.extend(body_to_desc_lines(body))

            # Pull comments for each new issue too
            if cfg.pull_comments:
                try:
                    remote_comments = gh.list_comments(number)
                except GitHubError as e:
                    warn(f"Could not fetch comments for #{number}: {e.message}")
                    remote_comments = []
                for rc in remote_comments:
                    append_lines.extend(render_comment_lines(
                        rc["id"], rc["user"]["login"], rc["body"]
                    ))
                    new_comments += 1

            append_lines.append("\n")
            new_issues += 1
            print(f"  Pulled new issue #{number}: {title}")

        # Append to the rewriter's line list directly (beyond existing lines)
        rw.lines.extend(append_lines)

    path.write_text("".join(rw.get_result()))
    print(
        f"Pull complete. {refreshed} refreshed, "
        f"{new_issues} new issue(s), {new_comments} new comment(s)."
    )


def cmd_push(doc: ParsedDocument, cfg: Config, gh: GitHub, path: Path) -> None:
    rw = FileRewriter(doc.lines)
    created = 0
    updated = 0

    for block in doc.issue_blocks:
        il = block.issue_line
        body = desc_lines_to_body(block.desc_lines) if il.is_top_level else ""
        actual_number: Optional[int] = None

        # Create new issue 
        if il.issue_marker == "gh":
            try:
                remote = gh.create_issue(il.title, body, il.labels)
            except GitHubError as e:
                warn(f"Could not create issue '{il.title}': {e.message}")
                continue

            actual_number = remote["number"]
            created += 1
            print(f"  Created #{actual_number}: {il.title}")

            new_state = il.state
            if il.state == "close_requested":
                try:
                    gh.update_issue(actual_number, il.title, body, il.labels, "closed")
                    new_state = "closed"
                except GitHubError as e:
                    warn(f"Could not close issue #{actual_number}: {e.message}")

            rw.replace(il.line_no, render_issue_line(
                il.indent, actual_number, new_state, il.labels, il.title
            ))

        # Update existing issue 
        elif isinstance(il.issue_marker, int):
            actual_number = il.issue_marker

            if il.state == "closed":
                # Already confirmed closed — nothing to push
                continue

            target_state = "closed" if il.state == "close_requested" else "open"

            try:
                gh.update_issue(actual_number, il.title, body, il.labels, target_state)
            except GitHubError as e:
                warn(f"Could not update issue #{actual_number}: {e.message}")
                continue

            updated += 1
            print(f"  Updated #{actual_number}: {il.title}")

            if il.state == "close_requested":
                rw.replace(il.line_no, render_issue_line(
                    il.indent, actual_number, "closed", il.labels, il.title
                ))

        # Comments 
        if actual_number is None or not il.is_top_level or not cfg.push_comments:
            continue

        for c in block.comment_lines:
            if c.comment_marker == "new":
                try:
                    remote_c = gh.create_comment(actual_number, c.text)
                except GitHubError as e:
                    warn(f"Could not create comment: {e.message}")
                    continue
                comment_id = remote_c["id"]
                print(f"    Created comment #{comment_id} on #{actual_number}")
                rw.replace_range(c.line_no, c.end_line_no + 1, render_comment_lines(
                    comment_id, gh.username, c.text
                ))

            elif isinstance(c.comment_marker, int):
                try:
                    gh.update_comment(c.comment_marker, c.text)
                except GitHubError as e:
                    warn(f"Could not update comment #{c.comment_marker}: {e.message}")

    path.write_text("".join(rw.get_result()))
    print(f"Push complete. {created} created, {updated} updated.")


def cmd_sync(doc: ParsedDocument, cfg: Config, gh: GitHub, path: Path) -> None:
    errors = cmd_check(doc)
    if errors:
        print(f"Validation failed ({len(errors)} error(s)) — aborting sync:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    print("-- pull --")
    cmd_pull(doc, cfg, gh, path)

    print("-- push --")
    # Re-parse after pull so push sees the refreshed state
    doc2 = ParsedDocument(path.read_text().splitlines(keepends=True))
    cmd_push(doc2, cfg, gh, path)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def resolve_path(file_arg: Optional[str], cfg_file: str) -> Path:
    if file_arg:
        return Path(file_arg)
    repo_root = TOOL_DIR.parent.parent
    return repo_root / cfg_file


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="issue-sync",
        description="Sync a Markdown todo file with GitHub Issues.",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    for cmd, help_text in [
        ("check", "Validate file syntax without touching GitHub"),
        ("pull",  "Refresh local file from GitHub"),
        ("push",  "Push local changes to GitHub"),
        ("sync",  "check → pull → push"),
    ]:
        p = sub.add_parser(cmd, help=help_text)
        p.add_argument("file", nargs="?", default=None,
                       help="Path to sync file (default: from config)")

    args = ap.parse_args()

    # load_config() auto-generates a template and exits if config is missing
    cfg = load_config()
    path = resolve_path(getattr(args, "file", None), cfg.file)

    if not path.exists():
        path.write_text(TODO_HEADER + "\n")
        print(f"Created {path} with syntax reference header. Add your issues and run again.")
        sys.exit(0)

    lines = path.read_text().splitlines(keepends=True)
    doc = ParsedDocument(lines)

    if args.command == "check":
        errors = cmd_check(doc)
        if errors:
            print(f"Found {len(errors)} error(s):")
            for e in errors:
                print(f"  {e}")
            sys.exit(1)
        print("OK — no syntax errors found.")

    elif args.command == "pull":
        gh = GitHub(cfg.resolved_token, cfg.owner, cfg.repo)
        cmd_pull(doc, cfg, gh, path)

    elif args.command == "push":
        errors = cmd_check(doc)
        if errors:
            print(f"Validation failed ({len(errors)} error(s)) — aborting push:")
            for e in errors:
                print(f"  {e}")
            sys.exit(1)
        gh = GitHub(cfg.resolved_token, cfg.owner, cfg.repo)
        cmd_push(doc, cfg, gh, path)

    elif args.command == "sync":
        gh = GitHub(cfg.resolved_token, cfg.owner, cfg.repo)
        cmd_sync(doc, cfg, gh, path)


if __name__ == "__main__":
    main()
