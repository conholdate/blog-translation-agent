"""
Localize internal links in a translated post.

A link to another post on the same blog gets the language prefix
(https://{domain}/{lang}/...) only when that post's translation exists, either
on disk (index.{lang}.md) or queued in the current run. Every other link is
kept exactly as in the English post, so translations never point at a 404.

Section and taxonomy pages (/total/, /tags/x/, ...) are not posts and are left
unchanged: many of them don't exist in every language (or at all).
"""

import re
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

_FRONTMATTER_URL = re.compile(r'^url:\s*["\']?([^"\'\s]+)["\']?\s*$', re.MULTILINE)
_CODE_FENCE = re.compile(r'(^```.*?^```[^\n]*$)', re.MULTILINE | re.DOTALL)


def _normalize_path(path: str) -> str:
    """'/total/foo' -> '/total/foo/' (no query or fragment, single trailing slash)."""
    path = re.split(r'[?#]', path, maxsplit=1)[0]
    if not path.startswith('/'):
        path = '/' + path
    return path.rstrip('/') + '/'


def build_url_index(content_root: str) -> Dict[str, Path]:
    """Map each post's frontmatter url (normalized) to its folder."""
    index: Dict[str, Path] = {}
    for md in Path(content_root).rglob('index.md'):
        try:
            with open(md, 'r', encoding='utf-8-sig') as f:
                head = f.read(4096)
        except OSError:
            continue
        frontmatter = head.split('\n---', 1)[0]
        match = _FRONTMATTER_URL.search(frontmatter)
        if match:
            index[_normalize_path(match.group(1))] = md.parent
    return index


class LinkLocalizer:
    """Per-domain link localizer. Build once per run and reuse for every post."""

    def __init__(self, domain: str, content_root: str):
        self.domain = domain
        self.content_root = content_root
        self.url_index = build_url_index(content_root)
        # (post folder, lang) pairs that will be translated in this run
        self.queued: Set[Tuple[str, str]] = set()

        host = re.escape(domain)
        # Absolute links to this blog, or root-relative links in markdown / href targets
        self._link = re.compile(
            rf'(?P<abs>https?://{host})(?P<abspath>/[^\s)"\'<>\]]*)'
            rf'|(?P<lead>\]\(|href=["\'])(?P<relpath>/(?!/)[^\s)"\'<>\]]*)'
        )
        print(f"   🔗 Link index for {domain}: {len(self.url_index)} posts")

    def queue(self, product: str, slug: str, lang: str):
        """Register a translation that is pending in the current run."""
        folder = Path(self.content_root) / product / slug
        self.queued.add((str(folder), lang.strip()))

    def translation_exists(self, path: str, lang: str) -> Optional[bool]:
        """True/False for a known post; None when the path is not a post."""
        folder = self.url_index.get(_normalize_path(path))
        if folder is None:
            return None
        return (folder / f'index.{lang}.md').exists() or (str(folder), lang) in self.queued

    def _localize_path(self, path: str, lang: str) -> str:
        # The LLM may have added the prefix itself; decide from the English path.
        prefix = f'/{lang}/'
        english = '/' + path[len(prefix):] if path.startswith(prefix) else path
        exists = self.translation_exists(english, lang)
        if exists:
            return prefix + english.lstrip('/')
        if exists is False:
            print(f"   🔗 Kept English link (no '{lang}' translation): {english}")
        return english

    def _localize_segment(self, text: str, lang: str) -> str:
        def replace(m: re.Match) -> str:
            if m.group('abs'):
                return m.group('abs') + self._localize_path(m.group('abspath'), lang)
            return m.group('lead') + self._localize_path(m.group('relpath'), lang)
        return self._link.sub(replace, text)

    def localize(self, content: str, lang: str) -> str:
        """Rewrite internal links in markdown content, leaving fenced code blocks alone."""
        parts = _CODE_FENCE.split(content)
        return ''.join(
            part if part.startswith('```') else self._localize_segment(part, lang)
            for part in parts
        )
