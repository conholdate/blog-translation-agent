"""
Translation Quality Validator  (Phase 2)
=========================================
Reads rows with Status=EMPTY from a domain's quality sheet, samples content
with AI to compute an accurate Error%, and updates the sheet in-place.
After all rows are updated, the sheet is sorted by Error% descending.

For rows with Status=Fixed it fills the "Error% after Fix" column instead,
allowing humans to see the improvement after they've corrected a translation.

Usage:
    python quality_validator.py --domain blog.aspose.com
    python quality_validator.py --domain all --limit 50
    python quality_validator.py --domain blog.aspose.com --key YOUR_API_KEY
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'translation_agent'))

import re
import yaml
import random
import argparse
import asyncio
from pathlib import Path
from datetime import datetime
from openai import AsyncOpenAI, OpenAI

import config
import lang_guard
import gspread
from io_google_spreadsheet import get_gc
from agents import Agent, Runner, function_tool, set_tracing_disabled, RunConfig
from agents.models.openai_provider import OpenAIProvider


# ============================================================================
# SHEET CONFIGURATION  (mirrors quality_scanner.py)
# ============================================================================

QUALITY_SHEET_IDS: dict[str, str] = {
    config.DOMAIN_ASPOSE_COM:       "1BuiSIqBKWCpcGoiDsUz1oJPHj0PvIQpmoTrGUv8vv8Q",
    config.DOMAIN_ASPOSE_CLOUD:     "1hhd3KgLsW0XplVsnE-ctTgpbdcRw8XfPAGxgDzkzufk",
    config.DOMAIN_GROUPDOCS_COM:    "1Qr6pq438SJBvop9NWCjF5ALrjgX5UcjLhgZbrEZn78I",
    config.DOMAIN_GROUPDOCS_CLOUD:  "1NtulRvHM8KDfK_OayKz7WeHtom-eyZlV8nmwr2OXypE",
    config.DOMAIN_CONHOLDATE_COM:   "17rNwX6IdrB6QIMMcRS3haqELojlCHYDguP8zxCIkUUE",
    config.DOMAIN_CONHOLDATE_CLOUD: "19sS8roVeISV4BbEhkRx5lY2FYUjZeY6JSBofzQdYkSs",
}

# Column positions (1-indexed, matching SHEET_HEADERS in quality_scanner.py)
COL_DOMAIN              = 1
COL_PRODUCT             = 2
COL_SLUG                = 3
COL_URL                 = 4
COL_AUTHOR              = 5
COL_LANG                = 6
COL_ERROR_HEURISTIC     = 7   # "Error% Heuristic"        — written by scanner (Phase 1)
COL_ERROR_AI            = 8   # "Error% AI (LLM)"         — written by validator (Phase 2)
COL_UNTRANSLATED_SAMPLES= 9   # "Untranslated Samples"    — written by validator (Phase 2)
COL_ANALYSED_AT         = 10  # "Analysed At"             — timestamp written by validator (Phase 2)
COL_STATUS              = 11  # "Status"                  — blank / Fixed (set manually by human)
COL_ERROR_AFTER         = 12  # "Error% after Fix"        — written by validator after human fix
COL_TRANSLATED_URL      = 13  # "Translated Page URL"     — domain/lang/post_url

# Sheet row offsets
# Row 1 = language-support line  (written by write_to_google_spreadsheet)
# Row 2 = column headers
# Row 3+ = data rows
DATA_ROW_OFFSET = 3   # first data row in 1-indexed sheet coords

STATUS_EMPTY = ""
STATUS_FIXED = "Fixed"

# Paragraph sample size for AI check (cost control)
AI_SAMPLE_PARAGRAPHS = 20

# Module-level sync client — initialised in main() before the agent runs
_llm_client: OpenAI = None


# ============================================================================
# TOOL
# ============================================================================

@function_tool
def validate_domain(domain: str, limit: int = 0) -> str:
    """
    For the given blog domain:
      1. Read the first worksheet of its quality sheet.
      2. For rows with Status=EMPTY  → compute AI Error%,  update 'Error% AI' column.
      3. For rows with Status=Fixed  → compute AI Error%,  update 'Error% after Fix' column.
      4. Sort all data rows by 'Error%' descending.

    Args:
        domain: e.g. 'blog.aspose.com'
        limit:  max rows to process in this run (0 = no limit, useful for testing)

    Returns a summary string.
    """
    domain = domain.strip().lower()

    if domain not in config.domains_data:
        return f"ERROR: Unknown domain '{domain}'"

    sheet_id = QUALITY_SHEET_IDS.get(domain)
    if not sheet_id:
        return f"ERROR: No quality sheet configured for '{domain}'"

    repo_path = config.domains_data[domain][config.KEY_LOCAL_GITHUB_REPO]

    print(f"\n{'='*60}")
    print(f"  Validating: {domain}")
    print(f"{'='*60}")

    # ── 1. Open sheet ──────────────────────────────────────────────────────
    ws, data_rows = _read_worksheet(sheet_id)
    if ws is None:
        return f"ERROR: Could not open sheet for '{domain}'"

    print(f"  Sheet has {len(data_rows)} data rows.")

    # ── 2. Filter rows to process ──────────────────────────────────────────
    # Skip rows already analysed (Error% AI is filled) UNLESS Status=Fixed,
    # which means a human has corrected the translation and wants a re-check.
    to_process = [
        r for r in data_rows
        if r["status"] == STATUS_FIXED or not r["error_ai"].strip()
    ]
    if limit > 0:
        to_process = to_process[:limit]

    print(f"  Rows to validate: {len(to_process)}"
          + (f" (limit={limit})" if limit > 0 else ""))

    updated = skipped = failed = 0

    # ── 3. Validate each row ───────────────────────────────────────────────
    for row in to_process:
        sheet_row   = row["sheet_row"]
        product     = row["product"]
        slug        = row["slug"]
        lang        = row["lang"]
        status      = row["status"]

        # Locate files
        original_path   = Path(repo_path) / product / slug / "index.md"
        translated_path = Path(repo_path) / product / slug / f"index.{lang}.md"

        if not original_path.exists() or not translated_path.exists():
            print(f"  ⚠️  Missing file(s) for {product}/{slug}/{lang} — skipping")
            skipped += 1
            continue

        timestamp       = datetime.now().strftime("%Y-%m-%d %H:%M")
        heuristic_pct   = _pct_to_float(row.get("error_heuristic", ""))

        # Skip AI call if heuristic says 0% — translation looks fine
        if heuristic_pct == 0.0:
            ws.update_cell(sheet_row, COL_ERROR_AI,     "NA")
            ws.update_cell(sheet_row, COL_ANALYSED_AT,  timestamp)
            print(f"  ⏭️  {product}/{slug} [{lang}]  Heuristic=0% → AI=NA  [{timestamp}]")
            updated += 1
            continue

        # AI error estimate
        try:
            error_pct, untranslated_samples = _ai_error_pct(original_path, translated_path, lang)
        except Exception as e:
            print(f"  ❌ AI check failed for {slug}/{lang}: {e}")
            failed += 1
            continue

        pct_str    = f"{error_pct:.0f}%"
        target_col = COL_ERROR_AI if status == STATUS_EMPTY else COL_ERROR_AFTER

        ws.update_cell(sheet_row, target_col,              pct_str)
        ws.update_cell(sheet_row, COL_UNTRANSLATED_SAMPLES, untranslated_samples)
        ws.update_cell(sheet_row, COL_ANALYSED_AT,          timestamp)
        print(f"  ✅ {product}/{slug} [{lang}]  {status} → Error%: {pct_str}  [{timestamp}]")
        updated += 1

    # ── 4. Sort sheet by Error% descending ─────────────────────────────────
    _sort_sheet_by_error_pct(ws)

    summary = (
        f"Domain '{domain}': {updated} rows updated, "
        f"{skipped} skipped, {failed} failed."
    )
    print(f"\n  {summary}")
    return summary


# ============================================================================
# SHEET HELPERS
# ============================================================================

def _read_worksheet(sheet_id: str) -> tuple:
    """
    Open the first worksheet and return (worksheet, list_of_row_dicts).

    Each row dict:
        sheet_row  – 1-indexed row number in the spreadsheet
        product    – col 2
        slug       – col 3
        url        – col 4
        author     – col 5
        lang       – col 6
        error_pct  – col 7
        status     – col 8
        error_after– col 9
    """
    try:
        gc = get_gc()
        if gc is None:
            return None, []
        ss = gc.open_by_key(sheet_id)
        ws = ss.get_worksheet(0)
        all_values = ws.get_all_values()
    except Exception as e:
        print(f"  ❌ Could not read sheet {sheet_id}: {e}")
        return None, []

    data_rows = []
    for idx, row in enumerate(all_values[DATA_ROW_OFFSET - 1:], start=DATA_ROW_OFFSET):
        # Pad short rows so index access is safe
        while len(row) < COL_TRANSLATED_URL:
            row.append("")
        data_rows.append({
            "sheet_row":            idx,
            "product":              row[COL_PRODUCT              - 1],
            "slug":                 row[COL_SLUG                 - 1],
            "url":                  row[COL_URL                  - 1],
            "author":               row[COL_AUTHOR               - 1],
            "lang":                 row[COL_LANG                 - 1],
            "error_heuristic":      row[COL_ERROR_HEURISTIC      - 1],
            "error_ai":             row[COL_ERROR_AI             - 1],
            "untranslated_samples": row[COL_UNTRANSLATED_SAMPLES - 1],
            "analysed_at":          row[COL_ANALYSED_AT          - 1],
            "status":               row[COL_STATUS               - 1],
            "error_after":          row[COL_ERROR_AFTER          - 1],
            "translated_url":       row[COL_TRANSLATED_URL       - 1],
        })

    return ws, data_rows


def _sort_sheet_by_error_pct(ws: gspread.Worksheet) -> None:
    """Re-write data rows sorted by Error% descending, leave header rows intact."""
    try:
        all_values = ws.get_all_values()
        # Rows 0 and 1 are the lang-support line and headers — keep them
        data = all_values[DATA_ROW_OFFSET - 1:]
        if not data:
            return

        data.sort(key=lambda r: _pct_to_float(r[COL_ERROR_AI - 1] if len(r) >= COL_ERROR_AI else ""), reverse=True)

        last_col_letter = chr(ord('A') + COL_TRANSLATED_URL - 1)
        last_row = DATA_ROW_OFFSET + len(data) - 1
        cell_range = f"A{DATA_ROW_OFFSET}:{last_col_letter}{last_row}"
        ws.update(cell_range, data)
        print(f"  📊 Sheet sorted by Error% descending.")
    except Exception as e:
        print(f"  ⚠️  Could not sort sheet: {e}")


def _pct_to_float(value: str) -> float:
    try:
        return float(value.replace('%', '').strip())
    except (ValueError, AttributeError):
        return 0.0


# ============================================================================
# AI QUALITY CHECK
# ============================================================================

def _ai_error_pct(original_file: Path, translated_file: Path, lang: str) -> tuple[float, str]:
    """
    Sample up to AI_SAMPLE_PARAGRAPHS paragraph pairs and ask the LLM:
      - what % of the translated text is still in English
      - which specific snippets were NOT translated

    Falls back to the heuristic if the LLM call fails.
    Returns (error_pct: float, untranslated_samples: str).
    """
    orig_body  = _strip_frontmatter(original_file.read_text(encoding="utf-8-sig"))
    trans_body = _strip_frontmatter(translated_file.read_text(encoding="utf-8-sig"))

    orig_paras  = [p.strip() for p in orig_body.split('\n\n')
                   if p.strip() and not lang_guard.should_skip_validation(p)]
    trans_paras = [p.strip() for p in trans_body.split('\n\n')
                   if p.strip() and not lang_guard.should_skip_validation(p)]

    pairs = list(zip(orig_paras, trans_paras))
    if not pairs:
        return 0.0, ""

    # Sample
    sample = random.sample(pairs, min(AI_SAMPLE_PARAGRAPHS, len(pairs)))
    sampled_text = "\n\n---\n\n".join(trans for _, trans in sample)
    lang_name = lang_guard.get_name(lang)

    prompt = f"""The following content was translated into {lang_name} (code: {lang}).
Review it and:
1. Count the total number of words in the TEXT (excluding code blocks, URLs, tags, categories, author names, abbreviations and file formats like HTML/REST/PDF, and brand/product names like Aspose.PDF/GroupDocs.Conversion/Conholdate.Total).
   Then count how many of those words are still in English and were NOT translated.
   Calculate: SCORE = (untranslated_words / total_words) * 100, rounded to nearest integer.
2. List the specific sentences or phrases (up to 5, one per line, one first 100 chars of each sentence) that were NOT translated.

Content sample:
{sampled_text}

Respond in EXACTLY this format (no extra text):
SCORE: <integer 0-100>
UNTRANSLATED:
<snippet 1>
<snippet 2>
...
"""

    try:
        response = _llm_client.chat.completions.create(
            model=config.PROFESSIONALIZE_LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a translation quality analyst. Follow the response format exactly."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,
        )
        raw = (response.choices[0].message.content or "").strip()
        print(f"  🤖  AI Response:\n{raw}\n")

        error_pct, samples = _parse_ai_response(raw)
        return error_pct, samples

    except Exception as e:
        print(f"    ⚠️  AI call failed ({e}), falling back to heuristic")
        return _heuristic_error_pct_simple(pairs), ""


def _parse_ai_response(raw: str) -> tuple[float, str]:
    """
    Parse the structured AI response into (error_pct, untranslated_samples_string).

    Expected format:
        SCORE: 45
        UNTRANSLATED:
        This text was not translated
        Another English snippet here
    """
    error_pct = 0.0
    samples   = ""

    score_match = re.search(r'SCORE:\s*(\d+)', raw, re.IGNORECASE)
    if score_match:
        error_pct = min(100.0, max(0.0, float(score_match.group(1))))

    untranslated_match = re.search(r'UNTRANSLATED:\s*\n(.*)', raw, re.IGNORECASE | re.DOTALL)
    if untranslated_match:
        lines = [l.strip() for l in untranslated_match.group(1).splitlines() if l.strip()]
        samples = " | ".join(lines[:5])   # pipe-separated, max 5, fits in a single cell

    return error_pct, samples


def _heuristic_error_pct_simple(pairs: list[tuple[str, str]]) -> tuple[float, str]:
    """Fallback: heuristic check on paragraph pairs. Returns (error_pct, samples)."""
    if not pairs:
        return 0.0, ""
    untranslated_pairs = [
        (orig, trans) for orig, trans in pairs
        if not lang_guard.appears_translated(orig, trans)
    ]
    error_pct = len(untranslated_pairs) / len(pairs) * 100.0
    samples   = " | ".join(trans[:80] for _, trans in untranslated_pairs[:5])
    return error_pct, samples


# ============================================================================
# FILE HELPERS
# ============================================================================

def _strip_frontmatter(text: str) -> str:
    m = re.match(r'^---\s*\n.*?\n---\s*\n(.*)', text, re.DOTALL)
    return m.group(1) if m else text


# ============================================================================
# AGENT
# ============================================================================

validator_agent = Agent(
    name="TranslationQualityValidator",
    instructions=(
        "You are a translation quality validator. "
        "For each domain the user specifies, call the validate_domain tool exactly once. "
        "If the user provided a limit, pass it as the 'limit' argument. "
        "After all domains are done, report a brief summary."
    ),
    tools=[validate_domain],
    model=config.PROFESSIONALIZE_LLM_MODEL,
)


# ============================================================================
# ENTRY POINT
# ============================================================================

async def _run(domains: list[str], api_key: str, limit: int):
    global _llm_client
    _llm_client = OpenAI(api_key=api_key, base_url=config.PROFESSIONALIZE_BASE_URL)

    set_tracing_disabled(True)

    async_client = AsyncOpenAI(api_key=api_key, base_url=config.PROFESSIONALIZE_BASE_URL)
    provider     = OpenAIProvider(openai_client=async_client, use_responses=False)
    run_cfg      = RunConfig(model_provider=provider)

    domain_list = ", ".join(domains)
    limit_note  = f" (limit {limit} rows per domain)" if limit > 0 else ""
    prompt      = (
        f"Validate translations for these blog domains{limit_note}: {domain_list}. "
        + (f"Use limit={limit}." if limit > 0 else "")
    )

    print(f"\n🚀 Quality Validator Agent starting ...")
    print(f"   Domains : {domain_list}")
    if limit:
        print(f"   Limit   : {limit} rows per domain")

    result = await Runner.run(validator_agent, input=prompt, run_config=run_cfg)
    print(f"\n✅ Validator Agent completed.")
    print(result.final_output)


def main():
    all_domains = list(config.domains_data.keys())

    parser = argparse.ArgumentParser(description="Translation Quality Validator")
    parser.add_argument("--domain", required=True,
                        help=f"Domain to validate or 'all'. Options: {', '.join(all_domains)}")
    parser.add_argument("--key",    required=False,
                        help="Professionalize LLM API key (or set PROFESSIONALIZE_API_KEY env var)")
    parser.add_argument("--limit",  type=int, default=0,
                        help="Max rows to validate per domain (0 = no limit)")
    args = parser.parse_args()

    api_key = (args.key or os.getenv("PROFESSIONALIZE_API_KEY", "")).strip()
    if not api_key:
        print("[ERROR] API key is required. Use --key or set PROFESSIONALIZE_API_KEY.")
        sys.exit(1)

    passed = args.domain.strip().lower()
    if passed == "all":
        selected = all_domains
    elif passed in all_domains:
        selected = [passed]
    else:
        print(f"[ERROR] Unknown domain: '{passed}'")
        print(f"Valid: all, {', '.join(all_domains)}")
        sys.exit(1)

    asyncio.run(_run(selected, api_key, args.limit))


if __name__ == "__main__":
    main()
