# Contributing

## Setup

### 1. Clone and create virtual environment

```bash
git clone https://gitlab.recruitize.ai/sialkot/lahore-aspose/lahore-blogs-team/blog-post-translator.git
cd blog-post-translator
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.lock
```

### 2. Configure environment variables

Copy `.env.example` to `.env` at the project root and fill in the values:

```bash
cp .env.example .env
```

Ask the team for actual values. Never commit `.env`.

### 3. Run tests

```bash
make test                 # full suite (pytest)
# or target one pipeline:
make test-translation     # Steps 1–2
make test-quality         # Steps 3–4
```

All tests must pass before submitting changes. CI runs the same suite with a coverage gate (`--cov-fail-under=35`) on every push and pull request — keep coverage at or above the floor.

---

## Adding a New Domain

1. **`tools/translation_agent/config.py`**
   - Add `DOMAIN_*` constant
   - Add `LANGS_*` string (pipe-separated language codes)
   - Add sheet ID constants: `SHEET_ID_*` and `QUALITY_SHEET_ID_*`
   - Add entry to `domains_data` dict with `sheet_id`, `local_github_repo`, `langs`, `mentions`

2. **`.env`** — add values for the new `TRANSLATION_SCAN_SHEET_ID_*` and `QUALITY_SHEET_ID_*` variables

3. **`tools/quality_agent/quality_scanner.py`**, **`quality_validator.py`**, **`quality_retranslator.py`** — add entry to `QUALITY_SHEET_IDS` dict

4. **`tools/translation_agent/git_repo_utils.py`** — add repo entry to the `repos` list

5. **`.github/workflows/`** — add the domain to the matrix in `scan-missing-translations.yml` and `translate-blogs.yml`

---

## Adding a New Language

1. **`tools/translation_agent/config.py`** — append the language code to the `LANGS_*` string for the relevant domain(s), e.g. `LANGS_ASPOSE_COM = "ar|cs|...|new-lang"`

2. **`tools/quality_agent/lang_guard.py`** — add the language code to `SUPPORTED_LANGS` and its display name to `LANG_NAMES`

3. Run `pytest` to verify `lang_guard` tests still pass.

---

## Changing the LLM

Update `PROFESSIONALIZE_BASE_URL` and `PROFESSIONALIZE_LLM_MODEL` in `.env`. The agents pick these up automatically via `config.py`. No code changes required unless the new endpoint requires a different authentication scheme.

---

## Updating Dependencies

- **GitHub Actions** — handled automatically by Dependabot (PRs open against `dev`).
- **Python packages** — manual, to keep `requirements.lock` reproducible:
  1. Edit the pinned version in `requirements.txt`
  2. Regenerate the lock: `pip install -r requirements.txt && pip freeze > requirements.lock`
  3. `make test`, then PR via `dev → main`

Dependabot security alerts still cover Python dependencies (via the dependency graph) even though it doesn't open routine version PRs for them.

---

## Code Style

- Python 3.13+
- No hardcoded secrets, tokens, URLs, or local paths — all must go through `config.py` → `.env`
- Never add a `run: env` step to a workflow — CI's secret-scan rejects it
- Tests live in `tools/translation_agent/tests/` and `tools/quality_agent/tests/`
- Run `make test` before every commit (CI enforces this plus a secret/env-dump scan)

---

## Branching Model

- **`main`** — production. Protected: no direct pushes; changes land only via pull request with the CI checks green. The daily scan/translate workflows and releases run from here.
- **`dev`** — integration branch. Do your work here (or on short-lived feature branches off `dev`).

Day-to-day flow:

1. Commit to `dev` (or a feature branch → `dev`) and push.
2. **CI runs on `dev`** — tests + coverage + secret/env-dump scan.
3. On green, a **`dev → main` pull request opens automatically** (`auto-pr-dev-to-main.yml`).
4. The PR re-runs CI as the required check.
5. **You merge** when ready — promotion to production is always a deliberate human decision; nothing auto-merges.
6. Cut a release from `main` (below).

Run `make test` locally before pushing so the gate rarely surprises you.

> Setup notes: the auto-PR workflow needs Settings → Actions → General → **"Allow GitHub Actions to create and approve pull requests"** enabled, and it only fires once `auto-pr-dev-to-main.yml` exists on `main`.

---

## Cutting a Release

Releases are versioned with [Keep a Changelog](https://keepachangelog.com/) entries + git tags. Current line: **v2.0.0** (the v1 era ran through 2025-12-31).

1. Add a `## [X.Y.Z] — YYYY-MM-DD` section to `CHANGELOG.md` describing the changes
2. Merge to `main`
3. Tag and push the version:
   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```
4. `release.yml` verifies the matching changelog entry, extracts the notes, and publishes the GitHub Release
