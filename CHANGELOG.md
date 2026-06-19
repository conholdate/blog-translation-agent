# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

---

## [2.0.0] — 2026-06-19

First tagged release of the **v2** line (the v1 era ran through 2025-12-31). Consolidates the operational hardening since 2026-06-14.

### Added
- CI quality gate (`.github/workflows/ci.yml`): `pytest` + coverage with `--cov-fail-under=35`, plus a secret/env-dump scan, on every push and PR
- `pytest-cov` dependency; coverage artifacts git-ignored
- `tools/translation_agent/tests/test_translator_guards.py` — 16 tests for the shortcode/code-fence guards and the URL-language helper
- `docs/RUNBOOK.md` — operational runbook (runs, credential rotation, recovery/rollback, escalation, severity guide)
- `docs/DATA_HANDLING.md` — data-flow, secrets, and retention summary
- `Makefile` — `test` / `test-translation` / `test-quality` targets; agents pre-approved to self-verify (see `AGENTS.md`)
- `.github/dependabot.yml` — weekly pip + GitHub Actions dependency updates
- `.github/workflows/release.yml` — tag-driven release that validates this changelog and publishes a GitHub Release
- `.github/workflows/alert-on-failure.yml` — single watcher that alerts when an operational workflow fails

### Changed
- Migrated production metrics from the Apps Script webhook to the REST endpoint (`METRICS_API_URL` + env-based `X-Api-Key`)
- Removed the `Print all environment variables` (`run: env`) step from all 8 operational workflows

### Fixed
- LLM corruption of Hugo shortcode syntax during translation retries
- Code-fence detection so marker-wrapped snippets translate as one block
- Stale metrics tests after the webhook→REST migration

### Security
- CI fails if a workflow reintroduces `run: env` or if a hardcoded secret pattern appears in tracked source
- Sensitive-logging risk (CI env dumps) eliminated

---

## [2026-06-14]

### Added
- Consolidated Google Sheet (`TRANSLATION_SCAN_SHEET_ID`) — one sheet, one tab per domain, replacing 6 separate per-domain scan sheets
- Per-domain worksheet tabs overwritten on each scan with Scan Date as first column (ISO 8601 with timezone)
- `history` tab: append-only cross-domain log with Status (`pending` / `partial` / `completed`) and Completed Date
- `write_domain_scan_results()`, `update_history_tab()`, `_auto_resize_columns()` in `io_google_spreadsheet.py`
- `GOOGLE_SERVICE_ACCOUNT_JSON` and `TRANSLATION_SCAN_SHEET_ID` config vars
- `.env.example` at project root — committed template listing all 25+ required variables
- `CHANGELOG.md` — this file

### Changed
- `.env` moved from `tools/translation_agent/` to project root; `load_dotenv()` updated with explicit path using `os.path.abspath(__file__)` to work reliably across Python versions and run locations
- `PRODUCTION_ENV` is now auto-detected: `True` in CI (no `.env` file present), `False` locally — no longer hardcoded
- `requirements.txt` consolidated to project root; `tools/translation_agent/requirements.txt` removed
- `tools/translation_agent/.venv` removed; root `.venv` is the single virtual environment (Python 3.13)
- `requirements.lock` regenerated from root `requirements.txt` for Python 3.13
- All 8 CI workflows now install from `requirements.lock`; upgraded to `actions/checkout@v5`, `actions/setup-python@v5`; added `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` for Node.js 24 compatibility
- All translate workflows now pass all required secrets (`TRANSLATION_SCAN_SHEET_ID_*`, `PROFESSIONALIZE_*`, `METRICS_*`) via `env:` blocks
- `blog-checkedout-repo/` moved from `tools/translation_agent/` to project root — aligns local layout with CI checkout path
- `pytest==8.4.2` added as an explicit direct dependency in `requirements.txt`
- API key masked as `***` in scanner args log; sheet URLs removed from success print statements
- Removed 14 hardcoded Google Sheet URLs from `README.md`

### Fixed
- History tab completion detection: replaced subset check (`cur_langs < hist_langs`) with intersection logic (`hist_langs & cur_langs`) — correctly handles multiple history rows sharing the same slug with different language sets
- `current_date` / `scan_date` initialized before the domain loop in scanner — prevents `UnboundLocalError` when a domain path does not exist
- Python 3.9 syntax error in `translator.py` — backslash inside f-string `{}` invalid in 3.9; replaced with `chr(10)` in 4 print statements
- `io_google_spreadsheet.py` init message changed from "GitHub Secret" to "GSheets client initialized" — removed misleading wording

### Security
- Removed all hardcoded Google Sheet URLs from `README.md`
- Masked `PROFESSIONALIZE_API_KEY` in terminal output (`***`)
- Sheet write URLs no longer printed to stdout/CI logs

---

## [2026-05-30]

### Added
- `docs/ORCHESTRATION.md` — state model, function-level control flow, and extension points for both agents
- `docs/ARCHITECTURE.md` — component map, external service dependencies, ASCII data flow diagram, CI/CD summary
- `CONTRIBUTING.md` — full environment setup, `.env` variable list, adding domains/languages, PR process
- `.github/CODEOWNERS` — ownership assignments for all repo areas

### Changed
- `GITHUB_TOKEN` env var renamed to `PAT_GITHUB_SK` — GitHub Actions reserves the `GITHUB_*` prefix
- `GITHUB_CLONE_PATH_*` env vars renamed to `CLONE_PATH_GITHUB_*`
- All 6 quality sheet IDs moved from hardcoded dicts in quality agent files to `QUALITY_SHEET_ID_*` env vars via `config.py`
- GitHub PAT file path and 6 local clone paths moved from `git_repo_utils.py` to `.env`
- All metrics tokens, webhook URLs, LLM endpoint, and sheet IDs moved to `.env`
- `io_google_spreadsheet.py` `__main__` example: hardcoded sheet ID replaced with `config.SHEET_ID_GROUPDOCS_COM`
- Project structure updated across all READMEs, `AGENTS.md`, `CONTRIBUTING.md`
- Clone URL corrected to GitLab in translation agent README and CONTRIBUTING.md
- `AGENTS.md` forbidden paths updated with `docs/`, `CONTRIBUTING.md`, `CODEOWNERS`

### Fixed
- Scanner crash when no posts are pending — `filter_valid_rows()` drops rows missing required fields before `TranslationOrchestrator` processes them

### Security
- Removed all hardcoded secrets from committed source files; all credentials, tokens, sheet IDs, and local paths now loaded exclusively from `.env`

---

## [2026-04-30]

### Added
- Three-phase Quality Control Agent pipeline
  - Phase 1 `quality_scanner.py` — heuristic word-overlap Error% per translated file, writes to quality sheet
  - Phase 2 `quality_validator.py` — AI-based Error% via LLM sampling 20 paragraphs, back-fills sheet; marks `NA` when heuristic is 0%
  - Phase 3 `quality_retranslator.py` — force-retranslates files above error threshold using `TranslationOrchestrator`
- `lang_guard.py` — language code normalisation, RTL detection, translation heuristics
- Test suite: 11 test files covering `config`, `filter_valid_rows`, `lang_guard`, `quality_scanner` helpers
- `pytest.ini` at project root
- `AGENTS.md` — agent governance policy defining allowed read/write paths and safety rules
- `requirements.lock` — pinned transitive dependency tree

---

## [2026-03-15]

### Added
- Blog Translation Agent
  - `TranslationOrchestrator` coordinating `FrontmatterTranslatorAgent`, `ContentTranslatorAgent`, `PlatformIdentifierAgent`
  - `ContentTranslatorAgent` retry logic: up to 3 attempts per chunk with AI validation on failure
  - `scan_missing_translations.py` — daily scanner writing results to per-domain Google Sheets
  - `git_repo_utils.py` — clone and pull the six blog repositories via GitHub PAT
  - `io_google_spreadsheet.py` — Google Sheets read/write with service account credentials
  - `utils.py` — metrics reporting to two Google Apps Script webhooks (team + production)
- GitHub Actions workflows: daily scan + per-domain translation (8 workflow files)
- Support for 22 languages across 6 domains (Aspose, GroupDocs, Conholdate — .com and .cloud)
