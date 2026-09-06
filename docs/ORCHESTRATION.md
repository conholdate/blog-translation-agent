# Orchestration

State model, control flow, and extension points for all four pipeline steps of the Blog Translation Agent.

---

## Step 1 — Scan: Consolidated Scan Sheet

The scanner writes to two places on every run:

**1. Per-domain tab** (`TRANSLATION_SCAN_SHEET_ID` — tab named by domain)
- Cleared and rewritten on each scan — always shows current issues only
- Columns: Scan Date, Domain, Product, Blog Post Directory, Blog Post URL, Author, Issue, Count, Target Translations, Action, Status
- `Issue` is `MISSING` (some language translations don't exist) or `EXTRA` (unexpected/junk files present); a post with both produces **two rows**, one per issue
- `Target Translations` is generic: missing language codes on a `MISSING` row, junk filenames on an `EXTRA` row
- `Action` is the corresponding remediation verb: `Translate` for `MISSING`, `Delete` for `EXTRA`
- Posts whose `index.md` has `draft: true` in front matter are excluded entirely — they never appear as missing, since draft content isn't final and won't be re-synced into translations once published

**2. History tab** (append-only, never cleared)
- One row per (blog post, issue type) per detection event, keyed by `(domain, slug, issue)` — MISSING and EXTRA lifecycles for the same post are tracked independently
- Status lifecycle: `pending` → `partial` → `completed`

### History Tab — Completion Detection

On each scan, `update_history_tab()` checks every pending history row against the current scan results **for the same `(domain, slug, issue)` key** — a MISSING row's langs are only ever compared against MISSING results, and an EXTRA row's filenames only against EXTRA results:

```
remaining = this_row_items ∩ current_scan_items_for_same_issue
```

| `remaining` | Meaning | Action |
|-------------|---------|--------|
| empty | All items in this row are resolved (translated, or junk file deleted) | `completed` + Completed Date = scan_date |
| `remaining < this_row_items` | Some resolved, some still flagged | `partial` + items updated to remaining |
| `remaining == this_row_items` | Nothing changed | no update |
| post+issue not in scan at all | Fully resolved | `completed` + Completed Date = scan_date |

**Note:** Completion is detected on the **next scan after** the translation is committed — the scanner must re-run with the updated blog repo to detect completion.

---

## Step 2 — Translate

### Entry Point

```
translator.py  →  start_translation()  →  filter_valid_rows()  →  TranslationOrchestrator.translate_files()
```

### State Model (Step 2)

| State | Description |
|-------|-------------|
| **Pending** | Row exists in Google Sheet with missing languages in column 7 |
| **Filtered** | Row passes `filter_valid_rows()` — domain, product, slug, and missing langs all non-empty |
| **In Progress** | `TranslationOrchestrator` is actively translating the post |
| **Translated** | `index.{lang}.md` written to `blog-checkedout-repo/content/…` |
| **Skipped** | `index.{lang}.md` already exists on disk — no LLM call made |
| **Failed** | Exception during translation — error logged, remaining langs continue |

### Control Flow (Step 2)

```
start_translation(domain, author, limit)
│
├── read_from_google_spreadsheet(sheet_id)   # fetch pending rows
├── filter_valid_rows(posts_list)            # drop rows missing required fields
│
└── TranslationOrchestrator.translate_files(posts_list)
    │
    └── for each post row:
        │
        ├── parse_markdown_file(index.md)       # read English source
        ├── [skip entire post if front matter has draft: true]
        ├── PlatformIdentifierAgent             # identify .NET / Java / Python / etc.
        │
        └── for each missing language:
            │
            ├── [skip if index.{lang}.md exists]
            │
            ├── FrontmatterTranslatorAgent.translate()
            │   ├── translate title, description, tags
            │   ├── protect product names and critical metadata
            │   └── update URL with language prefix
            │
            ├── ContentTranslatorAgent.translate()
            │   ├── split content into chunks
            │   ├── _translate_content_chunk()  (up to 3 retries per chunk)
            │   │   ├── LLM call → translated chunk
            │   │   ├── _appears_translated()   # heuristic check
            │   │   └── _ai_should_retry()      # AI validation on failure
            │   └── reassemble chunks
            │
            ├── write_markdown_file(index.{lang}.md)
            └── send_metrics()
```

### Retry Logic (Step 2)

`ContentTranslatorAgent._translate_content_chunk()` retries up to **3 times** per chunk:
1. First attempt — standard prompt
2. On failure — enhanced prompt explicitly requesting translation
3. On second failure — AI validation (`_analyze_translation_validity`) decides whether to accept or retry once more

---

## Steps 3 & 4 — Quality Check & Retranslate

### Entry Point (run in order)

```
quality_scanner.py      →  Step 3, Phase A: heuristic scan
quality_validator.py    →  Step 3, Phase B: AI validation
quality_retranslator.py →  Step 4: retranslation
```

Re-run Step 3 Phase B after Step 4 to fill the `Error% after Fix` column.

### State Model (per sheet row)

| Column state | Meaning |
|---|---|
| `Error% Heuristic` filled, `Error% AI` blank | Step 3 Phase A complete, Phase B pending |
| `Error% AI` = `NA` | Heuristic was 0% — file is fully translated, no LLM cost incurred |
| `Error% AI` filled, `Status` blank | Step 3 complete, Step 4 pending |
| `Status` = `Fixed` | Step 4 complete — re-run Step 3 Phase B to fill `Error% after Fix` |
| `Error% after Fix` filled | Full quality cycle complete |

### Control Flow — Step 3, Phase A (Scanner)

```
scan_domain(domain)
│
└── for each index.{lang}.md under blog-checkedout-repo/content/…:
    │
    ├── _parse_original_metadata(index.md)   # read URL and author
    ├── _heuristic_error_pct()               # word-overlap comparison vs English
    │   ├── strip frontmatter, code blocks, shortcodes
    │   └── (matching_words / total_words) * 100
    ├── _build_translated_url()
    └── write row to quality Google Sheet
        (sorted by Error% Heuristic descending)
```

### Control Flow — Step 3, Phase B (Validator)

```
validate_domain(domain, limit)
│
└── for each unanalysed row in quality sheet:
    │
    ├── [skip if Error% AI already filled]
    ├── [mark NA if Error% Heuristic = 0%]  →  Error% AI = NA, AI Decision = NA, AI Decision Reason = fixed text
    │
    ├── sample up to 20 paragraphs from the translated file
    ├── LLM call → returns Error% + DECISION (RETRANSLATE/KEEP) + short REASON + up to 5 untranslated samples
    ├── write Error% AI, Untranslated Samples, AI Decision, AI Decision Reason, Analysed At
    │
    └── [if Status = Fixed]  →  write Error% after Fix instead (AI Decision/Reason still overwritten)
│
└── re-sort sheet by Error% AI descending
```

### Control Flow — Step 4 (Retranslator)

```
retranslate_domain(domain, limit)
│
└── for each row where AI Decision = RETRANSLATE AND Status is blank:
    │
    ├── TranslationOrchestrator.translate_file()   # force-overwrites existing file
    └── update sheet: Status = "Fixed", Analysed At = now
```

---

## Extension Points

### Add a new domain

| File | Change |
|------|--------|
| `tools/translation_agent/config.py` | Add `DOMAIN_*` constant, `LANGS_*` string, `SHEET_ID_*`, `QUALITY_SHEET_ID_*`, entry in `domains_data` |
| `.env` (project root) | Add `TRANSLATION_SCAN_SHEET_ID_*` and `QUALITY_SHEET_ID_*` values |
| `tools/translation_agent/git_repo_utils.py` | Add repo entry to the `repos` list |
| `tools/quality_agent/quality_scanner.py` | Add entry to `QUALITY_SHEET_IDS` |
| `tools/quality_agent/quality_validator.py` | Add entry to `QUALITY_SHEET_IDS` |
| `tools/quality_agent/quality_retranslator.py` | Add entry to `QUALITY_SHEET_IDS` |
| `.github/workflows/` | Add domain to the matrix in both workflow files |

### Add a new language

| File | Change |
|------|--------|
| `tools/translation_agent/config.py` | Append language code to the relevant `LANGS_*` pipe-separated string |
| `tools/quality_agent/lang_guard.py` | Add code to `SUPPORTED_LANGS` and display name to `LANG_NAMES` |

### Change the LLM

Update `PROFESSIONALIZE_BASE_URL` and `PROFESSIONALIZE_LLM_MODEL` in `.env`. No code changes required.

### Adjust the retranslation decision

The retranslate/keep call is made by the LLM itself during Step 3 Phase B validation (`AI Decision` column), not by a locally configurable threshold in `quality_retranslator.py`. To change the criteria, edit the DECISION instructions in the validator's prompt in `tools/quality_agent/quality_validator.py`'s `_ai_error_pct()`. A numeric threshold (`FALLBACK_DECISION_THRESHOLD`, default `70`) still exists in that file, but only as a safety net used when the LLM's response can't be parsed or the call fails entirely.

### Batch large runs

All three quality scripts accept `--limit <N>` to cap rows processed per run.
