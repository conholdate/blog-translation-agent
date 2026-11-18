"""
Guards for the translation workflows (.github/workflows) — mistakes here fail
silently in GitHub (a misspelt workflow_run name never fires):
  - scheduled translations start from the scan workflow, by its exact name;
  - one run per blog at a time (concurrency, not cancelling a running one);
  - the run budget stays within 3 posts' worth (AGENTS.md standing instruction).
"""

import glob
import os

import pytest
import yaml

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
WF = os.path.join(ROOT, ".github", "workflows")


def load(name):
    with open(os.path.join(WF, name), encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data["on"] = data.pop(True, data.get("on"))      # YAML 1.1 reads the key `on` as True
    return data


SCAN = load("scan-missing-translations.yml")
TRANSLATE = sorted(os.path.basename(p) for p in glob.glob(os.path.join(WF, "translate-blog*.yml")))
SCHEDULED = [n for n in TRANSLATE if "workflow_run" in load(n)["on"]]


def test_scan_runs_twice_a_day_without_fail_fast():
    assert [c["cron"] for c in SCAN["on"]["schedule"]] == ["0 0 * * *", "0 12 * * *"]
    assert SCAN["jobs"]["scan"]["strategy"]["fail-fast"] is False


def test_the_five_maintained_blogs_follow_the_scan_and_groupdocs_com_does_not():
    assert SCHEDULED == [f"translate-blog-{d}.yml" for d in
                         ("aspose-cloud", "aspose-com", "conholdate-cloud", "conholdate-com", "groupdocs-cloud")]


@pytest.mark.parametrize("name", SCHEDULED)
def test_chained_to_the_scan_by_its_exact_name(name):
    wf = load(name)
    assert wf["on"]["workflow_run"] == {"workflows": [SCAN["name"]], "types": ["completed"]}
    assert "schedule" not in wf["on"]
    cond = wf["jobs"]["translate-blog-posts"]["if"]
    assert "workflow_run.event == 'schedule'" in cond and "'cancelled'" not in cond


@pytest.mark.parametrize("name", TRANSLATE)
def test_one_run_per_blog_and_budget_at_most_three(name):
    wf = load(name)
    assert wf["concurrency"]["group"].startswith("translate-${{ inputs.domain")
    assert wf["concurrency"]["cancel-in-progress"] is False
    limit = wf["on"]["workflow_dispatch"]["inputs"]["limit"]
    assert max(int(o) for o in limit["options"]) <= 3 and int(limit["default"]) <= 3
