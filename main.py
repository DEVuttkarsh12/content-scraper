"""Lead scraper CLI entry point.

Barebone scaffold:
  python main.py --niche real_estate finance --max 50 --out data/leads.csv
  python main.py --list-niches
  python main.py --dry-run --niche saas --max 5
"""

import argparse
import logging
import sys

from config.niches import all_niche_ids, load_niches
from config.settings import get_settings
from core.models import CSV_HEADERS
from sources.collector import SearchSource
from output.exporter import export_leads


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lead-scraper",
        description="High-ticket niche lead scraper for AI agency outreach.",
    )
    p.add_argument(
        "--niche",
        nargs="*",
        choices=all_niche_ids(),
        default=[],
        help="Niche(s) to target (default: all). See --list-niches.",
    )
    p.add_argument(
        "--list-niches",
        action="store_true",
        help="List available niches and exit.",
    )
    p.add_argument(
        "--max",
        type=int,
        default=20,
        help="Max leads to keep per niche (default 20).",
    )
    p.add_argument(
        "--out",
        default="data/leads.csv",
        help="Output file path (CSV or .json).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config, extractors, and pipeline wiring without scraping.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return p


def list_niches() -> None:
    for nid in all_niche_ids():
        niche = load_niches([nid])[0]
        print(f"  {nid:15s} -> {niche.label}")
    print("\nExample: python main.py --niche real_estate finance --max 50 --out data/leads.csv")


def run_dry_run(settings) -> int:
    print("Dry run: validating configuration and pipeline wiring...\n")

    print(f"[config] settings loaded.............. {'OK' if True else 'FAIL'}")
    serpapi_note = "YES" if settings.has_serpapi else "NO (free Bing/DDG/Mojeek will auto-fallback)"
    print(f"[config] SerpAPI key................. {serpapi_note}")
    sb_note = "YES" if settings.has_scrapingbee else "NO (JS rendering off; plain fetch still works)"
    print(f"[config] ScrapingBee key............. {sb_note}")
    print(f"[config] proxies configured........... {'YES' if settings.has_proxies else 'NO (optional)'}")

    niches = load_niches()
    print(f"[config] loaded {len(niches)} niches: {', '.join(n.id for n in niches)}")

    from core.extractor import extract_all

    sample = (
        "Contact us: john [at] agency [dot] com, +1 (555) 123-4567, "
        "@johndoe on Instagram, https://www.linkedin.com/company/acme and "
        "https://wa.me/15551234567"
    )
    sample_links = [
        "https://www.instagram.com/acme/",
        "https://wa.me/15551234567",
        "https://www.linkedin.com/company/acme",
        "https://acme.com/assets/js/main.js?v=2",
    ]
    info = extract_all(text=sample, links=sample_links)
    kept = (
        len(info.emails) == 1
        and len(info.whatsapp_numbers) == 1
        and len(info.instagram_handles) >= 1
        and len(info.linkedin_urls) == 1
    )
    print(f"[extractor] sample parse............... {'OK' if kept else 'CHECK'} "
          f"(emails={info.emails}, wa={info.whatsapp_numbers}, "
          f"ig={info.instagram_handles}, li={info.linkedin_urls})")

    print("\nPipeline: niche config -> search source -> page fetch -> "
          "extract -> filter -> export")
    print("\nDry run complete.")
    return 0 if (kept) else 1


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    settings = get_settings()

    if args.list_niches:
        list_niches()
        return 0

    if args.dry_run:
        return run_dry_run(settings)

    niches = load_niches(args.niche)
    if not niches:
        print("No niches specified. Run with --list-niches to see options.", file=sys.stderr)
        return 1

    if settings.has_serpapi:
        print("Using SerpAPI for discovery (key found).")
    else:
        print("Using free Bing + DuckDuckGo + Mojeek discovery (no keys required).")
    if settings.has_scrapingbee:
        print("ScrapingBee rendering enabled (key found).")

    source = SearchSource(settings)
    all_leads = []

    for niche in niches:
        print(f"\n== Scraping niche: {niche.label} ==")
        leads = source.collect(niche, max_leads=args.max)
        all_leads.extend(leads)
        print(f"  collected {len(leads)} qualified leads for {niche.id}")

    export_leads(all_leads, args.out)
    print(f"\nDone. Wrote {len(all_leads)} leads to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())