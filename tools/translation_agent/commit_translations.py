"""
Commits files already staged by `git add` as one commit PER translated post,
instead of one commit bundling every post in the run.

Usage (run with cwd inside the target repo checkout, after `git add content/`):
    python commit_translations.py --domain <domain>

Reuses the grouping/message-building already in build_commit_message.py so
each post's commit message matches the single-post format exactly.
"""

import argparse
import subprocess
import sys

from build_commit_message import group_by_post, build_message


def get_staged_files() -> list:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def commit_staged_translations(domain: str) -> int:
    """Commit each staged post separately. Returns the number of commits made."""
    groups = group_by_post(get_staged_files())

    if not groups:
        print("No translation changes to commit.")
        return 0

    total_files = 0
    for post_dir, group in groups.items():
        msg = build_message(domain, group["files"])
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
