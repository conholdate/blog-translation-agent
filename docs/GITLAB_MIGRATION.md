# Moving the pipelines to GitLab — analysis

Status: **analysed 20 Nov 2026, not started.** Waiting on the owner's answers to the open
questions below. Nothing runs on GitLab except the quality gate in `.gitlab-ci.yml`.

The question asked: can the scan and translation pipelines (GitHub Actions) be cloned and moved to
GitLab, where the code already is (`gitlab` remote, `gitlab.recruitize.ai/sialkot/lahore-aspose/
lahore-blogs-team/blog-post-translator`)? Answer: yes. The Python code needs almost no change; the
work is rewriting the workflows in GitLab CI and a cut-over that never lets both platforms run.

---

## What stays the same

- The Python code runs unchanged on a GitLab runner. With no `.env` at the project root,
  `config.PRODUCTION_ENV` is True automatically, as on GitHub.
- The blog repos stay on GitHub. The pipeline clones them and pushes with the same PAT
  (`PAT_GITHUB_SK`); commits look the same (author `shoaibkhan-aspose`).
- `io_google_spreadsheet.BASE_DIR` falls back to the working directory when `GITHUB_WORKSPACE` is
  unset, which is the project dir on GitLab too.

## Mapping

| GitHub now | GitLab equivalent | Note |
|---|---|---|
| Scan cron 00:00 / 12:00 UTC | Pipeline schedules | Set in the GitLab UI/API, not in YAML |
| Translations start after the scan (`workflow_run`) | One pipeline: scan jobs → translate jobs, each `needs:` its own domain's scan | Better than now: each blog starts when its own scan ends |
| `concurrency: translate-<domain>`, no cancelling | `resource_group: translate-<domain>` | Same queueing |
| `strategy.fail-fast: false` matrix | `parallel: matrix` (jobs are independent by default) | |
| `workflow_dispatch` inputs (domain, product, author, limit 1/2/3) | `spec: inputs` / pipeline variables with `options` | Same dropdowns |
| Repository secrets (~12) | Masked, protected CI/CD variables | Copied by hand by someone with access |
| `actions/checkout` of the blog repo, `fetch-depth: 0` | `git clone` with the PAT and **full history** | Shallow history makes OUTDATED / settling time silently find nothing |
| `actions/setup-python` 3.13 | `image: python:3.13` | |
| `alert-on-failure.yml` | GitLab failure notifications or a webhook | |
| GitHub's 6 h job kill | Project + runner job timeout | **GitLab default is 1 h** — must be raised to ~6 h |

## Code changes needed (small)

- `tools/translation_agent/run_log.py`: CI is detected only by `GITHUB_ACTIONS == "true"` and detail
  is folded with GitHub's `::group::` lines. Add `GITLAB_CI` and GitLab's collapsible sections
  (`section_start` / `section_end`), or GitLab logs show all detail unfolded.
- `tools/translation_agent/tests/test_workflows.py` guards the GitHub YAML (scan name in
  `workflow_run`, concurrency, limit ≤ 3); add the same guards for the GitLab pipeline.
- `.gitlab-ci.yml` header says the operational workflows are GitHub-only — update at cut-over.
- Docs: RUNBOOK ("Where it runs"), ORCHESTRATION (scheduling), both READMEs, AGENTS.md (allowed
  paths list `.github/workflows/`; "GitHub's 6 h kill"), CHANGELOG.

## Risks

1. **Both platforms live at once** — two runs could pick the same queue rows and push to the same
   blog repo, the same clash as editing the queue tab during a run (rows are found by number between
   read and write). GitHub workflows must be disabled at the moment the GitLab schedules are
   enabled (`gh workflow disable <file>` is reversible with `enable`).
2. **Runners** on gitlab.recruitize.ai — unknown whether the project has any and how many. Load:
   6 scan jobs + 5 translate jobs of ~3 h, twice a day; outbound access to github.com, Google APIs
   and the LLM API (`PROFESSIONALIZE_BASE_URL`).
3. **Job timeout** — 1 h default would kill translate jobs mid-run, committing nothing.
4. **Run history** — past logs stay on GitHub Actions.

Not affected: the blog-team-tools dashboard's `lib/workflows/workflows.ts` reads the *blog repos'*
GitHub workflows (deploys), not this repo's.

## Suggested order

1. Build the scan/translate jobs in `.gitlab-ci.yml` next to the quality gate, no schedules yet.
2. Run the scan by hand on GitLab — safe to repeat (reconcile never duplicates rows).
3. Run one translation by hand, limit 1, on one blog, with that blog's GitHub workflow disabled.
4. Cut over: disable the GitHub scan + translate workflows, create the two GitLab schedules.
5. Keep the GitHub workflow files for 1–2 weeks as fallback, then delete them.

## Open questions (owner)

1. Does gitlab.recruitize.ai have runners for this project, and can the job timeout be ~6 h?
   (Or provide a GitLab token so it can be checked via the API.)
2. Who adds the CI/CD variables (secrets) in GitLab?
3. Full move (GitHub disabled at cut-over), or GitLab as a standby switched on only when GitHub fails?
