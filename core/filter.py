"""In-niche filtering based on page tokens and URL characteristics."""

from urllib.parse import urlparse

from config.niches import Niche

# Domains that are never a business lead: reference sites, social platforms,
# property/marketplace portals, aggregators, mega-corporations, banks.
DENY_HOSTS = {
    # Reference / dictionaries
    "wikipedia.org", "wikimedia.org", "wiktionary.org",
    "dictionary.com", "merriam-webster.com", "cambridge.org",
    "oxfordlearnersdictionaries.com", "collinsdictionary.com",
    "thefreedictionary.com", "vocabulary.com", "urbandictionary.com",
    "investopedia.com", "britannica.com",
    "businessnewsdaily.com", "forbes.com", "entrepreneur.com",
    # Social / content platforms
    "youtube.com", "youtu.be", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "tiktok.com", "reddit.com", "quora.com", "pinterest.com",
    "linkedin.com", "github.com", "medium.com", "wordpress.com",
    # Property / marketplace portals
    "zillow.com", "realtor.com", "trulia.com", "redfin.com", "homes.com",
    "housing.com", "magicbricks.com", "99acres.com", "commonfloor.com",
    "apartments.com", "streeteasy.com", "rightmove.co.uk", "zoopla.co.uk",
    "booking.com", "airbnb.com", "expedia.com", "tripadvisor.com",
    "indeed.com", "glassdoor.com", "yelp.com", "yellowpages.com",
    "craigslist.org", "ebay.com", "amazon.com", "walmart.com",
    "homedepot.com", "lowes.com",
    # Banks / financial institutions (not outreach leads)
    "sbi.co.in", "hdfcbank.com", "icicibank.com", "axisbank.com",
    "citibank.com", "chase.com", "bankofamerica.com", "wellsfargo.com",
    "jpmorgan.com", "goldmansachs.com", "boi.co.in", "pnbindia.in",
    "bankofindia.com", "majorbanks.in", "reservebank",
    # Nationals / industry bodies / exchanges
    "ibef.org", "india.gov.in", "sebi.gov.in", "stockexchangeofindia",
    "bseindia.com", "nseindia.com", "nhc.co.in",
    # Logistics / telecom giants
    "dtdc.com", "tata.com", "tatagroup.com", "airtel.in", "jio.com",
    # Big tech / platforms (not clients)
    "google.com", "googleusercontent.com", "microsoft.com", "apple.com",
    "meta.com", "facebookusa.com", "amazonaws.com", "cloudflare.com",
    "netflix.com", "salesforce.com", "oracle.com", "ibm.com", "adobe.com",
    "shopify.com", "stripe.com", "squareup.com", "hubspot.com", "webflow.com",
    # Corporate / directory data portals
    "opencorporates.com", "crunchbase.com", "zoominfo.com", "datanyze.com",
    "leadfeeder.com", "kompass.com", "g2.com", "trustpilot.com",
}

SUFFIX_DENY = (".gov", ".gov.in", ".mil", ".edu")
# Institutional/bank .co.in generic patterns are covered above.

# Strong signals that the page belongs to a large listed corporation that
# does not buy boutique agency services (Tier-1 corporate filter).
CORPORATE_SCALE_SIGNALS = (
    "investor relations",
    "investor-relations",
    "market capitalization",
    "market cap",
    "nasdaq",
    "nyse",
    "bombay stock exchange",
    "national stock exchange",
    "stock exchange",
    "listed company",
    "listed on the",
    "annual report",
    "quarterly results",
    "earnings call",
    "shareholders",
    "fortune 500",
    "ftse 100",
    "s&p 500",
    "multinational corporation",
    "publicly traded",
    "ipo",
    "dividend declared",
    "global headquarters",
    "corporate headquarters",
    "profit after tax",
    "earnings before interest",
    "your bank",
)

# Strong signals the page is an educational institution or aggregator portal.
EDUCATION_SIGNALS = (
    "university",
    "college",
    "university school",
    "admission ",
    "faculty of",
    "academic calendars",
    "courses offered",
    "university library",
    "results portal",
    "class of ",
)

# Aggregators / marketplaces masquerading as niche sites.
PORTAL_SIGNALS = (
    "sign in to your account",
    "create your account",
    "seller central",
    "become a partner",
    "compare & save",
    "compare prices",
    "membership plans available",
    "price comparison",
    "placing an order",
    "track your order",
)


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


# Brand names that should never be treated as clients even when hosted on a
# subdomain we do not recognize (Google Workspace -> workspace.google.gg).
MEGA_BRAND_MARKERS = (
    "google", "microsoft", "apple", "amazon", "microsoft365", "meta ",
    "netflix", "salesforce", "oracle", "ibm", "adobe", "shopify", "stripe",
    "square inc", "hubspot", "webflow", "opencorporates",
)


def name_is_denied(business_name: str) -> bool:
    """True when a page's business name matches a known mega brand."""
    lowered = (business_name or "").lower()
    for marker in MEGA_BRAND_MARKERS:
        if marker in lowered:
            return True
    return False


def url_is_denied(url: str) -> bool:
    """True when a candidate website URL should be skipped outright."""
    host = _host_of(url)
    if not host:
        return True
    if host.endswith(SUFFIX_DENY):
        return True
    for deny in DENY_HOSTS:
        if host == deny or host.endswith("." + deny):
            return True
    # Blind block of the largest Indian financial majors even if subdomains vary.
    for marker in ("sbi.co", ".sbi", "hdfcbank", "bseindia", "nseindia", "ibef.org"):
        if marker in host:
            return True
    return False


def text_matches_scope(text: str, niche: Niche) -> bool:
    """True if a page's visible text looks like it belongs to the niche."""
    if not niche.scope_keywords:
        return True  # no filter configured means accept
    lowered = text.lower()
    for kw in niche.scope_keywords:
        if kw in lowered:
            return True
    return False


def text_has_exclusions(text: str, niche: Niche) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in niche.exclusion_keywords)


def is_corporate_scale(text: str) -> bool:
    """True when page signals a large listed/sovereign-scale organisation."""
    lowered = text.lower()
    hits = [s for s in CORPORATE_SCALE_SIGNALS if s in lowered]
    return len(hits) >= 1


def is_educational(text: str) -> bool:
    lowered = text.lower()
    return any(s in lowered for s in EDUCATION_SIGNALS)


def is_portal(text: str) -> bool:
    lowered = text.lower()
    return any(s in lowered for s in PORTAL_SIGNALS)


def is_valid_candidate_lead(
    text: str,
    niche: Niche,
    *,
    require_contact: bool = True,
    require_scope: bool = True,
    exclude_corporate: bool = True,
    exclude_education: bool = True,
    exclude_portals: bool = True,
) -> bool:
    if require_scope and not text_matches_scope(text, niche):
        return False
    if text_has_exclusions(text, niche):
        return False
    if exclude_corporate and is_corporate_scale(text):
        return False
    if exclude_education and is_educational(text):
        return False
    if exclude_portals and is_portal(text):
        return False
    return True