# RUNBOOK — Blog Translation Agent

Operational runbook for running, monitoring, and recovering the Blog Translation Agent.
Companion to [`ARCHITECTURE.md`](./ARCHITECTURE.md) and [`ORCHESTRATION.md`](./ORCHESTRATION.md).
Owner / on-call: **Shoaib Khan** (see [`.github/CODEOWNERS`](../.github/CODEOWNERS)).

---

## 1. Where it runs

| Surface | Detail |
|---|---|
| CI/CD | GitHub Actions — 8 workflows in `.github/workflows/` |
| Schedule | Daily `cron: "0 0 * * *"` (01:00 UTC) per workflow; manual via `workflow_dispatch` |
| Runtime | Python 3.13, dependencies pinned in `requirements.lock` |
| State | Google Sheets (per-domain scan tabs + append-only `history` tab) |
| Metrics | REST endpoint via `config.METRICS_API_URL` + `METRICS_API_KEY` (`X-Api-Key` header) |

The two pipelines (Translation = Steps 1–2, Quality = Steps 3–4) are independent and can be run separately.

---

## 2. Routine operations

### Trigger a run manually
GitHub → **Actions** → choose the workflow (e.g. `translate-blog-aspose-com`) → **Run workflow** → set inputs (domain, product, author, limit) → **Run**.

### Re-run a single failed domain
Each domain has its own workflow, so re-running is isolated — trigger only the affected `translate-blog-<domain>.yml`. Per-file failures are already isolated in code (one bad file does not halt the rest), so a partial failure usually only needs the failed slice re-run, not the whole batch.

### Check what happened
1. **Actions logs** — step-level output for the run.
2. **`history` tab** in the consolidated scan sheet — Status (`pending` / `partial` / `completed`) and Completed Date per domain.
3. **Metrics endpoint** — run_id, durations, items succeeded/failed/skipped, LLM token & call counts emitted by `send_metrics`.

---

## 3. Credential rotation

Secrets live as **GitHub Actions secrets** (CI) and in a local **`.env`** (never committed). Rotate by updating both.

| Secret | Used for | Rotation |
|---|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google Sheets read/write | Create a new key in the GCP service account, update the GitHub secret, delete the old key. |
| `PROFESSIONALIZE_API_KEY` | LLM translation calls | Issue a new key, update GitHub secret + local `.env`, revoke old. |
| `METRICS_API_KEY` | Metrics REST endpoint (`X-Api-Key`) | Rotate at the metrics service, update GitHub secret. Metrics failures do not halt the pipeline, so this is low-risk to rotate. |
| `PAT_GITHUB_SK` | Clone/push blog repos | Regenerate PAT (least-privilege), update secret, revoke old. |

After rotation, trigger one `workflow_dispatch` run with a small `limit` to confirm auth before the next scheduled run.

---

## 4. Recovery & rollback

The agent only writes language variants (`index.{lang}.md`) — it never modifies the English source (`index.md`).

- **Bad translation committed to a blog repo:** revert the specific file(s) in that repo (`git revert` / restore previous `index.{lang}.md`). The next quality-validator pass re-checks and the retranslator will re-fix if the AI Decision is still `RETRANSLATE`.
- **Corrupted batch:** identify the run via `run_id` in metrics / the `history` tab, then re-run only the affected domain/product with a `limit`.
- **Sheet state wrong:** the per-domain scan tab is overwritten on each scan; re-running the scanner rebuilds it. The `history` tab is append-only — correct forward, do not delete rows.

---

## 5. Common failures

| Symptom | Likely cause | Action |
|---|---|---|
| `PROFESSIONALIZE_API_KEY` missing / 401 | Secret not set or expired | Set/rotate the key (§3), re-run. |
| Google credential error | Service-account key invalid/expired | Rotate `GOOGLE_SERVICE_ACCOUNT_JSON` (§3). |
| Untranslated / partially-English output | LLM returned source text | Retries (3×) + AI validation already handle most; if persistent, re-run the file via the quality pipeline. |
| Shortcode / code-fence corruption | LLM altered Hugo syntax | Covered by recent retry hardening; if seen, file an issue with the post slug and re-run. |
| Sheet API quota / 429 | Rate limit | Re-run later; reduce `limit`. |
| Metrics not recorded | Metrics endpoint/key issue | Non-blocking by design — fix `METRICS_*`, no pipeline impact. |

---

## 6. Escalation

**Automated alerting:** `.github/workflows/alert-on-failure.yml` watches all scan/translate workflows and fires when one fails. Set the repo secret `ALERT_WEBHOOK_URL` (Slack/Teams/incoming webhook) to receive alerts; without it, GitHub still emails the run actor. Treat a failed scheduled run as the trigger to start here.

1. Owner / first responder: **Shoaib Khan**.
2. Sub-area owners per `.github/CODEOWNERS` (`tools/translation_agent/` co-maintainers).
3. For a suspected credential exposure: rotate immediately (§3), then review Actions logs for the affected window.

---

## 7. Severity guide

| Sev | Definition | Response |
|---|---|---|
| **S1** | Credential exposed, or wrong content published across domains | Rotate keys now; revert affected files; notify owner. |
| **S2** | One domain/workflow failing repeatedly | Re-run isolated domain; open issue. |
| **S3** | Isolated file/post failures | Let retry/quality loop self-heal; monitor `history` tab. |
