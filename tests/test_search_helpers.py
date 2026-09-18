"""Tests for sources.search pure helpers: bot detection, redirect unwrapping."""

import base64

from sources.search import (
    _dedupe_results,
    _is_bot_page,
    _unwrap_bing_redirect,
    _unwrap_ddg_redirect,
    _unwrap_ecosia_redirect,
    _unwrap_searx_url,
)


class TestBotDetection:
    def test_captcha_page(self):
        assert _is_bot_page("<html>Please verify you are human, captcha</html>")

    def test_unusual_traffic(self):
        assert _is_bot_page("Our systems have detected unusual traffic")

    def test_access_denied(self):
        assert _is_bot_page("Access denied by challenge-platform")

    def test_normal_page_not_bot(self):
        assert not _is_bot_page("<h1>Real search results here</h1>")

    def test_empty_is_bot(self):
        assert _is_bot_page("")


class TestUnwrapDdg:
    def test_ddg_redirect(self):
        href = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Facme.com%2Fx&rut=abc"
        assert _unwrap_ddg_redirect(href) == "https://acme.com/x"

    def test_double_encoded(self):
        href = "https://duckduckgo.com/l/?uddg=https%253A%252F%252Facme.com&rut=abc"
        assert _unwrap_ddg_redirect(href) == "https://acme.com"

    def test_plain_url_unchanged(self):
        assert _unwrap_ddg_redirect("https://acme.com/plain") is None


class TestUnwrapBing:
    def _make_href(self, target: str) -> str:
        b64 = base64.b64encode(target.encode()).decode().rstrip("=")
        return f"https://www.bing.com/ck/a?!&mkt=en&u=a1{b64}&ntb=1"

    def test_bing_redirect(self):
        assert _unwrap_bing_redirect(self._make_href("https://acme.com/x")) == "https://acme.com/x"

    def test_padding_edge_case(self):
        target = "https://acme.com"
        assert _unwrap_bing_redirect(self._make_href(target)) == target

    def test_plain_url_returns_direct(self):
        assert _unwrap_bing_redirect("https://acme.com/x") == "https://acme.com/x"

    def test_non_http_rejected(self):
        assert _unwrap_bing_redirect("ftp://acme.com/x") is None


class TestUnwrapEcosia:
    def test_plain_url(self):
        assert _unwrap_ecosia_redirect("https://acme.com/x") == "https://acme.com/x"

    def test_redirect_with_u(self):
        href = "https://www.ecosia.org/redirect?u=https%3A%2F%2Facme.com%2Fx"
        assert _unwrap_ecosia_redirect(href) == "https://acme.com/x"


class TestUnwrapSearx:
    def test_plain_url(self):
        assert _unwrap_searx_url("https://acme.com/x") == "https://acme.com/x"

    def test_q_param_double_encoded(self):
        href = "https://search.example/search?q=https%253A%252F%252Facme.com%252Fx"
        assert _unwrap_searx_url(href) == "https://acme.com/x"


class TestDedupeResults:
    def test_preserves_order(self):
        results = [{"url": "https://a.com"}, {"url": "https://a.com"}, {"url": "https://b.com"}]
        assert [r["url"] for r in _dedupe_results(results)] == ["https://a.com", "https://b.com"]