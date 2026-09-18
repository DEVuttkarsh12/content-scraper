"""Lead scraper CLI entry point.

Barebone scaffold:
  python main.py --niche real_estate finance --max 50 --out data/leads.csv
  python main.py --seeds data/seeds.txt --niche real_estate
  python main.py --list-niches
  python main.py --dry-run --niche saas --max 5
  python main.py --niche real_estate --out data/leads.json       # JSON out
  python main.py --niche real_estate --no-enrich                 # skip MX checks
  python main.py --niche finance --fresh                         # start over, ignore prior output
"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.niches import all_niche_ids, load_niches
from config.settings import get_settings
from core.models import CSV_HEADERS
from sources.collector import SearchSource
from output.exporter import dedupe_leads, export_leads, load_leads

logger = logging.getLogger("main")


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
        "--seeds",
        metavar="FILE",
        help="Optional file of business URLs to scrape directly (one URL per "
             "line, # comments/blank lines ignored). Bypasses search engines.",
    )
    p.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip email MX validation and social (IG/LinkedIn) discovery. "
             "Faster, but leads keep unverified emails and fewer social links.",
    )
    p.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore the existing output file: do not merge with prior "
             "leads and do not skip domains that were already scraped.",
    )
    p.add_argument(
        "--no-merge",
        action="store_true",
        help="Write only this run's leads to --out (overwrite file). "
             "Default is to merge into the existing file.",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of niches to scrape in parallel "
             "(default: MAX_CONCURRENT_REQUESTS, i.e. 4).",
    )
    p.add_argument(
        "--emails-only",
        action="store_true",
        help="Keep only leads that have at least one email. Best for outreach.",
    )
    p.add_argument(
        "--min-quality",
        type=int,
        default=0,
        help="Drop leads with a quality score below N (0-100). "
             "See quality_score per lead. Default 0 = keep all.",
    )
    p.add_argument(
        "--max-quality",
        type=int,
        default=100,
        help="Drop leads with a quality score above N (0-100). "
             "Use together with --min-quality to isolate one band "
             "(e.g. high 60-100, medium 30-59, low 0-29).",
    )
    p.add_argument(
        "--json",
        dest="json_out",
        action="store_true",
        help="Force JSON output regardless of --out extension.",
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


def load_seed_urls(path: str) -> list:
    urls = []
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    return urls


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


def _collect_niche(args, settings, niche, prior_domains):
    """Scrape a single niche in its own worker thread (own session)."""
    source = SearchSource(settings, enrich=not args.no_enrich and settings.verify_emails)
    if args.seeds:
        lead_list = source.collect_seeds(niche, args.seed_urls, max_leads=args.max)
    else:
        skip = None if args.fresh else prior_domains
        lead_list = source.collect(niche, max_leads=args.max, skip_domains=skip)
    logger.info("collected %d qualified leads for %s", len(lead_list), niche.id)
    return lead_list


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

    # Load any prior output so we can merge and skip already-scraped domains.
    prior_leads = [] if (args.fresh or args.no_merge) else load_leads(args.out)
    prior_domains = {
        (lead.website or "").lower().removeprefix("http://").removeprefix("https://")
        .removeprefix("www.").split("/")[0]
        for lead in prior_leads if lead.website
    }
    if prior_leads:
        print(f"Loaded {len(prior_leads)} prior leads from {args.out} "
              f"({len(prior_domains)} unique domains)."
              + ("" if args.seeds else "  Skipping those domains in search mode."))

    if args.seeds:
        args.seed_urls = load_seed_urls(args.seeds)
        if not args.seed_urls:
            print(f"No URLs found in {args.seeds}", file=sys.stderr)
            return 1
        print(f"Loaded {len(args.seed_urls)} seed URLs from {args.seeds}")

    workers = max(1, args.workers or settings.max_concurrent_requests)
    all_leads = []
    if len(niches) > 1 and workers > 1:
        print(f"\nScraping {len(niches)} niches with {workers} parallel workers...")
        with ThreadPoolExecutor(max_workers=min(workers, len(niches))) as pool:
            futures = {
                pool.submit(_collect_niche, args, settings, niche, prior_domains): niche.id
                for niche in niches
            }
            for future in as_completed(futures):
                nid = futures[future]
                try:
                    all_leads.extend(future.result())
                except Exception as exc:  # noqa: BLE001
                    logger.error("Niche %s failed: %s", nid, exc)
    else:
        for niche in niches:
            print(f"\n== Scraping niche: {niche.label} ==")
            leads = _collect_niche(args, settings, niche, prior_domains)
            all_leads.extend(leads)
            print(f"  collected {len(leads)} qualified leads for {niche.id}")

    all_leads = dedupe_leads(all_leads)

    # User quality filters.
    if args.emails_only:
        all_leads = [l for l in all_leads if l.emails]
        print(f"  --emails-only: kept {len(all_leads)} leads with emails.")
    if args.min_quality > 0:
        before = len(all_leads)
        all_leads = [l for l in all_leads if l.quality_score >= args.min_quality]
        print(f"  --min-quality {args.min_quality}: kept {len(all_leads)} of {before} leads.")
    if args.max_quality < 100:
        before = len(all_leads)
        all_leads = [l for l in all_leads if l.quality_score <= args.max_quality]
        print(f"  --max-quality {args.max_quality}: kept {len(all_leads)} of {before} leads.")

    out_path = args.out
    if args.json_out and not out_path.endswith(".json"):
        out_path = out_path.rsplit(".", 1)[0] + ".json" if "." in out_path.rsplit("/", 1)[-1] else out_path + ".json"
    export_leads(all_leads, out_path, merge=not args.no_merge)
    print(f"\nDone. Wrote {len(all_leads)} new leads to {out_path}")
    if not args.no_merge and (args.fresh is False) and prior_leads:
        print(f"  {len(prior_leads)} prior leads were preserved/merged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())