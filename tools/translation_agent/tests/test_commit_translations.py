"""
Tests for commit_translations.py — uses a real temporary git repo (no mocks)
so the actual `git commit -- <pathspec>` behavior is exercised.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from commit_translations import commit_staged_translations


def _run(args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.name", "Test Bot"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    return repo


def _seed_source_post(repo, post_dir, title):
    """
    Writes and commits only the English index.md, mirroring production where
    the source post already exists in the target repo before a translation
    run adds new index.<lang>.md files alongside it.
    """
    d = repo / "content" / "words" / post_dir
    d.mkdir(parents=True)
    (d / "index.md").write_text(f"---\ntitle: {title}\n---\n\nBody.\n", encoding="utf-8")
    _run(["git", "add", "content/"], repo)
    _run(["git", "commit", "-q", "-m", f"seed {post_dir}"], repo)
    return d


def _add_translations(post_dir_path, title, langs):
    """Writes new translated language files for an already-seeded post (not staged yet)."""
    for lang in langs:
        (post_dir_path / f"index.{lang}.md").write_text(
            f"---\ntitle: {title} ({lang})\n---\n\nBody.\n", encoding="utf-8"
        )


def _log_subjects(repo):
    """Newest-first list of commit subjects; [] for a repo with no commits yet."""
    result = subprocess.run(
        ["git", "log", "--format=%s"], cwd=repo, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return []
    return result.stdout.strip().splitlines()


def _committed_files(repo, commit_ref):
    result = subprocess.run(
        ["git", "show", "--name-only", "--format=", commit_ref],
        cwd=repo, capture_output=True, text=True, check=True,
    )
    return [line for line in result.stdout.strip().splitlines() if line]


class TestCommitStagedTranslations:
    def test_no_staged_files_makes_no_commit(self, tmp_path, monkeypatch):
        repo = _init_repo(tmp_path)
        monkeypatch.chdir(repo)

        count = commit_staged_translations("blog.conholdate.com")

        assert count == 0
        assert _log_subjects(repo) == []

    def test_two_posts_produce_two_separate_commits(self, tmp_path, monkeypatch):
        repo = _init_repo(tmp_path)
        post_a = _seed_source_post(repo, "post-a", "Post A")
        post_b = _seed_source_post(repo, "post-b", "Post B")
        _add_translations(post_a, "Post A", ["ja", "fr"])
        _add_translations(post_b, "Post B", ["de"])
        _run(["git", "add", "content/"], repo)
        monkeypatch.chdir(repo)

        count = commit_staged_translations("blog.conholdate.com")

        assert count == 2
        subjects = _log_subjects(repo)[:2]
        assert any('"Post A"' in s for s in subjects)
        assert any('"Post B"' in s for s in subjects)

    def test_each_commit_touches_only_its_own_post_files(self, tmp_path, monkeypatch):
        repo = _init_repo(tmp_path)
        post_a = _seed_source_post(repo, "post-a", "Post A")
        post_b = _seed_source_post(repo, "post-b", "Post B")
        _add_translations(post_a, "Post A", ["ja"])
        _add_translations(post_b, "Post B", ["de"])
        _run(["git", "add", "content/"], repo)
        monkeypatch.chdir(repo)

        commit_staged_translations("blog.conholdate.com")

        # HEAD~1 is the first translation commit made (post-a), HEAD is the second (post-b)
        first_files = _committed_files(repo, "HEAD~1")
        second_files = _committed_files(repo, "HEAD")

        assert first_files == ["content/words/post-a/index.ja.md"]
        assert second_files == ["content/words/post-b/index.de.md"]

    def test_single_post_multiple_languages_is_one_commit(self, tmp_path, monkeypatch):
        repo = _init_repo(tmp_path)
        post_a = _seed_source_post(repo, "post-a", "Post A")
        _add_translations(post_a, "Post A", ["ja", "fr", "de"])
        _run(["git", "add", "content/"], repo)
        monkeypatch.chdir(repo)

        count = commit_staged_translations("blog.conholdate.com")

        assert count == 1
        files = _committed_files(repo, "HEAD")
        assert sorted(files) == [
            "content/words/post-a/index.de.md",
            "content/words/post-a/index.fr.md",
            "content/words/post-a/index.ja.md",
        ]


class TestConflictMarkers:
    """ec990f7b (blog.groupdocs.cloud, 27 Nov 2026) committed `<<<<<<< Updated upstream`."""

    MARKED = (
        "---\ntitle: Post A (de)\n---\n\n"
        "<<<<<<< Updated upstream\n=======\napi_client = ApiClient(configuration)\n"
        ">>>>>>> Stashed changes\n"
    )

    def test_file_with_markers_is_not_committed_others_are(self, tmp_path, monkeypatch, capsys):
        repo = _init_repo(tmp_path)
        post_a = _seed_source_post(repo, "post-a", "Post A")
        _add_translations(post_a, "Post A", ["fr"])
        (post_a / "index.de.md").write_text(self.MARKED, encoding="utf-8")
        _run(["git", "add", "content/"], repo)
        monkeypatch.chdir(repo)

        count = commit_staged_translations("blog.conholdate.com")

        assert count == 1
        assert _committed_files(repo, "HEAD") == ["content/words/post-a/index.fr.md"]
        assert "::error::Not committed - git conflict markers in content/words/post-a/index.de.md" \
            in capsys.readouterr().out

    def test_only_markers_means_no_commit(self, tmp_path, monkeypatch):
        repo = _init_repo(tmp_path)
        post_a = _seed_source_post(repo, "post-a", "Post A")
        (post_a / "index.de.md").write_text(self.MARKED, encoding="utf-8")
        _run(["git", "add", "content/"], repo)
        monkeypatch.chdir(repo)

        assert commit_staged_translations("blog.conholdate.com") == 0
        assert _log_subjects(repo) == ["seed post-a"]

    def test_lookalikes_are_not_markers(self, tmp_path):
        from commit_translations import has_conflict_markers
        path = tmp_path / "index.de.md"
        # a setext heading (=======), a quote (>), an arrow in text, a marker inside a line
        path.write_text("Title\n=======\n\n> quote\n>>>>>>>no space\ntext <<<<<<< x\n", encoding="utf-8")
        assert has_conflict_markers(str(path)) is False
