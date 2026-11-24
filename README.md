# Blog Translation Agent

An AI-powered agent that keeps blog translations complete, accurate, and high quality across all six domains — automatically.

---

## What It Does

The agent runs a four-step pipeline:

| Step | What it does |
|------|-------------|
| **1. Scan** | Walks all blog repositories daily and reports to Google Sheets every post with a missing translation (`MISSING`), an unsupported extra file (`EXTRA`), or a translation older than its English `index.md` (`OUTDATED` — the English was committed after it), with a `Notes` column saying why (line 1 is a short headline for the dashboard, e.g. `New Post` or `Updated by Optimizer Agent on 2026-11-16`) |
| **2. Translate** | Reads the scan results, fills in missing translations and retranslates outdated ones using an LLM — preserving formatting, code blocks, and front matter. New posts always go first. A post is translated only 3 days (72 h) after its last English edit, so errors can be fixed in English first (Urgent rows skip the wait) |
| **3. Quality Check** | Scores all existing translations for accuracy using a heuristic pass followed by AI analysis |
| **4. Retranslate** | Re-translates files the AI validator flags `RETRANSLATE` — **not scheduled in any workflow yet** (see [ORCHESTRATION.md](docs/ORCHESTRATION.md#control-flow--step-4-retranslator)) |

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
│   │   ├── scan_helpers.py
│   │   ├── build_commit_message.py
│   │   ├── commit_translations.py
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
│   ├── DATA_HANDLING.md            # Data flow, secrets storage, retention
│   ├── GITLAB_MIGRATION.md         # Moving the pipelines to GitLab (analysis, not started)
│   └── PIPELINE_MAP.html           # Visual pipeline map
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
| [docs/GITLAB_MIGRATION.md](docs/GITLAB_MIGRATION.md) | Moving the scan/translate pipelines to GitLab — analysis, risks, open questions (not started) |
| [AGENTS.md](AGENTS.md) | Agent governance policy and allowed/forbidden paths |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Local setup, testing, and release process |

---

## Environment Variables

All secrets and environment-specific paths are stored in `.env` at the project root for local development and as repository secrets in GitHub Actions. No credentials are hardcoded in any committed file. Copy `.env.example` to `.env` and fill in the values to get started.

Key variables:

| Variable | Description |
|----------|-------------|
| `PROFESSIONALIZE_API_KEY` | LLM API key for translation and quality validation |
| `GOOGLE_CREDENTIALS_JSON_SK` | Google service account for the scan summary sheet and the quality sheets (the old per-domain scan sheets are no longer written; their `TRANSLATION_SCAN_SHEET_ID_<DOMAIN>` secrets are unused) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google service account for the consolidated scan sheet |
| `TRANSLATION_SCAN_SHEET_ID` | Consolidated scan sheet: one tab per domain (the persistent translation queue), `cleanup` (junk files) and `history` (completed rows) |
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

The scan runs at 00:00 and 12:00 UTC; the five maintained blogs' translation workflows start when a scheduled scan finishes (`workflow_run`) — two runs per blog a day, 2 posts' worth each (limit × the blog's languages), one run per blog at a time. All can be triggered manually via `workflow_dispatch`:

| Workflow file | Domain | Schedule (UTC) | What it does |
|---------------|--------|----------------|--------------|
| `scan-missing-translations.yml` | All 6 domains | 00:00 and 12:00 | Scans all blog repos for missing, extra and outdated translations and reconciles the translation queue in Google Sheets |
| `translate-blog-aspose-com.yml` | blog.aspose.com | after each scheduled scan | Works the translation queue by priority (missing, issues, outdated), commits to the blog repo |
| `translate-blog-aspose-cloud.yml` | blog.aspose.cloud | after each scheduled scan | Works the translation queue by priority (missing, issues, outdated), commits to the blog repo |
| `translate-blog-groupdocs-com.yml` | blog.groupdocs.com | manual only | Report-only blog: not translated on a schedule |
| `translate-blog-groupdocs-cloud.yml` | blog.groupdocs.cloud | after each scheduled scan | Works the translation queue by priority (missing, issues, outdated), commits to the blog repo |
| `translate-blog-conholdate-com.yml` | blog.conholdate.com | after each scheduled scan | Works the translation queue by priority (missing, issues, outdated), commits to the blog repo |
| `translate-blog-conholdate-cloud.yml` | blog.conholdate.cloud | after each scheduled scan | Works the translation queue by priority (missing, issues, outdated), commits to the blog repo |

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

- ~~**Unified scan dashboard**~~ — done: the consolidated sheet's domain tabs are the persistent translation queue for both scanning and translation (18 Nov 2026); the old per-domain sheets are no longer written
- **Real-time translation progress** — track each post's translation status live in the scan sheet as it moves through the pipeline, rather than reflecting it on the next scan cycle
- **Quality sheet consolidation** — bring all six per-domain quality sheets into a single sheet with domain tabs and a unified history, matching the scan sheet architecture
- **Prompt library** — LLM prompts extracted into versioned, readable files for easier tuning and review without touching agent code
