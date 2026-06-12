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
pytest
```

All tests must pass before submitting changes.

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

## Code Style

- Python 3.13+
- No hardcoded secrets, tokens, URLs, or local paths — all must go through `config.py` → `.env`
- Tests live in `tools/translation_agent/tests/` and `tools/quality_agent/tests/`
- Run `pytest` before every commit

---

## Submitting Changes

1. Create a branch from `main`
2. Make changes, ensure `pytest` passes
3. Open a pull request — CODEOWNERS will be notified automatically for review
4. Do not merge without at least one review approval
