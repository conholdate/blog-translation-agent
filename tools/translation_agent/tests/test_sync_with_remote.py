"""
Tests for sync_with_remote.py — real temporary git repos (a bare "origin" and a
clone), so the reset-and-write-back behaviour is exercised end to end.

The key case is the one that broke blog.groupdocs.cloud on 27 Nov 2026
(ec990f7b): another commit changed the same translation file while the run was
retranslating it. `git merge --ff-only --autostash` left conflict markers;
sync_with_remote must keep the agent's file intact instead.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sync_with_remote import changed_content_files, sync_with_remote

POST = "content/words/post-a"


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _write(repo, rel, text):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit_all(repo, msg):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def _setup(tmp_path):
    """origin (bare) + 'agent' clone (the workflow checkout) + 'other' clone (someone else)."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    clones = []
    for name in ("agent", "other"):
        _git(tmp_path, "clone", "-q", str(origin), name)
        repo = tmp_path / name
        _git(repo, "config", "user.name", "Test Bot")
        _git(repo, "config", "user.email", "test@example.com")
        _git(repo, "checkout", "-q", "-B", "master")
        clones.append(repo)
    agent, other = clones
    _write(other, f"{POST}/index.md", "English\n")
    _write(other, f"{POST}/index.de.md", "Deutsch alt\n")
    _write(other, f"{POST}/index.xx.md", "unsupported\n")
    _commit_all(other, "seed")
    _git(other, "push", "-q", "origin", "master")
    _git(agent, "pull", "-q", "origin", "master")
    return agent, other


def _push_from_other(other, files, msg="meanwhile"):
    _git(other, "pull", "-q", "origin", "master")
    for rel, text in files.items():
        _write(other, rel, text)
    _commit_all(other, msg)
    _git(other, "push", "-q", "origin", "master")


def _sync(agent, monkeypatch):
    monkeypatch.chdir(agent)
    _git(agent, "fetch", "-q", "origin")
    return sync_with_remote("origin/master")


def test_same_file_changed_on_remote_keeps_agent_version_without_markers(tmp_path, monkeypatch):
    agent, other = _setup(tmp_path)
    _write(agent, f"{POST}/index.de.md", "Deutsch neu (Agent)\n")                 # the run retranslates
    _push_from_other(other, {f"{POST}/index.de.md": "Deutsch Fix (Health Agent)\n"})  # meanwhile

    _sync(agent, monkeypatch)

    text = (agent / POST / "index.de.md").read_text(encoding="utf-8")
    assert text == "Deutsch neu (Agent)\n"
    assert "<<<<<<<" not in text and ">>>>>>>" not in text
    assert _git(agent, "rev-parse", "HEAD") == _git(agent, "rev-parse", "origin/master")


def test_new_translation_survives_and_other_remote_changes_arrive(tmp_path, monkeypatch):
    agent, other = _setup(tmp_path)
    _write(agent, f"{POST}/index.fr.md", "Français\n")
    _push_from_other(other, {"content/words/post-b/index.md": "Other post\n"})

    summary = _sync(agent, monkeypatch)

    assert (agent / POST / "index.fr.md").read_text(encoding="utf-8") == "Français\n"
    assert (agent / "content/words/post-b/index.md").is_file()
    assert summary["written"] == [f"{POST}/index.fr.md"]


def test_remote_added_the_same_new_file_agent_version_wins(tmp_path, monkeypatch):
    agent, other = _setup(tmp_path)
    _write(agent, f"{POST}/index.fr.md", "Français (Agent)\n")                 # untracked locally
    _push_from_other(other, {f"{POST}/index.fr.md": "Français (remote)\n"})    # tracked on remote

    _sync(agent, monkeypatch)

    assert (agent / POST / "index.fr.md").read_text(encoding="utf-8") == "Français (Agent)\n"


def test_deletion_of_extra_file_is_reapplied(tmp_path, monkeypatch):
    agent, other = _setup(tmp_path)
    os.remove(agent / POST / "index.xx.md")                                   # EXTRA cleanup
    _push_from_other(other, {f"{POST}/index.xx.md": "unsupported, edited\n"})

    summary = _sync(agent, monkeypatch)

    assert not (agent / POST / "index.xx.md").exists()
    assert summary["deleted"] == [f"{POST}/index.xx.md"]


def test_file_of_a_post_removed_on_remote_is_dropped(tmp_path, monkeypatch):
    agent, other = _setup(tmp_path)
    _write(agent, f"{POST}/index.fr.md", "Français\n")
    _git(other, "pull", "-q", "origin", "master")
    _git(other, "rm", "-q", "-r", POST)
    _git(other, "commit", "-q", "-m", "remove post")
    _git(other, "push", "-q", "origin", "master")

    summary = _sync(agent, monkeypatch)

    assert summary["dropped"] == [f"{POST}/index.fr.md"]
    assert not (agent / POST).exists()


def test_files_outside_content_are_not_carried_over(tmp_path, monkeypatch):
    agent, _ = _setup(tmp_path)
    _write(agent, "stray.txt", "not content\n")
    monkeypatch.chdir(agent)

    assert changed_content_files() == {}


def test_nothing_changed_is_a_clean_fast_forward(tmp_path, monkeypatch):
    agent, other = _setup(tmp_path)
    _push_from_other(other, {f"{POST}/index.de.md": "Deutsch Fix\n"})

    summary = _sync(agent, monkeypatch)

    assert summary == {"written": [], "deleted": [], "dropped": []}
    assert (agent / POST / "index.de.md").read_text(encoding="utf-8") == "Deutsch Fix\n"
