"""
Concise run logging for the translation pipeline.

- info(...)    always printed: post headers, one line per language, results, errors.
- detail(...)  step-by-step output (paragraphs, token tables, payloads):
                 * TRANSLATION_VERBOSE=1 (or --verbose)  -> printed inline
                 * GitHub Actions                         -> printed inside a collapsible
                                                             group (see group())
                 * otherwise (local default)              -> hidden
- group(title) wraps a block of detail output; in GitHub Actions it becomes a
  collapsed ::group:: section so the main log stays short.
"""

import os
from contextlib import contextmanager

VERBOSE = os.getenv("TRANSLATION_VERBOSE", "").strip().lower() in ("1", "true", "yes")
IN_CI = os.getenv("GITHUB_ACTIONS") == "true"

_group_open = False


def set_verbose(enabled: bool):
    global VERBOSE
    VERBOSE = bool(enabled)


def info(*args, **kwargs):
    print(*args, **kwargs, flush=True)


def detail(*args, **kwargs):
    if VERBOSE or _group_open:
        print(*args, **kwargs)


@contextmanager
def group(title: str):
    """Collapsible block of detail output in GitHub Actions; no-op elsewhere."""
    global _group_open
    use_group = IN_CI and not VERBOSE and not _group_open   # groups can't nest
    if use_group:
        print(f"::group::{title}", flush=True)
        _group_open = True
    try:
        yield
    finally:
        if use_group:
            _group_open = False
            print("::endgroup::", flush=True)


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def fmt_tokens(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)
