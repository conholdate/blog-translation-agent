# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- **Persistent translation queue** (18 Nov 2026): the domain tab is no longer cleared and rewritten by each scan — it is reconciled (`scan_queue.py`, `io_google_spreadsheet.sync_domain_queue()`): languages no longer flagged are removed (Status `partial`), rows with nothing left move to `history` as `completed`, new findings are added at the bottom. Row splits, order, Priority, Status, Comments and people's own columns survive. Why: the full rewrite wiped manual edits and made non-derivable rows (manual / agent ISSUE rows) impossible
- Queue columns `Priority` (Urgent / High / Normal / Low — defaults MISSING High, ISSUE Normal, OUTDATED Low; set on new rows only, never overwritten; Urgent is for people), `Source` (Scanner / Manual / agent name) and `Comments`; `Missing Since` is now kept on the queue row (first flagged, never changed)
- Queue Status `hold` (or any value other than blank / `pending` / `partial`) skips a row in Step 2 and keeps the scan from closing or re-adding it
- `cleanup` tab — EXTRA (junk file) rows of all domains in one tab; Step 2 deletes its domain's files from there
- `reset_scan_queue.py` — one-time reset by hand (dry run unless `--apply`): backs up tabs as `bak-…`, deletes non-completed and blog.groupdocs.com history rows, clears domain + cleanup tabs; the next scan rebuilds the queue
- **ISSUE rows** (Normal priority): retranslation requests from people or agents — `queue_add.py` CLI / `io_google_spreadsheet.add_to_queue()` (skips languages already queued for retranslation). They overwrite existing translations like OUTDATED rows; blank languages = all. Each scan validates them (post folder exists and isn't a draft, languages supported) and marks failures `invalid` with a `⚠️ Invalid: …` note, cleared once fixed
- **Language budget**: `--limit` is "posts' worth" — the run translates up to limit × the blog's languages (2 × 21 = 42), so several posts needing few languages fit in one run; a row that doesn't fit is cut and keeps the rest queued; a language asked for by two rows of a post is translated once. Why: a post-count cap wasted runs on posts needing 1–2 languages
- **Run time limit** (`--time-limit`, default 300 min): no new language starts after it; the post in progress logs `⏸️ Time limit n/m` with the languages not started. Why: GitHub kills jobs at 6 h and a killed job commits nothing
- Step 2 closes languages right after each post: removed from every open row of the post (one retranslation settles both an OUTDATED and an ISSUE row); empty rows move to `history`
- Scan workflow runs at 00:00 **and 12:00** UTC with `fail-fast: false`; the five maintained blogs' translate workflows start on `workflow_run` after a scheduled scan (success or failure, not cancelled, not manual) instead of their own 01:00 schedule — two runs per blog a day; `concurrency: translate-<domain>` (no cancelling) on every translate workflow
- Tests: `test_workflows.py` (scan name in `workflow_run`, concurrency, ≤ 3 limit); ISSUE / budget / time-limit cases in `test_outdated_rows.py`; manual-row validation in `test_scan_queue.py`; closing and `add_to_queue` cases in `test_history_comments.py` / `test_consolidated_scan_sheet.py`
- Tests: `test_scan_queue.py`, `test_reset_scan_queue.py`, queue sync / cleanup / history cases in `test_consolidated_scan_sheet.py`, queue comments in `test_history_comments.py`, priority ordering in `test_outdated_rows.py`, the scanner's queue write in `test_scan_missing_translations.py`; shared `tests/fake_sheet.py`
- `OUTDATED` / `Retranslate` scan rows: a translation is outdated when its post's `index.md` was committed after it (one `git log` pass per blog, `scan_helpers.last_commits()` / `outdated_langs()`; a fix committed to `index.md` and its translations together is not outdated; skipped with a warning when there is no git history). OUTDATED rows are listed after MISSING/EXTRA rows, most recent English edit first. Found 17 Nov 2026: 763 outdated posts on the 5 maintained blogs, mostly optimizer-agent edits
- Step 2 retranslates OUTDATED rows: they pass `filter_valid_rows()`, always run after MISSING rows (`missing_first()`), overwrite the existing `index.{lang}.md`, and log history comments on the OUTDATED history row
- `Notes` column (domain tab, old per-domain sheet, `history` tab) saying why a row was flagged: `New post` / `N of M languages missing` / `Unsupported language file(s)…` / `English updated <date> by <author> ("<subject>"); translations from <date>`. Refreshed on open history rows each scan. Step 2 reads columns by name and ignores it (`HEADERS_SCAN_RESULTS` = `HEADERS_MISSING_TRANSLATIONS` + `Notes`)
- Commit messages follow each staged file's git status: `Retranslate articles for: …` (modified), `Remove extra translations for: …` (deleted), `Update translations for: …` (mixed); added files keep `Translate articles for: …`
- OUTDATED Notes end with `; same commit changed N of M translations` when the English commit also changed some of the post's translations (a fix across languages); those rows are still retranslated — a Review step was rejected as costlier than retranslating ~26 posts (`scan_helpers.git_history()`, same single `git log` pass)
- `tools/translation_agent/scan_helpers.py` and tests: `test_scan_helpers.py`, `test_scan_missing_translations.py`, `test_outdated_rows.py`, `test_commit_message_kinds.py`, `test_history_scan_updates.py` (first tests for `update_history_tab`)
- Translated `title`, `seoTitle` and `description` are kept within search-result length (70 / 70 / 170 display width, East Asian characters count 2, the Health and Recovery audit's rule): a longer translation is shortened by a second LLM call that keeps product names (`TranslationConfig.length_limits`, `FrontmatterTranslatorAgent._fit_length`). Found 12 Nov 2026: the Java merge post's new translations had titles up to 82 and descriptions up to 197 wide
- `Issue` (`MISSING`/`EXTRA`) and `Action` (`Translate`/`Delete`) columns in the scan sheet — each flagged post now produces separate MISSING and/or EXTRA rows instead of one ambiguous combined row, so the sheet is directly actionable
- `TranslationOrchestrator.delete_extra_files()` / `filter_extra_rows()` in `translator.py` — deletes junk/extra files flagged by `EXTRA`-issue scan rows (reconstructed as `index.<fragment>.md`), using the same `git add content/` → commit → push mechanism as translations
- `AI Decision` + `AI Decision Reason` sheet columns — the LLM validation pass now returns an explicit RETRANSLATE/KEEP decision and reason instead of the retranslator independently re-deriving that call from a hardcoded `--threshold`
- `tools/translation_agent/build_commit_message.py` — generates a descriptive commit title/body (translated post + per-language file list, sourced from each post's English `index.md` title) from the actual staged files, replacing the static "Daily Blogs Translation: $DOMAIN" message, across all 7 translation workflows
- Aspose.LLM added to the product list (workflow inputs + `config.py`)
- `docs/PIPELINE_MAP.html` — visual pipeline map

### Changed
- **OUTDATED rows go newest post first** (19 Nov 2026): within a priority, Step 2 works OUTDATED rows by the post date in the folder name (`scan_queue.post_date()` / `order_rows()`; undated folders last), and the scanner adds new OUTDATED rows in that order (same date → newest English edit). MISSING and ISSUE rows stay first in, first out. Why: the "newest English edit first" order tied on the hundreds of posts the optimizer edited the same day and fell back to folder order, so 2022 posts came before 2026 ones. Tests in `test_scan_queue.py` / `test_outdated_rows.py`
- `resort_queue.py` — re-sorts the OUTDATED rows of the domain tabs newest post first by hand (only OUTDATED rows move; dry run unless `--apply`; `--domain`; changed tabs backed up as `bak-…`), so the sheet reads in work order. Tests: `test_resort_queue.py`
- `reset_scan_queue.py`'s closing hint names the scan workflow correctly ("Daily Blogs Scan - Missing Translations")
- Step 2 orders open queue rows by Priority, then sheet order (`queue_order()` replaces `missing_first()`); a tab without Priority falls back to the issue's default, so old-format tabs still work
- Step 2's per-post comments go to the post's open queue rows sharing a language with the run (`append_queue_comments`), any issue; they move to `history` with the row
- `history` tab holds completed rows only (history `Scan Date` = first flagged); gains `Priority` and `Source` columns; blog.groupdocs.com closed rows are dropped, not historied
- The summary sheet links to the domain's queue tab
- Scanner reads only the `index.md` front matter, with `utf-8-sig`; skips folders without `index.md`; author handles and the summary count/email cover MISSING/EXTRA posts only
- Scanner needs `PROFESSIONALIZE_API_KEY` only with `--translate`
- Translate workflows sync with `git merge --ff-only --autostash`, so retranslated (modified, tracked) files survive a remote change during the run
- Posts with `draft: true` in `index.md` front matter are excluded from the missing-translations scan and skipped by the translator, since draft content isn't final and won't be re-synced into existing translations once published
- Missing-translations sheet headers renamed: `Missing Count` → `Count`, `Missing Translations` → `Target Translations`, `Extra Translations` → `Action`
- History tab tracking now keyed on `(domain, slug, issue)` instead of `(domain, slug)`, so `MISSING` and `EXTRA` lifecycles for the same post progress independently
- AI decision policy leans toward RETRANSLATE whenever there's doubt — any fully untranslated sentence or meaningful phrase triggers it regardless of the overall Error% score; `KEEP` is reserved for leftover brand/product names, abbreviations, or stray technical terms; fallback-only decision threshold lowered 70% → 30%
- `quality_retranslator.py` row selection now filters on `AI Decision == RETRANSLATE`; removed the now-dead `--threshold` flag
- All translate workflows now `git fetch origin && git merge --ff-only` before staging translated files, to avoid push failures from remote changes during the 10–30+ min translation window
- Translation commits across all 7 workflows (`.github/workflows/translate-blog-*.yml`, `translate-blogs.yml`) are now authored/committed as `shoaibkhan-aspose <shoaib.khan@aspose.com>` instead of a generic bot identity; removed the dead `git config --global user.name/email` lines that were silently overridden by the `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env vars and never took effect

### Removed
- Scanner no longer writes the old per-domain sheets, and Step 2 no longer falls back to them (a queue read failure now fails the run and triggers the failure alert)
- `write_domain_scan_results`, `update_history_tab`, `get_history_first_seen`, `append_history_comment(s)` and `test_history_scan_updates.py` — replaced by the queue functions and `test_scan_queue.py`

### Fixed
- Scanner: a `draft: true` listed after `author`/`url` was missed; a post without `author` crashed the scan; a missing API key stopped the scan after the first domain; an orphan folder (translations, no `index.md`) was queued as MISSING for every language
- `update_history_tab()` rewrote whole history rows `USER_ENTERED`, including Comments cells that start with `- ` and could turn into formulas; it now writes Scan Date…Completed Date and Notes (`RAW`) only
- Pre-existing bug where the LLM-exception fallback in `quality_validator.py` nested a tuple instead of unpacking it
- Positional column reads in `translator.py` and `update_history_tab()` that shifted by one due to the inserted `Issue` column

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
