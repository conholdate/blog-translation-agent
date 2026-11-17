# Orchestration

State model, control flow, and extension points for all four pipeline steps of the Blog Translation Agent.

---

## Step 1 — Scan: Consolidated Scan Sheet

`scan_missing_translations.py --domain <domain|all>` walks
`blog-checkedout-repo/content/<Family>/<product>/<post>/` (read-only) and writes one row per
(post, issue). Helpers live in `scan_helpers.py` (frontmatter reading, git history, Notes text).

### What is scanned

| Folder | Treatment |
|---|---|
| Name doesn't start with a year `2020`–`2027`, or contains `discount` | Skipped (not a post) |
| No `index.md` | Skipped — nothing to translate from (an orphan folder with only `index.{lang}.md` files used to be queued as MISSING for every language) |
| `index.md` has `draft: true` in front matter | Skipped — draft content isn't final and won't be re-synced into translations once published |
| Anything else | Checked for the three issues below |

`index.md` is opened with `utf-8-sig` (some editors save a BOM) and **only the front matter block** is
read for `author`, `url` and `draft`, so a `draft: true` listed after `author`/`url` is found and body
text such as `author: …` is never picked up. A post without `author` is reported with an empty Author
(it used to crash the whole scan).

### Issues

| Issue | Detected when | Action | Target Translations | Notes (example) |
|---|---|---|---|---|
| `MISSING` | a supported language has no `index.{lang}.md` | `Translate` | missing language codes | `New post` · `3 of 21 languages missing` |
| `EXTRA` | a `.md` file isn't `index.md` / `index.{supported lang}.md` | `Delete` | the extra fragments (e.g. `xx`, `tmp`) | `Unsupported language file(s) — not a language of this blog` |
| `OUTDATED` | the post's `index.md` was **committed after** its `index.{lang}.md` | `Retranslate` | outdated language codes | `English updated 2026-11-16 by optimizer-agent ("Optimized Blog Posts"); translations from 2025-05-09` |

A post with several issues produces one row per issue.

### OUTDATED — how it is decided

- One `git log --name-only` pass over the domain's content folder (`last_commits()`, a few seconds for
  a whole blog) gives every file's **latest commit** (committer date, author, subject). The newest
  commit wins even when merges make `git log` order non-chronological.
- A language is outdated when `index.md`'s last commit time is **strictly later** than
  `index.{lang}.md`'s (`outdated_langs()`).
- A fix committed to `index.md` **and** its translations in the same commit leaves them equal → not
  outdated. A fix committed to `index.md` only → flagged. So: when fixing something in every language
  (a URL, an image), commit the English file together with the translations.
- A commit that changed `index.md` together with **only some** translations (e.g. a Health and
  Recovery fix, "Fixed parsing errors.") still flags the untouched translations as OUTDATED and they
  are retranslated. The Notes then end with `; same commit changed 18 of 22 translations` (counted in
  the same `git log` pass, `git_history()` → files per commit) — information only. A Review step for
  these was considered and rejected on 17 Nov 2026: about 26 such posts on the 5 maintained blogs
  (blog.aspose.com 21, blog.aspose.cloud 4, blog.conholdate.cloud 1; blog.groupdocs.com 116), cheaper
  to retranslate than to review, and a full retranslation fixes other issues in the post too.
- Translations not committed yet are never reported.
- Needs the blog repo's full history: `scan-missing-translations.yml` checks out with
  `fetch-depth: 0`. With no git history (e.g. the gitignored local test mirror
  `blog-checkedout-repo/`), the check is skipped with the warning
  `⚠️ No git history for … — OUTDATED check skipped.` — MISSING/EXTRA still work.
- Why git dates and not a content hash: a hash of `index.md` also changes for URL/typo fixes across
  all languages (decided with the owner on 17 Nov 2026); the date rule lets a combined commit pass.
- Typical source: the optimizer agent (`optimizer-agent` / "Optimized Blog Posts" commits) rewrites
  `seoTitle`, `description`, `summary` and paragraphs of ~3 posts a day and adds `lastmod`, touching
  `index.md` only — real content changes that the translations must follow.

### Row order and summary

- MISSING/EXTRA rows first, sorted by post folder; then OUTDATED rows, **most recent English edit
  first**. Step 2 works top-down, so new posts are never behind the retranslation backlog.
- Author handles (summary mentions) and the summary's folder count / send-email flag count only
  posts with MISSING or EXTRA issues — an outdated translation isn't the post author's to fix.
- Metrics `items_discovered` counts missing languages only (unchanged).

### Where results are written

**1. Domain tab** of the consolidated scan sheet (`TRANSLATION_SCAN_SHEET_ID`, tab named by domain)
- Cleared and rewritten on each scan — always shows current issues only.
- Columns: Scan Date, Missing Since, Days Missing, Domain, Product, Blog Post Directory, Blog Post
  URL, Author, Issue, Count, Target Translations, Action, Status, **Notes**.
- `Missing Since` = first scan that flagged the (post, issue), from the history tab.
- `config.HEADERS_SCAN_RESULTS` (= `HEADERS_MISSING_TRANSLATIONS` + `Notes`) is what the scanner
  writes. Step 2 reads `HEADERS_MISSING_TRANSLATIONS` **by column name** and ignores Notes, so tabs
  written before Notes existed still work.

**2. Old per-domain sheet** (first tab, same columns without the lead dates) — still written; Step 2
reads it only if the consolidated tab can't be read.

**3. History tab** (never cleared)
- Columns: Scan Date, Domain, Product, Blog Post Directory, Blog Post URL, Author, Issue, Target
  Translations, Count, Status, Completed Date, Comments, **Notes**.
- One row per (post, issue) detection, keyed by `(domain, slug, issue)` — MISSING, EXTRA and
  OUTDATED lifecycles of the same post are tracked independently.
- Status lifecycle: `pending` → `partial` → `completed`.
- `Comments` — Step 2's per-run results (see Step 2). `Notes` — the scanner's reason, refreshed on
  every open row each scan (e.g. a newer English edit) and kept on completed rows.
- Missing columns (Comments, Notes) are added to an existing tab automatically
  (`_ensure_history_columns`); Notes is located by header name.
- `update_history_tab()` writes only Scan Date…Completed Date (`USER_ENTERED`) and Notes (`RAW`); it
  **never rewrites Comments**, which start with `- ` and would be parsed as a formula if written
  `USER_ENTERED`.

**4. Summary sheet** — one row per domain per day (date, folder count, author handles, sheet link,
send-email flag).

### History Tab — Completion Detection

On each scan, `update_history_tab()` checks every open history row against the current scan results
**for the same `(domain, slug, issue)` key**:

```
remaining = this_row_items ∩ current_scan_items_for_same_issue
```

| `remaining` | Meaning | Action |
|-------------|---------|--------|
| empty | All items in this row are resolved (translated, deleted, or retranslated) | `completed` + Completed Date = scan_date |
| `remaining < this_row_items` | Some resolved, some still flagged | `partial` + items updated to remaining, Notes refreshed |
| `remaining == this_row_items` | Nothing resolved | Notes refreshed if the reason changed, otherwise no write |
| post+issue not in scan at all | Fully resolved | `completed` + Completed Date = scan_date |

**Note:** Completion is detected on the **next scan after** the translation is committed. An OUTDATED
row completes once the retranslation is committed (the translation is then newer than `index.md`).

### Options

| Option | Meaning |
|---|---|
| `--domain` (required) | one domain or `all` |
| `--translate` | also start translation after the scan — **currently paused in code**; only this needs `PROFESSIONALIZE_API_KEY` (without it a warning is printed and translation is skipped; the scan itself never needs the key) |
| `--product`, `--author`, `--limit`, `--key` | only used with `--translate` |

---

## Step 2 — Translate, Retranslate (and Delete)

`start_translation()` reads the sheet once and runs two independent flows from the same read:
`MISSING` and `OUTDATED` rows go to `TranslationOrchestrator.translate_files()`, `EXTRA` rows go to
`TranslationOrchestrator.delete_extra_files()`. Either can run with zero rows for the other.

### Entry Point

```
translator.py  →  start_translation()
                     ├── filter_valid_rows()   (MISSING + OUTDATED)
                     │     → drop_existing_translations()   (MISSING rows only)
                     │     → missing_first()                 (MISSING before OUTDATED)
                     │     → limit
                     │     → TranslationOrchestrator.translate_files()
                     └── filter_extra_rows()   (EXTRA)
                           → TranslationOrchestrator.delete_extra_files()
```

### Queue rules

- Rows are used as they are in the sheet (a post may be split by hand over several rows).
- `missing_first()`: all MISSING rows before all OUTDATED rows, each group in sheet order — new posts
  never wait behind the retranslation backlog. `--limit` (max 3 posts per run) counts both kinds.
- `drop_existing_translations()` drops languages whose file already exists (stale sheet) for MISSING
  rows only; OUTDATED rows pass through, their files exist by definition.

### State Model (Step 2)

| State | Description |
|-------|-------------|
| **Pending** | Row exists in Google Sheet with `Target Translations` populated (column 7) |
| **Filtered** | Row passes `filter_valid_rows()` (Issue == MISSING or OUTDATED) or `filter_extra_rows()` (Issue == EXTRA) |
| **In Progress** | `TranslationOrchestrator` is actively translating or deleting for the post |
| **Translated** | `index.{lang}.md` written to `blog-checkedout-repo/content/…` (new, or overwritten for OUTDATED) |
| **Deleted** | `index.{fragment}.md` removed from `blog-checkedout-repo/content/…` (EXTRA rows) |
| **Skipped** | MISSING row: `index.{lang}.md` already exists — no LLM call made. EXTRA row: the reconstructed `index.{fragment}.md` doesn't exist on disk — a junk file that doesn't follow the `index.*.md` naming pattern can't be losslessly reconstructed from its fragment, so it's skipped rather than guessed at. OUTDATED rows never skip an existing file |
| **Failed** | Exception during translation — error logged, remaining langs continue |

### Deletion detail (EXTRA rows)

`Target Translations` on an `EXTRA` row holds comma-separated fragments (e.g. `"cs, pl, sv"` or `"tmp"`). Each reconstructs as `index.<fragment>.md` — the same convention `translate_files` uses to write output files — and is removed with `os.remove()`. The CI workflow's generic `git add content/` → commit → push (same mechanism that commits new translations) picks up the deletion automatically; no separate git logic is needed in Python.

### History comments

After each post, a comment (result, failed languages, English links kept) is appended to the
`Comments` cell of the post's open history rows **of the row's issue** (`log_post_comment(…, issue=)`
→ `append_history_comments`), so a retranslation is logged on the OUTDATED row and a translation on
the MISSING row. Production only; local runs print it.

### Committing (translate workflows)

1. `git fetch origin && git merge --ff-only --autostash origin/<branch>` — the remote may have moved
   during the run. New translations are untracked and survive the merge as-is; retranslated files
   are modified tracked files, so `--autostash` sets them aside and puts them back. (Without it, a
   remote change to the same file aborted the merge and the run's work was lost.) If the remote
   changed the very same translation file, the stash can't be re-applied and the step fails — rare;
   re-run the post.
2. `git add content/`, then `commit_translations.py` makes **one commit per post**. The message
   (`build_commit_message.py`) follows each staged file's git status
   (`git diff --cached --name-status`):

| Files in the commit | Title | Body section |
|---|---|---|
| added | `Translate articles for: "<title>" - (N files)` | `Added translations in N languages:` |
| modified (OUTDATED) | `Retranslate articles for: "<title>" - (N files)` | `Retranslated N languages (English post was updated):` |
| deleted (EXTRA) | `Remove extra translations for: "<title>" - (N files)` | `Removed extra files in N languages:` |
| a mix | `Update translations for: "<title>" - (N files)` | one section per kind |

### Control Flow (Step 2)

```
start_translation(domain, author, limit)
│
├── read_domain_scan_rows(domain)            # consolidated tab; falls back to the old sheet
├── filter_valid_rows(posts_list)            # MISSING + OUTDATED rows with required fields
├── filter by author / product
├── drop_existing_translations()             # MISSING rows only
├── missing_first()                          # MISSING before OUTDATED
├── limit
│
└── TranslationOrchestrator.translate_files(posts_list)
    │
    └── for each post row:
        │
        ├── parse_markdown_file(index.md)       # read English source
        ├── [skip entire post if front matter has draft: true]
        ├── PlatformIdentifierAgent             # identify .NET / Java / Python / etc.
        │
        └── for each language in the row:
            │
            ├── [skip if index.{lang}.md exists — MISSING rows only; OUTDATED overwrites]
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
        │
        └── log_post_comment(…, issue=row issue)   # history Comments (production)
```

### Retranslation backlog (as of 17 Nov 2026)

The first scans with the OUTDATED check flag a large backlog (local clones of 13–16 Nov 2026):

| Domain | Outdated posts | Outdated files | English edited ≤30 d / ≤90 d / ≤1 y | Last English editors |
|---|---|---|---|---|
| blog.aspose.com | 426 | 8,651 | 75 / 126 / 390 | optimizer-agent 206, Farhan Raza 153 |
| blog.aspose.cloud | 77 | 1,574 | 34 / 34 / 40 | Farhan Raza 34, nayyer Shahbaz 32 |
| blog.groupdocs.cloud | 37 | 660 | 17 / 17 / 18 | nayyer Shahbaz 19, Farhan Raza 17 |
| blog.conholdate.com | 222 | 3,767 | 3 / 24 / 222 | optimizer-agent 208 |
| blog.conholdate.cloud | 1 | 4 | 1 / 1 / 1 | (local clone had only 5 posts) |
| blog.groupdocs.com *(report only)* | 207 (+34 MISSING) | 3,170 | 80 / 191 / 202 | Vladimir Litvinchik 155 |

763 posts (~14,650 files) on the 5 maintained blogs. At 3 posts per run (~1.5 h per post) that is
~250 runs; the newest-first order clears the last 30 days (~130 posts) in ~45 runs. The optimizer
adds ~3 outdated posts a day on blog.aspose.com alone.

**Idea (not planned):** retranslate only the changed parts of a post (git diff of `index.md` →
changed frontmatter fields and paragraphs), which would cut cost and time several times over. Full
retranslation stays the default because it also fixes other issues in a translation (owner,
17 Nov 2026); partial retranslation is only an option for clearing the backlog, built only if asked.

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

> **Not run in production (found 17 Nov 2026):** no workflow in `.github/workflows/` calls
> `quality_retranslator.py`, and nothing commits its output — files it writes when run by hand stay
> local. Posts that need retranslation today go through Step 1's OUTDATED rows (or a manual row in
> the scan sheet) and Step 2.

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
