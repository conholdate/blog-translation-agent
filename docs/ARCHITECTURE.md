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
| Scanner | `scan_missing_translations.py` | Walks blog repos, finds missing `index.{lang}.md` files, writes report to Google Sheets |
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
| Retranslator | `quality_retranslator.py` | Step 4 — force-retranslates files above error threshold via `TranslationOrchestrator` |
| Language Guard | `lang_guard.py` | Language code normalization, validation, RTL detection, translation heuristics |

---

## External Dependencies

| Service | Used by | Credential |
|---------|---------|------------|
| LLM API (`PROFESSIONALIZE_BASE_URL`) | Translation Agent, Quality Validator, Quality Retranslator | `PROFESSIONALIZE_API_KEY` |
| Google Sheets — per-domain scan sheets | Scanner, Translator | `GOOGLE_CREDENTIALS_JSON_SK` |
| Google Sheets — consolidated scan sheet | Scanner (`write_domain_scan_results`, `update_history_tab`) | `GOOGLE_SERVICE_ACCOUNT_JSON` |
| GitHub (6 blog repos) | `git_repo_utils.py` | `PAT_GITHUB_SK` |
| Google Apps Script webhooks (2) | `utils.py` | `METRICS_TOKEN_TEAM`, `METRICS_TOKEN_PROD` |

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
│   │   ├── utils.py                        # Metrics webhooks
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
│   └── ORCHESTRATION.md                    # State model + control flow
│
├── .github/
│   ├── workflows/                          # GitHub Actions (daily scan + translation)
│   └── CODEOWNERS
│
├── AGENTS.md                               # Agent governance policy
├── CONTRIBUTING.md                         # Developer guide
├── README.md
├── requirements.txt
└── pytest.ini
```

---

## CI / CD

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `scan-missing-translations.yml` | Daily 01:00 UTC + manual | Runs scanner for all 6 domains in parallel matrix |
| `translate-blogs.yml` | Manual dispatch | Translates posts for a chosen domain, product, author, and limit |

Secrets are injected via GitHub repository secrets — no credentials exist in committed files.
