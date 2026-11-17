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


# git status letter -> change kind. Translations are added (new post or
# language), modified (OUTDATED row: retranslated after the English post
# changed) or deleted (EXTRA row: unsupported file removed).
ADDED, UPDATED, REMOVED = "added", "updated", "removed"
_STATUS_KIND = {"A": ADDED, "M": UPDATED, "D": REMOVED}

# Title verb per set of change kinds; any other mix is "Update translations"
_TITLE_VERB = {
    frozenset({ADDED}):   "Translate articles",
    frozenset({UPDATED}): "Retranslate articles",
    frozenset({REMOVED}): "Remove extra translations",
}
_MIXED_VERB = "Update translations"


def _kind(file_path: str, statuses: "dict | None") -> str:
    """Change kind of a file; unknown or no status means added (the original behaviour)."""
    return _STATUS_KIND.get((statuses or {}).get(file_path, "A")[:1], ADDED)


def _post_sections(group: dict, domain: str, statuses: "dict | None") -> list:
    """[(kind, sorted langs)] for one post, in added / updated / removed order."""
    by_kind = {}
    for file_path in group["files"]:
        lang = _lang_from_filename(file_path)
        langs = by_kind.setdefault(_kind(file_path, statuses), [])
        if lang not in langs:
            langs.append(lang)
    return [(k, _sort_langs(by_kind[k], domain)) for k in (ADDED, UPDATED, REMOVED) if k in by_kind]


def _verb(kinds) -> str:
    return _TITLE_VERB.get(frozenset(kinds), _MIXED_VERB)


def _section_heading(kind: str, langs: list, where: str = "") -> str:
    noun = "language" if len(langs) == 1 else "languages"
    if kind == UPDATED:
        return f"Retranslated {len(langs)} {noun}{where} (English post was updated):"
    if kind == REMOVED:
        return f"Removed extra files in {len(langs)} {noun}{where}:"
    return f"Added translations in {len(langs)} {noun}{where}:"


def build_message(domain: str, file_paths: list, statuses: "dict | None" = None) -> str:
    """
    statuses maps a file path to its git status letter (A/M/D, as printed by
    `git diff --cached --name-status`); files without one count as added.
    """
    groups = group_by_post(file_paths)

    if not groups:
        return f"Daily Blogs Translation: {domain}"

    if len(groups) == 1:
        ((post_dir, group),) = groups.items()
        sections = _post_sections(group, domain, statuses)
        file_noun = "file" if len(group["files"]) == 1 else "files"
        title_line = (f'{_verb(k for k, _ in sections)} for: "{group["title"]}"'
                      f' - ({len(group["files"])} {file_noun})')
        body_lines = []
        for kind, langs in sections:
            body_lines += [_section_heading(kind, langs), ""]
            body_lines += [f"- {_lang_label(c)}" for c in langs]
            body_lines.append("")
        return title_line + "\n\n" + "\n".join(body_lines).rstrip()

    all_sections = {post_dir: _post_sections(group, domain, statuses) for post_dir, group in groups.items()}
    kinds = {k for sections in all_sections.values() for k, _ in sections}
    title_line = f"{_verb(kinds)} for {len(groups)} posts ({domain})"
    body_lines = []
    if kinds == {ADDED}:
        body_lines += [f"Added translations across {len(groups)} posts:", ""]
    for post_dir, group in groups.items():
        for kind, langs in all_sections[post_dir]:
            noun = "language" if len(langs) == 1 else "languages"
            if kinds == {ADDED}:
                body_lines.append(f'"{group["title"]}" — {len(langs)} {noun}:')
            else:
                heading = _section_heading(kind, langs)
                body_lines.append(f'"{group["title"]}" — {heading[0].lower()}{heading[1:]}')
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
