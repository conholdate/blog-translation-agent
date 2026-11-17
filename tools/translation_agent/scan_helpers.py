"""
Helpers for the missing-translation scanner (scan_missing_translations.py),
kept in their own module so they can be tested without running the scanner.

- read_post_meta():      author / url / draft from a post's frontmatter
- last_commits():        last git commit (time, author, subject) of every file under a folder
- last_commit_times():   the same, times only
- outdated_langs():      translations whose index.md was committed after them
- missing_note() / extra_note() / outdated_note(): the scan sheet's Notes text
"""

import re
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, NamedTuple, Optional

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_AUTHOR_RE      = re.compile(r"^author:\s*['\"]?([^'\"]+?)['\"]?\s*$")
_URL_RE         = re.compile(r"^url:\s*['\"]?([^\s'\"]+)['\"]?")
_DRAFT_RE       = re.compile(r"^draft:\s*['\"]?true['\"]?\s*$", re.IGNORECASE)


def read_post_meta(index_md_path: str) -> Dict[str, object]:
    """
    Return {"author": str, "url": str, "draft": bool} from the post's frontmatter.

    Only the frontmatter block is read, so every key is checked wherever it sits
    (a draft flag after author/url is no longer missed) and body text such as
    "author: ..." can't be picked up. Opened with utf-8-sig: some editors save
    index.md with a BOM. Missing keys come back as "" / False.
    """
    meta = {"author": "", "url": "", "draft": False}
    with open(index_md_path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        line = line.strip()
        if not meta["author"] and (a := _AUTHOR_RE.match(line)):
            meta["author"] = a.group(1).strip()
        elif not meta["url"] and (u := _URL_RE.match(line)):
            meta["url"] = u.group(1).strip()
        elif _DRAFT_RE.match(line):
            meta["draft"] = True
    return meta


class Commit(NamedTuple):
    time: int        # unix seconds, committer date
    author: str
    subject: str


def last_commits(folder: str) -> Optional[Dict[str, Commit]]:
    """
    Map each file under `folder` (path relative to it, '/' separated) to the
    latest commit that changed it.

    One `git log` pass over the folder — a few seconds for a whole blog. Needs the
    full history (the scan workflow checks out with fetch-depth: 0).
    Returns None when the folder isn't inside a git repo, has no committed files,
    or git fails (e.g. the local test mirror), so the caller can skip the check.
    """
    try:
        out = subprocess.run(
            ["git", "-c", "core.quotepath=off", "-C", folder, "log",
             "--format=@%ct%x09%an%x09%s", "--name-only", "--relative", "--", "."],
            capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None

    commits: Dict[str, Commit] = {}
    current = None
    for line in out.splitlines():
        if line.startswith("@"):
            ts, _, rest = line[1:].partition("\t")
            author, _, subject = rest.partition("\t")
            current = Commit(int(ts), author, subject)
        elif line and current:
            # git log isn't strictly date-ordered across merges: keep the newest
            if line not in commits or current.time > commits[line].time:
                commits[line] = current
    return commits or None


def last_commit_times(folder: str) -> Optional[Dict[str, int]]:
    """last_commits(), times only: {path: unix seconds}, or None (see last_commits)."""
    commits = last_commits(folder)
    return {path: c.time for path, c in commits.items()} if commits else None


def outdated_langs(times: Dict[str, int], post_rel_dir: str, langs: List[str]) -> List[str]:
    """
    Languages (of `langs`, whose index.{lang}.md exists) last committed before
    the post's index.md. Files git doesn't know about (not committed yet) are
    never reported. A fix committed to index.md and its translations together
    leaves them equal, so it doesn't count as outdated.
    """
    en = times.get(f"{post_rel_dir}/index.md")
    if en is None:
        return []
    return [lang for lang in langs
            if (t := times.get(f"{post_rel_dir}/index.{lang}.md")) is not None and t < en]


# ---------------------------------------------------------------------------
# Notes column — why a row was flagged
# ---------------------------------------------------------------------------

def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def missing_note(n_missing: int, n_supported: int) -> str:
    """'New post' when no translation exists yet, else 'N of M languages missing'."""
    if n_missing >= n_supported:
        return "New post"
    return f"{n_missing} of {n_supported} languages missing"


def extra_note() -> str:
    return "Unsupported language file(s) — not a language of this blog"


def outdated_note(commits: Dict[str, Commit], post_rel_dir: str, langs: List[str],
                  subject_max: int = 80) -> str:
    """
    E.g. 'English updated 2026-11-16 by optimizer-agent ("Optimized Blog Posts");
    translations from 2025-05-09' — the English file's last commit, and the
    date (or date range) of the outdated translations' last commits.
    """
    en = commits.get(f"{post_rel_dir}/index.md")
    if not en:
        return ""
    subject = en.subject if len(en.subject) <= subject_max else en.subject[:subject_max - 1] + "…"
    note = f'English updated {_date(en.time)} by {en.author} ("{subject}")'
    times = sorted(c.time for l in langs if (c := commits.get(f"{post_rel_dir}/index.{l}.md")))
    if times:
        first, last = _date(times[0]), _date(times[-1])
        note += f"; translations from {first}" if first == last else f"; translations from {first} to {last}"
    return note
