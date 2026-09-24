"""Tests for core.models: ContactInfo, Lead, quality scoring, serialization."""

from core.models import CSV_HEADERS, ContactInfo, Lead


class TestContactInfo:
    def test_has_anything_empty(self):
        assert not ContactInfo().has_anything

    def test_has_anything_with_contact(self):
        assert ContactInfo(emails=["a@b.com"]).has_anything
        assert ContactInfo(phones=["123"]).has_anything

    def test_default_origin_scraped(self):
        assert ContactInfo().email_origin == "scraped"


class TestLead:
    def test_from_contact_copies_origin(self):
        info = ContactInfo(emails=["a@b.com"], email_origin="inferred")
        lead = Lead.from_contact("Acme", "saas", "https://acme.com", info)
        assert lead.email_origin == "inferred"
        assert lead.emails == ["a@b.com"]
        assert lead.source_query is None

    def test_from_contact_with_query(self):
        info = ContactInfo(emails=["a@b.com"])
        lead = Lead.from_contact("Acme", "saas", "https://acme.com", info, "seed")
        assert lead.source_query == "seed"

    def test_has_contact(self):
        assert not Lead("X", "saas", "https://x.com").has_contact
        assert Lead("X", "saas", "https://x.com", linkedin_urls=["https://linkedin.com/company/x"]).has_contact

    def test_quality_bonus_for_email(self):
        one_email = Lead("A", "saas", "https://a.com", emails=["info@a.com"])
        assert one_email.quality_score == 17

    def test_guessed_mailboxes_do_not_get_scraped_email_score(self):
        lead = Lead("A", "saas", "https://a.com", emails=["info@a.com", "sales@a.com"],
                    email_origin="inferred")
        assert lead.quality_score == 2

    def test_quality_band_boundaries(self):
        def score_label(emails=0, wa=0, ig=0, li=0, ph=0):
            lead = Lead(
                "A", "saas", "https://a.com",
                emails=["e@a.com"] * emails,
                whatsapp_numbers=[str(i) for i in range(wa)],
                instagram_handles=[f"h{i}" for i in range(ig)],
                linkedin_urls=[f"https://linkedin.com/company/x{i}" for i in range(li)],
                phones=[str(i) for i in range(ph)],
            )
            return lead.quality_score, lead.quality_label

        assert score_label(emails=0)[1] == "low"
        assert score_label(emails=1, wa=1) == (30, "medium")
        assert score_label(emails=5) == (65, "high")
        assert score_label(emails=1, wa=1, ig=2, li=2, ph=2) == (52, "medium")
        assert score_label(emails=5, wa=3, ig=3, li=3, ph=3) == (100, "high")

    def test_quality_capped_at_100(self):
        lead = Lead(
            "A", "saas", "https://a.com",
            emails=[f"e{i}@a.com" for i in range(20)],
            whatsapp_numbers=[str(i) for i in range(20)],
        )
        assert lead.quality_score <= 100

    def test_to_dict_shape(self):
        lead = Lead("Acme", "saas growth", "https://acme.com", emails=["a@b.com"])
        d = lead.to_dict()
        assert d["emails"] == ["a@b.com"]
        assert d["email_origin"] == "scraped"
        assert d["quality_label"] == lead.quality_label
        assert d["quality_score"] == lead.quality_score

    def test_flat_row_matches_headers(self):
        lead = Lead("Acme", "saas", "https://acme.com", emails=["a@b.com"])
        row = lead.flat_row()
        assert len(row) == len(CSV_HEADERS)
        assert dict(zip(CSV_HEADERS, row))["emails"] == "a@b.com"

    def test_flat_row_joins_multi_values(self):
        lead = Lead("Acme", "saas", "https://acme.com",
                    emails=["a@b.com", "c@b.com"], phones=["123", "456"])
        row = dict(zip(CSV_HEADERS, lead.flat_row()))
        assert row["emails"] == "a@b.com | c@b.com"
        assert row["phones"] == "123 | 456"
