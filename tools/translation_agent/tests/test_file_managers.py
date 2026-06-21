"""
Tests for translation_files_managers.delete_translation_files — pure filesystem
logic (no LLM, no network). Builds a temp content tree and checks which files
are removed.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from translation_files_managers import delete_translation_files


def _make(path, name, text="x"):
    with open(os.path.join(path, name), "w", encoding="utf-8") as f:
        f.write(text)


def test_deletes_only_invalid_language_files(tmp_path):
    post = tmp_path / "product_A" / "2021-some-post"
    post.mkdir(parents=True)
    p = str(post)

    _make(p, "index.ar.md")      # valid lang
    _make(p, "index.es.md")      # valid lang
    _make(p, "index.cs.md")      # invalid lang -> delete
    _make(p, "index.xx.md")      # invalid lang -> delete
    _make(p, "index.md")         # English source (2 parts) -> kept
    _make(p, "other_file.txt")   # not index.*.md -> kept

    delete_translation_files(str(tmp_path), "ar|es")

    remaining = set(os.listdir(p))
    assert "index.ar.md" in remaining
    assert "index.es.md" in remaining
    assert "index.md" in remaining
    assert "other_file.txt" in remaining
    assert "index.cs.md" not in remaining
    assert "index.xx.md" not in remaining


def test_keeps_all_when_every_lang_is_valid(tmp_path):
    post = tmp_path / "p" / "2022-post"
    post.mkdir(parents=True)
    p = str(post)
    _make(p, "index.de.md")
    _make(p, "index.fr.md")

    delete_translation_files(str(tmp_path), "de|fr")

    assert set(os.listdir(p)) == {"index.de.md", "index.fr.md"}


def test_lang_code_is_case_insensitive(tmp_path):
    post = tmp_path / "p" / "2023-post"
    post.mkdir(parents=True)
    p = str(post)
    _make(p, "index.AR.md")   # upper-case lang, valid set has lower 'ar'

    delete_translation_files(str(tmp_path), "ar")

    # lang_code is lower-cased before the check, so this is treated as valid → kept
    assert "index.AR.md" in set(os.listdir(p))
