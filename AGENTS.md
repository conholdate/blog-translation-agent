# AGENTS.md
# Blog Translation Agent — Governance Policy

This file defines the operational boundaries for the Blog Translation Agent and its pipeline components.
The agent must not read, write, or modify any path not explicitly listed below.

Last updated: 2026-06-14
Authority: Shoaib Khan

---

## Agent

### Blog Translation Agent

One agent. Four pipeline steps. Two implementation directories.

**Translation Pipeline (Steps 1 & 2)**
- Step 1 — Scan: `tools/translation_agent/scan_missing_translations.py`
- Step 2 — Translate: `tools/translation_agent/translator.py`

**Quality Pipeline (Steps 3 & 4)**
- Step 3 — Quality Check: `tools/quality_agent/quality_scanner.py` → `quality_validator.py`
- Step 4 — Retranslate: `tools/quality_agent/quality_retranslator.py`

---

## Allowed Read Paths

| Path | Used by |
|------|---------|
| `tools/translation_agent/` | Translation Pipeline (Steps 1 & 2) |
| `tools/quality_agent/` | Quality Pipeline (Steps 3 & 4) |
| `blog-checkedout-repo/content/` | All pipeline steps (read originals and existing translations) |
| `.github/workflows/` | CI reference only |

---

## Allowed Write Paths

| Path | Step | What is written |
|------|------|-----------------|
| `blog-checkedout-repo/content/Aspose.Blog/**` | Step 2 (Translate), Step 4 (Retranslate) | `index.{lang}.md` translated files |
| `blog-checkedout-repo/content/Groupdocs.Blog/**` | Step 2 (Translate), Step 4 (Retranslate) | `index.{lang}.md` translated files |
| `blog-checkedout-repo/content/Conholdate.Total/**` | Step 2 (Translate), Step 4 (Retranslate) | `index.{lang}.md` translated files |
| `blog-checkedout-repo/content/Aspose.Cloud/**` | Step 2 (Translate), Step 4 (Retranslate) | `index.{lang}.md` translated files |
| `blog-checkedout-repo/content/GroupDocs.Cloud/**` | Step 2 (Translate), Step 4 (Retranslate) | `index.{lang}.md` translated files |
| `blog-checkedout-repo/content/Conholdate.Cloud/**` | Step 2 (Translate), Step 4 (Retranslate) | `index.{lang}.md` translated files |
| Google Sheets (via API) | All steps | Metrics, scan results, quality scores |

---

## Forbidden Paths — Never Modify

| Path | Reason |
|------|--------|
| `AGENTS.md` | Self-referential — policy file must not be auto-edited |
| `requirements.txt` | Dependency manifest — human-controlled |
| `requirements.lock` | Lockfile — human-controlled |
| `tools/translation_agent/config.py` | Runtime configuration — changing this affects all workflows |
| `tools/translation_agent/translator.py` | Core agent logic — not self-modifying |
| `tools/quality_agent/*.py` | Quality pipeline logic — not self-modifying |
| `.github/workflows/` | CI definitions — human-controlled |
| `tools/translation_agent/tests/` | Test suite — human-controlled |
| `tools/quality_agent/tests/` | Test suite — human-controlled |
| `README.md` | Documentation — human-controlled |
| `CONTRIBUTING.md` | Documentation — human-controlled |
| `docs/` | Documentation — human-controlled |
| `.github/CODEOWNERS` | Ownership file — human-controlled |

---

## Pipeline Steps

```
Blog Translation Agent
  Step 1 — Scan
    1. Walk blog-checkedout-repo/content/ (read-only)
    2. Detect every post missing a translated version
    3. Write results to Google Sheets

  Step 2 — Translate
    1. Read missing translations from Google Sheets
    2. Checkout target blog repo (read-only except content/)
    3. Translate English index.md → index.{lang}.md
    4. Write translated file to blog-checkedout-repo/content/...
    5. Send metrics to Google Sheets

  Step 3 — Quality Check
    Phase A — Scanner
      1. Walk blog-checkedout-repo/content/ (read-only)
      2. Compute heuristic Error% per translated file
      3. Write results to quality Google Sheet
    Phase B — Validator
      1. Read quality sheet rows
      2. Run AI-based Error% check on flagged files (read-only on files)
      3. Update Error% AI and Analysed At cells in sheet

  Step 4 — Retranslate
    1. Read quality sheet for files above error threshold
    2. Re-translate file via Step 2 pipeline
    3. Write corrected index.{lang}.md to blog-checkedout-repo/content/...
    4. Update Status and Analysed At cells in sheet
```

---

## Safety Rules

- Agents must never modify the English source file (`index.md`) — only language variants (`index.{lang}.md`)
- Agents must validate `PROFESSIONALIZE_API_KEY` is present before starting any LLM call
- Agents must validate Google credentials before accessing any sheet
- Metrics failures must not halt the main pipeline
- Per-file failures must be isolated — one failure must not stop processing of remaining files
- `PRODUCTION_ENV` is auto-detected from the presence of `.env` at the project root (`True` in CI, `False` locally) — never set this manually from agent code
