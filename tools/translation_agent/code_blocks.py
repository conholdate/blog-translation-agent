"""
Keeps fenced code blocks away from the LLM and checks them after translation.

Before translation, every fenced code block (``` or ~~~, opening line to closing
line) is replaced by one placeholder line such as `⟦CODE_3⟧`, together with the
`<!--[CODE_SNIPPET_START]-->` / `<!--[CODE_SNIPPET_END]-->` /
`<!--[COMPLETE_CODE_SNIPPET_START]-->` / `<!--[COMPLETE_CODE_SNIPPET_END]-->`
marker lines next to it (blank lines between marker and fence included).
After translation each placeholder line is replaced by its block, byte for byte.

Why (27 Nov 2026, blog.groupdocs.cloud, ec990f7b): the paragraph chunker splits
at blank lines and only re-joined code blocks while the ``` count was odd; the
model moved a fence (count unchanged, so the count check passed), half of each
code sample rendered as text, and code comments were translated in 14 languages.
With placeholders the model never sees code: code and its comments stay English.

Checks:
  - placeholders_intact(chunk, translated): every placeholder of the chunk is
    back exactly once, in the same order, on its own line, and none was added.
  - code_block_problem(english, translation): the whole translated body has the
    same fenced blocks as the English (count, fence lines incl. info string such
    as ```python, order, identical code); returns a reason or None.
"""

import re
from typing import List, Optional, Tuple

_FENCE_OPEN = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*?)[ \t\r]*$")
_FENCE_CLOSE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t\r]*$")
_MARKER = re.compile(r"^[ \t]*<!--\s*\[[A-Z_]*CODE_SNIPPET_(START|END)\]\s*-->[ \t\r]*$")
_PLACEHOLDER_LINE = re.compile(r"^[ \t]*⟦CODE_(\d+)⟧[ \t\r]*$")
_PLACEHOLDER_ANY = re.compile(r"⟦CODE_\d+⟧")


def placeholder(n: int) -> str:
    return f"⟦CODE_{n}⟧"


def find_fenced_blocks(lines: List[str]) -> List[Tuple[int, int]]:
    """(first, last) line index of each fenced block, fence lines included.

    A block closes at a line holding only the same fence character, at least as
    many times as the opening fence (CommonMark); a line like `print("```")`
    does not close it. An unclosed block runs to the end of the text.
    """
    blocks, i, n = [], 0, len(lines)
    while i < n:
        m = _FENCE_OPEN.match(lines[i])
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            char, length = m.group(1)[0], len(m.group(1))
            j = i + 1
            while j < n:
                c = _FENCE_CLOSE.match(lines[j])
                if c and c.group(1)[0] == char and len(c.group(1)) >= length:
                    break
                j += 1
            end = min(j, n - 1)
            blocks.append((i, end))
            i = end + 1
        else:
            i += 1
    return blocks


def _marker(line: str, kind: str) -> bool:
    m = _MARKER.match(line)
    return bool(m) and m.group(1) == kind


def protect_code_blocks(content: str) -> Tuple[str, List[str]]:
    """Replace each fenced block (and its snippet markers) with a placeholder line."""
    lines = content.split("\n")
    spans, prev_end = [], -1
    fenced = find_fenced_blocks(lines)
    for idx, (start, end) in enumerate(fenced):
        next_start = fenced[idx + 1][0] if idx + 1 < len(fenced) else len(lines)
        k = start - 1
        while k > prev_end and not lines[k].strip():
            k -= 1
        if k > prev_end and _marker(lines[k], "START"):
            start = k
        k = end + 1
        while k < next_start and not lines[k].strip():
            k += 1
        if k < next_start and _marker(lines[k], "END"):
            end = k
        spans.append((start, end))
        prev_end = end

    out, blocks, i = [], [], 0
    for start, end in spans:
        out.extend(lines[i:start])
        indent = re.match(r"[ \t]*", lines[start]).group(0)
        out.append(indent + placeholder(len(blocks)))
        blocks.append("\n".join(lines[start:end + 1]))
        i = end + 1
    out.extend(lines[i:])
    return "\n".join(out), blocks


def restore_code_blocks(text: str, blocks: List[str]) -> str:
    """Put every block back in place of its placeholder line."""
    out = []
    for line in text.split("\n"):
        m = _PLACEHOLDER_LINE.match(line)
        if m and int(m.group(1)) < len(blocks):
            out.append(blocks[int(m.group(1))])
        else:
            out.append(line)
    return "\n".join(out)


def _placeholder_lines(text: str) -> List[int]:
    return [int(m.group(1)) for m in map(_PLACEHOLDER_LINE.match, text.split("\n")) if m]


def placeholders_intact(original: str, translated: str) -> bool:
    """Same placeholders, same order, each on its own line, none added or glued to text."""
    expected = _placeholder_lines(original)
    return (_placeholder_lines(translated) == expected
            and len(_PLACEHOLDER_ANY.findall(translated)) == len(expected))


def only_placeholders(chunk: str) -> bool:
    """True when the chunk has nothing to translate (only placeholder and blank lines)."""
    lines = [l for l in chunk.split("\n") if l.strip()]
    return bool(lines) and all(_PLACEHOLDER_LINE.match(l) for l in lines)


def code_blocks(text: str) -> List[str]:
    lines = text.split("\n")
    return ["\n".join(lines[s:e + 1]) for s, e in find_fenced_blocks(lines)]


def code_block_problem(english: str, translation: str) -> Optional[str]:
    """Reason the translation's code blocks differ from the English, or None."""
    if _PLACEHOLDER_ANY.search(translation):
        return "a code placeholder was left in the text"
    en, tr = code_blocks(english), code_blocks(translation)
    if len(en) != len(tr):
        return f"{len(tr)} code blocks instead of {len(en)}"
    for n, (a, b) in enumerate(zip(en, tr), 1):
        if a != b:
            first = a.split("\n", 1)[0].strip()
            return f"code block {n} ({first}) differs from the English"
    return None


class CodeBlockMismatch(ValueError):
    """The translated file's code blocks differ from the English; the file is not written."""
