"""Extractors for emails, phone/WhatsApp numbers, and social handles.

All extractors operate on *visible body text* (scripts/styles stripped) plus
an optional list of anchor hrefs. This keeps junk pulled from JS file names,
CSS class names, and audit scripts from polluting the leads.
"""

import re

from core.models import ContactInfo

# Email: pragmatic pattern, excludes images and common trap TLDs.
EMAIL_RE = re.compile(
    r"[\w.+-]+@[\w-]+\.(?:com|net|org|io|co|ca|co\.uk|me|info|biz|us|in|"
    r"de|fr|es|it|au|nl|se|no|dk|fi|pl|cz|eu|ai|dev|agency|studio|site|"
    r"online|business|company)\b",
    re.IGNORECASE,
)

# Explicit obfuscated emails like "john [at] gmail [dot] com"
OBFUSCATED_EMAIL_RE = re.compile(
    r"[\w.+-]+\s*\[?\(?\s*(?:at|@)\s*\)?\]?\s*[\w-]+\s*\[?\(?\s*"
    r"(?:dot)\s*\)?\]?\s*(?:com|net|org|io|co|in|co\.uk)\b",
    re.IGNORECASE,
)

# International phone numbers. Digits only after cleaning.
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3}[\s.-]?\d{3}[\s.-]?\d{3,4}",
)

# WhatsApp links embedded in href attrs: wa.me/NNN or api.whatsapp.com/send?phone=NNN
WHATSAPP_LINK_RE = re.compile(
    r"(?:wa\.me/(?:widget/)?|api\.whatsapp\.com/send[^\"']*?phone=)(\d{7,15})",
    re.IGNORECASE,
)

# Instagram handle mentioned as @handle in visible text.
INSTAGRAM_AT_RE = re.compile(r"(?<!\w)@([a-zA-Z0-9_][a-zA-Z0-9_.]{1,29})", re.IGNORECASE)

# Instagram profile link: instagram.com/<handle> (filters photo/media paths).
INSTAGRAM_LINK_RE = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]{1,30})",
    re.IGNORECASE,
)

# LinkedIn company/profile URLs.
LINKEDIN_URL_RE = re.compile(
    r"https?://(?:www\.)?linkedin\.com/(?:company|in|school)/[a-zA-Z0-9\-_./%]+",
    re.IGNORECASE,
)

# Instagram paths that are NOT user profiles.
INSTAGRAM_SKIP_PATH = {
    "p", "reel", "reels", "explore", "share", "static", "tv", "create",
    "stories", "locations", "accounts", "discover", "directory", "csr",
    "privacy", "terms", "about", "help", "developer", "challenge", "oembed",
}

# Instagram handles that are platform noise.
INSTAGRAM_SKIP_HANDLE = {
    "share", "tag", "p", "reel", "reels", "explore", "instagram",
    "instagood", "follow", "followers", "tiktok", "facebook",
    "yourprofile", "yourusername", "username", "yourhandle", "profile",
}

# Common noisy email domains.
NOISE_DOMAINS = {
    "example.com", "sentry.io", "domain.com", "email.com",
    "yourdomain.com", "wordpress.com", "gravatar.com",
}

# Email domains that are never an outreach lead.
EMAIL_SUFFIX_DENY = (".gov", ".gov.in", ".mil")


def _email_domain_denied(domain: str) -> bool:
    if domain == "gov.in" or domain.endswith(".gov") or domain.endswith(".gov.in"):
        return True
    return domain.endswith(".mil")


def _clean_email(raw: str) -> str:
    return raw.strip().strip(".,;:<>'\"").replace(" ", "").lower()


def _clean_handle(raw: str) -> str:
    handle = raw.strip().strip(",.;:!?'\"()|")
    if handle.startswith("@"):
        handle = handle[1:]
    if "/" in handle:
        handle = handle.rsplit("/", 1)[-1]
    handle = handle.split("?")[0].split("#")[0]
    return handle


def _clean_phone(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def _is_valid_email(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    if domain.lower() in NOISE_DOMAINS:
        return False
    if _email_domain_denied(domain.lower()):
        return False
    if "@" in email:
        local, dom = email.split("@", 1)
        if not local or len(dom.split(".")) < 2:
            return False
    return len(email) <= 254


def _is_valid_handle(handle: str) -> bool:
    hl = handle.lower()
    if len(hl) < 2 or len(hl) > 30:
        return False
    if hl in INSTAGRAM_SKIP_HANDLE:
        return False
    if hl.startswith(".") or hl.endswith("."):
        return False
    # Asset/junk guards: file-like or numeric-heavy strings.
    if re.search(r"\.(?:js|css|png|jpe?g|gif|svg|json|html?|php)$", hl):
        return False
    if re.fullmatch(r"[0-9.]+", hl):
        return False
    if re.search(r"[^a-z0-9_.]", hl):
        return False
    return True


def extract_emails(text: str) -> list:
    """Extract and dedupe plain-text emails from visible text."""
    results = set()
    for match in EMAIL_RE.findall(text):
        email = _clean_email(match)
        if _is_valid_email(email):
            results.add(email)
    # Deobfuscate "at"/"dot" variants.
    for match in OBFUSCATED_EMAIL_RE.findall(text):
        deobf = (
            match.lower()
            .replace(" [at] ", "@")
            .replace("[at]", "@")
            .replace(" at ", "@")
            .replace("(at)", "@")
            .replace(" [dot] ", ".")
            .replace("[dot]", ".")
            .replace(" dot ", ".")
            .replace("(dot)", ".")
            .replace(" ", "")
        )
        if "@" in deobf and _is_valid_email(deobf):
            results.add(deobf)
    return sorted(results)


def extract_whatsapp_numbers(links: list | None = None, text: str = "") -> list:
    """Extract WhatsApp numbers from wa.me / api.whatsapp.com links."""
    results = set()
    for source in list(links or []) + [text]:
        for match in WHATSAPP_LINK_RE.findall(source):
            digits = _clean_phone(match)
            if 10 <= len(digits) <= 15:
                results.add(digits)
    return sorted(results)


def extract_phones(text: str) -> list:
    """Extract raw phone numbers (fallback when no WhatsApp link)."""
    results = set()
    for match in PHONE_RE.findall(text):
        digits = _clean_phone(match)
        if 10 <= len(digits) <= 15:
            results.add(digits)
    return sorted(results)


def extract_instagram_handles(links: list | None = None, text: str = "") -> list:
    """Extract Instagram handles from profile links and @handle mentions.

    `links` are anchor hrefs; `text` is visible body text. Handles found in
    JavaScript/CSS asset names are rejected by validation.
    """
    results = set()
    for link in links or []:
        for match in INSTAGRAM_LINK_RE.findall(link):
            handle = _clean_handle(match)
            if handle.lower() in INSTAGRAM_SKIP_PATH:
                continue
            if _is_valid_handle(handle):
                results.add(handle)
    for match in INSTAGRAM_AT_RE.findall(text):
        handle = _clean_handle(match)
        if _is_valid_handle(handle):
            results.add(handle)
    return sorted(results)


def extract_linkedin_urls(links: list | None = None, text: str = "") -> list:
    """Extract LinkedIn company/profile URLs.

    URLs are normalised (https, no trailing slash) so http/https and
    `/company/x` vs `/company/x/` variants collapse onto a single entry.
    """
    results = set()
    for source in list(links or []) + [text]:
        for match in LINKEDIN_URL_RE.findall(source):
            url = match.rstrip(".,;:)'\"")
            url = url.replace("http://", "https://", 1)
            url = url.replace("https://www.linkedin.com", "https://linkedin.com", 1)
            url = url.rstrip("/")
            results.add(url)
    return sorted(results)


def extract_all(*, text: str = "", links: list | None = None) -> ContactInfo:
    """Extract every contact type from visible text + anchor links."""
    info = ContactInfo()
    info.emails = extract_emails(text)
    info.whatsapp_numbers = extract_whatsapp_numbers(links=links, text=text)
    info.instagram_handles = extract_instagram_handles(links=links, text=text)
    info.linkedin_urls = extract_linkedin_urls(links=links, text=text)
    if not info.whatsapp_numbers:
        info.phones = extract_phones(text)
    return info