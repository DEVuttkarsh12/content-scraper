"""Page fetching and parsing helpers."""

import logging
import re
from urllib.parse import urlparse

import requests

from bs4 import BeautifulSoup

from core.network import Session
from sources.search import RenderClient

logger = logging.getLogger(__name__)

# Content types we are willing to parse.
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml")

# Public social handles that are not informative for outreach.
IGNORE_HANDLES = {
    "share", "tag", "p", "reel", "explore", "company", "in", "groups",
    "jobs", "posts", "feed", "home",
}


def is_page_url(url: str) -> bool:
    """Ask us to skip obvious non-web resources and file downloads."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError:
        return False
    if parsed.scheme != "http" and parsed.scheme != "https":
        return False
    if not host or parsed.username or parsed.password:
        return False
    path = parsed.path.lower()
    for ext in (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".csv", ".doc", ".docx", ".mp4"):
        if path.endswith(ext):
            return False
    return True


def fetch_page(session: Session, renderer: RenderClient, url: str) -> str:
    """Fetch a page as HTML, falling back to JS rendering when needed."""
    html, _ = fetch_page_full(session, renderer, url)
    return html


def fetch_page_full(session: Session, renderer: RenderClient, url: str):
    """Like fetch_page but also returns the post-redirect final URL.

    Redirects are followed by the session, so `resp.url` may differ from the
    requested URL — callers can use it to avoid crawling the same page twice
    via different paths (e.g. /contact -> /contact-us/).
    """
    resp = session.get(url)
    final_url = resp.url
    content_type = resp.headers.get("Content-Type", "")
    if not any(ct in content_type for ct in ALLOWED_CONTENT_TYPES):
        # Possibly a JS-rendered site served as something else, or PDF. Skip.
        if "application/pdf" in content_type:
            return "", final_url
        rendered = renderer.render(url)
        if rendered:
            return rendered, final_url
        return "", final_url
    if resp.status_code == 200 and not resp.text:
        rendered = renderer.render(url)
        return (rendered or ""), final_url
    return resp.text, final_url


def extract_text(html: str) -> str:
    """Strip HTML to visible text for keyword filtering."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "head"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def extract_business_name(html: str, fallback_url: str | None = None) -> str:
    """Derive a business name from og:site_name/title or the URL host."""
    if html:
        soup = BeautifulSoup(html, "lxml")
        og = soup.find("meta", property="og:site_name")
        if og and og.get("content", "").strip():
            return og["content"].strip()[:200]
        title = soup.title
        if title and title.get_text(strip=True):
            return title.get_text(strip=True)[:200]
    if fallback_url:
        host = urlparse(fallback_url).netloc
        return host.removeprefix("www.").split(".")[0].title()
    return "Unknown"


def html_body_text(html: str) -> str:
    """Return stripped text but keep anything we want to regex for contacts."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    # Keep link/meta text too so @handles and wa.me links in markup survive.
    return soup.get_text(" ", strip=True)


def anchor_links(html: str) -> list:
    """Return all anchor hrefs (de-duplicated) for social link extraction."""
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href and href not in seen:
            seen.add(href)
            links.append(href)
    return links


# Visible anchor text that hints at a contact / about / team page worth
# crawling for emails. Matches English, Spanish, German, French variants.
CONTACT_LINK_TEXT = re.compile(
    r"\b(contact|contact us|contact-us|contacto|kontakt|impressum|imprint"
    r"|get in touch|reach us\b|email us|write to us|talk to us|let's talk"
    r"|connect with us|inquiries?|enquiries?|our team|our staff|our people"
    r"|meet the team|about us|about-us|who we are)\b",
    re.IGNORECASE,
)


def contact_links(html: str) -> list:
    """Return on-site hrefs whose visible text hints at contact/about pages.

    Guessing ``/contact`` misses sites that use other paths. Scanning the
    homepage nav/footer for an actual "Contact us / About / Team" link and
    crawling *that* URL gets emails far more often.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(" ", strip=True)
        if not href or not text or href in seen:
            continue
        if href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        if CONTACT_LINK_TEXT.search(text):
            seen.add(href)
            # Absolute links are checked against the homepage host when
            # _ordered_contact_urls resolves this list.
            parsed = urlparse(href)
            if not parsed.netloc or parsed.scheme in ("http", "https"):
                out.append(href)
    return out
