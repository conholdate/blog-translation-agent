# Translation Pipeline — Steps 1 & 2

This directory implements the first two steps of the **Blog Translation Agent**: scanning blog repositories for missing translations and filling them in with AI-powered translation.

---

## Overview

| Step | Script | What it does |
|------|--------|--------------|
| **1 — Scan** | `scan_missing_translations.py` | Walks all blog repositories, detects every post missing a translated version, writes results to Google Sheets |
| **2 — Translate** | `translator.py` | Reads the scan results and fills in missing translations using an LLM — preserving formatting, code blocks, and front matter |

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

# Google Sheets — per-domain scan sheets (full JSON, minified to one line)
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

# Scanning sheet IDs
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

Scans blog repositories and writes results to Google Sheets.

```bash
python tools/translation_agent/scan_missing_translations.py --domain <DOMAIN>
```

**Options:**
- `--domain` (required) — Target domain or `all`

**Example:**
```bash
python tools/translation_agent/scan_missing_translations.py --domain blog.aspose.com
```

---

### Step 2: Translate Blog Posts

Reads the scan sheet and translates posts into missing languages.

```bash
python tools/translation_agent/translator.py \
  --domain <DOMAIN> \
  --key <API_KEY> \
  [--product <PRODUCT>] \
  [--author <AUTHOR>] \
  [--limit <NUMBER>]
```

**Required Parameters:**
- `--domain` — Target blog domain
- `--key` — API key (sk-xxxxxxxxx)

**Optional Parameters:**
- `--product` — Specific product (e.g., email, cells, conversion)
- `--author` — Author name (e.g., "Muhammad Mustafa")
- `--limit` — Number of posts to translate

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
├── translator.py                  # TranslationOrchestrator + 3 agent classes
├── scan_missing_translations.py   # Missing-translation scanner
├── git_repo_utils.py              # Clone / pull blog repos via GitHub PAT
├── io_google_spreadsheet.py       # Google Sheets read/write
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

Runs automatically at 00:00 UTC daily.

**File:** `.github/workflows/scan-missing-translations.yml`

**Trigger:** Scheduled (cron) or manual dispatch

**Matrix:** Runs for all 6 domains in parallel

### Translation Workflows

Run automatically at 01:00 UTC daily, one workflow per domain.

**Files:** `.github/workflows/translate-blog-*.yml`

**Trigger:** Scheduled (cron) or manual dispatch

---

## Reports

Scan results are automatically saved to Google Sheets with:
- Domain
- Product name
- Blog post directory
- Author
- Missing translation count
- Missing languages list
- Extra/invalid files
- Direct links to details

**Summary Sheet:** Aggregated daily reports across all domains

---

## Security

- **API Keys:** Store in GitHub Secrets or environment variables
- **Google Credentials:** Use service account with minimal permissions
- **GitHub Tokens:** Use Personal Access Tokens (PAT) with repo scope only
- **Never commit:** `.env` files, API keys, or credentials

---

## Troubleshooting

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
