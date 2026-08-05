"""
Translation Quality Retranslator  (Phase 3)
============================================
Reads the quality sheet, finds rows where the LLM's AI Decision is
RETRANSLATE and Status is blank, then force-retranslates those files using
the existing TranslationOrchestrator from translator.py.

After retranslation each row's Status is set to "Fixed" so the validator
(Phase 2) will re-check it on its next run.

Usage:
    python quality_retranslator.py --domain blog.aspose.com --key YOUR_KEY
    python quality_retranslator.py --domain all --key YOUR_KEY
    python quality_retranslator.py --domain blog.aspose.com --limit 10 --key YOUR_KEY
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'translation_agent'))

import argparse
import asyncio
from pathlib import Path
from datetime import datetime

import config
from io_google_spreadsheet import get_gc
from translator import TranslationOrchestrator
from agents import Agent, Runner, function_tool, set_tracing_disabled, RunConfig
from agents.models.openai_provider import OpenAIProvider
from openai import AsyncOpenAI


# ============================================================================
# SHEET CONFIGURATION  (mirrors quality_scanner.py / quality_validator.py)
# ============================================================================

QUALITY_SHEET_IDS: dict[str, str] = {
    config.DOMAIN_ASPOSE_COM:       config.QUALITY_SHEET_ID_ASPOSE_COM,
    config.DOMAIN_ASPOSE_CLOUD:     config.QUALITY_SHEET_ID_ASPOSE_CLOUD,
    config.DOMAIN_GROUPDOCS_COM:    config.QUALITY_SHEET_ID_GROUPDOCS_COM,
    config.DOMAIN_GROUPDOCS_CLOUD:  config.QUALITY_SHEET_ID_GROUPDOCS_CLOUD,
    config.DOMAIN_CONHOLDATE_COM:   config.QUALITY_SHEET_ID_CONHOLDATE_COM,
    config.DOMAIN_CONHOLDATE_CLOUD: config.QUALITY_SHEET_ID_CONHOLDATE_CLOUD,
}

# Column positions (1-indexed) — must stay in sync with quality_scanner.py SHEET_HEADERS
COL_DOMAIN              = 1
COL_PRODUCT             = 2
COL_SLUG                = 3
COL_URL                 = 4
COL_AUTHOR              = 5
COL_LANG                = 6
COL_ERROR_HEURISTIC     = 7
COL_ERROR_AI            = 8
COL_UNTRANSLATED_SAMPLES= 9
COL_ANALYSED_AT         = 10
COL_STATUS              = 11
COL_ERROR_AFTER         = 12
COL_TRANSLATED_URL      = 13
COL_AI_DECISION         = 14
COL_DECISION_REASON     = 15  # not read here, kept for column-layout sync with quality_scanner.py

DATA_ROW_OFFSET = 3     # rows 1–2 are lang-support line + headers

STATUS_EMPTY  = ""
STATUS_FIXED  = "Fixed"

# Module-level orchestrator — initialised once in _run() and reused by the tool
_orchestrator: TranslationOrchestrator = None


# ============================================================================
# TOOL
# ============================================================================

@function_tool
def retranslate_domain(domain: str, limit: int = 0) -> str:
    """
    For the given blog domain:
      1. Read the quality sheet.
      2. Filter rows: AI Decision == RETRANSLATE AND Status is blank.
      3. For each row: force-retranslate index.{lang}.md using TranslationOrchestrator.
      4. Update the sheet row: Status = "Fixed", Analysed At = now.

    Args:
        domain: e.g. 'blog.aspose.com'
        limit:  Max rows to retranslate in this run (0 = no limit)

    Returns a summary string.
    """
    domain = domain.strip().lower()

    if domain not in config.domains_data:
        return f"ERROR: Unknown domain '{domain}'"

    sheet_id  = QUALITY_SHEET_IDS.get(domain)
    repo_path = config.domains_data[domain][config.KEY_LOCAL_GITHUB_REPO]

    print(f"\n{'='*60}")
    print(f"  Retranslating: {domain}  (AI Decision = RETRANSLATE)")
    print(f"{'='*60}")

    # ── 1. Read sheet ──────────────────────────────────────────────────────
    ws, data_rows = _read_worksheet(sheet_id)
    if ws is None:
        return f"ERROR: Could not open sheet for '{domain}'"

    print(f"  Sheet has {len(data_rows)} data rows.")

    # ── 2. Filter rows ─────────────────────────────────────────────────────
    to_process = [
        r for r in data_rows
        if r["status"] == STATUS_EMPTY
        and r["ai_decision"].strip().upper() == "RETRANSLATE"
    ]

    if limit > 0:
        to_process = to_process[:limit]

    print(f"  Rows to retranslate: {len(to_process)}"
          + (f" (limit={limit})" if limit > 0 else ""))

    retranslated = skipped = failed = 0

    # ── 3. Retranslate each row ────────────────────────────────────────────
    for row in to_process:
        sheet_row = row["sheet_row"]
        product   = row["product"]
        slug      = row["slug"]
        lang      = row["lang"]

        index_md = Path(repo_path) / product / slug / "index.md"

        if not index_md.exists():
            print(f"  ⚠️  index.md not found for {product}/{slug} — skipping")
            skipped += 1
            continue

        print(f"\n  🔄 Retranslating: {product}/{slug} [{lang}]  "
              f"(AI Error%: {row['error_ai']})")

        try:
            # translate_file() always writes the output file — no skip-if-exists guard
            _orchestrator.translate_file(str(index_md), lang, domain)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            ws.update_cell(sheet_row, COL_STATUS,      STATUS_FIXED)
            ws.update_cell(sheet_row, COL_ANALYSED_AT, timestamp)

            print(f"  ✅ Done — Status set to '{STATUS_FIXED}'  [{timestamp}]")
            retranslated += 1

        except Exception as e:
            print(f"  ❌ Failed: {product}/{slug} [{lang}]: {e}")
            failed += 1
            continue

    summary = (
        f"Domain '{domain}': {retranslated} retranslated, "
        f"{skipped} skipped, {failed} failed."
    )
    print(f"\n  {summary}")
    return summary


# ============================================================================
# SHEET HELPERS
# ============================================================================

def _read_worksheet(sheet_id: str) -> tuple:
    """Open the first worksheet and return (worksheet, list_of_row_dicts)."""
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
        while len(row) < COL_AI_DECISION:
            row.append("")
        data_rows.append({
            "sheet_row":   idx,
            "product":     row[COL_PRODUCT      - 1],
            "slug":        row[COL_SLUG         - 1],
            "lang":        row[COL_LANG         - 1],
            "error_ai":    row[COL_ERROR_AI     - 1],
            "status":      row[COL_STATUS       - 1],
            "ai_decision": row[COL_AI_DECISION  - 1],
        })

    return ws, data_rows


# ============================================================================
# AGENT
# ============================================================================

retranslator_agent = Agent(
    name="TranslationQualityRetranslator",
    instructions=(
        "You are a translation quality retranslator. "
        "For each domain the user specifies, call the retranslate_domain tool exactly once. "
        "Pass the limit argument if the user provided one. "
        "After all domains are done, report a brief summary."
    ),
    tools=[retranslate_domain],
    model=config.PROFESSIONALIZE_LLM_MODEL,
)


# ============================================================================
# ENTRY POINT
# ============================================================================

async def _run(domains: list[str], api_key: str, limit: int):
    global _orchestrator
    _orchestrator = TranslationOrchestrator(api_key=api_key)

    set_tracing_disabled(True)

    async_client = AsyncOpenAI(api_key=api_key, base_url=config.PROFESSIONALIZE_BASE_URL)
    provider     = OpenAIProvider(openai_client=async_client, use_responses=False)
    run_cfg      = RunConfig(model_provider=provider)

    domain_list  = ", ".join(domains)
    limit_note   = f" (limit {limit} per domain)" if limit > 0 else ""
    prompt       = (
        f"Retranslate poor-quality translations for these blog domains{limit_note}: {domain_list}."
        + (f" Use limit={limit}." if limit > 0 else "")
    )

    print(f"\n🚀 Quality Retranslator Agent starting ...")
    print(f"   Domains   : {domain_list}")
    print(f"   Selection : AI Decision = RETRANSLATE")
    if limit:
        print(f"   Limit     : {limit} rows per domain")

    result = await Runner.run(retranslator_agent, input=prompt, run_config=run_cfg)
    print(f"\n✅ Retranslator Agent completed.")
    print(result.final_output)


def main():
    all_domains = list(config.domains_data.keys())

    parser = argparse.ArgumentParser(description="Translation Quality Retranslator")
    parser.add_argument("--domain",    required=True,
                        help=f"Domain to process or 'all'. Options: {', '.join(all_domains)}")
    parser.add_argument("--key",       required=False,
                        help="Professionalize LLM API key (or set PROFESSIONALIZE_API_KEY env var)")
    parser.add_argument("--limit",     type=int, default=0,
                        help="Max rows to retranslate per domain (0 = no limit)")
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
