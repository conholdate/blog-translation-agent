"""
Helpers for the missing-translation scanner (scan_missing_translations.py),
kept in their own module so they can be tested without running the scanner.

- read_post_meta():      author / url / draft from a post's frontmatter
- last_commit_times():   last git commit time of every file under a folder
- outdated_langs():      translations whose index.md was committed after them
"""

import re
import subprocess
from typing import Dict, List, Optional

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


def last_commit_times(folder: str) -> Optional[Dict[str, int]]:
    """
    Map each file under `folder` (path relative to it, '/' separated) to the
    latest commit time (unix seconds, committer date) of a commit that changed it.

    One `git log` pass over the folder — a few seconds for a whole blog. Needs the
    full history (the scan workflow checks out with fetch-depth: 0).
    Returns None when the folder isn't inside a git repo or git fails (e.g. the
    local test mirror), so the caller can skip the outdated check.
    """
    try:
        out = subprocess.run(
            ["git", "-c", "core.quotepath=off", "-C", folder, "log",
             "--format=@%ct", "--name-only", "--relative", "--", "."],
            capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None

    times: Dict[str, int] = {}
    ts = 0
    for line in out.splitlines():
        if line.startswith("@"):
            ts = int(line[1:])
        elif line:
            # git log isn't strictly date-ordered across merges: keep the newest
            if ts > times.get(line, -1):
                times[line] = ts
    return times or None


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
