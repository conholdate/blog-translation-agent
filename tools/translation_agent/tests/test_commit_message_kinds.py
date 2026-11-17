"""
Tests for commit-message wording by change kind: added translations
("Translate articles"), retranslated ones from OUTDATED rows ("Retranslate
articles"), removed EXTRA files ("Remove extra translations") and mixes.
The commit_translations tests use a real temporary git repo (no mocks).
"""

import subprocess

from build_commit_message import build_message
from commit_translations import commit_staged_translations, get_staged_changes

DOMAIN = "blog.conholdate.com"


def _write(path, title):
    path.write_text(f"---\ntitle: {title}\n---\n\nBody.\n", encoding="utf-8")
    return str(path)


def _post(tmp_path, slug="my-post", title="My Post", langs=("ja", "fr")):
    d = tmp_path / "content" / "words" / slug
    d.mkdir(parents=True)
    _write(d / "index.md", title)
    return d, [_write(d / f"index.{l}.md", title) for l in langs]


class TestBuildMessageKinds:
    def test_no_statuses_keeps_the_added_wording(self, tmp_path):
        _, files = _post(tmp_path)
        msg = build_message(DOMAIN, files)
        assert msg.splitlines()[0] == 'Translate articles for: "My Post" - (2 files)'
        assert "Added translations in 2 languages:" in msg

    def test_modified_files_say_retranslate(self, tmp_path):
        _, files = _post(tmp_path)
        msg = build_message(DOMAIN, files, {f: "M" for f in files})
        assert msg.splitlines()[0] == 'Retranslate articles for: "My Post" - (2 files)'
        assert "Retranslated 2 languages (English post was updated):" in msg
        assert "Added translations" not in msg

    def test_deleted_files_say_remove(self, tmp_path):
        _, files = _post(tmp_path, langs=("ja",))
        msg = build_message(DOMAIN, files, {files[0]: "D"})
        assert msg.splitlines()[0] == 'Remove extra translations for: "My Post" - (1 file)'
        assert "Removed extra files in 1 language:" in msg

    def test_mixed_added_and_modified(self, tmp_path):
        _, (ja, fr) = _post(tmp_path)
        msg = build_message(DOMAIN, [ja, fr], {ja: "A", fr: "M"})
        lines = msg.splitlines()
        assert lines[0] == 'Update translations for: "My Post" - (2 files)'
        added = lines.index("Added translations in 1 language:")
        updated = lines.index("Retranslated 1 language (English post was updated):")
        assert added < updated
        assert lines[added + 2] == "- Japanese (ja)"
        assert lines[updated + 2] == "- French (fr)"

    def test_multiple_posts_retranslated(self, tmp_path):
        _, a = _post(tmp_path, "post-a", "Post A", ("ja",))
        _, b = _post(tmp_path, "post-b", "Post B", ("fr",))
        msg = build_message(DOMAIN, a + b, {a[0]: "M", b[0]: "M"})
        assert msg.splitlines()[0] == f"Retranslate articles for 2 posts ({DOMAIN})"
        assert '"Post A" — retranslated 1 language (English post was updated):' in msg


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["git", "init", "-q"], ["git", "config", "user.name", "Test Bot"],
                 ["git", "config", "user.email", "test@example.com"]):
        _run(args, repo)
    return repo


class TestCommitStagedKinds:
    def _seed(self, repo):
        d = repo / "content" / "words" / "my-post"
        d.mkdir(parents=True)
        _write(d / "index.md", "My Post")
        _write(d / "index.ja.md", "My Post (ja)")
        _write(d / "index.xx.md", "junk")
        _run(["git", "add", "content/"], repo)
        _run(["git", "commit", "-q", "-m", "seed"], repo)
        return d

    def test_staged_status_letters(self, tmp_path, monkeypatch):
        repo = _repo(tmp_path)
        d = self._seed(repo)
        monkeypatch.chdir(repo)
        _write(d / "index.ja.md", "My Post (ja, retranslated)")
        _write(d / "index.fr.md", "My Post (fr)")
        (d / "index.xx.md").unlink()
        _run(["git", "add", "content/"], repo)
        assert get_staged_changes() == {
            "content/words/my-post/index.ja.md": "M",
            "content/words/my-post/index.fr.md": "A",
            "content/words/my-post/index.xx.md": "D",
        }

    def test_retranslated_post_commit_subject(self, tmp_path, monkeypatch):
        repo = _repo(tmp_path)
        d = self._seed(repo)
        monkeypatch.chdir(repo)
        _write(d / "index.ja.md", "My Post (ja, retranslated)")
        _run(["git", "add", "content/"], repo)

        assert commit_staged_translations(DOMAIN) == 1
        subject = _run(["git", "log", "-1", "--format=%s"], repo).strip()
        assert subject == 'Retranslate articles for: "My Post" - (1 file)'

    def test_deleted_file_is_committed(self, tmp_path, monkeypatch):
        repo = _repo(tmp_path)
        d = self._seed(repo)
        monkeypatch.chdir(repo)
        (d / "index.xx.md").unlink()
        _run(["git", "add", "content/"], repo)

        assert commit_staged_translations(DOMAIN) == 1
        assert _run(["git", "status", "--porcelain"], repo) == ""
        subject = _run(["git", "log", "-1", "--format=%s"], repo).strip()
        assert subject.startswith("Remove extra translations for:")
