"""
Ask for a retranslation: add an ISSUE row to a blog's translation queue (the
domain tab of the consolidated scan sheet). For people and for other agents —
agents in Python can call io_google_spreadsheet.add_to_queue() directly.

Languages an open row of the post already retranslates (ISSUE or OUTDATED) are
skipped. The next scan checks the row (post folder exists, languages supported)
and marks it 'invalid' with the reason in Notes if not. Step 2 picks it up by
Priority (default Normal) and closes it once its languages are retranslated.

    python tools/translation_agent/queue_add.py --domain blog.aspose.com \\
        --post pdf/2024-05-01-convert-pdf-to-word --langs "fr, de" \\
        --reason "Tables left in English" [--source quality-agent] [--priority Urgent]

    --langs omitted = every language of the blog, written out in the row.  --dry-run shows the row without writing.
"""

import argparse
import sys

import config
import io_google_spreadsheet as gs


def parse_post(value: str):
    """'product/post-folder' (a full content path or URL-ish value is trimmed to its last two parts)."""
    parts = [p for p in value.strip().strip("/").split("/") if p]
    if len(parts) < 2:
        raise argparse.ArgumentTypeError("--post must be <product>/<post folder>, e.g. pdf/2024-05-01-my-post")
    return parts[-2], parts[-1]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Add a retranslation request (ISSUE row) to the translation queue")
    p.add_argument("--domain", required=True, choices=sorted(config.domains_data))
    p.add_argument("--post", required=True, type=parse_post, help="<product>/<post folder>")
    p.add_argument("--langs", default="", help="comma-separated language codes (default: all)")
    p.add_argument("--reason", required=True,
                   help="what is wrong — a short headline: Notes line 1 (line 2: 'Requested by <source>')")
    p.add_argument("--source", default=config.SOURCE_MANUAL, help="who asks: Manual (default) or an agent's name")
    p.add_argument("--priority", choices=list(config.PRIORITY_RANK), default=None,
                   help=f"default: {config.DEFAULT_PRIORITY[config.ISSUE_ISSUE]}")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    product, slug = args.post
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    supported = [l for l in config.domains_data[args.domain][config.KEY_SUPPORTED_LANGS].split("|") if l]
    bad = [l for l in langs if l not in supported]
    if bad:
        print(f"❌ Not a language of {args.domain}: {', '.join(bad)} (supported: {', '.join(supported)})")
        return 2

    print(f"{args.domain} · {product}/{slug} · ISSUE · {', '.join(langs or supported)} · "
          f"{args.priority or config.DEFAULT_PRIORITY[config.ISSUE_ISSUE]} · {args.source} · {args.reason}")
    if args.dry_run:
        print("Dry run — nothing written.")
        return 0
    added = gs.add_to_queue(args.domain, product, slug, langs, args.reason,
                            source=args.source, priority=args.priority)
    return 1 if added is None else 0


if __name__ == "__main__":
    sys.exit(main())
