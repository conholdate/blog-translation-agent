# Add "AI Decision" column to the quality pipeline

## Context

Today `quality_validator.py` only writes a numeric `Error% AI (LLM)` score to the sheet, and `quality_retranslator.py` independently decides whether to retranslate by comparing that score to a hardcoded `--threshold` (default 70). This means the actual "should this be retranslated?" judgment is a dumb threshold check done outside the LLM call, even though the LLM already read the content and is well-positioned to judge nuance (e.g. only a brand name like "Aspose.PDF" is untranslated vs. entire paragraphs still in English).

The user wants the LLM to make that judgment explicitly, as part of the same validation call, and have it persisted in the sheet as a 14th column ("AI Decision", right after "Translated Page URL") so a human scanning the sheet can see the LLM's actual call, not just a score. Per the user's confirmed answers: the retranslator should then key off this new column instead of the numeric threshold, and the `--threshold` flag/plumbing should be removed as dead code rather than left as an unused shim.

## Approach

### 1. `tools/quality_agent/quality_scanner.py`
- Append `"AI Decision"` to `SHEET_HEADERS` ([quality_scanner.py:48-52](../../tools/quality_agent/quality_scanner.py#L48-L52)) — becomes column 14.
- Append a matching `""` placeholder (col 14) to the `rows.append([...])` call in `scan_domain()` ([quality_scanner.py:123-137](../../tools/quality_agent/quality_scanner.py#L123-L137)), same pattern as the existing validator-filled placeholders.
- No other changes needed — `write_to_google_spreadsheet()` sizes headers/columns dynamically from `len(column_headers)`.

### 2. `tools/quality_agent/quality_validator.py`
- Add `COL_AI_DECISION = 14` to the column constants block ([quality_validator.py:52-64](../../tools/quality_agent/quality_validator.py#L52-L64)), and a new `FALLBACK_DECISION_THRESHOLD = 70` constant near `AI_SAMPLE_PARAGRAPHS` — used **only** as a safety net when the LLM's response can't be parsed or the call throws entirely (not as the primary decision path).
- `_read_worksheet()` ([quality_validator.py:198-245](../../tools/quality_agent/quality_validator.py#L198-L245)): pad rows to `COL_AI_DECISION` width instead of `COL_TRANSLATED_URL`; add `"ai_decision": row[COL_AI_DECISION - 1]` to the returned dict.
- Heuristic-0% free path ([quality_validator.py:159-164](../../tools/quality_agent/quality_validator.py#L159-L164)): also write `COL_AI_DECISION = "NA"` — no LLM call, same as today's `Error% AI = "NA"`.
- Main AI branch ([quality_validator.py:166-181](../../tools/quality_agent/quality_validator.py#L166-L181)): unpack the now-3-tuple `(error_pct, samples, decision)` and write `decision` to `COL_AI_DECISION` unconditionally (same column regardless of whether this is the first pass or the `Status=Fixed` re-check pass — the column always reflects the latest judgment, per the user's answer to reuse a single column).
- `_ai_error_pct()` ([quality_validator.py:279-340](../../tools/quality_agent/quality_validator.py#L279-L340)):
  - Return type becomes `tuple[float, str, str]`.
  - Prompt gets a new instruction between the SCORE and UNTRANSLATED steps, asking the LLM to output `DECISION: RETRANSLATE` or `DECISION: KEEP` based on its own judgment (not just the score), and the "Respond in EXACTLY this format" block gains a `DECISION:` line **between** `SCORE:` and `UNTRANSLATED:` (ordering matters — the `UNTRANSLATED:` regex is `DOTALL` and captures to end-of-string, so `DECISION:` must come before it).
  - Exception fallback: fix the existing tuple-nesting bug (`return _heuristic_error_pct_simple(pairs), ""` currently nests a 2-tuple inside a 2-tuple instead of unpacking it) while adding the decision — unpack `fallback_pct, fallback_samples = _heuristic_error_pct_simple(pairs)`, derive `fallback_decision` from `FALLBACK_DECISION_THRESHOLD`, return all three.
- `_parse_ai_response()` ([quality_validator.py:343-365](../../tools/quality_agent/quality_validator.py#L343-L365)): add `re.search(r'DECISION:\s*(RETRANSLATE|KEEP)', raw, re.IGNORECASE)`; if it doesn't match (LLM ignored the format), derive decision from `FALLBACK_DECISION_THRESHOLD` as a safety net. Return the 3-tuple.

### 3. `tools/quality_agent/quality_retranslator.py`
- Remove `DEFAULT_THRESHOLD` constant, the `--threshold` argparse flag, and the `threshold` parameter from `retranslate_domain()`, `_run()`, and `main()` end-to-end — it becomes dead once selection moves to the decision column.
- Add `COL_AI_DECISION = 14`; add `"ai_decision"` to `_read_worksheet()`'s returned dict and pad width.
- Change the row filter ([quality_retranslator.py:113-117](../../tools/quality_agent/quality_retranslator.py#L113-L117)) from `status == STATUS_EMPTY and error_ai > threshold` to `status == STATUS_EMPTY and ai_decision.strip().upper() == "RETRANSLATE"`.
- Delete `_pct_to_float()` — no longer used anywhere in this file once the threshold comparison is gone.
- Update the print banner, docstrings, and the agent's natural-language instructions to describe "AI Decision = RETRANSLATE" instead of a threshold. Keep `error_ai` in the row dict/log line — it's still useful human-readable context even though it no longer drives filtering.

### 4. Docs

- **`tools/quality_agent/README.md`**: add column 14 to the Sheet Columns table; note the DECISION field in the Step 3 Phase B section; update Step 4's description/CLI table/examples to drop `--threshold` and describe the `AI Decision == RETRANSLATE` filter; update the Troubleshooting entry about retranslator row selection.
- **`docs/ORCHESTRATION.md`**: update the `retranslate_domain(domain, threshold, limit)` signature reference and the "for each row where Error% AI > threshold" line ([ORCHESTRATION.md:162-164](../ORCHESTRATION.md#L162-L164)) to reflect the decision-column filter; update/remove the "Adjust quality threshold" extension-point section ([ORCHESTRATION.md:197-199](../ORCHESTRATION.md#L197-L199)) since `--threshold` no longer exists.
- **`docs/ARCHITECTURE.md`**: reword the Retranslator one-liner ([ARCHITECTURE.md:59](../ARCHITECTURE.md#L59)) from "above error threshold" to "flagged RETRANSLATE by the AI validator".
- **`docs/RUNBOOK.md`**: reword line 57 ("if it is still above threshold" → "if the AI Decision is still RETRANSLATE").
- **`AGENTS.md`**: reword line 100 ("files above error threshold" → "files with AI Decision = RETRANSLATE").
- **Root `README.md`**: reword line 16 ("quality score falls below the configured threshold" → "quality score is flagged RETRANSLATE by the AI validator").

### 5. Tests
No changes expected. `tools/quality_agent/tests/test_quality_scanner.py` only imports pure helpers (`_pct_to_float`, `_parse_original_metadata`, `_strip_frontmatter`, `_build_translated_url`, `_heuristic_error_pct`) — none reference `SHEET_HEADERS` or row/column layout. There are no existing tests for `quality_validator.py` or `quality_retranslator.py`, so no test scaffolding is being added for this change (consistent with current coverage scope).

## Notes / accepted tradeoffs
- No migration needed for old sheet tabs: `quality_scanner.py` always clears-and-rewrites (or creates) a fresh date-named tab, and the validator/retranslator only ever read `worksheet(0)` — the most recent scan. The very next scan run naturally produces the full 14-column layout.
- This adds one more `ws.update_cell()` call per processed row (3→4 in the main AI branch, 2→3 in the free NA branch). Neither script has retry/backoff for Sheets API rate limits today — that's a pre-existing gap, not something this change introduces or is fixing.

## Verification
1. `cd tools/quality_agent && python -m pytest tests/ -v` — confirm existing tests still pass unmodified.
2. Manual dry run against a real (or scratch) domain sheet: `python quality_scanner.py --domain <small-domain> --key $PROFESSIONALIZE_API_KEY` → confirm the new tab has 14 columns with header `AI Decision` and blank col-14 cells.
3. `python quality_validator.py --domain <small-domain> --limit 3 --key $PROFESSIONALIZE_API_KEY` → confirm:
   - rows with heuristic 0% get `AI Decision = NA`
   - rows that go through the LLM get `RETRANSLATE` or `KEEP` written, and the console log line shows the decision
4. `python quality_retranslator.py --domain <small-domain> --limit 1 --key $PROFESSIONALIZE_API_KEY` → confirm it only picks up rows with `AI Decision = RETRANSLATE` and `Status` blank (spot-check the sheet before/after), and that `--threshold` is no longer a recognized flag (`--help` output).
