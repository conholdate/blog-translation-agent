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
2. **`history` tab** in the consolidated scan sheet — Status (`pending` / `partial` / `completed`), Completed Date, **Comments** (Step 2's per-run result for the post) and **Notes** (why the scanner flagged it) per (post, issue). The domain tab shows the same Notes for today's rows.
3. **Metrics endpoint** — run_id, durations, items succeeded/failed/skipped, LLM token & call counts emitted by `send_metrics`.

### Outdated translations (OUTDATED / Retranslate)
- The scanner flags a translation when the post's `index.md` was committed after it — usually the optimizer agent's "Optimized Blog Posts" commits. The Notes column names the English commit (date, author, subject) and the translations' dates.
- Step 2 runs MISSING rows first, then OUTDATED rows newest English edit first, overwriting the existing files; commits are titled `Retranslate articles for: …`.
- **Fixing something in English and all translations (URL, image)?** Commit them **together** — equal commit times are not outdated. An English-only commit makes every language OUTDATED and costs ~20 LLM translations per post.
- **Skip a flagged post:** deleting its row from the domain tab only skips it until the next daily scan re-adds it; to settle it for good, commit the translations after the English change.
- **Backlog:** 763 outdated posts on the 5 maintained blogs as of 17 Nov 2026 (see [ORCHESTRATION.md — Retranslation backlog](./ORCHESTRATION.md#retranslation-backlog-as-of-17-nov-2026)). Raise the run limit only within the 3-posts-per-run rule (AGENTS.md).

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

- **Bad translation committed to a blog repo:** revert the specific file(s) in that repo (`git revert` / restore previous `index.{lang}.md`). Note a revert is a new commit on the translation — it won't be OUTDATED unless `index.md` changes again. The quality retranslator (`quality_retranslator.py`) is not run by any workflow, so for a re-fix add the post to the scan sheet by hand or run the translator for it.
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
| Scan log: `No git history for … — OUTDATED check skipped` | Blog repo checked out without history | Keep `fetch-depth: 0` in `scan-missing-translations.yml`. Locally expected (the test mirror has no history). |
| Translate workflow fails at `git merge --ff-only --autostash` with a stash conflict | Someone pushed a change to the same translation file the run retranslated | Re-run the post; the retranslation will start from the new remote version. |
| Scan sheet `Comments` cells show `#ERROR!` | A Comments cell was written `USER_ENTERED` (parsed as a formula) | Code writes Comments `RAW` only (`append_history_comments`); `update_history_tab` no longer rewrites them (fixed 17 Nov 2026). Fix old cells by hand. |

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
