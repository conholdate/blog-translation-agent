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
| `MISSING` | a supported language has no `index.{lang}.md` | `Translate` | missing language codes | `New Post` · `3 of 21 languages missing` |
| `EXTRA` | a `.md` file isn't `index.md` / `index.{supported lang}.md` | `Delete` | the extra fragments (e.g. `xx`, `tmp`) | `Unsupported language file(s) — not a language of this blog` |
| `OUTDATED` | the post's `index.md` was **committed after** its `index.{lang}.md` | `Retranslate` | outdated language codes | `Updated by Optimizer Agent on 2026-11-16` ⏎ `"Optimized Blog Posts"; translations from 2025-05-09` |

A post with several issues produces one row per issue.

**Notes layout (since 24 Nov 2026).** Line 1 is a short **headline** with the main reason, so a web
page (the dashboard) can show just that line. Line 2 has the details, `;`-delimited. The
`⏳ Waiting until …` line comes last. On an invalid manual row, the `⚠️ Invalid: …` line goes on top.

| Row | Line 1 (headline) | Line 2 (details) |
|---|---|---|
| MISSING | `New Post` · `N of M languages missing` | none |
| OUTDATED | `Updated by <name> on <date>` | `"<commit subject>"; translations from <date>[ to <date>][; same commit changed N of M translations]` |
| ISSUE | the request's `--reason` | `Requested by <source>` |
| EXTRA | `Unsupported language file(s) — not a language of this blog` | none |

`<name>` comes from `scan_helpers.display_author()`. Known git logins are mapped in `AUTHOR_NAMES`
(`shoaibkhan-aspose` → Shoaib Khan, `mustafabutt-dev` → Mustafa Butt; add new committers there).
Other login-like names (no spaces, with `-`, `_` or `.`) are split into capitalised words:
`optimizer-agent` → Optimizer Agent, `roy.wang` → Roy Wang. Readable names such as `Muzammil Khan` are
kept. Every scan rewrites the scanner's Notes, so open rows switched at the first scan after the
change. ISSUE rows added earlier and `history` rows of closed posts keep the old one-line text.
**Rollout (24 Nov 2026):** commit `48b2262` was pushed at about 08:21 UTC. Four translation runs
were still in progress, so the manual scan waited until they had all finished. It ran at
11:14–11:17 UTC (run 45382374825, `workflow_dispatch`, success on all 6 domains) and rewrote the open
rows' Notes. Being manual, it started no translation runs. Scheduled scans have kept the format
since (24 Nov 22:01, 25 Nov 06:24 and 21:16, 26 Nov 06:16 UTC, all successful).

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
- **Known blind spot (accepted 17 Nov 2026):** any commit that touches the translations (bulk
  link-prefix edits such as 2024-05-23 "Internal links prefixes updated", the 2025-02-11
  "Restructured category" move, tag fixes) resets their date and hides older English changes.
  Ignored on purpose: in the checked example (`2022-04-12-extract-text-and-images-from-pdf-documents-using-java`,
  blog.conholdate.com) the hidden English changes were 1–2 line link fixes ("Fixed Broken Links",
  2023-12-13). Catching them would need rename tracking plus a size threshold on both sides
  (`git log --numstat -M`), and would mostly queue link-fix churn against the run budget (3 posts' worth).
  English changes made from now on are caught; old link problems belong to the 404-link sweep and
  stale text to the quality pipeline.
- Needs the blog repo's full history: `scan-missing-translations.yml` checks out with
  `fetch-depth: 0`. With no git history (e.g. the gitignored local test mirror
  `blog-checkedout-repo/`), the check is skipped with the warning
  `⚠️ No git history for … — OUTDATED check skipped.` — MISSING/EXTRA still work.
- Why git dates and not a content hash: a hash of `index.md` also changes for URL/typo fixes across
  all languages (decided with the owner on 17 Nov 2026); the date rule lets a combined commit pass.
- Typical source: the optimizer agent (`optimizer-agent` / "Optimized Blog Posts" commits) rewrites
  `seoTitle`, `description`, `summary` and paragraphs of ~3 posts a day and adds `lastmod`, touching
  `index.md` only — real content changes that the translations must follow.

### The queue — a persistent domain tab (since 18 Nov 2026)

The domain tab of the consolidated scan sheet is the **translation queue**. Until 18 Nov 2026 it
was cleared and rewritten on every scan, which wiped everything people did on it (row splits,
ordering, Status) and made rows that a scan can't see (manual additions) impossible. Each scan now
**reconciles** the tab instead (`scan_queue.reconcile()`, pure logic; sheet I/O in
`io_google_spreadsheet.sync_domain_queue()`).

What goes in the queue:

| Issue | Who adds it | Priority (default) | Closed when |
|---|---|---|---|
| `MISSING` | scanner | **High** | the scan no longer finds the language missing |
| `ISSUE` | a person or an agent (manual rows, `queue_add.py` / `add_to_queue()`) | **Normal** | Step 2 has retranslated its languages |
| `OUTDATED` | scanner (any English commit — optimizer agent or a person; the commit author is in Notes) | **Low** | the retranslation is committed (translation newer than `index.md`) |
| any | — | **Urgent** — set by people only | — |

`EXTRA` rows (junk files) are **not** queue rows: they go to the shared `cleanup` tab (below).

**Reconcile rules (per scan):**

| Queue row | Result |
|---|---|
| MISSING/OUTDATED row, all its languages still flagged | kept as is; Scan Date, Days Missing, Notes, URL, Author, Ready After refreshed |
| … some languages no longer flagged | those languages removed, Count updated, Status `partial` |
| … no language left | **closed**: removed from the queue and appended to `history` as `completed` |
| flagged languages no open row tracks | **new row at the bottom** (Priority by issue, Source `Scanner`, Missing Since = today) |
| ISSUE row (or any issue the scan can't see) | **validated** (below); otherwise left alone — blank Priority / Source / Action / Missing Since are filled in |
| old EXTRA row in the queue | dropped (EXTRA lives in the cleanup tab) |
| row with Status other than blank / `pending` / `partial` (e.g. `hold`, `invalid`) | left alone, never closed, and still counts as tracking its languages, so no duplicate is added behind it |
| blank rows, old `!!! NO MISSING TRANSLATION FOUND !!!` placeholder | dropped |

- Rows are matched by **(domain, product, post folder, issue)** and language — never by row
  number. A post split by hand over several rows stays split; each part shrinks on its own.
- **Kept from people:** row order, row splits, Priority, Status, Source, Comments, and any extra
  column (columns are found by name; missing ones are appended).
- New rows are added in this order: MISSING by post folder, then OUTDATED **most recent English edit
  first**. Existing rows keep their place.
- **Missing Since** is set when the row is first flagged and never changed; `Days Missing` is
  recomputed each scan. For rows that existed before 18 Nov 2026 it starts at the reset date (the old
  first-seen dates and comments were dropped on purpose — not needed by the owner).
- Writes go **from A1 first, then blank the leftover rows below** (`_write_tab`), so a failed write
  never leaves an empty queue. Values are written `RAW` (Comments start with `- ` and must never be
  parsed as formulas) — so the queue tab shouldn't hold formulas: they'd be kept as their values.
- Author handles (summary mentions) and the summary's folder count / send-email flag count only
  posts with MISSING or EXTRA issues — an outdated translation isn't the post author's to fix.
- Metrics `items_discovered` counts missing languages only (unchanged).

### Where results are written

**1. Domain tab = the queue** (`TRANSLATION_SCAN_SHEET_ID`, tab named by domain), columns
(`config.HEADERS_QUEUE`): Scan Date, Missing Since, Days Missing, **Priority**, Domain, Product,
Blog Post Directory, Blog Post URL, Author, Issue, Count, Target Translations, Action, Status,
**Source**, Notes, **Comments**, **Ready After**.

**Ready After** (since 20 Nov 2026): on MISSING / OUTDATED rows the scanner writes the English
`index.md`'s last commit + 72 h (`scan_queue.ready_after()`, e.g. `2026-11-22 14:05 UTC`). Each scan
refreshes it, on held rows too. While that time is ahead, the row's Notes end with
`⏳ Waiting until <time> UTC (72 h after the last English edit)` (`scan_helpers.waiting_note()`).
It is blank when the blog checkout has no git history, and blank on ISSUE rows (they don't wait).
Step 2 skips a row until then (see Queue rules → Settling time).

| Status | Meaning |
|---|---|
| blank / `pending` / `partial` | open — Step 2 works on it |
| `invalid` | a manual row the scanner can't match (reason in Notes) |
| anything else (e.g. `hold`) | skipped by Step 2 and never closed by the scan, until cleared |

**Manual rows (ISSUE) — validation and how to add one.** Retranslation requests the scan can't
detect (bad tables, wrong terms, a quality finding) are ISSUE rows. Add them with
`python tools/translation_agent/queue_add.py --domain <d> --post <product>/<folder> --langs "fr, de"
--reason "…" [--source <agent>] [--priority Urgent]` (agents in Python: `io_google_spreadsheet.add_to_queue()`),
or type a row into the tab by hand (Issue `ISSUE`; Domain, Product, Blog Post Directory, languages).
`add_to_queue()` skips languages an open ISSUE / OUTDATED row of the post already retranslates and
appends one row at the bottom (Priority Normal unless given, Source as given, Missing Since today,
Notes = the reason as the headline + `Requested by <source>` on line 2, `scan_helpers.issue_note()`).
Every scan checks open and `invalid` ISSUE rows against the repo (`validate_manual_row()`): the post
folder must exist (non-draft, with `index.md`) and every language must be one of the blog's; blank
languages mean all of them. A failing row gets Status `invalid` and a `⚠️ Invalid: …` line on top of
its Notes (the person's own note stays below); once corrected, the next scan clears both.

**2. Cleanup tab** (`cleanup`, one tab for all domains, `config.HEADERS_CLEANUP`) — EXTRA rows.
Each scan replaces that domain's rows and keeps the other domains'. Derived entirely from the repo,
so it has no history. Step 2 deletes the files listed for its domain.

**3. History tab** (`history`) — **completed rows only**. Closed queue rows are appended
(`append_history_rows`, `RAW`) with their Comments, Notes, Priority and Source; history's
`Scan Date` is the row's Missing Since (first flagged). Columns are mapped by name; missing ones
(`Priority`, `Source`) are added automatically (`_ensure_history_columns`).
**blog.groupdocs.com** keeps its queue (MISSING / OUTDATED / cleanup — reported, not translated) but
its closed rows are dropped instead of moved (`config.NO_HISTORY_DOMAINS`), and it has no history rows.

**4. Summary sheet** — one row per domain per day (date, folder count, author handles, **link to the
domain's queue tab**, send-email flag).

The old **per-domain sheets are no longer written** (since 18 Nov 2026), and Step 2 no longer falls
back to them; the summary's link points to the queue tab instead.

### One-time reset (18 Nov 2026)

`reset_scan_queue.py` (run by hand, after the translation runs in progress have committed; dry run
unless `--apply`):

1. backs up every tab it changes as `bak-YYYYMMDD-HHMM-<tab>` in the same spreadsheet (a Drive file
   copy isn't used — service accounts usually can't create Drive files);
2. deletes every history row that isn't `completed` (old pending / partial rows and their comments
   are not carried over — decided by the owner) and **every blog.groupdocs.com row**, completed or not;
3. clears every domain tab and the cleanup tab down to the header row.

The next scan rebuilds the queue (a scan against an empty queue is a rebuild): MISSING (High), then
OUTDATED (Low), Missing Since = that day. A translation run between the reset and that scan finds an
empty queue and does nothing.

Applied 18 Nov 2026 (after the day's runs had pushed): 1,134 history rows deleted, 361 completed rows
kept (aspose.cloud 133, aspose.com 121, groupdocs.cloud 58, conholdate.com 47, conholdate.cloud 2);
backups `bak-20261118-1739-<tab>` (local time). The manual scan then rebuilt the queue: aspose.com
434 rows / 8,819 languages (2 MISSING), conholdate.com 222 / 3,767, groupdocs.com 242 / 3,376
(35 MISSING), aspose.cloud 76 / 1,553, groupdocs.cloud 35 / 624, conholdate.cloud 0; cleanup empty.

### Re-sorting OUTDATED rows (19 Nov 2026)

`resort_queue.py` (by hand, when no translation run is in progress; dry run unless `--apply`;
`--domain` for one tab) moves the OUTDATED rows of the domain tabs newest post first, among the places
OUTDATED rows hold — MISSING, ISSUE, held and invalid rows don't move and no cell changes. A changed
tab is backed up first as `bak-YYYYMMDD-HHMM-<tab>`. Step 2 sorts the queue itself
(`scan_queue.order_rows()`), so this only makes the sheet read in work order; it was first used
because the queue rebuilt on 18 Nov listed OUTDATED rows by English edit (2022 posts first).
Applied 19 Nov 2026 (no run in progress): aspose.com 430 rows moved, groupdocs.com 207,
conholdate.com 217, aspose.cloud 72, groupdocs.cloud 31; conholdate.cloud empty. Backups
`bak-20261119-1417-<tab>`; checked afterwards: same rows as the backups, OUTDATED newest post first.
Both sets of backup tabs (`bak-20261118-1739-*`, 7 tabs, and `bak-20261119-1417-*`, 5 tabs) were
deleted on 19 Nov 2026 at the owner's request once the results were checked; Google Sheets version
history still holds the earlier states.

### Options

| Option | Meaning |
|---|---|
| `--domain` (required) | one domain or `all` |
| `--translate` | also start translation after the scan — **currently paused in code**; only this needs `PROFESSIONALIZE_API_KEY` (without it a warning is printed and translation is skipped; the scan itself never needs the key) |
| `--product`, `--author`, `--limit`, `--key` | only used with `--translate` |

---

## Step 2 — Translate, Retranslate (and Delete)

`start_translation()` reads the queue (domain tab) and the domain's rows of the cleanup tab once
and runs two independent flows from that read: `MISSING` and `OUTDATED` rows go to
`TranslationOrchestrator.translate_files()`, `EXTRA` rows go to
`TranslationOrchestrator.delete_extra_files()`. Either can run with zero rows for the other. If the
queue can't be read the run fails (there is no fallback to the old per-domain sheets any more), and
the failure alert fires.

### Entry Point

```
translator.py  →  start_translation()
                     ├── filter_valid_rows()   (MISSING + OUTDATED)
                     │     → drop_existing_translations()   (MISSING rows only)
                     │     → queue_order()                   (open rows, by Priority)
                     │     → limit
                     │     → TranslationOrchestrator.translate_files()
                     └── filter_extra_rows()   (EXTRA)
                           → TranslationOrchestrator.delete_extra_files()
```

### Queue rules

- Rows are used as they are in the sheet (a post may be split by hand over several rows).
- `queue_order()`: only **open** rows (Status blank / `pending` / `partial`), sorted by Priority —
  Urgent, High, Normal, Low; a blank or unknown Priority (e.g. a tab from before 18 Nov 2026) falls
  back to the issue's default (MISSING High, ISSUE Normal, OUTDATED Low). Rows of the same priority
  keep their **sheet order** — first in, first out — so a split post ("these 2 languages first")
  still runs in that order.
- **OUTDATED rows go newest post first** (since 19 Nov 2026, `scan_queue.order_rows()`): within a
  priority they take the places OUTDATED rows hold, sorted by the post date in the folder name
  (`2026-…` before `2022-…`; folders without a date last; same date → sheet order). MISSING and ISSUE
  rows never move (FIFO), and an OUTDATED row raised to High keeps its place among the High rows.
  The scanner also adds new OUTDATED rows newest post first (same post date → most recently edited
  English first). Why: the old "newest English edit first" order tied on hundreds of posts the
  optimizer edited the same day and fell back to folder order, putting 2022 posts first; newer posts
  get more traffic. To bring an old post forward, raise its Priority — moving the row up in the sheet
  no longer puts it ahead of newer OUTDATED posts.
- **Settling time** (since 20 Nov 2026, `split_settled()` / `scan_queue.is_settled()`): a row is
  held back until its **Ready After** (column 11 of the read) has passed: the English `index.md`'s
  last commit + `config.TRANSLATION_SETTLE_HOURS` (72 h). The rule is the same for new (MISSING)
  and updated or optimised (OUTDATED) posts. Each scan refreshes Ready After, so a new English edit
  restarts the wait. **Urgent** rows (forced by a person) and **ISSUE** rows (reviewed retranslation
  requests) don't wait. A blank or unreadable Ready After (no git history, e.g. the local mirror;
  manual rows; tabs from before the column existed) means ready. Waiting rows are dropped **before**
  the budget, so they don't use it. They stay in the queue untouched, and the run logs
  `Waiting: n row(s)` (each row in verbose). Why: the owner's request. Errors found in a fresh
  English article (often fixed in the first days) are corrected before they are copied into
  every language, which saves fix-ups and retranslation cost.
  **In practice the wait is 72–87 h.** Translation runs start only after the two daily scheduled
  scans, so a post is picked up by the first run after its 72 h are up. GitHub starts those scans
  hours late (see Scheduling), so gaps between them are about 8–15 h, not 12 h. The first estimate
  was 72–84 h; it was corrected on 26 Nov 2026.
  **Rollout (20 Nov 2026):**
  - Commit `fc15060` was pushed at about 09:20 UTC. A manual scan followed at 09:25–09:27 UTC
    (run 44710572846, success on all 6 domains). It added the Ready After column to every domain
    tab and filled it on the MISSING / OUTDATED rows.
  - Open rows per tab: aspose.com 434 (3 new), aspose.cloud 69, groupdocs.cloud 27,
    conholdate.com 214, conholdate.cloud 0, groupdocs.com 237 (2 closed).
  - The five chained translate runs were **skipped**, because the scan was manual (see Schedules).
    The first translation runs that apply the wait are the ones after the next scheduled scan.
  - Before that scan the column didn't exist, so every row counted as ready.
- **Language budget** (since 18 Nov 2026): `--limit` is "posts' worth" — the run translates up to
  `limit × the blog's language count` languages (`language_budget()`; e.g. 2 × 21 = 42 on blog.aspose.com,
  3 × 17 = 51 on blog.conholdate.com), taken from the ordered queue (`apply_language_budget()`). Why:
  a post-count cap wasted the day when the queued posts needed only one or two languages each; now
  5 posts × 12 languages fit in a 3-posts'-worth run. A row that doesn't fit is **cut** to the
  languages that do, and the queue row keeps the rest open; rows further down are not pulled
  forward (that would break the priority order). A language already taken for the same post by an
  earlier row (e.g. OUTDATED and ISSUE both asking for `fr`) is translated once.
- **Run time limit**: no new language is started after `--time-limit` minutes (default
  `config.TRANSLATION_TIME_LIMIT_MIN` = 300, i.e. 5 h). The post in progress gets a
  `⏸️ Time limit n/m` comment listing the languages not started; later posts stay in the queue
  untouched; the workflow then commits what was done. Why: GitHub kills a job at 6 h, and a killed
  job commits nothing (~4.3 min per translation, so 63 translations ≈ 4.5 h; long posts take longer).
- ISSUE rows behave like OUTDATED rows: they overwrite the existing translation; an ISSUE row with
  blank languages means every language of the blog (`fill_issue_langs()`).
- `drop_existing_translations()` drops languages whose file already exists (stale sheet) for MISSING
  rows only; OUTDATED rows pass through, their files exist by definition.

### State Model (Step 2)

| State | Description |
|-------|-------------|
| **Pending** | Open queue row (Status blank / `pending` / `partial`) with `Target Translations` populated (column 7) |
| **Filtered** | Row passes `filter_valid_rows()` (Issue == MISSING or OUTDATED) or `filter_extra_rows()` (Issue == EXTRA) |
| **In Progress** | `TranslationOrchestrator` is actively translating or deleting for the post |
| **Translated** | `index.{lang}.md` written to `blog-checkedout-repo/content/…` (new, or overwritten for OUTDATED) |
| **Deleted** | `index.{fragment}.md` removed from `blog-checkedout-repo/content/…` (EXTRA rows) |
| **Skipped** | MISSING row: `index.{lang}.md` already exists — no LLM call made. EXTRA row: the reconstructed `index.{fragment}.md` doesn't exist on disk — a junk file that doesn't follow the `index.*.md` naming pattern can't be losslessly reconstructed from its fragment, so it's skipped rather than guessed at. OUTDATED rows never skip an existing file |
| **Failed** | Exception during translation — error logged, remaining langs continue |

### Deletion detail (EXTRA rows)

`Target Translations` on an `EXTRA` row holds comma-separated fragments (e.g. `"cs, pl, sv"` or `"tmp"`). Each reconstructs as `index.<fragment>.md` — the same convention `translate_files` uses to write output files — and is removed with `os.remove()`. The CI workflow's generic `git add content/` → commit → push (same mechanism that commits new translations) picks up the deletion automatically; no separate git logic is needed in Python.

### Queue comments

After each post, a comment (result, failed languages, English links kept) is appended to the
`Comments` cell of the post's **open queue rows that share a language with the run**, each row
getting only its own languages (`log_post_comment(…, run_langs=)` → `append_queue_comments`). If no
open row shares one, the last open row of the post gets the whole comment; a whole-post comment
(error, draft) goes to the rows sharing the run's languages. The tab is re-read and rows are found
by key at write time, so rows added, removed or re-sorted during the run don't matter. When the row
is closed, its comments move with it to the history tab. Production only; local runs print it.
(Until 18 Nov 2026 comments went to open history rows of the row's issue.)

**Closing.** In the same write, the post's translated languages (and, on MISSING rows, languages that
already existed) are removed from **every** open queue row of the post that tracks them — one
retranslation of `fr` settles both an OUTDATED and an ISSUE row. A row left with no language is closed
right away: deleted from the queue (bottom-up, so no row shifts) and appended to `history` as completed
with its new comment; others become `partial`. Failed and not-started languages stay open. ISSUE rows
can only be closed this way (the scan can't see them). Caveat: the row is closed before the workflow
commits; if the commit then fails, MISSING / OUTDATED rows come back with the next scan, but an ISSUE
row would have to be added again.

### Scheduling (since 18 Nov 2026)

- `scan-missing-translations.yml` runs at **00:00 and 12:00 UTC** (matrix of all 6 domains,
  `fail-fast: false` so one domain's failure doesn't cancel the others).
- **GitHub starts scheduled runs hours late** (cron is best-effort under load). Observed 18–26 Nov
  2026: the 00:00 scan started between **04:28 and 07:51 UTC**, and the 12:00 scan between **19:11
  and 23:33 UTC**. Before 18 Nov, the single 00:00 scan started at 02:36–05:57. The chained
  translation runs start later by the same amount. Nothing is broken and the workflow isn't
  changed: two scans and two translation runs per blog still happen each day, just later than the
  cron says. Gaps between scans vary from about 8 h to 15 h. When planning a manual scan, check
  `gh run list` rather than the clock (see RUNBOOK).
- The five maintained blogs' `translate-blog-*.yml` have **no schedule of their own**: they start on
  `workflow_run` when a **scheduled** scan finishes as success or failure (a failure is usually
  another domain's leg; the queue is persistent, so this blog's is usable — and Step 2 re-checks files
  on disk). Not after a cancelled scan, and not after a manual scan, so re-scanning during the day
  doesn't start a third run. Manual `workflow_dispatch` runs work as before. Inputs are empty on
  `workflow_run`, so the defaults apply (limit 2 posts' worth).
- `translate-blog-groupdocs-com.yml` stays manual only (blog.groupdocs.com is report-only).
- Every translate workflow has `concurrency: translate-<domain>` with `cancel-in-progress: false`
  (shared with `translate-blogs.yml`): a second run for the same blog waits instead of picking the
  same rows or racing on commits. GitHub keeps one pending run per group — a newer pending run
  replaces an older pending one.
- `test_workflows.py` guards the scan name in `workflow_run`, the concurrency settings and the ≤ 3
  limit, since mistakes there fail silently.

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
├── read_domain_scan_rows(domain)            # the queue (domain tab) + read_cleanup_rows(domain)
├── filter_valid_rows(posts_list)            # MISSING + OUTDATED rows with required fields
├── filter by author / product
├── drop_existing_translations()             # MISSING rows only
├── split_settled()                          # hold back rows whose Ready After hasn't passed (not Urgent / ISSUE)
├── queue_order()                            # open rows, by Priority then sheet order (OUTDATED newest post first)
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
~250 runs. OUTDATED rows go newest post first (by post date since 19 Nov 2026), so recent posts are
retranslated before the old backlog. The optimizer
adds ~3 outdated posts a day on blog.aspose.com alone. Since 18 Nov 2026 each blog gets **two runs a
day of 2 posts' worth** (~42 translations each on a 21-language blog, ~3 h) — ~84 translations a day
instead of ≤ 63 — and OUTDATED rows (Low) run only once nothing of higher priority is left. Low can
starve if new work keeps arriving faster than that; measure before adding aging rules (e.g. promote
to Normal after 30 days).

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
