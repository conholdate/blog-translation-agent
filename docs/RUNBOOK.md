# RUNBOOK — Blog Translation Agent

Operational runbook for running, monitoring, and recovering the Blog Translation Agent.
Companion to [`ARCHITECTURE.md`](./ARCHITECTURE.md) and [`ORCHESTRATION.md`](./ORCHESTRATION.md).
Owner / on-call: **Shoaib Khan** (see [`.github/CODEOWNERS`](../.github/CODEOWNERS)).

---

## 1. Where it runs

| Surface | Detail |
|---|---|
| CI/CD | GitHub Actions — 8 workflows in `.github/workflows/` |
| Schedule | Scan at 00:00 and 12:00 UTC; each scheduled scan starts the five maintained blogs' translation workflows when it finishes (`workflow_run`). Manual via `workflow_dispatch` |
| Runtime | Python 3.13, dependencies pinned in `requirements.lock` |
| State | Google Sheets (domain tabs = persistent queue, `cleanup`, `history` = completed rows) |
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
2. **Domain tab (the queue)** in the consolidated scan sheet — open rows with Priority, Status (blank / `partial` open; `hold`, `invalid` skipped), **Comments** (Step 2's per-run results) and **Notes** (why it was flagged). **`history` tab** — completed rows only, with their Comments and Completed Date. The queue is persistent since 18 Nov 2026: edits there are kept by the scans (see below).
3. **Metrics endpoint** — run_id, durations, items succeeded/failed/skipped, LLM token & call counts emitted by `send_metrics`.

### Working with the queue (domain tab)
- **Run something first:** set its Priority to `Urgent` (Urgent → High → Normal → Low; defaults MISSING High, OUTDATED Low). The scan never overwrites a priority.
- **Translate part of a post first:** split the row by hand (copy it, divide the languages between the copies); rows of the same priority run in sheet order (OUTDATED rows of different posts: newest post first), and each part shrinks on its own.
- **3-day settling time (since 20 Nov 2026):** a post is translated only when **72 h have passed since the last commit to its English `index.md`**. This applies to new posts (MISSING) and updated or optimised posts (OUTDATED) alike, so errors in the English article can be fixed before they reach every language. The **Ready After** column shows when (UTC); while it is ahead, Notes end with `⏳ Waiting until …`. Each new English commit restarts the wait. Waiting rows stay queued and don't use the run's budget. **Need it sooner?** Set Priority `Urgent`, which skips the wait. ISSUE rows (retranslation requests) never wait. The rule lives in `config.TRANSLATION_SETTLE_HOURS`.
- **Bring a post forward:** raise its Priority (e.g. `Urgent`). Moving a row up in the sheet only changes FIFO order among MISSING / ISSUE rows; OUTDATED rows are always worked newest post first within their priority.
- **Your own columns** are kept (columns are found by name). Don't put formulas in the tab — values are rewritten as plain values.
- **Closed rows** (nothing left to translate) move to `history` at the next scan, comments included. blog.groupdocs.com rows are dropped instead (not translated, no history).
- **Junk files (EXTRA)** are listed in the shared `cleanup` tab, not the queue.
- **Ask for a retranslation** (bad tables, wrong terms, a quality finding): `python tools/translation_agent/queue_add.py --domain blog.aspose.com --post pdf/2024-05-01-my-post --langs "fr, de" --reason "Tables left in English"` (omit `--langs` for all languages; `--priority Urgent`; `--source <agent>`; `--dry-run`). It adds an ISSUE row (Normal) unless those languages are already queued. You can also type the row in by hand. A row the next scan can't match gets Status `invalid` and a `⚠️ Invalid: …` line in Notes — fix the folder or languages and the next scan clears it.
- **How much a run does:** the `limit` input is posts' worth — limit × the blog's languages (2 × 21 = 42 translations on blog.aspose.com). A post needing few languages uses less, so more posts fit; a row that doesn't fit is cut and the rest stays queued. No new language starts after 5 h, so the run can still commit before GitHub's 6 h kill (a `⏸️ Time limit` comment lists what wasn't started).
- **When rows close:** Step 2 removes the languages it translated from every open row of the post right after the post (so one retranslation settles both an OUTDATED and an ISSUE row); empty rows move to `history`. If a run's commit fails afterwards, MISSING / OUTDATED rows come back at the next scan, but an ISSUE row must be added again.
- **One-time reset** (18 Nov 2026): `python tools/translation_agent/reset_scan_queue.py` shows what it would change; `--apply` backs up the tabs (`bak-…`), deletes non-completed and blog.groupdocs.com history rows and clears the domain + cleanup tabs. Run it only after translation runs in progress have committed, then run the scan workflow by hand to rebuild the queue.
- **Re-sort OUTDATED rows** (newest post first, so the sheet reads in work order): `python tools/translation_agent/resort_queue.py` shows what would move; `--apply` backs up each changed tab (`bak-…`) and re-sorts; `--domain blog.aspose.com` for one tab. Only OUTDATED rows move. Run it only when no translation run is in progress (they write to the tabs). Not required — Step 2 sorts the queue itself.
- **Backup tabs** (`bak-…`): safe to move to the end of the spreadsheet or delete once the change is checked — the pipeline finds tabs by name, not position.

### Outdated translations (OUTDATED / Retranslate)
- The scanner flags a translation when the post's `index.md` was committed after it — usually the optimizer agent's "Optimized Blog Posts" commits. The Notes column names the English commit (date, author, subject) and the translations' dates.
- Step 2 runs rows by Priority — MISSING (High) before OUTDATED (Low) by default; MISSING and ISSUE rows first in, first out; OUTDATED rows newest post first (folder date, so a 2026 post goes before a 2022 one; raise Priority to bring an old post forward) — overwriting the existing files; commits are titled `Retranslate articles for: …`.
- **Fixing something in English and all translations (URL, image)?** Commit them **together** — equal commit times are not outdated. An English-only commit makes every language OUTDATED and costs ~20 LLM translations per post.
- **Skip a flagged post:** set its Status to `hold` (any value other than blank / `pending` / `partial`) — Step 2 skips it and the scan neither closes it nor re-adds it. Deleting the row only skips it until the next scan re-adds it. To settle it for good, commit the translations after the English change.
- **Backlog:** 763 outdated posts on the 5 maintained blogs as of 17 Nov 2026 (see [ORCHESTRATION.md — Retranslation backlog](./ORCHESTRATION.md#retranslation-backlog-as-of-17-nov-2026)). Two runs a day per blog at 2 posts' worth each; raise the limit only within the 3-posts'-worth rule (AGENTS.md).

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
| Scan sheet `Comments` cells show `#ERROR!` | A Comments cell was written `USER_ENTERED` (parsed as a formula) | Code writes every queue / history cell `RAW` (`append_queue_comments`, `sync_domain_queue`, `append_history_rows`; fixed 17 Nov 2026, queue since 18 Nov 2026). Fix old cells by hand. |

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
