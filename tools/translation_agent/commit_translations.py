"""
Commits files already staged by `git add` as one commit PER translated post,
instead of one commit bundling every post in the run.

Usage (run with cwd inside the target repo checkout, after `git add content/`):
    python commit_translations.py --domain <domain>

Reuses the grouping/message-building already in build_commit_message.py so
each post's commit message matches the single-post format exactly. Each file's
git status picks the wording: added -> "Translate articles", modified ->
"Retranslate articles" (OUTDATED rows), deleted -> "Remove extra translations".

Git conflict markers are never committed: a staged file with a line starting
with `<<<<<<< ` or `>>>>>>> ` is unstaged and reported, the other files are
committed as usual (ec990f7b on blog.groupdocs.cloud, 27 Nov 2026, put
`<<<<<<< Updated upstream` on 4 live pages).
"""

import argparse
import os
import re
import subprocess
import sys

from build_commit_message import group_by_post, build_message

CONFLICT_MARKER = re.compile(r"^(<<<<<<<|>>>>>>>) ", re.MULTILINE)


def has_conflict_markers(path: str) -> bool:
    """True when the file has a git conflict marker line (`<<<<<<< x` / `>>>>>>> x`)."""
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8", errors="replace") as f:
        return bool(CONFLICT_MARKER.search(f.read()))


def unstage_conflicted(statuses: dict) -> list:
    """Unstage files that hold conflict markers; returns their paths."""
    bad = [p for p in statuses if has_conflict_markers(p)]
    if bad:
        subprocess.run(["git", "reset", "-q", "--", *bad], check=True)
        for path in bad:
            print(f"::error::Not committed - git conflict markers in {path}")
    return bad


def get_staged_changes() -> dict:
    """Staged file -> git status letter: A (added), M (retranslated), D (deleted)."""
    result = subprocess.run(
        ["git", "-c", "core.quotepath=off", "diff", "--cached", "--name-status", "--no-renames"],
        capture_output=True, text=True, check=True,
    )
    changes = {}
    for line in result.stdout.splitlines():
        status, _, path = line.partition("\t")
        if path:
            changes[path] = status[:1]
    return changes


def get_staged_files() -> list:
    return list(get_staged_changes())


def commit_staged_translations(domain: str) -> int:
    """Commit each staged post separately. Returns the number of commits made."""
    statuses = get_staged_changes()
    for path in unstage_conflicted(statuses):
        del statuses[path]
    groups = group_by_post(list(statuses))

    if not groups:
        print("No translation changes to commit.")
        return 0

    total_files = 0
    for post_dir, group in groups.items():
        msg = build_message(domain, group["files"], statuses)
        subprocess.run(
            ["git", "commit", "-m", msg, "--", *group["files"]],
            check=True,
        )
        total_files += len(group["files"])

    print(f"Committed {len(groups)} post(s), {total_files} file(s) total.")
    return len(groups)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    args = parser.parse_args(argv)

    commit_staged_translations(args.domain)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
