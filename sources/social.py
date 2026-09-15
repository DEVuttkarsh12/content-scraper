"""Social platform lead sources (stubs for future API hookups).

These modules are placeholders in the barebone scaffold. Each will be
wired to a real endpoint once the corresponding API key is added:

  InstagramSource  -> instagram scraper / graph API client
  LinkedInSource   -> linkedin people/company search client
  EmailEnricher    -> domain email verification (e.g. deliverability check)

They all share the same contract: given a domain or business name, return
extra ContactInfo that gets merged into the Lead.
"""

from core.models import ContactInfo


class InstagramSource:
    """Placeholder: discover Instagram business handles from a domain."""

    def __init__(self, settings):  # noqa: ANN001
        self._settings = settings

    def find_from_domain(self, domain: str) -> list:
        """TODO: query Instagram API with SCRAPINGBEE / rapidapi key."""
        del domain  # placeholder
        return []


class LinkedInSource:
    """Placeholder: discover LinkedIn company profiles from a domain."""

    def __init__(self, settings):  # noqa: ANN001
        self._settings = settings

    def find_from_domain(self, domain: str) -> list:
        """TODO: query LinkedIn company search / people search API."""
        del domain  # placeholder
        return []


class EmailEnricher:
    """Placeholder: verify + enrich emails (MX check, catch-all detect)."""

    def __init__(self, settings):  # noqa: ANN001
        self._settings = settings

    def enrich(self, contact: ContactInfo) -> ContactInfo:
        """TODO: run MX/verification and mark valid vs invalid."""
        return contact


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