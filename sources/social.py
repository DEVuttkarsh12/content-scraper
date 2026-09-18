"""Social platform lead sources and email enrichment.

InstagramSource / LinkedInSource use free search engines to discover
social profiles linked to a domain.  EmailEnricher validates emails
via MX-record checks (email-validator) and filters out disposable
addresses.

They all share the same contract: given a domain or ContactInfo, return
extra data that gets merged into the Lead.
"""

import logging
import re
from urllib.parse import urlparse

from config.settings import ScraperSettings
from core.models import ContactInfo

logger = logging.getLogger(__name__)

# Disposable / catch-all email domains we never want to keep.
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net",
    "tempmail.com", "throwaway.email", "temp-mail.org",
    "fakeinbox.com", "sharklasers.com", "guerrillamailblock.com",
    "grr.la", "dispostable.com", "yopmail.com", "yopmail.fr",
    "maildrop.cc", "mailnesia.com", "trashmail.com", "trashmail.net",
    "trashmail.org", "10minutemail.com", "getnada.com",
    "emailondeck.com", "mohmal.com", "burnermail.io",
    "harakirimail.com", "tmpmail.net", "tmpmail.org",
}

# Generic mailboxes tried (in order) when a site publishes no email anywhere.
# The first mailbox that passes a real SMTP deliverability check is kept.
FALLBACK_MAILBOXES = (
    "info", "hello", "contact", "admin", "office",
    "sales", "enquiries", "reception", "booking", "mail",
)


class InstagramSource:
    """Discover Instagram business handles from a domain via search engines.

    Searches for ``site:instagram.com "domain"`` across a free-engine chain
    (Mojeek -> Bing RSS -> DuckDuckGo) and parses results for
    instagram.com/<handle> URLs.  No API key required.
    """

    def __init__(self, settings: ScraperSettings):
        self._settings = settings
        self._session = None
        self._clients = None

    def set_session(self, session) -> None:
        self._session = session
        self._clients = None  # rebuild with the new shared session

    def _engines(self):
        from sources.search import BingClient, BingRssClient, DuckDuckGoClient, MojeekClient

        if self._clients is None:
            self._clients = [
                BingRssClient(self._settings, session=self._session),
                BingClient(self._settings, session=self._session),
                MojeekClient(self._settings, session=self._session),
                DuckDuckGoClient(self._settings, session=self._session),
            ]
        return self._clients

    def find_from_domain(self, domain: str) -> list:
        """Return deduped Instagram handles found for *domain*."""
        query = f'site:instagram.com "{domain}"'
        handles: set = set()
        for engine in self._engines():
            try:
                results = engine.search(query, num=10)
            except Exception as exc:  # noqa: BLE001
                logger.debug("%s search failed for %s: %s",
                             type(engine).__name__, domain, exc)
                continue
            for r in results:
                url = r.get("url", "")
                h = _extract_handle_from_url(url)
                if h:
                    handles.add(h)
            if handles:
                logger.debug("IG found %d handle(s) for %s via %s",
                             len(handles), domain, type(engine).__name__)
                break
        return sorted(handles)


class LinkedInSource:
    """Discover LinkedIn company pages from a domain via search engines.

    Searches for ``site:linkedin.com/company "domain"`` across a free-engine
    chain (Mojeek -> Bing RSS -> DuckDuckGo) and parses the results for
    linkedin.com/company/<slug> URLs.  No API key required.
    """

    def __init__(self, settings: ScraperSettings):
        self._settings = settings
        self._session = None
        self._clients = None

    def set_session(self, session) -> None:
        self._session = session
        self._clients = None  # rebuild with the new shared session

    def _engines(self):
        from sources.search import BingClient, BingRssClient, DuckDuckGoClient, MojeekClient

        if self._clients is None:
            self._clients = [
                BingRssClient(self._settings, session=self._session),
                BingClient(self._settings, session=self._session),
                MojeekClient(self._settings, session=self._session),
                DuckDuckGoClient(self._settings, session=self._session),
            ]
        return self._clients

    def find_from_domain(self, domain: str) -> list:
        """Return deduped LinkedIn company URLs found for *domain*."""
        query = f'site:linkedin.com/company "{domain}"'
        urls: set = set()
        for engine in self._engines():
            try:
                results = engine.search(query, num=10)
            except Exception as exc:  # noqa: BLE001
                logger.debug("%s search failed for %s: %s",
                             type(engine).__name__, domain, exc)
                continue
            for r in results:
                url = r.get("url", "")
                norm = _normalize_linkedin_url(url)
                if norm:
                    urls.add(norm)
            if urls:
                logger.debug("LinkedIn found %d URL(s) for %s via %s",
                             len(urls), domain, type(engine).__name__)
                break
        return sorted(urls)


class EmailEnricher:
    """Verify emails via MX-record checks and filter disposable addresses.

    Uses the ``email_validator`` library for DNS-level MX lookups and
    syntax validation.  Emails that fail validation are removed.
    """

    def __init__(self, settings: ScraperSettings):
        self._settings = settings
        self._available = _check_validator()

    def enrich(self, contact: ContactInfo) -> ContactInfo:
        """Return *contact* with invalid emails removed."""
        if not self._available or not contact.emails:
            return contact
        valid: list = []
        for email in contact.emails:
            if self._is_valid(email):
                valid.append(email)
            else:
                logger.debug("Dropped invalid email: %s", email)
        contact.emails = valid
        return contact

    def infer_emails(self, domain: str, limit: int = 6) -> list:
        """Propose generic mailboxes for a domain that published no email.

        Many B2B sites only expose a contact *form* — no address anywhere on
        the page. This is the last-resort fallback: try the most common
        generic mailboxes (info@, hello@, contact@, …) and keep only the
        ones that actually accept mail (real SMTP deliverability probe), so
        every lead leaves the pipeline with a genuinely valid address.
        """
        domain = (domain or "").lower().strip()
        if not self._available or not domain:
            return []
        out: list = []
        for mailbox in FALLBACK_MAILBOXES:
            candidate = f"{mailbox}@{domain}"
            if self._is_valid(candidate, strict=True):
                logger.debug("Inferred valid mailbox: %s", candidate)
                out.append(candidate)
            if len(out) >= limit:
                break
        return out

    def _is_valid(self, email: str, *, strict: bool = False) -> bool:
        """Check syntax + disposable domain + MX record.

        In *strict* mode a transient DNS/network error counts as invalid so
        we never invent a mailbox on flaky lookups (used for inferred
        addresses). Non-strict keeps scraped emails on hiccups.
        """
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        if domain.lower() in DISPOSABLE_DOMAINS:
            return False
        try:
            from email_validator import validate_email, EmailNotValidError

            validate_email(email, check_deliverability=True)
            return True
        except EmailNotValidError:
            return False
        except Exception:  # noqa: BLE001
            # DNS errors, network issues — keep scraped emails rather than
            # drop them, but never accept an unproven inferred one.
            return not strict


def _check_validator() -> bool:
    """Return True if email_validator is importable."""
    try:
        import email_validator  # noqa: F401

        return True
    except ImportError:
        logger.warning("email-validator not installed; email validation disabled")
        return False


def _extract_handle_from_url(url: str) -> str | None:
    """Pull the Instagram handle from an instagram.com URL."""
    try:
        parsed = urlparse(url)
        if "instagram.com" not in (parsed.hostname or ""):
            return None
        path = parsed.path.strip("/")
        if not path:
            return None
        handle = path.split("/")[0]
        # Skip non-profile paths
        skip = {"p", "reel", "reels", "explore", "share", "tv",
                "stories", "locations", "accounts", "directories",
                "legal", "privacy", "about", "help"}
        if handle.lower() in skip:
            return None
        if len(handle) < 2 or len(handle) > 30:
            return None
        return handle
    except Exception:  # noqa: BLE001
        return None


def _normalize_linkedin_url(url: str) -> str | None:
    """Normalize a LinkedIn company URL to a canonical form."""
    try:
        parsed = urlparse(url)
        if "linkedin.com" not in (parsed.hostname or ""):
            return None
        path = parsed.path.strip("/")
        if not path.startswith("company/"):
            return None
        slug = path.split("company/")[1].split("/")[0].split("?")[0]
        if not slug:
            return None
        return f"https://linkedin.com/company/{slug}"
    except Exception:  # noqa: BLE001
        return None


def merge_contacts(*contacts: ContactInfo) -> ContactInfo:
    """Merge multiple ContactInfo sources into one deduped result."""
    merged = ContactInfo()
    all_emails = set()
    all_wa = set()
    all_ig = set()
    all_li = set()
    all_phones = set()
    for c in contacts:
        all_emails.update(c.emails)
        all_wa.update(c.whatsapp_numbers)
        all_ig.update(c.instagram_handles)
        all_li.update(c.linkedin_urls)
        all_phones.update(c.phones)
    merged.emails = sorted(all_emails)
    merged.whatsapp_numbers = sorted(all_wa)
    merged.instagram_handles = sorted(all_ig)
    merged.linkedin_urls = sorted(all_li)
    merged.phones = sorted(all_phones)
    return merged
