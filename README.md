# Custom Lead Scraper

High-ticket lead scraper for an AI agency offering premium websites, custom
software, AI automation, and CRM builds. Discovers businesses in target
niches and harvests outreach contact points: **emails, WhatsApp numbers,
Instagram handles, LinkedIn profiles, and phone numbers**.

> This is the **barebone scaffold**. Wire up API keys in `.env` to go live.

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
python main.py --dry-run    # validate the barebone without scraping
python main.py --list-niches
```

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

Discovery works **out of the box with zero API keys** using the built-in
free Bing-RSS + DuckDuckGo + Bing + Mojeek clients, failing over gracefully
when an engine bot-checks your IP (challenge/captcha pages are detected and
skipped). SerpAPI and ScrapingBee are optional upgrades auto-detected when
their keys are present.

## API keys (optional)

- **[SerpAPI]** — `SERPAPI_KEY`: higher-quality Google organic results and
  bigger rate limits. Auto-used when set, else falls back to DuckDuckGo.
- **[ScrapingBee]** — `SCRAPINGBEE_API_KEY`: renders JS-heavy sites so
  contacts behind JavaScript are still parsed, and enables premium proxies
  automatically.
- **PROXY_LIST** (optional) — comma-separated
  `http://user:pass@host:port` entries used with rotation.

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
URL deny-list → extract emails · wa.me numbers · @instagram · linkedin · phones
        │
        ▼
in-niche keyword filter + exclusion + corporate/portal/education rules
        │
        ▼
dedupe (by website) → CSV / JSON export
```

## Project layout

```
config/   settings (delays, retries, proxy list) + niche definitions
core/     data model, extractors, networking, niche filter
sources/  search clients (SerpAPI + free Bing/DuckDuckGo/Mojeek), page fetcher,
          collection pipeline, social/email-enrichment stubs
output/   CSV + JSON exporters
utils/    proxy pool, host chunking helpers
```

## Extending

- **New niche:** add a `Niche` entry in `config/niches.py`.
- **Instagram API hookup:** implement `sources/social.py::InstagramSource` and
  merge results via `merge_contacts`.
- **New source:** subclass the pattern in `sources/collector.py`.

## Note

Respect robots.txt and each site's terms; only contact businesses that
intended to be contacted (public contact information). Rate limits are
baked in by design.