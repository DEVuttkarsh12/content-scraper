"""HTTP networking layer with rate limiting, retries, and proxy handling."""

import logging
import random
import time

import requests

from config.settings import ScraperSettings
from utils.proxies import ProxyPool

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) "
    "Gecko/20100101 Firefox/124.0",
]


class Session:
    """A rate-limited, proxy-rotating HTTP session."""

    def __init__(self, settings: ScraperSettings):
        self.settings = settings
        self._http = requests.Session()
        self._proxies = ProxyPool(settings.proxies)
        self._last_request_at = 0.0
        self._requests_since_proxy = 0
        self._rotate_every = max(4, len(settings.proxies)) if settings.proxies else 0

    @property
    def _rate_limit_seconds(self) -> float:
        return self.settings.delay_between_requests

    def _respect_rate_limit(self) -> None:
        wait = self._rate_limit_seconds
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < wait:
            time.sleep(wait - elapsed)

    def _pick_proxy(self, force: bool = False) -> dict | None:
        if not self._proxies.available:
            return None
        self._requests_since_proxy += 1
        if not force and self._requests_since_proxy < self._rotate_every:
            return None  # keep using the current IP until rotation window
        self._requests_since_proxy = 0
        return self._proxies.next()

    def _headers(self) -> dict:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        if self.settings.user_agent_rotate:
            headers["User-Agent"] = random.choice(USER_AGENTS)
        else:
            headers["User-Agent"] = USER_AGENTS[0]
        return headers

    def get(self, url: str, *, params: dict | None = None, headers: dict | None = None, timeout: int | None = None):
        """Perform a GET with rate limiting and retries."""
        final_headers = {**self._headers(), **(headers or {})}
        timeout_s = timeout or self.settings.timeout_seconds
        max_retries = self.settings.max_retries
        delay = self._rate_limit_seconds

        last_exc = None
        for attempt in range(max_retries + 1):
            self._respect_rate_limit()
            proxies = self._pick_proxy(force=attempt > 0)
            self._last_request_at = time.monotonic()
            try:
                resp = self._http.get(
                    url,
                    params=params,
                    headers=final_headers,
                    proxies=proxies,
                    timeout=timeout_s,
                )
                if resp.status_code == 429 and attempt < max_retries:
                    logger.warning("Rate limited on %s, backing off", url)
                    time.sleep(min(delay * (attempt + 1), 8))
                    continue
                # Treat proxy permission errors as retriable.
                if resp.status_code in (403, 407) and attempt < max_retries:
                    logger.warning("Blocked (%s) on %s, rotating proxy", resp.status_code, url)
                    time.sleep(delay)
                    continue
                # Don't retry other 4xx client errors (404, 410, etc.).
                if 400 <= resp.status_code < 500:
                    raise requests.HTTPError(
                        f"{resp.status_code} Client Error for url: {url}",
                        response=resp,
                    )
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:  # noqa: PERF203
                # 4xx errors are not retriable; 5xx/transport errors retry.
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and 400 <= status < 500:
                    raise exc
                last_exc = exc
                logger.debug("Request failed (%s): %s", url, exc)
                if attempt < max_retries:
                    self._proxies.mark_failed(proxies["http"]) if proxies else None
                    time.sleep(min(delay * (attempt + 1), 8))
                    continue
        if last_exc:
            raise last_exc
        raise requests.RequestException(f"Failed to fetch {url}")


def build_session(settings: ScraperSettings) -> Session:
    return Session(settings)