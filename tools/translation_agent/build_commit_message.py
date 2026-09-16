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
import config

LANG_NAMES = {
    "ar": "Arabic",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "fa": "Persian",
    "fr": "French",
    "he": "Hebrew",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ka": "Georgian",
    "ko": "Korean",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ru": "Russian",
    "sv": "Swedish",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
    "zh": "Chinese (Simplified)",
    "zh-hant": "Chinese (Traditional)",
    "zh-tw": "Chinese (Traditional)",
}


def _lang_label(code: str) -> str:
    return f"{LANG_NAMES.get(code, code)} ({code})"


def _domain_lang_order(domain: str) -> list:
    """Canonical per-domain language order from config.py, if known."""
    data = config.domains_data.get(domain)
    if not data:
        return []
    return data[config.KEY_SUPPORTED_LANGS].split("|")


def _sort_langs(langs: list, domain: str) -> list:
    order = _domain_lang_order(domain)
    if not order:
        return sorted(langs)
    rank = {code: i for i, code in enumerate(order)}
    return sorted(langs, key=lambda c: (rank.get(c, len(order)), c))


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

    if not groups:
        return f"Daily Blogs Translation: {domain}"

    if len(groups) == 1:
        ((post_dir, group),) = groups.items()
        langs = _sort_langs(group["langs"], domain)
        title_line = f'Translate articles for: "{group["title"]}"'
        noun = "language" if len(langs) == 1 else "languages"
        body_lines = [f"Added translations in {len(langs)} {noun}:", ""]
        body_lines += [f"- {_lang_label(c)}" for c in langs]
        return title_line + "\n\n" + "\n".join(body_lines)

    title_line = f"Translate articles for {len(groups)} posts ({domain})"
    body_lines = [f"Added translations across {len(groups)} posts:", ""]
    for post_dir, group in groups.items():
        langs = _sort_langs(group["langs"], domain)
        noun = "language" if len(langs) == 1 else "languages"
        body_lines.append(f'"{group["title"]}" — {len(langs)} {noun}:')
        body_lines += [f"- {_lang_label(c)}" for c in langs]
        body_lines.append("")
    return title_line + "\n\n" + "\n".join(body_lines).rstrip()


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    print(build_message(args.domain, args.files))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
