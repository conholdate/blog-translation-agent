# Translation Pipeline — Steps 1 & 2

This directory implements the first two steps of the **Blog Translation Agent**: scanning blog repositories for missing translations and filling them in with AI-powered translation.

---

## Overview

| Step | Script | What it does |
|------|--------|--------------|
| **1 — Scan** | `scan_missing_translations.py` | Walks all blog repositories, finds missing, extra and outdated translations (with a `Notes` reason) and reconciles them into the persistent translation queue (domain tab of the scan sheet) |
| **2 — Translate** | `translator.py` | Reads the scan results, fills in missing translations and retranslates outdated ones using an LLM (preserving formatting, code blocks, and front matter), and deletes extra/junk files flagged with `Action = Delete` |

Steps 3 & 4 (Quality Check and Retranslate) live in `tools/quality_agent/`. See the [root README](../../README.md) for the full pipeline.

---

## Features

- Automated daily scanning — detects missing translations across all domains
- AI-powered translation with retry logic and quality validation
- Format preservation — maintains Markdown formatting, code blocks, and links
- Front-matter protection — never translates product names or critical metadata
- Multi-domain support — works across 6 blog domains
- 22 languages
- GitHub Actions integration — automated daily workflows

---

## Prerequisites

- Python 3.13+
- API key for translation service (Professionalize LLM)
- Google Sheets API credentials (for scanning reports)
- GitHub access token (for repository operations)

---

## Installation

### 1. Clone Repository

```bash
git clone <repo-url>
cd blog-translation-agent
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.lock
```

---

## Configuration

Create `.env` at the **project root** (copy from `.env.example`) with the variables below. In GitHub Actions these are stored as repository secrets. `config.py` loads this file automatically via `python-dotenv`.

```bash
# LLM translation service
PROFESSIONALIZE_API_KEY=
PROFESSIONALIZE_BASE_URL=
PROFESSIONALIZE_LLM_MODEL=

# Google Sheets — scan summary sheet and quality sheets (full JSON, minified to one line)
GOOGLE_CREDENTIALS_JSON_SK=

# Google Sheets — consolidated scan sheet (full JSON, minified to one line)
GOOGLE_SERVICE_ACCOUNT_JSON=
TRANSLATION_SCAN_SHEET_ID=

# GitHub access
PAT_GITHUB_SK=

# Local clone paths for the six blog repositories
CLONE_PATH_GITHUB_ASPOSE_COM=
CLONE_PATH_GITHUB_ASPOSE_CLOUD=
CLONE_PATH_GITHUB_GROUPDOCS_COM=
CLONE_PATH_GITHUB_GROUPDOCS_CLOUD=
CLONE_PATH_GITHUB_CONHOLDATE_COM=
CLONE_PATH_GITHUB_CONHOLDATE_CLOUD=

# Metrics
METRICS_API_KEY=
METRICS_WEBHOOK_URL_TEAM=
METRICS_TOKEN_TEAM=

# Old per-domain scan sheet IDs — no longer written or read (since 18 Nov 2026)
TRANSLATION_SCAN_SHEET_ID_ASPOSE_COM=
TRANSLATION_SCAN_SHEET_ID_ASPOSE_CLOUD=
TRANSLATION_SCAN_SHEET_ID_GROUPDOCS_COM=
TRANSLATION_SCAN_SHEET_ID_GROUPDOCS_CLOUD=
TRANSLATION_SCAN_SHEET_ID_CONHOLDATE_COM=
TRANSLATION_SCAN_SHEET_ID_CONHOLDATE_CLOUD=
TRANSLATION_SCAN_SHEET_ID_SUMMARY=
TRANSLATION_SCAN_SHEET_ID_TEST_QA=
```

---

## Usage

### Step 1: Scan for Missing Translations

Scans blog repositories and reconciles the results into the translation queue — the domain tab of
the consolidated scan sheet, which is never cleared: fixed languages are removed, rows with nothing
left move to `history`, new findings are added at the bottom, and people's edits (row splits,
Priority, Status, Comments) are kept. EXTRA rows go to the shared `cleanup` tab. No LLM key is
needed to scan.

```bash
python tools/translation_agent/scan_missing_translations.py --domain <DOMAIN>
```

**Options:**
- `--domain` (required) — Target domain or `all`
- `--translate` — also translate after scanning (currently paused in code); only this needs `PROFESSIONALIZE_API_KEY` / `--key`
- `--product`, `--author`, `--limit` — only used with `--translate`

**What it reports** (one row per post and issue):

| Issue | Action | When |
|---|---|---|
| `MISSING` | `Translate` | a supported language has no `index.{lang}.md` |
| `EXTRA` | `Delete` | a `.md` file that isn't `index.md` / `index.{supported lang}.md` |
| `OUTDATED` | `Retranslate` | `index.md` was committed after `index.{lang}.md` (git history; a fix committed to both together isn't outdated) |

Skipped: drafts (`draft: true`), folders without `index.md`, undated folders and discount posts.
The OUTDATED check needs the blog repo's git history; on the local test mirror it is skipped with a
warning. Full rules: [docs/ORCHESTRATION.md — Step 1](../../docs/ORCHESTRATION.md#step-1--scan-consolidated-scan-sheet).

**Example:**
```bash
python tools/translation_agent/scan_missing_translations.py --domain blog.aspose.com
```

---

### Step 2: Translate Blog Posts

Reads the queue (domain tab) and translates posts into missing languages (`MISSING` rows), and
overwrites translations for `OUTDATED` rows and `ISSUE` rows (retranslation requests). Open rows
only, by Priority — Urgent, High (MISSING), Normal (ISSUE), Low (OUTDATED) — then sheet order. The
run translates up to `--limit` × the blog's languages (a row that doesn't fit is cut; the rest stays
queued) and starts no new language after `--time-limit` minutes (default 300). Translated languages
are closed in the queue right after each post.

To request a retranslation (ISSUE row):

```bash
python tools/translation_agent/queue_add.py --domain blog.aspose.com \
  --post pdf/2024-05-01-my-post --langs "fr, de" --reason "Tables left in English" \
  [--source <agent>] [--priority Urgent] [--dry-run]
```

```bash
python tools/translation_agent/translator.py \
  --domain <DOMAIN> \
  --key <API_KEY> \
  [--product <PRODUCT>] \
  [--author <AUTHOR>] \
  [--limit <POSTS_WORTH>] \
  [--time-limit <MINUTES>]
```

**Required Parameters:**
- `--domain` — Target blog domain
- `--key` — API key (sk-xxxxxxxxx)

**Optional Parameters:**
- `--product` — Specific product (e.g., email, cells, conversion)
- `--author` — Author name (e.g., "Muhammad Mustafa")
- `--limit` — Run budget in posts' worth: limit × the blog's language count translations (default 3; workflows use 2)
- `--time-limit` — Minutes after which no new language is started (default 300)

---

## Supported Domains

- `blog.aspose.com`
- `blog.groupdocs.com`
- `blog.conholdate.com`
- `blog.aspose.cloud`
- `blog.groupdocs.cloud`
- `blog.conholdate.cloud`

---

## Supported Languages

```
ar (Arabic)         | cs (Czech)       | de (German)      | es (Spanish)
fa (Persian)        | fr (French)      | he (Hebrew)      | id (Indonesian)
it (Italian)        | ja (Japanese)    | ko (Korean)      | nl (Dutch)
pl (Polish)         | pt (Portuguese)  | ru (Russian)     | sv (Swedish)
th (Thai)           | tr (Turkish)     | uk (Ukrainian)   | vi (Vietnamese)
zh (Chinese)        | zh-hant (Chinese Traditional)
```

**Total: 22 languages**

---

## Architecture

### File Structure

```
tools/translation_agent/
├── translator.py                  # TranslationOrchestrator + 3 agent classes + delete_extra_files()
├── scan_missing_translations.py   # Missing / extra / outdated-translation scanner
├── scan_helpers.py                # Scanner helpers: front matter, git history, Notes text
├── scan_queue.py                  # Queue reconcile rules (pure logic, no sheet access)
├── queue_add.py                   # CLI: request a retranslation (ISSUE row)
├── reset_scan_queue.py            # One-time queue reset (18 Nov 2026; dry run unless --apply)
├── git_repo_utils.py              # Clone / pull blog repos via GitHub PAT
├── io_google_spreadsheet.py       # Google Sheets: queue sync / read, cleanup, history, comments, add_to_queue
├── build_commit_message.py        # Commit title/body from staged files (Translate / Retranslate / Remove)
├── commit_translations.py         # One commit per post, used by the translate workflows
├── utils.py                       # Metrics webhook calls
├── config.py                      # All constants and env-var-backed secrets
└── tests/
```

### Internal Agents

**TranslationOrchestrator**
- Coordinates the full translation workflow and token tracking
- Wires up the three specialized agents below

**FrontmatterTranslatorAgent**
- Translates YAML front matter fields (title, description, tags)
- Protects product names and critical metadata
- Updates URLs with language prefix

**ContentTranslatorAgent**
- Translates Markdown body in chunks
- Preserves code blocks, Hugo shortcodes, and formatting
- Retries up to 3 times per chunk with AI validation on failure

**PlatformIdentifierAgent**
- Identifies the programming platform (.NET, Java, Python, …)
- Provides platform context to improve translation accuracy

For the full control flow and state model see [docs/ORCHESTRATION.md](../../docs/ORCHESTRATION.md).

---

## GitHub Actions

### Daily Scan Workflow

Runs automatically at 00:00 and 12:00 UTC.

**File:** `.github/workflows/scan-missing-translations.yml`

**Trigger:** Scheduled (cron) or manual dispatch

**Matrix:** Runs for all 6 domains in parallel (`fail-fast: false`)

### Translation Workflows

One workflow per domain. The five maintained blogs' workflows start when a scheduled scan finishes
(two runs per blog a day, 2 posts' worth each); blog.groupdocs.com is manual only. One run per blog
at a time.

**Files:** `.github/workflows/translate-blog-*.yml`

**Trigger:** `workflow_run` after a scheduled scan (success or failure; not cancelled or manual scans), or manual dispatch

---

## Reports

Scan results are automatically saved to Google Sheets with:
- Domain
- Product name
- Blog post directory
- Author
- Issue (`MISSING`, `EXTRA` or `OUTDATED` — one row per issue of a post)
- Count
- Target Translations (missing / outdated language codes, or junk fragments for `EXTRA`)
- Action (`Translate`, `Delete` or `Retranslate`)
- Status — blank / `partial` = open; `hold` (or any other value) = skipped; `invalid` = a manual row the scan can't match
- Notes — why the row was flagged, e.g. `New post`, `3 of 21 languages missing`,
  `English updated 2026-11-16 by optimizer-agent ("Optimized Blog Posts"); translations from 2025-05-09`;
  when the English commit also changed some translations (a fix across languages) it adds
  `; same commit changed 18 of 22 translations` — the untouched ones are still retranslated
- Direct links to details

The domain tab (the queue) also has Scan Date, Missing Since (first flagged, never changed), Days
Missing, Priority, Source and Comments (Step 2 results). Closed rows move to the `history` tab
(completed rows only; none for blog.groupdocs.com). EXTRA rows are in the `cleanup` tab.

**Summary Sheet:** Aggregated daily reports across all domains

---

## Security

- **API Keys:** Store in GitHub Secrets or environment variables
- **Google Credentials:** Use service account with minimal permissions
- **GitHub Tokens:** Use Personal Access Tokens (PAT) with repo scope only
- **Never commit:** `.env` files, API keys, or credentials

---

## Troubleshooting

**Scan log says `No git history for … — OUTDATED check skipped`**
The blog repo has no git history (local test mirror, or a shallow checkout). In CI the scan workflow
checks out with `fetch-depth: 0`; keep it.

**A fix in the English post was flagged OUTDATED but needs no retranslation**
Commit the English fix together with the same fix in the translations — equal commit times are not
outdated. To skip it, set the row's Status to `hold` (removing the row only skips it until the next
scan adds it back); to settle it, commit the translations after the English fix (any commit that
touches them).

**Translation fails with `401 Authentication Error`**
Verify API key is valid and active.

**Translation returns untranslated content**
The agent retries up to 3 times per chunk with enhanced prompts.

**`Spreadsheet not found`**
Check Google credentials and sheet permissions.

**Repository not accessible**
Verify GitHub token has correct permissions.

**Code blocks not preserved**
The agent automatically detects and skips translation validation for code blocks. If issues persist, check Markdown formatting.
