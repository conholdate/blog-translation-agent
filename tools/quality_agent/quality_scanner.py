"""
Translation Quality Scanner  (Phase 1)
=======================================
Traverses all local blog repos, finds every translated index.{lang}.md file,
computes a heuristic Error% for each, and writes results to the per-domain
Google Sheet.

Usage:
    python quality_scanner.py --domain blog.aspose.com
    python quality_scanner.py --domain all
    python quality_scanner.py --domain blog.groupdocs.com --key YOUR_API_KEY
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'translation_agent'))

import re
import yaml
import argparse
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

import config
import lang_guard
import gspread
from io_google_spreadsheet import write_to_google_spreadsheet, get_gc
from openai import AsyncOpenAI
from agents import Agent, Runner, function_tool, set_tracing_disabled, RunConfig
from agents.models.openai_provider import OpenAIProvider


# ============================================================================
# SHEET CONFIGURATION
# ============================================================================

QUALITY_SHEET_IDS: dict[str, str] = {
    config.DOMAIN_ASPOSE_COM:       "1BuiSIqBKWCpcGoiDsUz1oJPHj0PvIQpmoTrGUv8vv8Q",
    config.DOMAIN_ASPOSE_CLOUD:     "1hhd3KgLsW0XplVsnE-ctTgpbdcRw8XfPAGxgDzkzufk",
    config.DOMAIN_GROUPDOCS_COM:    "1Qr6pq438SJBvop9NWCjF5ALrjgX5UcjLhgZbrEZn78I",
    config.DOMAIN_GROUPDOCS_CLOUD:  "1NtulRvHM8KDfK_OayKz7WeHtom-eyZlV8nmwr2OXypE",
    config.DOMAIN_CONHOLDATE_COM:   "17rNwX6IdrB6QIMMcRS3haqELojlCHYDguP8zxCIkUUE",
    config.DOMAIN_CONHOLDATE_CLOUD: "19sS8roVeISV4BbEhkRx5lY2FYUjZeY6JSBofzQdYkSs",
}

SHEET_HEADERS = [
    "Domain", "Product", "Blog Post Directory", "Blog Post URL",
    "Author", "Page Lang", "Error% Heuristic", "Error% AI (LLM)", "Untranslated Samples",
    "Analysed At", "Status", "Error% after Fix", "Translated Page URL",
]

STATUS_EMPTY = ""

# Matches index.ar.md, index.zh-hant.md, etc. — but NOT index.md
_LANG_FILE_RE = re.compile(r'^index\.(.+)\.md$')


# ============================================================================
# TOOL
# ============================================================================

@function_tool
def scan_domain(domain: str) -> str:
    """
    Walk the local repo for the given blog domain, discover every translated
    index.{lang}.md file, compute a heuristic Error% for each, and write all
    rows to the domain's Google Sheet sorted by Error% descending.

    Returns a short summary string.
    """
    domain = domain.strip().lower()

    if domain not in config.domains_data:
        return f"ERROR: Unknown domain '{domain}'. Valid: {list(config.domains_data)}"

    sheet_id = QUALITY_SHEET_IDS.get(domain)
    if not sheet_id:
        return f"ERROR: No quality sheet ID configured for '{domain}'"

    repo_path = config.domains_data[domain][config.KEY_LOCAL_GITHUB_REPO]
    if not os.path.exists(repo_path):
        return f"ERROR: Repo path not found: {repo_path}"

    print(f"\n{'='*60}")
    print(f"  Scanning: {domain}")
    print(f"  Repo:     {repo_path}")
    print(f"{'='*60}")

    rows: list[list] = []

    # Repo structure: {repo_path}/{product}/{slug}/index.md + index.{lang}.md
    for product_dir in sorted(Path(repo_path).iterdir()):
        if not product_dir.is_dir():
            continue
        product = product_dir.name

        for slug_dir in sorted(product_dir.iterdir()):
            if not slug_dir.is_dir():
                continue
            slug = slug_dir.name

            original_file = slug_dir / "index.md"
            if not original_file.exists():
                continue

            url, author = _parse_original_metadata(original_file)

            for md_file in sorted(slug_dir.iterdir()):
                m = _LANG_FILE_RE.match(md_file.name)
                if not m:
                    continue
                lang = m.group(1)
                if not lang_guard.is_valid(lang):
                    continue

                print(f"  --- > ORIGINAL PATH ---\n{original_file}\n")
                print(f"  --- > MD File PATH ---\n{md_file}\n")

                translated_url  = _build_translated_url(domain, lang, url)
                error_pct       = _heuristic_error_pct(original_file, md_file,lang, translated_url)
                rows.append([
                    domain,
                    product,
                    slug,
                    url,
                    author,
                    lang,
                    f"{error_pct:.0f}%",    # Error% Heuristic      (col 7)
                    "",                     # Error% AI (LLM)       (col 8)  — filled by validator
                    "",                     # Untranslated Samples  (col 9)  — filled by validator
                    "",                     # Analysed At           (col 10) — filled by validator
                    STATUS_EMPTY,           # Status                (col 11)
                    "",                     # Error% after Fix      (col 12) — filled after human fix
                    translated_url,         # Translated Page URL   (col 13)
                ])

    # Sort by Error% descending so highest-error pages appear at the top
    rows.sort(key=lambda r: _pct_to_float(r[6]), reverse=True)

    print(f"  Found {len(rows)} translated files.")

    valid_langs = config.domains_data[domain][config.KEY_SUPPORTED_LANGS]
    worksheet_name = datetime.now().strftime("%Y-%m-%d")

    sheet_url = write_to_google_spreadsheet(
        spreadsheet_id=sheet_id,
        valid_extensions=valid_langs,
        column_headers=SHEET_HEADERS,
        data_to_write=rows,
        worksheet_name=worksheet_name,
    )

    summary = (
        f"Domain '{domain}': {len(rows)} translated files written to sheet "
        f"(tab: {worksheet_name}). URL: {sheet_url}"
    )
    print(f"  ✅ {summary}")
    return summary


# ============================================================================
# HELPERS
# ============================================================================

def _parse_original_metadata(original_file: Path) -> tuple[str, str]:
    """Return (url, author) from the English index.md frontmatter."""
    try:
        text = original_file.read_text(encoding="utf-8-sig")
        m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
        if not m:
            return "", ""
        fm = yaml.safe_load(m.group(1)) or {}
        url = str(fm.get("url", ""))
        raw_author = fm.get("authors") or fm.get("author") or ""
        if isinstance(raw_author, list):
            author = raw_author[0] if raw_author else ""
        else:
            author = str(raw_author)
        return url, author
    except Exception:
        return "", ""


def _build_translated_url(domain: str, lang: str, post_url: str) -> str:
    """
    Construct the full URL of the translated page.

    Example:
        domain   = "blog.aspose.com"
        lang     = "pt"
        post_url = "/3d/build-an-obj-to-u3d-converter-in-csharp/"
        →  "blog.aspose.com/pt/3d/build-an-obj-to-u3d-converter-in-csharp/"
    """
    if not post_url:
        return ""
    # Ensure post_url starts with exactly one slash
    url = "/" + post_url.lstrip("/")
    return f"https://{domain}/{lang}{url}"


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter, return body only."""
    m = re.match(r'^---\s*\n.*?\n---\s*\n(.*)', text, re.DOTALL)
    return m.group(1) if m else text


def _heuristic_error_pct(original_file: Path, translated_file: Path, lang: str = "", translated_url: str = "") -> float:
    """
    Estimate the fraction of content paragraphs that appear untranslated.
    Returns 0.0–100.0.
    """
    try:
        print(f"  ---> ORIGINAL PATH ---\n{original_file}\n")
        print(f"  ---> TRANSLATED PATH ---\n{translated_file}")

        orig_body  = _strip_frontmatter(original_file.read_text(encoding="utf-8-sig"))
        trans_body = _strip_frontmatter(translated_file.read_text(encoding="utf-8-sig"))

        print(f"  ---> ORIGINAL BODY ---\n{orig_body[:50]}")
        print(f"  ---> TRANSLATED BODY ---\n{trans_body[:50]}")

        orig_paras  = [p.strip() for p in orig_body.split('\n\n')  if p.strip()]
        trans_paras = [p.strip() for p in trans_body.split('\n\n') if p.strip()]

        pairs = list(zip(orig_paras, trans_paras))
        if not pairs:
            return 0.0

        checked = untranslated = 0
        for orig_p, trans_p in pairs:
            if lang_guard.should_skip_validation(orig_p):
                continue
            checked += 1
            if not lang_guard.appears_translated(orig_p, trans_p):
                untranslated += 1

        if checked and untranslated == checked:
            print(f"\n{'='*60}")
            print(f"  ⚠️  100% untranslated [{lang}]: {translated_file}")
            print(f"  --- TRANSLATED URL ---:{translated_url}\n")
            print(f"  --- ORIGINAL PATH ---\n{original_file}\n")
            print(f"  --- ORIGINAL BODY ---\n{orig_body}")
            print(f"  --- TRANSLATED PATH ---\n{translated_file}")
            print(f"  --- TRANSLATED BODY ---\n{trans_body}")
            print(f"{'='*60}\n")

        return (untranslated / checked * 100.0) if checked else 0.0

    except Exception:
        return 0.0


def _pct_to_float(value: str) -> float:
    """Parse '60%' → 60.0, handles blank/malformed values."""
    try:
        return float(value.replace('%', '').strip())
    except (ValueError, AttributeError):
        return 0.0


# ============================================================================
# AGENT
# ============================================================================

scanner_agent = Agent(
    name="TranslationQualityScanner",
    instructions=(
        "You are a translation quality scanner. "
        "For each domain the user specifies, call the scan_domain tool exactly once. "
        "After all scans are done, report a brief summary of results."
    ),
    tools=[scan_domain],
    model=config.PROFESSIONALIZE_LLM_MODEL,
)


# ============================================================================
# ENTRY POINT
# ============================================================================

async def _run(domains: list[str], api_key: str):
    set_tracing_disabled(True)

    async_client = AsyncOpenAI(api_key=api_key, base_url=config.PROFESSIONALIZE_BASE_URL)
    provider     = OpenAIProvider(openai_client=async_client, use_responses=False)
    run_cfg      = RunConfig(model_provider=provider)

    domain_list = ", ".join(domains)
    print(f"\n🚀 Quality Scanner Agent starting ...")
    print(f"   Domains : {domain_list}")

    result = await Runner.run(
        scanner_agent,
        input=f"Scan the following blog domains and write results to their quality sheets: {domain_list}",
        run_config=run_cfg,
    )
    print(f"\n✅ Scanner Agent completed.")
    print(result.final_output)


def main():
    all_domains = list(config.domains_data.keys())

    parser = argparse.ArgumentParser(description="Translation Quality Scanner")
    parser.add_argument("--domain",  required=True,
                        help=f"Domain to scan or 'all'. Options: {', '.join(all_domains)}")
    parser.add_argument("--key",     required=False,
                        help="Professionalize LLM API key (or set PROFESSIONALIZE_API_KEY env var)")
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

    asyncio.run(_run(selected, api_key))


if __name__ == "__main__":
    main()
