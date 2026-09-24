"""Target-site HTTP policy: robots, redirects, and configured proxies."""

import pytest

from config.settings import ScraperSettings
from core.network import Session


class Response:
    def __init__(self, url, status=200, text="", headers=None):
        self.url = url
        self.status_code = status
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_robots_disallow_prevents_page_fetch():
    settings = ScraperSettings(request_delay_min=0, request_delay_max=0, max_retries=0)
    session = Session(settings)
    calls = []

    def fake_get(url, **_kwargs):
        calls.append(url)
        return Response(url, text="User-agent: *\nDisallow: /private\n")

    session._http.get = fake_get
    with pytest.raises(Exception, match="robots.txt"):
        session.get("https://acme.test/private")
    assert calls == ["https://acme.test/robots.txt"]


def test_redirect_checks_destination_robots():
    settings = ScraperSettings(request_delay_min=0, request_delay_max=0, max_retries=0)
    session = Session(settings)
    calls = []

    def fake_get(url, **_kwargs):
        calls.append(url)
        if url.endswith("robots.txt"):
            return Response(url, status=404)
        if url == "https://acme.test/":
            return Response(url, status=302, headers={"Location": "https://new.test/contact"})
        return Response(url, text="contact")

    session._http.get = fake_get
    result = session.get("https://acme.test/")
    assert result.url == "https://new.test/contact"
    assert calls == ["https://acme.test/robots.txt", "https://acme.test/",
                     "https://new.test/robots.txt", "https://new.test/contact"]


def test_configured_proxy_used_on_first_request():
    settings = ScraperSettings(proxies=["http://proxy-one:8000", "http://proxy-two:8000"])
    session = Session(settings)
    assert session._pick_proxy()["http"] == "http://proxy-one:8000"
    assert session._pick_proxy()["http"] == "http://proxy-one:8000"
