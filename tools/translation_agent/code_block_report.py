"""
Read-only report: which translations have code blocks that differ from the English.

Usage:
    python code_block_report.py <content-dir> [<content-dir> ...] [--csv out.csv] [--list]

For every post folder with an English index.md, each index.{lang}.md is put in
one category (first match wins):
  markers    git conflict markers (`<<<<<<< ` / `>>>>>>> ` lines) - shown as text on the page
  legacy     the translation has the English code blocks (identical, in order) plus at most
             one extra block per English {{< gist >}} (older translations pasted gist code
             inline) - renders fine, not this bug
  structure  the fence lines differ from the English (count, ```lang info strings
             or order) - code renders as text and text as code
  code       same fences, but code inside differs (e.g. translated code comments)
  ok         identical code blocks
It also checks that protect/restore (code_blocks.py) gives back every English
index.md byte for byte, so the placeholder parser is proven on real posts.

Nothing is changed: no files, no sheets, no LLM calls. Added 27 Nov 2026 to
size the damage from the code-block bug fixed in code_blocks.py.
"""

import argparse
import csv
import glob
import os
import re
import sys
from collections import Counter, defaultdict

from code_blocks import code_blocks, protect_code_blocks, restore_code_blocks

_FRONTMATTER = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_CONFLICT = re.compile(r"^(<<<<<<<|>>>>>>>) ", re.MULTILINE)


def _body(path: str) -> str:
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return _FRONTMATTER.sub("", f.read(), count=1)


def _fences(blocks):
    return [(b.split("\n")[0].strip(), b.split("\n")[-1].strip()) for b in blocks]


_GIST = re.compile(r"\{\{<\s*gist\b")


def _legacy_gists(english: str, en: list, tr: list) -> bool:
    """Translation = the English blocks (in order) plus at most one block per English gist."""
    extra = len(tr) - len(en)
    if extra <= 0 or extra > len(_GIST.findall(english)):
        return False
    it = iter(tr)
    return all(any(b == t for t in it) for b in en)


def classify(english: str, translation: str) -> str:
    if _CONFLICT.search(translation):
        return "markers"
    en, tr = code_blocks(english), code_blocks(translation)
    if _legacy_gists(english, en, tr):
        return "legacy"
    if _fences(en) != _fences(tr):
        return "structure"
    return "ok" if en == tr else "code"


def scan(content_dirs):
    """Yields (english_path, lang, category) and (english_path, None, 'roundtrip-fail')."""
    for root in content_dirs:
        for en_path in sorted(glob.glob(os.path.join(root, "**", "index.md"), recursive=True)):
            english = _body(en_path)
            protected, blocks = protect_code_blocks(english)
            if restore_code_blocks(protected, blocks) != english:
                yield en_path, None, "roundtrip-fail"
            folder = os.path.dirname(en_path)
            for tr_path in sorted(glob.glob(os.path.join(folder, "index.*.md"))):
                lang = os.path.basename(tr_path)[len("index."):-len(".md")]
                yield en_path, lang, classify(english, _body(tr_path))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("content_dirs", nargs="+")
    parser.add_argument("--csv", help="write every non-ok file to this CSV")
    parser.add_argument("--list", action="store_true", help="print every non-ok file")
    args = parser.parse_args(argv)

    totals, posts, rows = Counter(), defaultdict(set), []
    for en_path, lang, cat in scan(args.content_dirs):
        totals[cat] += 1
        if cat != "ok":
            posts[cat].add(os.path.dirname(en_path))
            rows.append((cat, os.path.dirname(en_path), lang or ""))
            if args.list:
                print(f"{cat:<15} {lang or '-':<8} {os.path.dirname(en_path)}")

    for cat in ("markers", "structure", "code", "legacy", "ok", "roundtrip-fail"):
        if totals[cat]:
            extra = f" in {len(posts[cat])} post(s)" if cat != "ok" else ""
            print(f"{cat:<15} {totals[cat]:>7} file(s){extra}")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["category", "post_folder", "lang"])
            w.writerows(rows)
    return 1 if totals["roundtrip-fail"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
