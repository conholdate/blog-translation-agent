# Data Handling — Blog Translation Agent

Compliance summary: what data the agent touches, where secrets live, and what is retained.
Companion to [`ARCHITECTURE.md`](./ARCHITECTURE.md) and [`RUNBOOK.md`](./RUNBOOK.md).

## What data is processed

| Data | Source | Sensitivity | Where it goes |
|---|---|---|---|
| Blog post Markdown (`index.md`, `index.{lang}.md`) | Public blog repos (Aspose/GroupDocs/Conholdate) | Public content | Translated variants written back to the same repos |
| Scan / quality results | Computed from the above | Operational | Google Sheets (per-domain tabs + `history`) |
| Run metrics (run_id, durations, counts, token usage) | Pipeline runtime | Operational, non-PII | Metrics REST endpoint (`METRICS_API_URL`) |

**No personal data (PII) is processed.** The agent operates only on public blog content and its own operational metadata.

## Secrets — where they live

All credentials are injected at runtime; **none are committed**.

| Secret | Storage |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | GitHub Actions secret (CI) / local `.env` (dev) |
| `PROFESSIONALIZE_API_KEY`, `PROFESSIONALIZE_BASE_URL`, `PROFESSIONALIZE_LLM_MODEL` | GitHub Actions secret / `.env` |
| `METRICS_API_KEY` | GitHub Actions secret / `.env` |
| `PAT_GITHUB_SK` | GitHub Actions secret / `.env` |

- `.env` is git-ignored; only `.env.example` (names, no values) is tracked.
- CI workflows never run `env`/secret dumps (enforced by the secret-scan job in `ci.yml`).
- Rotation procedure: see [`RUNBOOK.md` §3](./RUNBOOK.md).

## Retention

- **Google Sheets:** per-domain scan tabs are overwritten each run; the `history` tab is append-only (operational log, no PII).
- **CI logs:** retained per the repository's GitHub Actions log-retention setting; contain no secrets (masked + no env dumps).
- **Metrics:** retained by the metrics service; operational counters only.

## Access & ownership

Ownership and review responsibilities are defined in [`.github/CODEOWNERS`](../.github/CODEOWNERS); operational authority and allowed/forbidden paths in [`AGENTS.md`](../AGENTS.md).
