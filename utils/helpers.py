"""Shared small helpers: rate signals, chunking, URL normalization."""

import logging
import time
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


def backoff(min_wait: float, max_wait: float) -> float:
    """Random sleep within [min_wait, max_wait]."""
    wait = round(time.uniform(min_wait, max_wait), 2)
    if wait > 0:
        time.sleep(wait)
    return wait


def chunked(items: list, size: int):
    """Yield successive chunks of `items`."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def normalize_domain(url: str) -> str | None:
    """Strip scheme/path from a URL, returning lowercase domain or None."""
    try:
        parts = urlsplit(url if url.startswith("http") else "http://" + url)
    except ValueError:
        return None
    host = parts.hostname
    if not host:
        return None
    return host.lower().removeprefix("www.")


def is_same_domain(url_a: str, url_b: str) -> bool:
    a = normalize_domain(url_a)
    b = normalize_domain(url_b)
    return bool(a and b and a == b)