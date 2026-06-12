# Blogs Translation Quality Control Agent

A three-phase pipeline that scans all existing translated blog posts, scores their translation quality using AI, and retranslates the poor-quality ones — ensuring every language version is genuinely translated and not just a copy of the English original.

---

## Overview

The Quality Control Agent adds three automated phases on top of the existing Blog Translation Agent:

| Phase | Script | What it does |
|-------|--------|--------------|
| 1 | `quality_scanner.py` | Traverses all repos, computes a heuristic Error% per file, writes results to Google Sheets |
| 2 | `quality_validator.py` | Reads the sheet, sends files to an LLM for AI-based Error% scoring, back-fills the sheet |
| 3 | `quality_retranslator.py` | Reads the sheet, force-retranslates files with AI Error% above a threshold |

---

## Prerequisites

- Python 3.13+
- Root `.venv` from the project root (shared with the Translation Agent)
- `.env` at the project root with all required variables
- API key for the translation/LLM service

---

## Installation

No additional dependencies. The quality agent shares `requirements.lock`, `.venv`, and `.env` with the translation agent — all at the project root.

```bash
cd blog-post-translator
source .venv/bin/activate    # Windows: .venv\Scripts\activate
```

If you haven't set up the environment yet:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
cp .env.example .env          # then fill in values
```

---

## Environment Variables

The quality agent shares `config.py` and `.env` (at the project root) with the translation agent. All variables are listed in [.env.example](../../.env.example).

The key variables used by the quality agent are:

| Variable | Purpose |
|----------|---------|
| `PROFESSIONALIZE_API_KEY` | LLM API key for AI validation and retranslation |
| `PROFESSIONALIZE_BASE_URL` | LLM endpoint URL |
| `PROFESSIONALIZE_LLM_MODEL` | Model name |
| `GOOGLE_CREDENTIALS_JSON_SK` | Google service account for per-domain scan sheets |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google service account for the consolidated scan sheet |
| `TRANSLATION_SCAN_SHEET_ID` | Consolidated scan sheet (one tab per domain + history) |
| `QUALITY_SHEET_ID_ASPOSE_COM` | Quality sheet ID for blog.aspose.com |
| `QUALITY_SHEET_ID_ASPOSE_CLOUD` | Quality sheet ID for blog.aspose.cloud |
| `QUALITY_SHEET_ID_GROUPDOCS_COM` | Quality sheet ID for blog.groupdocs.com |
| `QUALITY_SHEET_ID_GROUPDOCS_CLOUD` | Quality sheet ID for blog.groupdocs.cloud |
| `QUALITY_SHEET_ID_CONHOLDATE_COM` | Quality sheet ID for blog.conholdate.com |
| `QUALITY_SHEET_ID_CONHOLDATE_CLOUD` | Quality sheet ID for blog.conholdate.cloud |

---

## File Structure

```
tools/
├── translation_agent/          # Blog Translation Agent
└── quality_agent/              # Quality Control Agent
    ├── quality_scanner.py      # Phase 1 — heuristic scan
    ├── quality_validator.py    # Phase 2 — AI validation
    ├── quality_retranslator.py # Phase 3 — retranslation
    ├── lang_guard.py           # Language utility functions
    └── tests/                  # Unit tests
```

For the full state model and control flow see [docs/ORCHESTRATION.md](../../docs/ORCHESTRATION.md).

---

## Google Sheets

Each domain has its own quality sheet. The sheet is created/overwritten each run with a tab named by date (`YYYY-MM-DD`).

Sheet IDs are loaded from environment variables (`QUALITY_SHEET_ID_*`) via `config.py`. Ask the team for access to the relevant sheets.

### Sheet Columns

| # | Column | Filled by |
|---|--------|-----------|
| 1 | Domain | Scanner |
| 2 | Product | Scanner |
| 3 | Blog Post Directory | Scanner |
| 4 | Blog Post URL | Scanner |
| 5 | Author | Scanner |
| 6 | Page Lang | Scanner |
| 7 | Error% Heuristic | Scanner |
| 8 | Error% AI (LLM) | Validator |
| 9 | Untranslated Samples | Validator |
| 10 | Analysed At | Validator |
| 11 | Status | Retranslator / manual |
| 12 | Error% after Fix | Validator (re-run after fix) |
| 13 | Translated Page URL | Scanner |

---

## Phase 1 — Quality Scanner

Traverses all local blog repositories, finds every `index.{lang}.md` file, computes a heuristic Error% by comparing paragraph word sets against the English original, and writes one row per translated file to the domain's quality sheet sorted by Error% descending.

Skips code blocks, Hugo shortcodes, and front-matter — only prose text is evaluated.

```bash
python quality_scanner.py --domain <DOMAIN> --key <API_KEY>
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--domain` | Yes | Target domain (e.g. `blog.aspose.com`) or `all` |
| `--key` | No | LLM API key (or set `PROFESSIONALIZE_API_KEY` env var) |

**Examples:**

```bash
python quality_scanner.py --domain blog.aspose.com --key sk-xxxxxxxxx
python quality_scanner.py --domain all --key sk-xxxxxxxxx
```

---

## Phase 2 — Quality Validator

Reads the quality sheet and AI-validates translations not yet analysed:

- Rows where heuristic Error% is `0%` are marked `NA` immediately — no LLM call, no cost.
- For remaining rows: randomly samples up to 20 paragraphs and sends them to the LLM.
- LLM calculates `(untranslated_words / total_words) * 100` as the Error% score.
- LLM also returns up to 5 specific untranslated sentences or phrases as samples.
- Writes `Error% AI (LLM)`, `Untranslated Samples`, and `Analysed At` back to the sheet.
- Re-sorts the sheet by `Error% AI` descending so the worst translations are always at the top.
- Safe to re-run — skips already-analysed rows.
- On `Status = Fixed` rows: re-validates and fills the `Error% after Fix` column.

```bash
python quality_validator.py --domain <DOMAIN> --key <API_KEY> [OPTIONS]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--domain` | Yes | Target domain or `all` |
| `--key` | No | LLM API key |
| `--limit` | No | Max rows to validate per domain in this run |

**Examples:**

```bash
python quality_validator.py --domain blog.aspose.com --key sk-xxxxxxxxx
python quality_validator.py --domain all --limit 50 --key sk-xxxxxxxxx
```

---

## Phase 3 — Quality Retranslator

Reads the quality sheet and force-retranslates files where `Error% AI > threshold` and `Status` is blank. Uses the existing `TranslationOrchestrator` from the Blog Translation Agent — no changes to the original translator required.

After retranslation, sets `Status = Fixed` and updates `Analysed At`. The validator automatically picks up `Status = Fixed` rows on its next run to fill `Error% after Fix`.

```bash
python quality_retranslator.py --domain <DOMAIN> --key <API_KEY> [OPTIONS]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--domain` | Yes | Target domain or `all` |
| `--key` | No | LLM API key |
| `--threshold` | No | Minimum AI Error% to trigger retranslation (default: `70`) |
| `--limit` | No | Max rows to retranslate per domain in this run |

**Examples:**

```bash
python quality_retranslator.py --domain blog.aspose.com --key sk-xxxxxxxxx
python quality_retranslator.py --domain all --key sk-xxxxxxxxx
python quality_retranslator.py --domain blog.aspose.com --threshold 50 --limit 10 --key sk-xxxxxxxxx
```

---

## Full Pipeline

Run the phases in order. Each phase can also be scheduled independently.

```bash
# Phase 1 — Scan all domains
python quality_scanner.py --domain all --key sk-xxxxxxxxx

# Phase 2 — AI-validate results
python quality_validator.py --domain all --key sk-xxxxxxxxx

# Phase 3 — Retranslate poor-quality files
python quality_retranslator.py --domain all --key sk-xxxxxxxxx

# Phase 2 again — re-check fixed rows, fill Error% after Fix
python quality_validator.py --domain all --key sk-xxxxxxxxx
```

---

## Supported Domains

| Domain | Group |
|--------|-------|
| `blog.aspose.com` | Aspose |
| `blog.aspose.cloud` | Aspose |
| `blog.groupdocs.com` | GroupDocs |
| `blog.groupdocs.cloud` | GroupDocs |
| `blog.conholdate.com` | Conholdate |
| `blog.conholdate.cloud` | Conholdate |

---

## Supported Languages

```
ar  Arabic             cs  Czech            de  German
es  Spanish            fa  Persian          fr  French
he  Hebrew             id  Indonesian       it  Italian
ja  Japanese           ko  Korean           nl  Dutch
pl  Polish             pt  Portuguese       ru  Russian
sv  Swedish            th  Thai             tr  Turkish
uk  Ukrainian          vi  Vietnamese       zh  Chinese (Simplified)
zh-hant  Chinese (Traditional)
```

---

## Troubleshooting

**Sheet not found** — Confirm the Google service account has editor access to all quality sheets.

**`index.md` not found for a row** — The local blog repository may be out of date. Pull the latest changes from the remote.

**Retranslator skips a row that looks wrong** — Check that `Status` is blank and `Error% AI` is above the threshold. Rows with any non-blank status (e.g. `Fixed`, `NA`) are not retranslated.

**Validator re-processes already-analysed rows** — This should not happen. If `Error% AI` is filled, the validator skips the row. If the column appears blank in the sheet, check for invisible whitespace.

**High API cost on first validator run** — Use `--limit` to process rows in batches across multiple runs rather than all at once.
