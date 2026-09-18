"""Tests for sources.collector pure helper functions (no network)."""

from sources.collector import (
    _candidate_score,
    _dedupe_urls,
    _extract_domain,
    _normalize_candidate_url,
    _ordered_contact_urls,
    _results_relevant,
)


class TestExtractDomain:
    def test_bare_host(self):
        assert _extract_domain("https://www.AcmeRealty.com/contact") == "acmerealty.com"

    def test_no_www(self):
        assert _extract_domain("https://acmerealty.com/x") == "acmerealty.com"

    def test_invalid_returns_none(self):
        assert _extract_domain("not a url") is None


class TestNormalizeCandidateUrl:
    def test_content_page_to_root(self):
        assert (
            _normalize_candidate_url("https://acme.com/blog/7-email-templates")
            == "https://acme.com/"
        )

    def test_homepage_unchanged(self):
        assert _normalize_candidate_url("https://acme.com/") == "https://acme.com/"

    def test_other_paths_unchanged(self):
        assert (
            _normalize_candidate_url("https://acme.com/branches/north/")
            == "https://acme.com/branches/north/"
        )


class TestCandidateScore:
    def test_scope_keyword_bonus(self, real_estate_niche):
        score = _candidate_score("https://acmerealty.com", "Real Estate Brokerage", real_estate_niche)
        assert score > 0

    def test_homepage_bonus(self, real_estate_niche):
        home = _candidate_score("https://acme.com/", "", real_estate_niche)
        deep = _candidate_score("https://acme.com/a/b/c/d/e", "", real_estate_niche)
        assert home > deep

    def test_junk_title_heavy_penalty(self, real_estate_niche):
        assert _candidate_score("https://acme.com", "Sign in to your account", real_estate_niche) < 0

    def test_denied_brand_min_score(self, real_estate_niche):
        assert _candidate_score("https://acme.com", "Microsoft Dynamics", real_estate_niche) == -100


class TestResultsRelevant:
    def test_relevant_results_pass(self, real_estate_niche):
        items = [
            {"url": "https://a.com", "title": "Real estate brokerage"},
            {"url": "https://b.com", "title": "Property developer"},
            {"url": "https://c.com", "title": "A football club"},
        ]
        assert _results_relevant(items, real_estate_niche)

    def test_off_topic_results_fail(self, real_estate_niche):
        items = [
            {"url": "https://a.com", "title": "Football club"},
            {"url": "https://b.com", "title": "Dictionary entry"},
        ]
        assert not _results_relevant(items, real_estate_niche)

    def test_no_niche_accepts(self, real_estate_niche):
        assert _results_relevant([], real_estate_niche) is True


class TestDedupeUrls:
    def test_dedupe_dicts_preserving_order(self):
        items = [
            {"url": "https://a.com", "title": "A"},
            {"url": "https://a.com", "title": "A dup"},
            {"url": "https://b.com", "title": "B"},
        ]
        out = _dedupe_urls(items)
        assert [i["url"] for i in out] == ["https://a.com", "https://b.com"]

    def test_dedupe_strings(self):
        assert _dedupe_urls(["https://a.com", "https://a.com"]) == ["https://a.com"]


class TestOrderedContactUrls:
    def test_discovered_first_then_guessed(self):
        urls = _ordered_contact_urls(
            "https://acme.com", ["/about", "/contact-us"]
        )
        assert urls[0] == "https://acme.com/about"
        assert urls[1] == "https://acme.com/contact-us"
        assert "https://acme.com/contact" in urls

    def test_dedupes_and_skips_base(self):
        urls = _ordered_contact_urls("https://acme.com/", ["/about", "/", "/about"])
        assert urls.count("https://acme.com/about") == 1
        assert "https://acme.com/" not in urls

    def test_handles_relative_paths(self):
        urls = _ordered_contact_urls("https://acme.com/site/index.html", ["contact.html"])
        assert urls[0] == "https://acme.com/site/contact.html"