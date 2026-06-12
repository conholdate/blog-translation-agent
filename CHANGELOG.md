# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- Consolidated Google Sheet (`TRANSLATION_SCAN_SHEET_ID`) replacing 6 per-domain scan sheets — one sheet, one tab per domain
- Per-domain worksheet tabs overwritten on each scan with Scan Date as first column (ISO 8601 with timezone)
- `history` tab: append-only cross-domain log tracking every missing translation with Status (`pending` / `partial` / `completed`) and Completed Date — filled automatically on the scan that detects a translation was finished
- `write_domain_scan_results()` and `update_history_tab()` in `io_google_spreadsheet.py`
- `_auto_resize_columns()` — auto-fits all column widths after every sheet write
- `GOOGLE_SERVICE_ACCOUNT_JSON` and `TRANSLATION_SCAN_SHEET_ID` config vars
- `.env.example` at project root — committed template listing all required variables

### Changed
- `.env` moved from `tools/translation_agent/` to project root
- `requirements.txt` consolidated to project root; `tools/translation_agent/requirements.txt` removed
- `tools/translation_agent/.venv` removed; root `.venv` is the single virtual environment
- `requirements.lock` regenerated from root `requirements.txt` for Python 3.9
- All 8 CI workflows now install from `requirements.lock` instead of the unpinned subfolder file
- `pytest==8.4.2` added as an explicit direct dependency in `requirements.txt`

### Fixed
- Python 3.9 syntax error in `translator.py` — backslash escape inside f-string `{}` (4 occurrences); replaced with `chr(10)`

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
