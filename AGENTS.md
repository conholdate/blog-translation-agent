# AGENTS.md
# Blog Translation Agent — Governance Policy

This file defines the operational boundaries for the Blog Translation Agent and its pipeline components.
The agent must not read, write, or modify any path not explicitly listed below, unless the user
explicitly approves it in the current session (see "User-Approved Changes").

This file is a living document: agents keep it updated with the standing instructions agreed in
discussions with the user (see "Standing Instructions").

Last updated: 2026-10-29
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
    2. Detect every post missing a translated version
    3. Write results to Google Sheets

  Step 2 — Translate
    1. Read missing translations from Google Sheets
    2. Checkout target blog repo (read-only except content/)
    3. Translate English index.md → index.{lang}.md
    4. Write translated file to blog-checkedout-repo/content/...
    5. Send metrics to Google Sheets
    6. Append a per-post comment (result, failed languages, EN links kept) to the
       "Comments" column of the scan sheet's `history` tab — production only; local runs print it

  Step 3 — Quality Check
    Phase A — Scanner
      1. Walk blog-checkedout-repo/content/ (read-only)
      2. Compute heuristic Error% per translated file
      3. Write results to quality Google Sheet
    Phase B — Validator
      1. Read quality sheet rows
      2. Run AI-based Error% + RETRANSLATE/KEEP decision check on flagged files (read-only on files)
      3. Update Error% AI, AI Decision, and Analysed At cells in sheet

  Step 4 — Retranslate
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
| 2026-10-29 | Do not add the agent's email to commits. The trailer is just `Co-Authored-By: Claude Opus 5.5` (model name, no `<noreply@anthropic.com>`). |
| 2026-10-29 | For local testing, copy posts from a freshly fetched blog repo into `blog-checkedout-repo/content/<Domain>/<product>/`. Emptying that folder first (and removing product folders with no posts) is fine — it is an untracked mirror. Test with only a few languages to save LLM cost. |
| 2026-10-29 | Commits to blog repos (only after approval) go to: **blog.aspose.com**, **blog.aspose.cloud**, **blog.groupdocs.cloud**, **blog.conholdate.com**, **blog.conholdate.cloud**. |
| 2026-10-29 | **blog.groupdocs.com** is not maintained for translations: identify and report its issues, but do not translate for it or commit to its repo. |
