# Custom Lead Scraper

High-ticket lead scraper for an AI agency offering premium websites, custom
software, AI automation, and CRM builds. Discovers businesses in target
 niches and harvests outreach contact points: **emails, WhatsApp numbers,
Instagram handles, LinkedIn profiles, and phone numbers**.

## Niches (high-ticket, pre-configured)

| Niche            | Targets                                   |
| ---------------- | ----------------------------------------- |
| `real_estate`    | Real estate & property development        |
| `finance`        | Wealth management, financial advisory     |
| `healthcare`     | Private clinics, cosmetic, med-spa        |
| `legal`          | Corporate law firms, attorneys            |
| `saas`           | B2B SaaS & software companies             |
| `ecommerce`      | D2C brands & online stores                |
| `coaching`       | High-ticket coaching & consulting         |
| `automotive`     | Luxury dealers, exotic car dealerships    |
| `hospitality`    | Luxury hotels, resorts, fine dining       |

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # then paste your keys
python main.py --dry-run    # validate the pipeline without scraping
python main.py --list-niches
```

### Tests

```bash
pip install -r requirements-dev.txt
python -m pytest            # 150+ offline unit tests (no keys, no network)
```

The suite covers the extractors (emails, Cloudflare decoding, phones,
WhatsApp/Instagram/LinkedIn), filters and deny lists, the lead model and
quality scoring, CSV/JSON round-trips and merge/dedupe, dashboard log parsing,
and the pure helper functions of the search/collector/social modules. It
catches regressions without ever hitting the network.

### Go live (no payment needed)

```bash
python main.py --niche real_estate finance --max 30 --out data/leads.csv
python main.py --niche saas --max 100 --out data/leads.json
python main.py                      # all niches, default limits
```

### Zero-search-discovery mode (guaranteed, works everywhere)

If the free engines are bot-checking your IP, still scrape today using your
own shortlist of business websites:

```bash
python main.py --seeds data/seeds.example.txt --niche real_estate --max 10 --out data/leads.csv
```

`--seeds` takes a file with one URL per line (`#` comments and blank lines are
ignored), runs every URL through the exact same fetch → filter → extract →
export pipeline, and **bypasses search engines completely**. Pair it with any
method of finding websites (Google Maps, directories, your own research).

### CLI flags

| Flag              | Purpose                                              |
| ----------------- | ---------------------------------------------------- |
| `--niche X Y`     | Target one or more niches (default: all)             |
| `--max N`         | Max leads per niche (default: 20)                    |
| `--out FILE`      | Output path — `.csv` or `.json` (default: leads.csv) |
| `--json`          | Force JSON output regardless of `--out` extension    |
| `--seeds FILE`    | Scrape a URL list directly, bypass search engines    |
| `--no-enrich`     | Skip email MX validation + social discovery (faster) |
| `--workers N`     | Scrape N niches in parallel (default: 4)             |
| `--emails-only`   | Keep only leads that have at least one email         |
| `--min-quality N` | Drop leads scoring below N (0-100)                   |
| `--fresh`         | Ignore existing output — no merge, no domain skip    |
| `--no-merge`      | Overwrite `--out` with only this run's leads         |
| `--verbose`       | Debug logging                                        |
| `--dry-run`       | Validate config/extractors without scraping          |
| `--list-niches`   | Print available niches and exit                      |

Discovery works **out of the box with zero API keys** using a failover chain
of free engines — Bing-RSS → DuckDuckGo → Bing → Mojeek → Brave → Ecosia →
SearXNG pool — automatically skipping any engine that bot-checks your IP.
SerpAPI and ScrapingBee are optional upgrades auto-detected when their keys
are present.

## Zero-budget email harvesting tricks

- **Cloudflare email shields** are decoded (`data-cfemail`) — many sites hide
  their email behind Cloudflare and plain scrapers get nothing.
- **Encoded emails** (`info%40domain%2Ecom`) are unquoted.
- **Real contact links** are discovered from the page's own nav/footer text
  ("Contact us", "About", "Team") and crawled — not just guessed `/contact`.
- **JS-only sites** fall back to the free `r.jina.ai` reader proxy
  (`FREE_JS_RENDER=true`, no key) so emails hidden behind JavaScript still
  surface.
- **Search caching** (`CACHE_SEARCH=true`) banks every engine result to
  `data/cache/` so reruns never have to re-hit the engines that bot-block —
  each query is only searched once a week.

## Incremental runs & lead quality

Runs are incremental by default:

- **Merge:** new leads are merged into the existing `--out` file instead of
  overwriting it (duplicates collapse to the richer version).
- **Domain skip:** domains already in the output are skipped in search mode,
  so reruns find *new* prospects instead of re-scraping the same ones.
- Use `--fresh` to start from scratch or `--no-merge` to overwrite.

Every lead is rated with a **quality score** (0-100): emails weigh heaviest,
then WhatsApp → Instagram → LinkedIn → phones. Exports are sorted best-first
and each row is tagged `quality_label` (high / medium / low) so you prospect
the strongest contacts first.

## API keys (optional)

- **[SerpAPI]** — `SERPAPI_KEY`: higher-quality Google organic results and
  bigger rate limits. Auto-used when set, else falls back to DuckDuckGo.
- **[ScrapingBee]** — `SCRAPINGBEE_API_KEY`: renders JS-heavy sites so
  contacts behind JavaScript are still parsed, and enables premium proxies
  automatically.
- **PROXY_LIST** (optional) — comma-separated
  `http://user:pass@host:port` entries used with rotation.

## Email verification

Emails are automatically validated via DNS MX-record lookups using the
`email-validator` library. Disposable email domains (mailinator, yopmail,
etc.) are filtered out. Disable with `--no-enrich` or `VERIFY_EMAILS=false`
in `.env`.

## Social discovery

When a scraped page doesn't contain Instagram or LinkedIn links, the scraper
automatically searches DuckDuckGo for `site:instagram.com "domain"` and
`site:linkedin.com/company "domain"` to discover social profiles. This
requires no API keys — just the free search engines. Disable with `--no-enrich`.

## How it works

```
niche queries ──▶ DuckDuckGo / Bing-RSS / Bing / Mojeek (free) or SerpAPI ──▶ business URLs
        │                     or --seeds <url-list-file>
        ▼
fetch page (proxy-rotated, rate-limited, retry w/ backoff)
        │
        ▼
ScrapingBee render if empty/JS-only (optional)
        │
        ▼
URL deny-list → extract emails · mailto: links · wa.me numbers · @instagram · linkedin · phones
        │
        ▼
in-niche keyword filter + exclusion + corporate/portal/education rules
        │
        ▼
contact page crawl (/contact, /about, etc.) → merge emails
        │
        ▼
social discovery (IG + LinkedIn via DDG) → merge contacts
        │
        ▼
email MX validation (drop invalids + disposables)
        │
        ▼
dedupe (by website) → CSV / JSON export
```

## Project layout

```
config/   settings (delays, retries, proxy list) + niche definitions
core/     data model, extractors, networking, niche filter
sources/  search clients, page fetcher, collection pipeline, social/email enrichment
output/   CSV + JSON exporters
utils/    proxy pool, host chunking helpers
```

## Extending

- **New niche:** add a `Niche` entry in `config/niches.py`.
- **New source:** subclass the pattern in `sources/collector.py`.

## Note

Respect robots.txt and each site's terms; only contact businesses that
intended to be contacted (public contact information). Rate limits are
baked in by design.
