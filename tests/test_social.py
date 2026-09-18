"""Tests for sources.social: contact merging, handle/URL parsing, inference."""

from core.models import ContactInfo
from sources.social import (
    EmailEnricher,
    _extract_handle_from_url,
    _normalize_linkedin_url,
    merge_contacts,
)


class TestMergeContacts:
    def test_single_scraped(self):
        merged = merge_contacts(ContactInfo(emails=["a@x.com"]))
        assert merged.emails == ["a@x.com"]
        assert merged.email_origin == "scraped"

    def test_unions_all_channels(self):
        a = ContactInfo(emails=["a@x.com"], instagram_handles=["acme"])
        b = ContactInfo(emails=["b@x.com"], phones=["123"])
        merged = merge_contacts(a, b)
        assert merged.emails == ["a@x.com", "b@x.com"]
        assert merged.instagram_handles == ["acme"]
        assert merged.phones == ["123"]

    def test_dedupes(self):
        merged = merge_contacts(
            ContactInfo(emails=["a@x.com"]), ContactInfo(emails=["a@x.com"])
        )
        assert merged.emails == ["a@x.com"]

    def test_origin_mixed_when_inferred_present(self):
        merged = merge_contacts(
            ContactInfo(emails=["a@x.com"], email_origin="scraped"),
            ContactInfo(emails=["b@x.com"], email_origin="inferred"),
        )
        assert merged.email_origin == "mixed"

    def test_origin_all_inferred(self):
        merged = merge_contacts(
            ContactInfo(emails=["a@x.com"], email_origin="inferred")
        )
        assert merged.email_origin == "inferred"

    def test_no_emails_defaults_scraped(self):
        merged = merge_contacts(ContactInfo(whatsapp_numbers=["15551234567"]))
        assert merged.email_origin == "scraped"


class TestHandleFromUrl:
    def test_basic(self):
        assert _extract_handle_from_url("https://www.instagram.com/acme_realty/") == "acme_realty"

    def test_non_instagram_rejected(self):
        assert _extract_handle_from_url("https://facebook.com/acme") is None

    def test_non_profile_path_rejected(self):
        assert _extract_handle_from_url("https://www.instagram.com/p/abc") is None

    def test_empty_path_rejected(self):
        assert _extract_handle_from_url("https://www.instagram.com/") is None


class TestLinkedInNormalize:
    def test_company_url(self):
        assert (
            _normalize_linkedin_url("https://www.linkedin.com/company/acme/")
            == "https://linkedin.com/company/acme"
        )

    def test_strips_query(self):
        assert (
            _normalize_linkedin_url("https://www.linkedin.com/company/acme?trk=foo")
            == "https://linkedin.com/company/acme"
        )

    def test_non_linkedin_rejected(self):
        assert _normalize_linkedin_url("https://example.com/company/acme") is None

    def test_profile_not_company_rejected(self):
        assert _normalize_linkedin_url("https://www.linkedin.com/in/john") is None


class TestEmailEnricher:
    def test_infer_emails_disabled_when_validator_missing(self):
        enricher = EmailEnricher.__new__(EmailEnricher)
        enricher._available = False
        enricher._settings = None
        assert enricher.infer_emails("acme.com") == []

    def test_enrich_drops_invalid(self):
        enricher = EmailEnricher.__new__(EmailEnricher)
        enricher._available = True
        enricher._is_valid = lambda email, strict=False: email == "good@x.com"
        contact = ContactInfo(emails=["good@x.com", "bad@x.com"])
        enriched = enricher.enrich(contact)
        assert enriched.emails == ["good@x.com"]

    def test_infer_skips_empty_domain(self):
        enricher = EmailEnricher.__new__(EmailEnricher)
        enricher._available = True
        assert enricher.infer_emails("") == []