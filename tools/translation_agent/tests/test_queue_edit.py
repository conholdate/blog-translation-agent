"""Tests for queue_edit.py — the by-hand Priority / languages edit of a post's open queue rows."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from queue_edit import blog_langs, matching_rows, planned_cells

H = ["Priority", "Domain", "Product", "Blog Post Directory", "Issue", "Count", "Target Translations", "Status"]
D = "blog.groupdocs.cloud"


def _values(*rows):
    return [H] + [list(r) for r in rows]


def test_finds_only_open_rows_of_the_post():
    values = _values(
        ["Normal", D, "conversion", "post-a", "ISSUE", "0", "", ""],              # row 2: open
        ["Low", D, "conversion", "post-a", "OUTDATED", "1", "de", "partial"],     # row 3: open
        ["Low", D, "conversion", "post-a", "OUTDATED", "1", "fr", "hold"],        # row 4: held
        ["Low", D, "conversion", "post-b", "ISSUE", "1", "de", ""],               # row 5: other post
        ["Low", D, "viewer", "post-a", "ISSUE", "1", "de", ""],                   # row 6: other product
        ["Normal", D, "conversion", "post-a", "ISSUE"],                           # row 7: short row, open
    )
    assert matching_rows(H, values, D, "conversion", "post-a") == [2, 3, 7]
    assert matching_rows(H, values, D, "conversion", "post-a", issue="ISSUE") == [2, 7]


def test_planned_cells():
    assert planned_cells("Urgent", None) == {"Priority": "Urgent"}
    assert planned_cells(None, ["de", "fr"]) == {"Target Translations": "de, fr", "Count": "2"}
    assert planned_cells(None, None) == {}


def test_all_langs_is_the_blogs_list():
    langs = blog_langs(D)
    assert langs == [l for l in config.domains_data[D][config.KEY_SUPPORTED_LANGS].split("|") if l]
    assert "de" in langs and "" not in langs
