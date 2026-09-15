"""Proxy handling: rotation, validation, and reuse of proxy pools."""

import logging

logger = logging.getLogger(__name__)


class ProxyPool:
    """Round-robin pool of http(s) proxies with health tracking."""

    def __init__(self, proxies: list, *, cooldown_seconds: float = 60.0):
        self._proxies = list(proxies)
        self._idx = 0
        self._cooldown = cooldown_seconds
        self._disabled_until: dict[str, float] = {}

    @property
    def available(self) -> bool:
        return bool(self._proxies)

    def next(self) -> dict | None:
        """Return the next healthy proxy dict, or None when empty."""
        if not self._proxies:
            return None
        for _ in range(len(self._proxies)):
            proxy = self._proxies[self._idx]
            self._idx = (self._idx + 1) % len(self._proxies)
            disabled = self._disabled_until.get(proxy, 0.0)
            if disabled > __import__("time").time():
                continue
            return {"http": proxy, "https": proxy}
        return None

    def mark_failed(self, proxy: str) -> None:
        """Temporarily disable a failing proxy for the cooldown period."""
        import time

        self._disabled_until[proxy] = time.time() + self._cooldown
        logger.debug("Proxy disabled for cooldown: %s", proxy)

    def add(self, proxy: str) -> None:
        if proxy not in self._proxies:
            self._proxies.append(proxy)