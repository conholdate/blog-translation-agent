"""
Builds a descriptive git commit message (title + body) for a translation-agent
run, from the list of markdown files staged for commit.

Usage:
    python build_commit_message.py --domain <domain> <staged-file-path> [...]

Reads each file's YAML frontmatter `title` via translator.parse_markdown_file
and groups files by post directory, so multiple language files of the same
post collapse into a single entry.
"""

import argparse
import os
import sys

from translator import parse_markdown_file


def _lang_from_filename(file_path: str) -> str:
    """index.ja.md -> 'ja'; index.md -> 'en' (source language)."""
    name = os.path.basename(file_path)
    parts = name.split(".")
    if len(parts) >= 3 and parts[0] == "index":
        return parts[1]
    return "en"


def _post_title(post_dir: str, files: list) -> str:
    """
    Prefer the English source post's title (index.md) since translated
    titles vary by language; fall back to a translated file, then the
    directory name.
    """
    candidates = [os.path.join(post_dir, "index.md")] + files
    for file_path in candidates:
        try:
            parsed = parse_markdown_file(file_path)
            title = parsed["frontmatter"].get("title")
            if title:
                return str(title)
        except Exception:
            continue
    return os.path.basename(post_dir.rstrip("/")) or post_dir


def group_by_post(file_paths: list) -> "dict[str, dict]":
    """Group staged markdown files by their parent (post) directory."""
    groups: "dict[str, dict]" = {}
    for file_path in file_paths:
        if not file_path.lower().endswith(".md"):
            continue
        post_dir = os.path.dirname(file_path)
        group = groups.setdefault(post_dir, {"files": [], "langs": []})
        group["files"].append(file_path)
        lang = _lang_from_filename(file_path)
        if lang not in group["langs"]:
            group["langs"].append(lang)

    for post_dir, group in groups.items():
        group["title"] = _post_title(post_dir, group["files"])

    return groups


def build_message(domain: str, file_paths: list) -> str:
    groups = group_by_post(file_paths)
    total_files = sum(len(g["files"]) for g in groups.values())

    if not groups:
        return f"Daily Blogs Translation: {domain}"

    if len(groups) == 1:
        ((post_dir, group),) = groups.items()
        title_line = f'Translate blog post: "{group["title"]}" ({domain})'
        langs = ", ".join(group["langs"])
        body_lines = [
            f'Added {langs} translation(s) for "{group["title"]}".',
            "",
            f"Files ({total_files}):",
        ]
        body_lines += [f"- {f}" for f in group["files"]]
        return title_line + "\n\n" + "\n".join(body_lines)

    title_line = f"Translate {len(groups)} blog posts for {domain}"
    body_lines = [
        f"Adding the following translations ({total_files} files across {len(groups)} posts):",
        "",
    ]
    for post_dir, group in groups.items():
        langs = ", ".join(group["langs"])
        body_lines.append(f'- "{group["title"]}" ({langs}) - {post_dir}')
    return title_line + "\n\n" + "\n".join(body_lines)


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    print(build_message(args.domain, args.files))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
