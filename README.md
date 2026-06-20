# Blog Translation Agent

An AI-powered agent that keeps blog translations complete, accurate, and high quality across all six domains — automatically.

---

## What It Does

The agent runs a four-step pipeline:

| Step | What it does |
|------|-------------|
| **1. Scan** | Walks all blog repositories daily, detects every post missing a translated version, and reports results to Google Sheets |
| **2. Translate** | Reads the scan results and fills in missing translations using an LLM — preserving formatting, code blocks, and front matter |
| **3. Quality Check** | Scores all existing translations for accuracy using a heuristic pass followed by AI analysis |
| **4. Retranslate** | Automatically re-translates any post whose quality score falls below the configured threshold |

---

## Supported Domains

| Domain | Group |
|--------|-------|
| blog.aspose.com | Aspose |
| blog.aspose.cloud | Aspose |
| blog.groupdocs.com | GroupDocs |
| blog.groupdocs.cloud | GroupDocs |
| blog.conholdate.com | Conholdate |
| blog.conholdate.cloud | Conholdate |

---

## Supported Languages

22 languages: `ar` `cs` `de` `es` `fa` `fr` `he` `id` `it` `ja` `ko` `nl` `pl` `pt` `ru` `sv` `th` `tr` `uk` `vi` `zh` `zh-hant`

---

## Project Structure

```
blog-translation-agent/
├── tools/
│   ├── translation_agent/          # Steps 1 & 2 — Scan + Translate
│   │   ├── translator.py
│   │   ├── scan_missing_translations.py
│   │   ├── git_repo_utils.py
│   │   ├── io_google_spreadsheet.py
│   │   ├── utils.py
│   │   ├── config.py
│   │   ├── tests/
│   │   └── README.md
│   └── quality_agent/              # Steps 3 & 4 — Quality Check + Retranslate
│       ├── quality_scanner.py
│       ├── quality_validator.py
│       ├── quality_retranslator.py
│       ├── lang_guard.py
│       ├── tests/
│       └── README.md
├── docs/
│   ├── ARCHITECTURE.md             # System overview and component map
│   ├── ORCHESTRATION.md            # Pipeline steps, state models, extension points
│   ├── RUNBOOK.md                  # Operations: runs, credential rotation, recovery, escalation
│   └── DATA_HANDLING.md            # Data flow, secrets storage, retention
├── .github/
│   ├── workflows/                  # GitHub Actions (CI gate, operational, release, alerts)
│   ├── dependabot.yml              # Weekly pip + Actions dependency updates
│   └── CODEOWNERS
├── blog-checkedout-repo/           # Blog repo checkouts (gitignored — local + CI)
├── AGENTS.md                       # Agent governance policy
├── CHANGELOG.md                    # Change history (Keep a Changelog)
├── CONTRIBUTING.md                 # Developer guide
├── Makefile                        # test / test-translation / test-quality targets
├── .env                            # Local secrets (gitignored — copy from .env.example)
├── .env.example                    # Template with all required variable names
├── requirements.txt                # Direct dependencies
├── requirements.lock               # Pinned dependency tree (CI installs from this)
└── pytest.ini
```

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System overview and component map |
| [docs/ORCHESTRATION.md](docs/ORCHESTRATION.md) | Pipeline steps, state models, extension points |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Operations: manual runs, credential rotation, recovery, escalation |
| [docs/DATA_HANDLING.md](docs/DATA_HANDLING.md) | What data is processed, where secrets live, retention |
| [AGENTS.md](AGENTS.md) | Agent governance policy and allowed/forbidden paths |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Local setup, testing, and release process |

---

## Environment Variables

All secrets and environment-specific paths are stored in `.env` at the project root for local development and as repository secrets in GitHub Actions. No credentials are hardcoded in any committed file. Copy `.env.example` to `.env` and fill in the values to get started.

Key variables:

| Variable | Description |
|----------|-------------|
| `PROFESSIONALIZE_API_KEY` | LLM API key for translation and quality validation |
| `GOOGLE_CREDENTIALS_JSON_SK` | Google service account for per-domain scan sheets |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google service account for the consolidated scan sheet |
| `TRANSLATION_SCAN_SHEET_ID` | Consolidated scan sheet (one tab per domain + history tab) |
| `PAT_GITHUB_SK` | GitHub Personal Access Token for cloning and pushing blog repos |
| `METRICS_API_KEY` | Production metrics API key (`https://metrics-api.aspose.app/agents`) |
| `METRICS_WEBHOOK_URL_TEAM` / `METRICS_TOKEN_TEAM` | Team metrics webhook |

For the full list of all variables see [.env.example](.env.example).

---

## Continuous Integration & Workflows

All workflows live in `.github/workflows/`.

### Quality gate — `ci.yml`

Runs on every push and pull request to `main` and `dev`:

- **Tests + coverage** — `pytest` with a coverage floor (`--cov-fail-under=35`)
- **Secret & env-dump scan** — fails the build if any workflow reintroduces `run: env` or a hardcoded secret pattern appears in tracked source

Enable branch protection on `main` requiring these checks so nothing merges without passing.

### Operational workflows

Run on a daily cron and can also be triggered manually via `workflow_dispatch`:

| Workflow file | Domain | Schedule (UTC) | What it does |
|---------------|--------|----------------|--------------|
| `scan-missing-translations.yml` | All 6 domains | 00:00 daily | Scans all blog repos for missing translations and writes results to Google Sheets |
| `translate-blog-aspose-com.yml` | blog.aspose.com | 01:00 daily | Auto-translates missing posts and commits to the blog repo |
| `translate-blog-aspose-cloud.yml` | blog.aspose.cloud | 01:00 daily | Auto-translates missing posts and commits to the blog repo |
| `translate-blog-groupdocs-com.yml` | blog.groupdocs.com | 01:00 daily | Auto-translates missing posts and commits to the blog repo |
| `translate-blog-groupdocs-cloud.yml` | blog.groupdocs.cloud | 01:00 daily | Auto-translates missing posts and commits to the blog repo |
| `translate-blog-conholdate-com.yml` | blog.conholdate.com | 01:00 daily | Auto-translates missing posts and commits to the blog repo |
| `translate-blog-conholdate-cloud.yml` | blog.conholdate.cloud | 01:00 daily | Auto-translates missing posts and commits to the blog repo |

### Release & alerts

- `release.yml` — triggered by a `vX.Y.Z` tag; validates the matching `CHANGELOG.md` entry and publishes a GitHub Release
- `alert-on-failure.yml` — watches the operational workflows and alerts (via the `ALERT_WEBHOOK_URL` secret) when one fails
- `auto-pr-dev-to-main.yml` — when CI passes on `dev`, automatically opens a `dev → main` promotion PR (never auto-merges)

### Branching

Work happens on **`dev`**; **`main`** is protected production. Push to `dev` → CI runs → on green a `dev → main` PR opens automatically → you review and merge → tag a release. See [CONTRIBUTING.md](CONTRIBUTING.md#branching-model) for the full flow.

---

## Development

```bash
# Set up
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock
cp .env.example .env          # then fill in values

# Run tests
make test                     # full suite (or: make test-translation / make test-quality)
```

Tests live in `tools/translation_agent/tests/` and `tools/quality_agent/tests/`. CI runs the same suite with a coverage gate on every push and PR.

### Releases

Versioned via [Keep a Changelog](https://keepachangelog.com/) + git tags (current line: **v2.0.0**; the v1 era ran through 2025-12-31). To cut a release: add a `## [X.Y.Z]` entry to `CHANGELOG.md`, then push a `vX.Y.Z` tag — `release.yml` validates the entry and publishes the GitHub Release.

---

## 📊 Spreadsheets

Scan results, translation reports, and quality scores are written to Google Sheets automatically. Sheet IDs are configured in `.env` — ask the team for access to the relevant sheets.

---

## 🚀 Roadmap

- **Unified scan dashboard** — a single consolidated sheet with one tab per domain will drive both scanning and translation, simplifying configuration and giving a cross-domain view in one place
- **Real-time translation progress** — track each post's translation status live in the scan sheet as it moves through the pipeline, rather than reflecting it on the next scan cycle
- **Quality sheet consolidation** — bring all six per-domain quality sheets into a single sheet with domain tabs and a unified history, matching the scan sheet architecture
- **Prompt library** — LLM prompts extracted into versioned, readable files for easier tuning and review without touching agent code
