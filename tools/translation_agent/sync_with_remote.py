"""
Brings the blog checkout up to date with the remote before committing, keeping
this run's translations exactly as the agent wrote them.

Usage (cwd inside the target repo checkout, after `git fetch origin`):
    python sync_with_remote.py --ref origin/<default-branch>

Why not `git merge --ff-only --autostash` (used until 27 Nov 2026):
a run takes 10 min to 5 h. When another commit changed the same translation
file meanwhile (e.g. the Health and Recovery Agent's fix 4b6eda6a on
blog.groupdocs.cloud), the autostash re-apply conflicted, git left
`<<<<<<< Updated upstream` / `>>>>>>> Stashed changes` markers in the files, the
step did not fail, and `git add content/` committed them (ec990f7b, 4 files).

What this does instead:
  1. Saves every file under content/ that the run added, changed or deleted
     (git status, untracked files included).
  2. `git reset --hard <ref>`: the checkout now matches the remote exactly.
  3. Writes the saved files back and repeats the deletions.
The agent's version wins: a translation run replaces the whole file, and if the
English changed meanwhile the next scan flags the file as OUTDATED again.
A file whose post folder no longer has an English index.md on the remote (post
moved or removed meanwhile) is not written back, so no orphan folder appears.
"""

import argparse
import os
import subprocess
import sys


def _git(*args) -> str:
    return subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        capture_output=True, text=True, check=True,
    ).stdout


def changed_content_files(root: str = "content/") -> dict:
    """Path -> 'write' (file on disk, new or changed) or 'delete' (removed by the run)."""
    out = _git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames", "--", root)
    changes = {}
    for entry in out.split("\0"):
        if len(entry) < 4:
            continue
        path = entry[3:]
        changes[path] = "write" if os.path.isfile(path) else "delete"
    return changes


def sync_with_remote(ref: str, root: str = "content/") -> dict:
    """Reset to `ref` and re-apply this run's content changes. Returns a summary."""
    changes = changed_content_files(root)
    saved = {}
    for path, action in changes.items():
        if action == "write":
            with open(path, "rb") as f:
                saved[path] = f.read()
            os.remove(path)          # an untracked file must not block the reset

    _git("reset", "--hard", "-q", ref)

    summary = {"written": [], "deleted": [], "dropped": []}
    for path, data in saved.items():
        if not os.path.isfile(os.path.join(os.path.dirname(path), "index.md")):
            summary["dropped"].append(path)
            continue
        with open(path, "wb") as f:
            f.write(data)
        summary["written"].append(path)
    for path, action in changes.items():
        if action == "delete" and os.path.isfile(path):
            os.remove(path)
            summary["deleted"].append(path)
    return summary


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True, help="e.g. origin/master")
    args = parser.parse_args(argv)

    summary = sync_with_remote(args.ref)
    print(f"Synced with {args.ref}: {len(summary['written'])} file(s) written back, "
          f"{len(summary['deleted'])} deletion(s) re-applied.")
    for path in summary["dropped"]:
        print(f"::warning::Not written back (no English index.md on {args.ref}): {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
