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
| Scanner | `scan_missing_translations.py` | Walks blog repos, finds missing `index.{lang}.md` files (skipping posts where `index.md` has `draft: true`), writes report to Google Sheets |
| Orchestrator | `translator.py` — `TranslationOrchestrator` | Coordinates the translation workflow, manages agents and token tracking |
| Frontmatter Agent | `translator.py` — `FrontmatterTranslatorAgent` | Translates YAML front matter; protects product names, updates URL with lang prefix |
| Content Agent | `translator.py` — `ContentTranslatorAgent` | Translates Markdown body in chunks; preserves code blocks and shortcodes; 3-retry logic |
| Platform Agent | `translator.py` — `PlatformIdentifierAgent` | Identifies the programming platform (.NET, Java, Python, …) to improve translation context |
| Sheets I/O | `io_google_spreadsheet.py` | Reads/writes Google Sheets via service account credentials |
| Git Utils | `git_repo_utils.py` | Clones or pulls the six blog repositories via GitHub PAT |
| Metrics | `utils.py` | POSTs job metrics to two Google Apps Script webhooks (team + prod) |
| Config | `config.py` | Single source of truth for all constants and env-var-backed secrets |

### Quality Pipeline (Steps 3 & 4)

| Component | File | Responsibility |
|-----------|------|----------------|
| Scanner | `quality_scanner.py` | Step 3, Phase A — heuristic word-overlap Error% per translated file; writes one row per file to quality sheet |
| Validator | `quality_validator.py` | Step 3, Phase B — AI-based Error% via LLM; samples 20 paragraphs; back-fills sheet |
| Retranslator | `quality_retranslator.py` | Step 4 — force-retranslates files flagged `RETRANSLATE` by the AI validator via `TranslationOrchestrator` |
| Language Guard | `lang_guard.py` | Language code normalization, validation, RTL detection, translation heuristics |

---

## External Dependencies

| Service | Used by | Credential |
|---------|---------|------------|
| LLM API (`PROFESSIONALIZE_BASE_URL`) | Translation Agent, Quality Validator, Quality Retranslator | `PROFESSIONALIZE_API_KEY` |
| Google Sheets — per-domain scan sheets | Scanner, Translator | `GOOGLE_CREDENTIALS_JSON_SK` |
| Google Sheets — consolidated scan sheet | Scanner (`write_domain_scan_results`, `update_history_tab`) | `GOOGLE_SERVICE_ACCOUNT_JSON` |
| GitHub (6 blog repos) | `git_repo_utils.py` | `PAT_GITHUB_SK` |
| Metrics REST API (`https://metrics-api.aspose.app/agents`) | `utils.py` | `METRICS_API_KEY` |
| Google Apps Script webhook (team) | `utils.py` | `METRICS_TOKEN_TEAM` |

---

## Data Flow

```
                     ┌──────────────┐
                     │ Google Sheet │  ← scan results / quality scores
                     └──────┬───────┘
                            │ read pending rows
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
│   │   ├── scan_missing_translations.py    # Missing-translation scanner
│   │   ├── git_repo_utils.py               # Clone / pull blog repos
│   │   ├── io_google_spreadsheet.py        # Google Sheets read/write
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
│   └── DATA_HANDLING.md                    # Data flow, secrets, retention
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

**Operational** — daily cron + manual dispatch:

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `scan-missing-translations.yml` | Daily 00:00 UTC + manual | Runs scanner for all 6 domains |
| `translate-blog-*.yml` (per domain) | Daily 01:00 UTC + manual | Translates and commits missing posts |
| `translate-blogs.yml` | Manual dispatch | Translates a chosen domain, product, author, and limit |

**Release & alerts:**

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `release.yml` | `vX.Y.Z` tag | Validates the `CHANGELOG.md` entry and publishes a GitHub Release |
| `alert-on-failure.yml` | Operational workflow failure | Alerts via the `ALERT_WEBHOOK_URL` secret |
| `auto-pr-dev-to-main.yml` | CI success on `dev` | Opens a `dev → main` promotion PR (never auto-merges) |

Secrets are injected via GitHub repository secrets — no credentials exist in committed files, and workflows never dump the environment (`run: env`); CI enforces both.
