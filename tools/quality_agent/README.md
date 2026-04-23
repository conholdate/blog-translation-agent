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
- Same virtual environment as the Blog Translation Agent (`.venv`)
- Google Sheets service account credentials (same as the translation agent)
- API key for the translation/LLM service

---

## Installation

No additional dependencies. The quality agent shares the same `requirements.txt` and `.venv` as the translation agent.

```bash
cd blog-post-translator
source .venv/bin/activate    # Windows: .venv\Scripts\activate
```

---

## File Structure

```
tools/
├── translation_agent/          # Existing translation agent
└── quality_agent/              # Quality Control Agent
    ├── quality_scanner.py      # Phase 1 — heuristic scan
    ├── quality_validator.py    # Phase 2 — AI validation
    ├── quality_retranslator.py # Phase 3 — retranslation
    └── lang_guard.py           # Language utility functions
```

---

## Google Sheets

Each domain has its own quality sheet. The sheet is created/overwritten each run with a tab named by date (`YYYY-MM-DD`).

Sheet IDs are configured in `quality_scanner.py` under `QUALITY_SHEET_IDS`. Ask the team for access to the relevant sheets.

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
