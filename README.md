# Blog Translation Agents

Two automated agents that keep blog translations complete, consistent, and high quality across all six domains.

---

## Agents

### 1. Blog Translation Agent
Scans blog repositories daily for missing translations and automatically translates blog posts into 22 languages. See [tools/translation_agent/README.md](tools/translation_agent/README.md) for full documentation.

### 2. Blog Translation Quality Control Agent
Scans all existing translated files, scores their translation quality using a heuristic pass followed by AI analysis, and force-retranslates any file whose score exceeds a set threshold. See [tools/quality_agent/README.md](tools/quality_agent/README.md) for full documentation.

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

## Project Structure

```
blog-translation-agent/
├── tools/
│   ├── translation_agent/          # Blog Translation Agent
│   │   ├── translator.py
│   │   ├── scan_missing_translations.py
│   │   ├── git_repo_utils.py
│   │   ├── io_google_spreadsheet.py
│   │   ├── utils.py
│   │   ├── config.py
│   │   ├── tests/
│   │   └── README.md
│   └── quality_agent/              # Blog Translation Quality Control Agent
│       ├── quality_scanner.py
│       ├── quality_validator.py
│       ├── quality_retranslator.py
│       ├── lang_guard.py
│       ├── tests/
│       └── README.md
├── docs/
│   ├── ARCHITECTURE.md             # System overview and component map
│   └── ORCHESTRATION.md            # State model, control flow, extension points
├── .github/
│   ├── workflows/                  # GitHub Actions
│   └── CODEOWNERS
├── blog-checkedout-repo/           # Blog repo checkouts (gitignored — local + CI)
├── AGENTS.md                       # Agent governance policy
├── CHANGELOG.md                    # Change history
├── CONTRIBUTING.md                 # Developer guide
├── .env                            # Local secrets (gitignored — copy from .env.example)
├── .env.example                    # Template with all required variable names
└── pytest.ini
```

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
| `METRICS_WEBHOOK_URL_PROD` / `METRICS_TOKEN_PROD` | Production metrics webhook |
| `METRICS_WEBHOOK_URL_TEAM` / `METRICS_TOKEN_TEAM` | Team metrics webhook |

For the full list of all 34 variables see [.env.example](.env.example).

---

## CI Workflows

All workflows live in `.github/workflows/`. They run on a daily cron schedule and can also be triggered manually via `workflow_dispatch`.

| Workflow file | Domain | Schedule (UTC) | What it does |
|---------------|--------|----------------|--------------|
| `scan-missing-translations.yml` | All 6 domains | 00:00 daily | Scans all blog repos for missing translations and writes results to Google Sheets |
| `translate-blog-aspose-com.yml` | blog.aspose.com | 01:00 daily | Auto-translates missing posts and commits to the blog repo |
| `translate-blog-aspose-cloud.yml` | blog.aspose.cloud | 01:00 daily | Auto-translates missing posts and commits to the blog repo |
| `translate-blog-groupdocs-com.yml` | blog.groupdocs.com | 01:00 daily | Auto-translates missing posts and commits to the blog repo |
| `translate-blog-groupdocs-cloud.yml` | blog.groupdocs.cloud | 01:00 daily | Auto-translates missing posts and commits to the blog repo |
| `translate-blog-conholdate-com.yml` | blog.conholdate.com | 01:00 daily | Auto-translates missing posts and commits to the blog repo |
| `translate-blog-conholdate-cloud.yml` | blog.conholdate.cloud | 01:00 daily | Auto-translates missing posts and commits to the blog repo |

---

## 📊 Spreadsheets

Scan results, translation reports, and weekly summaries are written to Google Sheets automatically. Sheet IDs are configured in `.env` — ask the team for access to the relevant sheets.

---

## 🚀 Roadmap

- **Unified scan dashboard** — a single consolidated sheet with one tab per domain will drive both scanning and translation, simplifying configuration and giving a cross-domain view in one place
- **Real-time translation progress** — track each post's translation status live in the scan sheet as it moves through the pipeline, rather than reflecting it on the next scan cycle
- **Quality sheet consolidation** — bring all six per-domain quality sheets into a single sheet with domain tabs and a unified history, matching the scan sheet architecture
- **Prompt library** — LLM prompts extracted into versioned, readable files for easier tuning and review without touching agent code
