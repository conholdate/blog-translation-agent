"""Tests for code_block_report.py — the read-only code-block damage report (27 Nov 2026)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from code_block_report import classify, main

EN = "Intro\n\n```python\nx = 1\n\ny = 2\n```\n\n{{< gist user abc \"A.cs\" >}}\n\nEnd"


def test_identical_code_is_ok():
    assert classify(EN, EN.replace("Intro", "Einleitung")) == "ok"


def test_translated_comment_is_code():
    assert classify("```python\n# Configuration\n```", "```python\n# Konfiguration\n```") == "code"


def test_split_block_is_structure():
    broken = EN.replace("x = 1\n\ny = 2\n```", "x = 1\n```\n\ny = 2\n```")
    assert classify(EN, broken) == "structure"


def test_gist_pasted_inline_is_legacy():
    inlined = EN.replace('{{< gist user abc "A.cs" >}}', "```\nusing System;\n```")
    assert classify(EN, inlined) == "legacy"


def test_more_extra_blocks_than_gists_is_structure():
    inlined = EN.replace('{{< gist user abc "A.cs" >}}', "```\na\n```\n\n```\nb\n```")
    assert classify(EN, inlined) == "structure"


def test_conflict_markers_win():
    assert classify(EN, EN + "\n<<<<<<< Mis à jour en amont\n=======\n>>>>>>> Changements cachés\n") == "markers"


def test_main_reads_frontmatter_posts_and_writes_csv(tmp_path, capsys):
    post = tmp_path / "content" / "Blog" / "words" / "post-a"
    post.mkdir(parents=True)
    fm = "---\ntitle: A\n---\n\n"
    (post / "index.md").write_text(fm + EN, encoding="utf-8-sig")         # BOM, like some editors
    (post / "index.de.md").write_text(fm + EN, encoding="utf-8")
    (post / "index.fr.md").write_text(fm + EN.replace("x = 1\n\n", "x = 1\n```\n\n"), encoding="utf-8")
    out = tmp_path / "r.csv"

    assert main([str(tmp_path / "content"), "--csv", str(out)]) == 0

    printed = capsys.readouterr().out
    assert "structure" in printed and "ok" in printed and "roundtrip-fail" not in printed
    rows = out.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "category,post_folder,lang" and rows[1].startswith("structure,") and rows[1].endswith(",fr")
