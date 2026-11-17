"""
Tests for scan_helpers.py — frontmatter reading and the git-based OUTDATED
check used by the missing-translation scanner. Git tests use a real temporary
repo with fixed commit dates (no mocks).
"""

import os
import subprocess

import pytest

from scan_helpers import read_post_meta, last_commit_times, outdated_langs


# ---------------------------------------------------------------------------
# read_post_meta()
# ---------------------------------------------------------------------------

def _write(tmp_path, text, name="index.md"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


class TestReadPostMeta:
    def test_reads_author_url_draft(self, tmp_path):
        p = _write(tmp_path, '---\ntitle: T\nauthor: "Jane Doe"\nurl: /words/post/\ndraft: false\n---\nBody\n')
        assert read_post_meta(p) == {"author": "Jane Doe", "url": "/words/post/", "draft": False}

    def test_utf8_bom_is_ignored(self, tmp_path):
        p = _write(tmp_path, "﻿---\nauthor: Jane\nurl: /x/\n---\n")
        assert read_post_meta(p)["author"] == "Jane"

    def test_draft_after_author_and_url_is_found(self, tmp_path):
        p = _write(tmp_path, "---\nauthor: Jane\nurl: /x/\ndraft: true\n---\n")
        assert read_post_meta(p)["draft"] is True

    @pytest.mark.parametrize("value", ["true", "'true'", '"true"', "True"])
    def test_draft_value_variants(self, tmp_path, value):
        p = _write(tmp_path, f"---\ndraft: {value}\n---\n")
        assert read_post_meta(p)["draft"] is True

    def test_missing_author_returns_empty_string(self, tmp_path):
        p = _write(tmp_path, "---\ntitle: T\nurl: /x/\n---\n")
        assert read_post_meta(p)["author"] == ""

    def test_body_text_is_not_read_as_frontmatter(self, tmp_path):
        p = _write(tmp_path, "---\ntitle: T\n---\nauthor: Not Me\ndraft: true\n")
        assert read_post_meta(p) == {"author": "", "url": "", "draft": False}

    def test_no_frontmatter(self, tmp_path):
        p = _write(tmp_path, "just text\n")
        assert read_post_meta(p) == {"author": "", "url": "", "draft": False}

    def test_crlf_line_endings(self, tmp_path):
        p = tmp_path / "index.md"
        p.write_bytes(b"---\r\nauthor: Jane\r\nurl: /x/\r\n---\r\nBody\r\n")
        assert read_post_meta(str(p)) == {"author": "Jane", "url": "/x/", "draft": False}


# ---------------------------------------------------------------------------
# last_commit_times() / outdated_langs()
# ---------------------------------------------------------------------------

def _git(repo, *args, date=None):
    env = dict(os.environ)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "content" / "Blog" / "words" / "post").mkdir(parents=True)
    _git(r, "init", "-q")
    _git(r, "config", "user.name", "Test Bot")
    _git(r, "config", "user.email", "test@example.com")
    return r


def _commit(repo, files, date, msg="c"):
    """Write {relative path under content/Blog: text} and commit at `date`."""
    for rel, text in files.items():
        p = repo / "content" / "Blog" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg, date=date)


POST = "words/post"


class TestLastCommitTimes:
    def test_paths_relative_to_folder_with_latest_time(self, repo):
        _commit(repo, {f"{POST}/index.md": "v1"}, "2026-01-01T00:00:00+00:00")
        _commit(repo, {f"{POST}/index.md": "v2"}, "2026-02-01T00:00:00+00:00")
        times = last_commit_times(str(repo / "content" / "Blog"))
        assert set(times) == {f"{POST}/index.md"}
        assert times[f"{POST}/index.md"] == 1769904000   # 2026-02-01 UTC

    def test_non_ascii_paths_are_not_quoted(self, repo):
        _commit(repo, {"words/café/index.md": "v1"}, "2026-01-01T00:00:00+00:00")
        assert "words/café/index.md" in last_commit_times(str(repo / "content" / "Blog"))

    def test_not_a_git_repo_returns_none(self, tmp_path):
        d = tmp_path / "plain"
        d.mkdir()
        assert last_commit_times(str(d)) is None

    def test_folder_with_no_tracked_files_returns_none(self, repo):
        # e.g. the gitignored local test mirror inside the agent repo
        _commit(repo, {f"{POST}/index.md": "v1"}, "2026-01-01T00:00:00+00:00")
        untracked = repo / "mirror"
        untracked.mkdir()
        (untracked / "index.md").write_text("x")
        assert last_commit_times(str(untracked)) is None


class TestOutdatedLangs:
    def _times(self, repo):
        return last_commit_times(str(repo / "content" / "Blog"))

    def test_english_edited_after_translation_is_outdated(self, repo):
        _commit(repo, {f"{POST}/index.md": "v1"}, "2026-01-01T00:00:00+00:00")
        _commit(repo, {f"{POST}/index.de.md": "de", f"{POST}/index.fr.md": "fr"}, "2026-01-02T00:00:00+00:00")
        _commit(repo, {f"{POST}/index.md": "v2 optimized"}, "2026-03-01T00:00:00+00:00")
        assert outdated_langs(self._times(repo), POST, ["de", "fr"]) == ["de", "fr"]

    def test_translation_newer_than_english_is_not_outdated(self, repo):
        _commit(repo, {f"{POST}/index.md": "v1"}, "2026-01-01T00:00:00+00:00")
        _commit(repo, {f"{POST}/index.de.md": "de"}, "2026-01-02T00:00:00+00:00")
        assert outdated_langs(self._times(repo), POST, ["de"]) == []

    def test_fix_committed_to_english_and_translations_together_is_not_outdated(self, repo):
        _commit(repo, {f"{POST}/index.md": "v1"}, "2026-01-01T00:00:00+00:00")
        _commit(repo, {f"{POST}/index.de.md": "de"}, "2026-01-02T00:00:00+00:00")
        _commit(repo, {f"{POST}/index.md": "v1 url fix", f"{POST}/index.de.md": "de url fix"},
                "2026-03-01T00:00:00+00:00")
        assert outdated_langs(self._times(repo), POST, ["de"]) == []

    def test_only_the_older_languages_are_reported(self, repo):
        _commit(repo, {f"{POST}/index.md": "v1"}, "2026-01-01T00:00:00+00:00")
        _commit(repo, {f"{POST}/index.de.md": "de", f"{POST}/index.fr.md": "fr"}, "2026-01-02T00:00:00+00:00")
        _commit(repo, {f"{POST}/index.md": "v2"}, "2026-02-01T00:00:00+00:00")
        _commit(repo, {f"{POST}/index.fr.md": "fr retranslated"}, "2026-02-02T00:00:00+00:00")
        assert outdated_langs(self._times(repo), POST, ["de", "fr"]) == ["de"]

    def test_uncommitted_translation_is_never_reported(self, repo):
        _commit(repo, {f"{POST}/index.md": "v1"}, "2026-01-01T00:00:00+00:00")
        (repo / "content" / "Blog" / POST / "index.de.md").write_text("new, not committed")
        assert outdated_langs(self._times(repo), POST, ["de"]) == []

    def test_unknown_english_file_returns_nothing(self):
        assert outdated_langs({"other/post/index.de.md": 1}, POST, ["de"]) == []


# ---------------------------------------------------------------------------
# last_commits() and the Notes texts
# ---------------------------------------------------------------------------

from scan_helpers import Commit, last_commits, missing_note, extra_note, outdated_note


class TestLastCommits:
    def test_author_and_subject_of_latest_commit(self, repo):
        _commit(repo, {f"{POST}/index.md": "v1"}, "2026-01-01T00:00:00+00:00", msg="published post")
        _commit(repo, {f"{POST}/index.md": "v2"}, "2026-02-01T00:00:00+00:00", msg="Optimized Blog Posts")
        c = last_commits(str(repo / "content" / "Blog"))[f"{POST}/index.md"]
        assert c == Commit(1769904000, "Test Bot", "Optimized Blog Posts")

    def test_subject_with_tabs_and_unicode(self, repo):
        _commit(repo, {f"{POST}/index.md": "v1"}, "2026-01-01T00:00:00+00:00", msg="Fix «links»\tagain")
        c = last_commits(str(repo / "content" / "Blog"))[f"{POST}/index.md"]
        assert c.subject == "Fix «links»\tagain"


class TestNotes:
    def test_missing_note(self):
        assert missing_note(21, 21) == "New post"
        assert missing_note(3, 21) == "3 of 21 languages missing"

    def test_extra_note(self):
        assert extra_note().startswith("Unsupported language file")

    def test_outdated_note_single_date(self):
        commits = {
            f"{POST}/index.md":    Commit(1763251200, "optimizer-agent", "Optimized Blog Posts"),  # 2025-11-16
            f"{POST}/index.de.md": Commit(1746748800, "bot", "t"),                               # 2025-05-09
            f"{POST}/index.fr.md": Commit(1746748800, "bot", "t"),
        }
        assert outdated_note(commits, POST, ["de", "fr"]) == (
            'English updated 2025-11-16 by optimizer-agent ("Optimized Blog Posts"); '
            "translations from 2025-05-09")

    def test_outdated_note_date_range(self):
        commits = {
            f"{POST}/index.md":    Commit(1763251200, "Jane", "Edit"),
            f"{POST}/index.de.md": Commit(1746748800, "bot", "t"),   # 2025-05-09
            f"{POST}/index.fr.md": Commit(1750000000, "bot", "t"),   # 2025-06-15
        }
        assert outdated_note(commits, POST, ["de", "fr"]).endswith("translations from 2025-05-09 to 2025-06-15")

    def test_outdated_note_long_subject_is_shortened(self):
        commits = {f"{POST}/index.md": Commit(1763251200, "Jane", "x" * 200)}
        note = outdated_note(commits, POST, [])
        assert '("' + "x" * 79 + '…")' in note

    def test_outdated_note_without_english_commit(self):
        assert outdated_note({}, POST, ["de"]) == ""
