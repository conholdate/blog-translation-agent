# AGENTS.md
# Blog Translation Agents — Governance Policy

This file defines the operational boundaries for all AI agents in this repository.
Agents must not read, write, or modify any path not explicitly listed below.

Last updated: 2026-04-30
Authority: Shoaib Khan

---

## Agents

### 1. Blog Translation Agent
**Entry point:** `tools/translation_agent/translator.py`
**Purpose:** Scans blog repositories for missing translations and produces translated Markdown files.

### 2. Blog Translation Quality Control Agent
**Entry point:** `tools/quality_agent/quality_scanner.py` → `quality_validator.py` → `quality_retranslator.py`
**Purpose:** Scores translation quality and force-retranslates files above the error threshold.

---

## Allowed Read Paths

| Path | Used by |
|------|---------|
| `tools/translation_agent/` | Translation Agent |
| `tools/quality_agent/` | Quality Agent |
| `blog-checkedout-repo/content/` | Both agents (read originals and existing translations) |
| `.github/workflows/` | CI reference only |

---

## Allowed Write Paths

| Path | Agent | What is written |
|------|-------|-----------------|
| `blog-checkedout-repo/content/Aspose.Blog/**` | Translation Agent, Quality Retranslator | `index.{lang}.md` translated files |
| `blog-checkedout-repo/content/Groupdocs.Blog/**` | Translation Agent, Quality Retranslator | `index.{lang}.md` translated files |
| `blog-checkedout-repo/content/Conholdate.Total/**` | Translation Agent, Quality Retranslator | `index.{lang}.md` translated files |
| `blog-checkedout-repo/content/Aspose.Cloud/**` | Translation Agent, Quality Retranslator | `index.{lang}.md` translated files |
| `blog-checkedout-repo/content/GroupDocs.Cloud/**` | Translation Agent, Quality Retranslator | `index.{lang}.md` translated files |
| `blog-checkedout-repo/content/Conholdate.Cloud/**` | Translation Agent, Quality Retranslator | `index.{lang}.md` translated files |
| Google Sheets (via API) | Both agents | Metrics, scan results, quality scores |

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

---

## Pipeline Steps

```
Translation Agent
  1. Read missing translations from Google Sheets
  2. Checkout target blog repo (read-only except content/)
  3. Translate English index.md → index.{lang}.md
  4. Write translated file to blog-checkedout-repo/content/...
  5. Send metrics to Google Sheets

Quality Control Agent
  Phase 1 — Scanner
    1. Walk blog-checkedout-repo/content/ (read-only)
    2. Compute heuristic Error% per translated file
    3. Write results to quality Google Sheet

  Phase 2 — Validator
    1. Read quality sheet rows
    2. Run AI-based error% check on flagged files (read-only on files)
    3. Update Error% AI and Analysed At cells in sheet

  Phase 3 — Retranslator
    1. Read quality sheet for files above error threshold
    2. Re-translate file via Translation Agent pipeline
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
- `PRODUCTION_ENV` in `config.py` controls whether production metrics are sent — never toggle this from agent code
