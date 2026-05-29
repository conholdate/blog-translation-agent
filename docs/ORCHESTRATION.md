# Orchestration

State model, control flow, and extension points for both agent families.

---

## Translation Agent

### Entry Point

```
translator.py  →  start_translation()  →  filter_valid_rows()  →  TranslationOrchestrator.translate_files()
```

### State Model

| State | Description |
|-------|-------------|
| **Pending** | Row exists in Google Sheet with missing languages in column 7 |
| **Filtered** | Row passes `filter_valid_rows()` — domain, product, slug, and missing langs all non-empty |
| **In Progress** | `TranslationOrchestrator` is actively translating the post |
| **Translated** | `index.{lang}.md` written to `blog-checkedout-repo/content/…` |
| **Skipped** | `index.{lang}.md` already exists on disk — no LLM call made |
| **Failed** | Exception during translation — error logged, remaining langs continue |

### Control Flow

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

### Retry Logic

`ContentTranslatorAgent._translate_content_chunk()` retries up to **3 times** per chunk:
1. First attempt — standard prompt
2. On failure — enhanced prompt explicitly requesting translation
3. On second failure — AI validation (`_analyze_translation_validity`) decides whether to accept or retry once more

---

## Quality Control Agent

### Entry Point (3 phases, run in order)

```
quality_scanner.py    →  Phase 1: heuristic scan
quality_validator.py  →  Phase 2: AI validation
quality_retranslator.py →  Phase 3: retranslation
```

Re-run Phase 2 after Phase 3 to fill the `Error% after Fix` column.

### State Model (per sheet row)

| Column state | Meaning |
|---|---|
| `Error% Heuristic` filled, `Error% AI` blank | Phase 1 complete, Phase 2 pending |
| `Error% AI` = `NA` | Heuristic was 0% — file is fully translated, no LLM cost incurred |
| `Error% AI` filled, `Status` blank | Phase 2 complete, Phase 3 pending |
| `Status` = `Fixed` | Phase 3 complete, re-run Phase 2 to fill `Error% after Fix` |
| `Error% after Fix` filled | Full cycle complete |

### Control Flow — Phase 1 (Scanner)

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

### Control Flow — Phase 2 (Validator)

```
validate_domain(domain, limit)
│
└── for each unanalysed row in quality sheet:
    │
    ├── [skip if Error% AI already filled]
    ├── [mark NA if Error% Heuristic = 0%]
    │
    ├── sample up to 20 paragraphs from the translated file
    ├── LLM call → returns Error% + up to 5 untranslated samples
    ├── write Error% AI, Untranslated Samples, Analysed At
    │
    └── [if Status = Fixed]  →  write Error% after Fix instead
│
└── re-sort sheet by Error% AI descending
```

### Control Flow — Phase 3 (Retranslator)

```
retranslate_domain(domain, threshold, limit)
│
└── for each row where Error% AI > threshold AND Status is blank:
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
| `tools/translation_agent/.env` | Add `TRANSLATION_SCAN_SHEET_ID_*` and `QUALITY_SHEET_ID_*` values |
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

### Adjust quality threshold

Pass `--threshold <N>` to `quality_retranslator.py`. Default is `70` (retranslate files with AI Error% above 70%).

### Batch large runs

All three quality scripts accept `--limit <N>` to cap rows processed per run.
