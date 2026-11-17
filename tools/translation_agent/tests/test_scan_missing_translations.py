"""
Tests for validate_blog_dirs() in scan_missing_translations.py — the folder
walk that finds MISSING, EXTRA and OUTDATED translations. Uses a real temporary
git repo for the OUTDATED cases.

The scanner parses its command line at import time, so it is imported with a
stand-in argv.
"""

import importlib
import os
import re
import subprocess
import sys

import pytest

import config

LANGS = "de|fr"
VALID_RE = re.compile(r"^index(?:\.(" + LANGS + r"))?\.md$")


@pytest.fixture(scope="module")
def scanner():
    saved = sys.argv
    sys.argv = ["scan_missing_translations.py", "--domain", "blog.aspose.com"]
    try:
        return importlib.import_module("scan_missing_translations")
    finally:
        sys.argv = saved


def _git(repo, *args, date=None):
    env = dict(os.environ)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env)


def _post(base, slug, files, product="words"):
    d = base / product / slug
    d.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


EN = '---\ntitle: T\nauthor: "Jane Doe"\nurl: /words/{slug}/\n---\nBody\n'


def _scan(scanner, base):
    return {r[config.KEY_DIR_BASE]: r for r in scanner.validate_blog_dirs(str(base), VALID_RE, LANGS, 3)}


class TestWalk:
    def test_missing_and_extra(self, scanner, tmp_path):
        _post(tmp_path, "2026-01-01-a", {"index.md": EN.format(slug="a"), "index.de.md": "x", "index.xx.md": "junk"})
        r = _scan(scanner, tmp_path)["2026-01-01-a"]
        assert r[config.KEY_MISSING_FILES] == ["fr"]
        assert r[config.KEY_MISSING_COUNT] == 1
        assert r[config.KEY_EXTRA_FILES] == ["xx"]
        assert r[config.KEY_AUTHOR] == "Jane Doe"
        assert r[config.KEY_POST_URL] == "/words/a/"

    def test_fully_translated_post_is_not_reported(self, scanner, tmp_path):
        _post(tmp_path, "2026-01-01-a", {"index.md": EN.format(slug="a"), "index.de.md": "x", "index.fr.md": "x"})
        assert _scan(scanner, tmp_path) == {}

    def test_folder_without_index_md_is_skipped(self, scanner, tmp_path):
        _post(tmp_path, "2026-01-01-orphan", {"index.de.md": "x"})
        assert _scan(scanner, tmp_path) == {}

    def test_draft_listed_last_is_skipped(self, scanner, tmp_path):
        _post(tmp_path, "2026-01-01-d", {"index.md": "---\nauthor: A\nurl: /d/\ndraft: true\n---\n"})
        assert _scan(scanner, tmp_path) == {}

    def test_post_without_author_does_not_crash(self, scanner, tmp_path):
        _post(tmp_path, "2026-01-01-n", {"index.md": "---\ntitle: T\nurl: /n/\n---\n"})
        assert _scan(scanner, tmp_path)["2026-01-01-n"][config.KEY_AUTHOR] == ""

    def test_bom_index_md_is_read(self, scanner, tmp_path):
        _post(tmp_path, "2026-01-01-b", {"index.md": "﻿" + EN.format(slug="b")})
        assert _scan(scanner, tmp_path)["2026-01-01-b"][config.KEY_AUTHOR] == "Jane Doe"

    def test_undated_and_discount_folders_are_skipped(self, scanner, tmp_path):
        _post(tmp_path, "about", {"index.md": EN.format(slug="about")})
        _post(tmp_path, "2026-01-01-discount-offer", {"index.md": EN.format(slug="x")})
        assert _scan(scanner, tmp_path) == {}

    def test_no_git_history_means_no_outdated(self, scanner, tmp_path):
        _post(tmp_path, "2026-01-01-a", {"index.md": EN.format(slug="a"), "index.de.md": "x", "index.fr.md": "x"})
        assert _scan(scanner, tmp_path) == {}


class TestOutdated:
    @pytest.fixture
    def repo(self, tmp_path):
        r = tmp_path / "repo"
        r.mkdir()
        _git(r, "init", "-q")
        _git(r, "config", "user.name", "Test Bot")
        _git(r, "config", "user.email", "test@example.com")
        return r

    def _commit(self, repo, date):
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "c", date=date)

    def test_english_edited_later_flags_outdated_langs(self, scanner, repo):
        d = _post(repo, "2026-01-01-a", {"index.md": EN.format(slug="a")})
        self._commit(repo, "2026-01-01T00:00:00+00:00")
        _post(repo, "2026-01-01-a", {"index.de.md": "de", "index.fr.md": "fr"})
        self._commit(repo, "2026-01-02T00:00:00+00:00")
        (d / "index.md").write_text(EN.format(slug="a") + "Optimized.\n", encoding="utf-8")
        self._commit(repo, "2026-03-01T00:00:00+00:00")

        r = _scan(scanner, repo)["2026-01-01-a"]
        assert r[scanner.KEY_OUTDATED_FILES] == ["de", "fr"]
        assert r[config.KEY_MISSING_COUNT] == 0
        assert r[scanner.KEY_SOURCE_COMMIT_TIME] == 1772323200    # 2026-03-01 UTC

    def test_up_to_date_post_is_not_reported(self, scanner, repo):
        _post(repo, "2026-01-01-a", {"index.md": EN.format(slug="a")})
        self._commit(repo, "2026-01-01T00:00:00+00:00")
        _post(repo, "2026-01-01-a", {"index.de.md": "de", "index.fr.md": "fr"})
        self._commit(repo, "2026-01-02T00:00:00+00:00")
        assert _scan(scanner, repo) == {}

    def test_missing_and_outdated_on_same_post(self, scanner, repo):
        d = _post(repo, "2026-01-01-a", {"index.md": EN.format(slug="a")})
        self._commit(repo, "2026-01-01T00:00:00+00:00")
        _post(repo, "2026-01-01-a", {"index.de.md": "de"})
        self._commit(repo, "2026-01-02T00:00:00+00:00")
        (d / "index.md").write_text(EN.format(slug="a") + "Optimized.\n", encoding="utf-8")
        self._commit(repo, "2026-03-01T00:00:00+00:00")

        r = _scan(scanner, repo)["2026-01-01-a"]
        assert r[config.KEY_MISSING_FILES] == ["fr"]
        assert r[scanner.KEY_OUTDATED_FILES] == ["de"]


class TestNotes:
    def test_missing_and_extra_notes(self, scanner, tmp_path):
        _post(tmp_path, "2026-01-01-new", {"index.md": EN.format(slug="new")})
        _post(tmp_path, "2026-01-01-part", {"index.md": EN.format(slug="part"), "index.de.md": "x",
                                            "index.xx.md": "junk"})
        res = _scan(scanner, tmp_path)
        assert res["2026-01-01-new"][scanner.KEY_ROW_NOTES] == {config.ISSUE_MISSING: "New post"}
        notes = res["2026-01-01-part"][scanner.KEY_ROW_NOTES]
        assert notes[config.ISSUE_MISSING] == "1 of 2 languages missing"
        assert notes[config.ISSUE_EXTRA].startswith("Unsupported language file")

    def test_outdated_note_names_the_english_commit(self, scanner, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        for args in (["init", "-q"], ["config", "user.name", "optimizer-agent"],
                     ["config", "user.email", "o@example.com"]):
            _git(repo, *args)
        d = _post(repo, "2026-01-01-a", {"index.md": EN.format(slug="a")})
        _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "publish", date="2026-01-01T00:00:00+00:00")
        _post(repo, "2026-01-01-a", {"index.de.md": "de", "index.fr.md": "fr"})
        _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "translate", date="2026-01-02T00:00:00+00:00")
        (d / "index.md").write_text(EN.format(slug="a") + "More.\n", encoding="utf-8")
        _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "Optimized Blog Posts",
                                      date="2026-03-01T00:00:00+00:00")

        note = _scan(scanner, repo)["2026-01-01-a"][scanner.KEY_ROW_NOTES][config.ISSUE_OUTDATED]
        assert note == ('English updated 2026-03-01 by optimizer-agent ("Optimized Blog Posts"); '
                        "translations from 2026-01-02")
