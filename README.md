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

Discovery works **out of the box with zero API keys** using the built-in
free Bing + DuckDuckGo + Mojeek clients (Bing first, with each subsequent
engine failing over gracefully if one bot-checks your IP). SerpAPI and
ScrapingBee are optional upgrades auto-detected when their keys are present.

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
niche queries ──▶ Bing / DuckDuckGo / Mojeek (free) or SerpAPI ──▶ business URLs
        │
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
in-niche keyword filter + exclusion rules
        │
        ▼
dedupe → CSV / JSON export
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