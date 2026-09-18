"""Extractors for emails, phone/WhatsApp numbers, and social handles.

All extractors operate on *visible body text* (scripts/styles stripped) plus
an optional list of anchor hrefs. This keeps junk pulled from JS file names,
CSS class names, and audit scripts from polluting the leads.
"""

import re
from urllib.parse import unquote

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

# Common 1-3 digit country calling codes used to sanity-check long numbers.
CALLING_CODES = {
    "1", "7", "20", "27", "30", "31", "32", "33", "34", "36", "39", "40",
    "41", "43", "44", "45", "46", "47", "48", "49", "51", "52", "53", "54",
    "55", "56", "57", "58", "60", "61", "62", "63", "64", "65", "66", "81",
    "82", "84", "86", "90", "91", "92", "93", "94", "95", "98", "212", "213",
    "234", "351", "352", "353", "354", "355", "356", "357", "358", "359",
    "370", "371", "372", "373", "374", "375", "376", "377", "380", "381",
    "385", "386", "387", "420", "421", "971", "972", "973", "974", "975",
    "976", "966", "971", "974",
}

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

# Cloudflare email-protection (data-cfemail) obfuscated addresses.
CFEMAIL_RE = re.compile(r'data-cfemail="([0-9a-fA-F]+)"')

# URL-encoded emails like info%40example%2Ecom.
PERCENT_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+%40[A-Za-z0-9._%-]+",
    re.IGNORECASE,
)

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


def _is_plausible_phone(digits: str) -> bool:
    """Sanity-check a cleaned digit string as a real phone number.

    Rules:
      - 10 digits: accepted (US/CA or mobile without country code).
      - 11 digits: accepted only when the leading digit is a valid calling
        code (1 for NANP, 7 for Russia/Kazakhstan).
      - 12-15 digits: accepted only when the leading 1-3 digits match a
        known calling code.
      - Longer or leading-zero-heavy strings are rejected.
    """
    n = len(digits)
    if n == 10:
        return True
    if n == 11:
        return digits[0] in ("1", "7")
    if 12 <= n <= 15:
        return any(
            digits.startswith(code)
            for code in CALLING_CODES
            if len(code) in (2, 3)
        ) or (n == 12 and digits[0] == "1")
    return False


def _dedupe_phones(numbers: list) -> list:
    """Drop bare local numbers when the international version is also listed."""
    result = []
    for num in sorted(numbers, key=len, reverse=True):
        is_superstring = any(num.strip("+") in other for other in result)
        if not is_superstring:
            result.append(num)
    return sorted(result)


def extract_phones(text: str) -> list:
    """Extract raw phone numbers (fallback when no WhatsApp link).

    Filters out garbage matches: sequences of repeated digits, numbers
    starting with too many zeros, and numeric strings that are really
    years, prices, or hex codes.
    """
    results = set()
    for match in PHONE_RE.findall(text):
        digits = _clean_phone(match)
        if not _is_plausible_phone(digits):
            continue
        # Reject if mostly zeros (e.g. "0000000000").
        if digits.count("0") > len(digits) * 0.5:
            continue
        # Reject all-same-digit strings ("11111111111").
        if len(set(digits)) <= 2:
            continue
        # Reject sequences that are just years or small numbers padded.
        if digits.startswith("00"):
            continue
        results.add(digits)
    return _dedupe_phones(sorted(results))


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
    # Also pull emails from mailto: hrefs in the links list.
    mailto_emails = set()
    for link in links or []:
        if link.lower().startswith("mailto:"):
            email = link[7:].split("?")[0].strip().lower()
            if "@" in email and _is_valid_email(email):
                mailto_emails.add(email)
    info.emails = sorted(set(info.emails) | mailto_emails)
    info.whatsapp_numbers = extract_whatsapp_numbers(links=links, text=text)
    info.instagram_handles = extract_instagram_handles(links=links, text=text)
    info.linkedin_urls = extract_linkedin_urls(links=links, text=text)
    if not info.whatsapp_numbers:
        info.phones = extract_phones(text)
    return info


def decode_cloudflare_email(hex_data: str) -> str | None:
    """Decode a Cloudflare email-protection string.

    Cloudflare XOR-encodes the address one byte at a time; the first byte is
    the key. ``data-cfemail="2a3f333..."`` -> back to plaintext email.
    """
    try:
        h = (hex_data or "").strip()
        if len(h) < 4 or len(h) % 2 != 0:
            return None
        key = int(h[:2], 16)
        out = []
        for i in range(2, len(h), 2):
            out.append(chr(int(h[i : i + 2], 16) ^ key))
        email = "".join(out).strip()
        if "@" in email and "." in email.split("@")[-1]:
            return email
    except ValueError:
        return None
    return None


def extract_cloudflare_emails(html: str) -> list:
    """Recover emails hidden behind Cloudflare's data-cfemail shields."""
    results = set()
    for match in CFEMAIL_RE.findall(html or ""):
        email = decode_cloudflare_email(match)
        if email:
            cleaned = _clean_email(email)
            if _is_valid_email(cleaned):
                results.add(cleaned)
    return sorted(results)


def extract_encoded_emails(html: str) -> list:
    """Recover URL-encoded emails like ``info%40example%2Ecom``."""
    results = set()
    for match in PERCENT_EMAIL_RE.findall(html or ""):
        try:
            decoded = unquote(match)
        except Exception:  # noqa: BLE001
            continue
        cleaned = _clean_email(decoded)
        if "@" in cleaned and _is_valid_email(cleaned):
            results.add(cleaned)
    return sorted(results)


def extract_from_html(html: str) -> ContactInfo:
    """Extract emails that live in raw HTML rather than visible text.

    Catches Cloudflare-protected addresses and percent-encoded variants so
    we grab a site's email even when it is hidden from the rendered page.
    """
    info = ContactInfo()
    if not html:
        return info
    info.emails = sorted(
        set(extract_cloudflare_emails(html)) | set(extract_encoded_emails(html))
    )
    return info