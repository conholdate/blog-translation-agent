# AGENTS.md
# Blog Translation Agent — Governance Policy

This file defines the operational boundaries for the Blog Translation Agent and its pipeline components.
The agent must not read, write, or modify any path not explicitly listed below, unless the user
explicitly approves it in the current session (see "User-Approved Changes").

This file is a living document: agents keep it updated with the standing instructions agreed in
discussions with the user (see "Standing Instructions").

Last updated: 2026-11-19
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
| Any project file | Only with the user's explicit approval in the current session | Code, docs and config changes the user requested |

---

## Forbidden Paths — Never Modify Autonomously

The paths below must never be changed by pipeline runs or on an agent's own initiative.
They **may** be changed when the user explicitly approves it in the current session.

| Path | Reason |
|------|--------|
| `AGENTS.md` | Policy file — updated only per user instructions (see "Standing Instructions") |
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
    2. Detect per post (skipping drafts and folders without index.md):
       MISSING → Translate (no index.{lang}.md), EXTRA → Delete (unsupported .md),
       OUTDATED → Retranslate (index.md committed after index.{lang}.md — git history;
       a fix committed to both together is not outdated; skipped without git history)
    3. Reconcile the results into the persistent queue — the domain tab of the consolidated scan
       sheet (scan_queue.py; never cleared since 18 Nov 2026): languages no longer flagged are
       removed, rows with none left move to the `history` tab (completed rows only; dropped for
       blog.groupdocs.com), new findings are added at the bottom (MISSING by folder, then
       OUTDATED newest post first by folder date) with Priority MISSING High / OUTDATED Low, Source
       Scanner and Missing Since. People's edits (row splits, Priority incl. Urgent, Status such
       as `hold`, Comments, own columns) are kept. EXTRA rows go to the shared `cleanup` tab.
       Each row has a Notes reason (e.g. which English commit made it OUTDATED)

  Step 2 — Translate
    1. Read the queue (domain tab) and the domain's `cleanup` rows; no fallback to the old
       per-domain sheets (no longer written). Open rows only (Status blank / pending / partial),
       by Priority (Urgent, High, Normal, Low; blank → issue default), then sheet order (FIFO),
       except OUTDATED rows, which go newest post first (folder date) — a post
       may be split by hand over several rows (e.g. to translate 2 languages first). OUTDATED
       and ISSUE rows overwrite the existing translation. Budget: limit (posts' worth) × the
       blog's languages; a row that doesn't fit is cut, the rest stays queued. No new language
       starts after 5 h (TRANSLATION_TIME_LIMIT_MIN), so the run still commits before GitHub's
       6 h kill
    2. Checkout target blog repo (read-only except content/)
    3. Translate English index.md → index.{lang}.md
    4. Write translated file to blog-checkedout-repo/content/...
    5. Send metrics to Google Sheets
    6. Append a per-post comment (result, failed languages, EN links kept) to the
       "Comments" column of the post's open queue rows (moves to `history` with the row) —
       production only; local runs print it. Each row sharing a language with the run gets a
       comment for just its own languages; no shared language → last open row. Rows are found
       by key at write time, never by remembered row numbers. Translated languages are removed
       from every open row of the post; empty rows move to `history` (ISSUE rows close only here)

  Step 3 — Quality Check
    Phase A — Scanner
      1. Walk blog-checkedout-repo/content/ (read-only)
      2. Compute heuristic Error% per translated file
      3. Write results to quality Google Sheet
    Phase B — Validator
      1. Read quality sheet rows
      2. Run AI-based Error% + RETRANSLATE/KEEP decision check on flagged files (read-only on files)
      3. Update Error% AI, AI Decision, and Analysed At cells in sheet

  Step 4 — Retranslate (not run by any workflow, output never committed — as of 2026-11-17)
    1. Read quality sheet for files with AI Decision = RETRANSLATE
    2. Re-translate file via Step 2 pipeline
    3. Write corrected index.{lang}.md to blog-checkedout-repo/content/...
    4. Update Status and Analysed At cells in sheet
```

---

## Testing — agents may self-verify

Agents **are allowed to run the test suite** to verify their own changes. Running tests is a
read-only operation and is encouraged before reporting a task complete.

| Command | Scope |
|---------|-------|
| `make test` &nbsp;/&nbsp; `python -m pytest -q` | Full suite (paths from `pytest.ini`) |
| `make test-translation` &nbsp;/&nbsp; `python -m pytest tools/translation_agent/tests/` | Translation Pipeline (Steps 1–2) |
| `make test-quality` &nbsp;/&nbsp; `python -m pytest tools/quality_agent/tests/` | Quality Pipeline (Steps 3–4) |

Notes:
- **Running** tests is allowed; **modifying** the test files under `tools/*/tests/` needs user approval (see Forbidden Paths).
- Tests are helper/edge-case level and do not require live credentials.
- Translation logs are concise by default (one line per language, a result per post, a run summary — see `tools/translation_agent/run_log.py`). Use `--verbose` or `TRANSLATION_VERBOSE=1` for step-by-step detail; in GitHub Actions the detail is kept in collapsed `::group::` sections.
- On the maintainer's machine these commands are pre-approved for Claude in `.claude/settings.local.json`, so they run without prompting. `.claude/` is gitignored, so the pre-approval is per-machine and not shared through the repo.

---

## Safety Rules

- Agents must never modify the English source file (`index.md`) — only language variants (`index.{lang}.md`)
- Agents must validate `PROFESSIONALIZE_API_KEY` is present before starting any LLM call
- Agents must validate Google credentials before accessing any sheet
- Metrics failures must not halt the main pipeline
- Per-file failures must be isolated — one failure must not stop processing of remaining files
- `PRODUCTION_ENV` is auto-detected from the presence of `.env` at the project root (`True` in CI, `False` locally) — never set this manually from agent code
- Markdown readers must open posts with `encoding='utf-8-sig'` — some editors save `index.md` with a UTF-8 BOM, which breaks `^---` frontmatter matching under plain `utf-8`
- Internal links in a translation get the `/{lang}/` prefix only when the linked post's `index.{lang}.md` exists (on disk or queued in the same run); otherwise the English URL is kept. Non-post links (sections, tags, home) and other domains are left unchanged. This is handled by `tools/translation_agent/link_localizer.py` — the LLM prompt must not add prefixes itself

---

## User-Approved Changes

- The user may approve changes to any project file, including Forbidden Paths, in the current session.
- Approval covers the task it was given for; it does not carry over to unrelated work.
- After a change, run the relevant tests (see Testing) and report the results.

---

## Standing Instructions

Agreed with the user in ongoing discussions. Agents add new entries here as they are given,
with the date, and update `Last updated` above.

| Date | Instruction |
|------|-------------|
| 2026-10-29 | Keep this `AGENTS.md` updated with new instructions from regular discussions with the user. |
| 2026-10-29 | Never run `git commit` (or push) without asking the user first. Suggest a title and message instead. |
| 2026-10-29 | When a commit is allowed, author and commit as **Shoaib Khan — `shoaibkhan-aspose` <shoaib.khan@aspose.com>**. |
| 2026-10-29 | Do not start working on a task until the user's message is complete (they sometimes hit Enter early). Restate the understanding and get a "go ahead" ("double-take confirmation") before starting. |
| 2026-10-29 | A translation run must not exceed **3 posts** (2 posts take ~3 hours). Workflow input "Max Posts to Translate" is a 1/2/3 choice; keep defaults ≤ 3. *Superseded 2026-11-18 — see below.* |
| 2026-10-29 | Do not add the agent's email to commits. The trailer is just `Co-Authored-By: Claude Opus 5.5` (model name, no `<noreply@anthropic.com>`). |
| 2026-10-29 | For local testing, copy posts from a freshly fetched blog repo into `blog-checkedout-repo/content/<Domain>/<product>/`. Emptying that folder first (and removing product folders with no posts) is fine — it is an untracked mirror. Test with only a few languages to save LLM cost. |
| 2026-10-29 | Commits to blog repos (only after approval) go to: **blog.aspose.com**, **blog.aspose.cloud**, **blog.groupdocs.cloud**, **blog.conholdate.com**, **blog.conholdate.cloud**. |
| 2026-10-29 | **blog.groupdocs.com** is not maintained for translations: identify and report its issues, but do not translate for it or commit to its repo. |
| 2026-11-04 | Do not run a full Hugo build of a blog repo (it takes hours). To verify a post, build only that post in a throwaway site in a temp folder. |
| 2026-11-17 | Document everything — no information may be lost. Every behaviour change goes into the docs in the same piece of work: `docs/` (ORCHESTRATION, ARCHITECTURE, RUNBOOK, DATA_HANDLING, PIPELINE_MAP), both READMEs, `CHANGELOG.md` and this file, including findings, numbers and decisions with their reasons. Tests are updated or added with every change. |
| 2026-11-17 | Split work into reasonable, self-contained commits (each passing the tests), still only after the user approves. |
| 2026-11-18 | The domain tab is a persistent translation queue: scans reconcile it, never clear it. Queue = MISSING (High), ISSUE (Normal, manual/agent), OUTDATED (Low, any English commit); `Urgent` is set by the user only and never overwritten. EXTRA goes to one shared `cleanup` tab. Closed rows move to `history`, which keeps completed rows only. |
| 2026-11-18 | blog.groupdocs.com: keep its queue (missing / outdated / extra) but write nothing to `history` for it. |
| 2026-11-18 | Run budget is in **translations**, not posts: limit (1/2/3, "posts' worth", keep ≤ 3) × the blog's language count, with a **5 h** time limit (no new language after it). Rows that don't fit are cut, not skipped. |
| 2026-11-18 | Scan at 00:00 and 12:00 UTC; the five maintained blogs' translations start when a scheduled scan finishes (workflow_run, not after manual or cancelled scans), limit 2 each — two runs per blog a day. One run per blog at a time (concurrency). |
| 2026-11-18 | Retranslation requests from people or agents go in as ISSUE rows via `queue_add.py` / `add_to_queue()` (no duplicate languages); the scan marks unmatched rows `invalid`. |
| 2026-11-19 | Queue order within a priority: MISSING and ISSUE first in, first out (sheet order); OUTDATED newest post first (folder date — a 2026 post before a 2022 one). |
| 2026-11-19 | Keep every operational script (resets, re-sorts, one-off sheet fixes) in the repo with tests and docs, never only in a temp/scratch folder — nothing may be lost. Scripts that change sheets are dry run by default, back up what they change, and record their results in the docs. |
