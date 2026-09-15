"""Orchestrates lead discovery for a niche.

Flow: niche queries -> search engines (SerpAPI / Bing / DuckDuckGo)
-> fetch pages -> extract contacts -> niche + corporate tier filter
-> crawl contact pages for emails -> qualified leads.
"""

import logging
from urllib.parse import urljoin

from config.niches import Niche
from config.settings import ScraperSettings
from core.extractor import extract_all
from core.filter import is_valid_candidate_lead, name_is_denied, url_is_denied
from core.models import ContactInfo, Lead
from core.network import build_session
from sources.page import (
    anchor_links,
    extract_business_name,
    fetch_page,
    html_body_text,
    is_page_url,
)
from sources.search import (
    BingClient,
    DuckDuckGoClient,
    MojeekClient,
    RenderClient,
    SearchClient,
)
from sources.social import merge_contacts

logger = logging.getLogger(__name__)

# Subpages crawled when the homepage yields no emails.
CONTACT_PATHS = (
    "/contact",
    "/contact-us",
    "/contactus",
    "/contact.html",
    "/get-in-touch",
    "/about",
    "/about-us",
)


class SearchSource:
    """Discover business websites via search and harvest their contacts.

    Engine selection: SerpAPI when its key is configured, then free engines
    (Bing, DuckDuckGo) in fallback order — so scraping works with zero API
    keys even when one engine bot-checks the IP.
    """

    def __init__(self, settings: ScraperSettings):
        self.settings = settings
        self.session = build_session(settings)
        self.search = SearchClient(settings)
        self.bing = BingClient(settings, session=self.session)
        self.ddg = DuckDuckGoClient(settings, session=self.session)
        self.mojeek = MojeekClient(settings, session=self.session)
        self.renderer = RenderClient(settings)
        self.free_engines = [self.bing, self.ddg, self.mojeek]

    def _discover(self, query: str, num: int = 10) -> list:
        """Try paid engine first, then each free engine until results."""
        if self.search.available:
            try:
                urls = self.search.search(query, num=num)
                if urls:
                    return urls
            except Exception as exc:  # noqa: BLE001
                logger.error("SerpAPI failed (%s); falling back to free engines", exc)
        for engine in self.free_engines:
            try:
                urls = engine.search(query, num=num)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Engine %s failed: %s", type(engine).__name__, exc)
                continue
            if urls:
                return urls
        return []

    def collect(self, niche: Niche, max_leads: int = 20) -> list:
        """Collect up to max_leads qualified leads for a niche."""
        leads: list = []
        seen_urls: set = set()
        candidate_urls: list = []

        for query in niche.search_queries:
            logger.info("Searching: %r", query)
            urls = self._discover(query, num=20)
            for item in urls:
                url = item["url"] if isinstance(item, dict) else item
                if (
                    is_page_url(url)
                    and not url_is_denied(url)
                    and url not in seen_urls
                ):
                    seen_urls.add(url)
                    candidate_urls.append((url, query))
            # Respect search engine rate limits between queries.
            import time

            time.sleep(self.settings.delay_between_requests)

        logger.info("Found %d candidate URLs for %s", len(candidate_urls), niche.id)

        for url, query in candidate_urls:
            if len(leads) >= max_leads:
                break
            contact, name = self._process_url(url, niche)
            if contact is None:
                continue
            lead = Lead.from_contact(
                business_name=name or "Unknown",
                niche=niche.id,
                website=url,
                contact=contact,
                source_query=query,
            )
            if lead.has_contact:
                leads.append(lead)
                logger.debug("Lead: %s (%s contact points)", name, _contact_count(contact))

        return leads

    def _process_url(self, url: str, niche: Niche):
        """Fetch + extract one URL. Returns (ContactInfo|None, name)."""
        try:
            html = fetch_page(self.session, self.renderer, url)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skipping %s: %s", url, exc)
            return None, None

        if not html:
            logger.debug("Empty page: %s", url)
            return None, None

        body = html_body_text(html)
        if not is_valid_candidate_lead(body, niche):
            logger.debug("Out of niche scope, skipping: %s", url)
            return None, None
        links = anchor_links(html)
        contact = extract_all(text=body, links=links)
        name = extract_business_name(html, fallback_url=url)
        if name_is_denied(name):
            logger.debug("Mega brand, skipping: %s", url)
            return None, None
        # Emails usually live on contact pages, not the homepage. Crawl a few
        # of the site's subpages when the homepage alone yielded no emails.
        if not contact.emails:
            crawler = self._crawl_contact_pages(url, niche)
            merged = merge_contacts(contact, crawler)
            if merged.has_anything:
                contact = merged
        return contact, name

    def _crawl_contact_pages(self, base_url: str, niche: Niche) -> ContactInfo:
        """Fetch likely contact/about subpages and merge their contacts."""
        aggregated = ContactInfo()
        for path in CONTACT_PATHS:
            sub_url = urljoin(base_url, path)
            try:
                html = fetch_page(self.session, self.renderer, sub_url)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Subpage crawl skipped %s: %s", sub_url, exc)
                continue
            if not html:
                continue
            body = html_body_text(html)
            if not is_valid_candidate_lead(body, niche):
                continue
            links = anchor_links(html)
            sub_contact = extract_all(text=body, links=links)
            if sub_contact.has_anything:
                aggregated = merge_contacts(aggregated, sub_contact)
                if aggregated.emails:
                    logger.debug("Found emails on %s", sub_url)
                    break
        return aggregated


def _contact_count(info: ContactInfo) -> int:
    return (
        len(info.emails)
        + len(info.whatsapp_numbers)
        + len(info.instagram_handles)
        + len(info.linkedin_urls)
        + len(info.phones)
    )