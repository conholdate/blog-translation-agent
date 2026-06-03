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
├── AGENTS.md                       # Agent governance policy
├── CONTRIBUTING.md                 # Developer guide
└── pytest.ini
```

---

## Environment Variables

All secrets and environment-specific paths are stored in `tools/translation_agent/.env` for local development and as repository secrets in GitHub Actions. No credentials are hardcoded in any committed file.

Key variables:

| Variable | Description |
|----------|-------------|
| `PROFESSIONALIZE_API_KEY` | API key for the LLM translation service |
| `GOOGLE_CREDENTIALS_JSON_SK` | Google service account JSON for Sheets access |
| `PAT_GITHUB_SK` | GitHub Personal Access Token for cloning and pushing blog repos |
| `METRICS_WEBHOOK_URL_PROD` / `METRICS_TOKEN_PROD` | Production metrics webhook |
| `METRICS_WEBHOOK_URL_TEAM` / `METRICS_TOKEN_TEAM` | Team metrics webhook |

For the full variable list see [CONTRIBUTING.md](CONTRIBUTING.md#setup).

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

### Missing Translation — Daily Scanning Results

| Blog | Spreadsheet |
|------|-------------|
| All Blogs | https://docs.google.com/spreadsheets/d/1G_Q_shGbNXJCp-xu_maqFZWddpB-VksQh_Ni0OfxDts/ |
| blog.aspose.com | https://docs.google.com/spreadsheets/d/1gxx6xk2HJ7IPpRsvLG7Ef18jc7BnQuAAJ33UyHn8b3w |
| blog.groupdocs.com | https://docs.google.com/spreadsheets/d/1H8M5ZTBdSFRTuYMjzn-O0gRDX6beIB50t55g6dOPWoA |
| blog.conholdate.com | https://docs.google.com/spreadsheets/d/10vzH3ZBiURAXamt0VOppYODKZNmDt0LR_zYXb13YJhs |
| blog.aspose.cloud | https://docs.google.com/spreadsheets/d/1HcHQxooeva8iwnDmee-SX07KNKke5sXjWC6ZPJw1G0o |
| blog.groupdocs.cloud | https://docs.google.com/spreadsheets/d/1x0Jx0yniKjGMcccmb_2JPJylVP6EIWeN-H2UOC6Y47U |
| blog.conholdate.cloud | https://docs.google.com/spreadsheets/d/1Ofoc8f-jbguE4rUGkKNLFvLObxPll9s3_Hw97UsZizs |

### Translated Blog Posts

| Description | Spreadsheet |
|-------------|-------------|
| All Blogs (Separate & Consolidated) | https://docs.google.com/spreadsheets/d/1GKqlqf4BSmZ4dgPVXTsmq4GmY9cJRZ5oWWOXQTHOq_Y |

### Weekly Reports

| Blog | Spreadsheet |
|------|-------------|
| blog.aspose.com | https://docs.google.com/spreadsheets/d/1u1NI9MiU1pqKQ2t3G5aCQ5tkcIzVmjdp6foG5Wl2j2o |
| blog.groupdocs.com | https://docs.google.com/spreadsheets/d/1qs31oJDfdu4rFbd5wocqOTgWqHMF1RQZGdg6ygnMxNk |
| blog.conholdate.com | https://docs.google.com/spreadsheets/d/1ZCm2dq2NQKecdmpmOyZ73bXPgEGF-kzLdiNmuGZMHwc |
| blog.aspose.cloud | https://docs.google.com/spreadsheets/d/11zPd8AlIM3zfKTxUSTbr5RRmYfvE_dxXWg0vRvZf0QI |
| blog.groupdocs.cloud | https://docs.google.com/spreadsheets/d/1bmR61_R9-vHGLAoxsak12YLuSZITwCKB0qqhzh_W2XU |
| blog.conholdate.cloud | https://docs.google.com/spreadsheets/d/1__c5m-C9H23MIgmDK-YSW7L6JIn47ig3l1e5RpPcK9g |
