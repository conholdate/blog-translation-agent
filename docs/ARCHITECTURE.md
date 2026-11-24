# Architecture

---

## System Overview

One agent. Four pipeline steps. Two implementation directories.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Blog Translation Agent                       │
│                                                                     │
│  ┌──────────────────────────────┐  ┌───────────────────────────────┐ │
│  │   Translation Pipeline       │  │   Quality Pipeline            │ │
│  │   tools/translation_agent/   │  │   tools/quality_agent/        │ │
│  │                              │  │                               │ │
│  │  Step 1 — Scan               │  │  Step 3 — Quality Check       │ │
│  │    scan_missing_             │  │    quality_scanner.py  (Ph.A) │ │
│  │      translations.py         │  │    quality_validator.py (Ph.B)│ │
│  │                              │  │                               │ │
│  │  Step 2 — Translate          │  │  Step 4 — Retranslate         │ │
│  │    translator.py             │  │    quality_retranslator.py    │ │
│  │                              │  │                               │ │
│  └──────────────┬───────────────┘  └──────────────┬────────────────┘ │
│                 │                                  │                  │
│                 └──────────────┬───────────────────┘                  │
│                                │                                      │
│                ┌───────────────▼────────────────┐                     │
│                │           config.py            │                     │
│                │     (loads .env via dotenv)    │                     │
│                └────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Components

### Translation Pipeline (Steps 1 & 2)

| Component | File | Responsibility |
|-----------|------|----------------|
| Scanner | `scan_missing_translations.py` | Walks blog repos (skipping drafts and folders without `index.md`), finds missing `index.{lang}.md` files, extra/junk files and translations whose `index.md` was committed after them; writes one row per (post, issue) — `MISSING`/`Translate`, `EXTRA`/`Delete`, `OUTDATED`/`Retranslate` — with a `Notes` reason, and **reconciles** them into the persistent queue (the domain tab: fixed languages removed, closed rows moved to `history`, new findings added at the bottom; EXTRA rows to the `cleanup` tab). See [ORCHESTRATION.md — Step 1](ORCHESTRATION.md#step-1--scan-consolidated-scan-sheet) |
| Queue logic | `scan_queue.py` | Pure reconcile rules for the persistent queue (no sheet access): per-language row shrinking / closing, new rows, priorities, open/held Status, column merging, the 72 h settling time (`ready_after()`, `is_settled()`) |
| Queue add | `queue_add.py` | CLI for people and agents to request a retranslation (ISSUE row) via `io_google_spreadsheet.add_to_queue()`, which skips languages already queued for retranslation |
| Queue reset | `reset_scan_queue.py` | One-time, by hand (18 Nov 2026): backs up tabs, deletes non-completed and blog.groupdocs.com history rows, clears domain + cleanup tabs (dry run unless `--apply`) |
| Queue re-sort | `resort_queue.py` | By hand (19 Nov 2026): moves OUTDATED rows of the domain tabs newest post first, among their own places; backs up changed tabs (dry run unless `--apply`) |
| Scan helpers | `scan_helpers.py` | Front matter reading (`utf-8-sig`, front matter block only), one-pass `git log` of a blog's content (`last_commits()`), the OUTDATED rule (`outdated_langs()`) and the Notes texts |
| Orchestrator | `translator.py` — `TranslationOrchestrator` | Coordinates the translation workflow, manages agents and token tracking; translates `MISSING` rows and overwrites files for `OUTDATED` rows; open queue rows only, by Priority (Urgent, High, Normal, Low — defaults MISSING High, OUTDATED Low), then sheet order (FIFO), OUTDATED rows newest post first (`scan_queue.order_rows()`); holds back rows until their Ready After (last English commit + 72 h, `split_settled()` / `scan_queue.is_settled()`; Urgent and ISSUE rows don't wait); also deletes junk files flagged by `EXTRA`-issue rows (`delete_extra_files()`) |
| Frontmatter Agent | `translator.py` — `FrontmatterTranslatorAgent` | Translates YAML front matter; protects product names, updates URL with lang prefix |
| Content Agent | `translator.py` — `ContentTranslatorAgent` | Translates Markdown body in chunks; preserves code blocks and shortcodes; 3-retry logic |
| Platform Agent | `translator.py` — `PlatformIdentifierAgent` | Identifies the programming platform (.NET, Java, Python, …) to improve translation context |
| Sheets I/O | `io_google_spreadsheet.py` | Reads/writes Google Sheets via service account credentials |
| Git Utils | `git_repo_utils.py` | Clones or pulls the six blog repositories via GitHub PAT |
| Commit Message Builder | `build_commit_message.py` | Builds a descriptive commit title/body from the staged files (post title + per-language list), worded by each file's git status: added → "Translate articles", modified → "Retranslate articles", deleted → "Remove extra translations", mixed → "Update translations" |
| Per-post committer | `commit_translations.py` | Run by all 7 translate workflows after `git add content/`: reads `git diff --cached --name-status` and makes one commit per post with the message above |
| Metrics | `utils.py` | POSTs job metrics to two Google Apps Script webhooks (team + prod) |
| Config | `config.py` | Single source of truth for all constants and env-var-backed secrets |

### Quality Pipeline (Steps 3 & 4)

| Component | File | Responsibility |
|-----------|------|----------------|
| Scanner | `quality_scanner.py` | Step 3, Phase A — heuristic word-overlap Error% per translated file; writes one row per file to quality sheet |
| Validator | `quality_validator.py` | Step 3, Phase B — AI-based Error% via LLM; samples 20 paragraphs; back-fills sheet |
| Retranslator | `quality_retranslator.py` | Step 4 — force-retranslates files flagged `RETRANSLATE` by the AI validator via `TranslationOrchestrator`. **Not wired to any workflow and its output is never committed** (found 17 Nov 2026) — production retranslation goes through Step 1 `OUTDATED` rows + Step 2 |
| Language Guard | `lang_guard.py` | Language code normalization, validation, RTL detection, translation heuristics |

---

## External Dependencies

| Service | Used by | Credential |
|---------|---------|------------|
| LLM API (`PROFESSIONALIZE_BASE_URL`) | Translation Agent, Quality Validator, Quality Retranslator | `PROFESSIONALIZE_API_KEY` |
| Google Sheets — summary sheet (and quality sheets) | Scanner summary, Quality pipeline | `GOOGLE_CREDENTIALS_JSON_SK` |
| Google Sheets — consolidated scan sheet (domain tabs = queue, `cleanup`, `history`) | Scanner (`sync_domain_queue`, `replace_cleanup_rows`, `append_history_rows`), Translator (`read_domain_scan_rows`, `read_cleanup_rows`, `append_queue_comments`) | `GOOGLE_SERVICE_ACCOUNT_JSON` |
| GitHub (6 blog repos) | `git_repo_utils.py` | `PAT_GITHUB_SK` |
| Metrics REST API (`https://metrics-api.aspose.app/agents`) | `utils.py` | `METRICS_API_KEY` |
| Google Apps Script webhook (team) | `utils.py` | `METRICS_TOKEN_TEAM` |

---

## Data Flow

```
                     ┌──────────────┐
                     │ Google Sheet │  ← scan results / quality scores
                     └──────┬───────┘
                            │ read open queue rows (by Priority)
                            ▼
               translator.py / quality_*.py
                            │
              ┌─────────────┼──────────────┐
              │             │              │
              ▼             ▼              ▼
    FrontmatterAgent  ContentAgent   LLM API
    (YAML fields)     (Markdown      (translate /
                       body)          validate)
              │             │
              └──────┬──────┘
                     │ write
                     ▼
        blog-checkedout-repo/content/
          {Family}/{Product}/{Slug}/
            index.{lang}.md          ← output file
                     │
                     ▼
             git push → GitHub
```

---

## Repository Layout

```
blog-translation-agent/
│
├── tools/
│   ├── translation_agent/
│   │   ├── translator.py                   # Orchestrator + 3 agents
│   │   ├── scan_missing_translations.py    # Missing / extra / outdated-translation scanner
│   │   ├── scan_helpers.py                 # Scanner helpers: front matter, git history, Notes
│   │   ├── git_repo_utils.py               # Clone / pull blog repos
│   │   ├── io_google_spreadsheet.py        # Google Sheets read/write
│   │   ├── build_commit_message.py         # Descriptive git commit title/body
│   │   ├── commit_translations.py          # One commit per post (used by translate workflows)
│   │   ├── utils.py                        # Metrics (REST API)
│   │   ├── config.py                       # All constants + env vars
│   │   └── tests/
│   │
│   └── quality_agent/
│       ├── quality_scanner.py              # Step 3A — heuristic scan
│       ├── quality_validator.py            # Step 3B — AI validation
│       ├── quality_retranslator.py         # Step 4 — retranslation
│       ├── lang_guard.py                   # Language utilities
│       └── tests/
│
├── docs/
│   ├── ARCHITECTURE.md                     # This file
│   ├── ORCHESTRATION.md                    # State model + control flow
│   ├── RUNBOOK.md                          # Operations + incident response
│   ├── DATA_HANDLING.md                    # Data flow, secrets, retention
│   ├── GITLAB_MIGRATION.md                 # Moving the pipelines to GitLab (analysis, not started)
│   └── PIPELINE_MAP.html                   # Visual pipeline map
│
├── .github/
│   ├── workflows/                          # CI gate, operational (scan/translate), release, alerts
│   ├── dependabot.yml                      # Weekly dependency updates
│   └── CODEOWNERS
│
├── AGENTS.md                               # Agent governance policy
├── CHANGELOG.md                            # Change history
├── CONTRIBUTING.md                         # Developer guide
├── Makefile                                # Test targets
├── README.md
├── requirements.txt / requirements.lock
└── pytest.ini
```

---

## CI / CD

**Quality gate** — `ci.yml`, on every push and pull request to `main`/`dev`:

| Job | What it does |
|-----|--------------|
| Tests | `pytest` with a coverage floor (`--cov-fail-under=35`) |
| Secret & env-dump scan | Fails if a workflow reintroduces `run: env` or a hardcoded secret appears in tracked source |

**Operational** — scan twice a day, translations chained to it, plus manual dispatch:

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `scan-missing-translations.yml` | 00:00 and 12:00 UTC + manual | Runs scanner for all 6 domains (blog repo checked out with full history for the OUTDATED check); `fail-fast: false` |
| `translate-blog-*.yml` (per domain) | When a scheduled scan finishes (`workflow_run`; not groupdocs.com) + manual | Works the queue by priority within a language budget (limit × the blog's languages, default 2 posts' worth) and a 5 h time limit, syncs with `git merge --ff-only --autostash`, commits one commit per post; one run per blog at a time (`concurrency`) |
| `translate-blogs.yml` | Manual dispatch | Translates a chosen domain, product, author, and limit |

**Release & alerts:**

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `release.yml` | `vX.Y.Z` tag | Validates the `CHANGELOG.md` entry and publishes a GitHub Release |
| `alert-on-failure.yml` | Operational workflow failure | Alerts via the `ALERT_WEBHOOK_URL` secret |
| `auto-pr-dev-to-main.yml` | CI success on `dev` | Opens a `dev → main` promotion PR (never auto-merges) |

Secrets are injected via GitHub repository secrets — no credentials exist in committed files, and workflows never dump the environment (`run: env`); CI enforces both.
