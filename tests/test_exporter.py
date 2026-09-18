"""Tests for output.exporter: CSV/JSON round-trips, merge, dedupe, purge."""

import json

import pytest

from core.models import Lead
from output.exporter import (
    dedupe_leads,
    export_leads,
    load_leads,
    merge_leads,
    purge_invalid,
)


def _make_lead(name="Acme Realty", site="https://acme.com", emails=None,
               wa=None, ig=None, li=None, ph=None, niche="real_estate"):
    return Lead(
        business_name=name,
        niche=niche,
        website=site,
        emails=emails or [],
        whatsapp_numbers=wa or [],
        instagram_handles=ig or [],
        linkedin_urls=li or [],
        phones=ph or [],
    )


class TestPurge:
    def test_denied_host_purged(self):
        leads = [_make_lead(site="https://zillow.com/x"), _make_lead()]
        kept = purge_invalid(leads)
        assert len(kept) == 1
        assert kept[0].website == "https://acme.com"

    def test_provider_name_purged(self):
        leads = [_make_lead(name="Emailmovers | Email Marketing | Data")]
        assert purge_invalid(leads) == []


class TestMerge:
    def test_richer_version_wins(self):
        base = _make_lead(site="https://www.acme.com/", emails=["info@acme.com"])
        rich = _make_lead(site="https://acme.com", emails=["info@acme.com", "sales@acme.com"])
        merged = merge_leads([base], [rich])
        assert len(merged) == 1
        assert merged[0].emails == ["info@acme.com", "sales@acme.com"]

    def test_distinct_domains_kept(self):
        a = _make_lead(site="https://acme.com")
        b = _make_lead(site="https://other.com")
        assert len(merge_leads([a], [b])) == 2

    def test_sorted_best_first(self):
        low_q = _make_lead()
        high_q = _make_lead(site="https://high.com", emails=["a@high.com", "b@high.com"])
        merged = merge_leads([low_q, high_q], [])
        assert merged[0].website == "https://high.com"


class TestDedupe:
    def test_dedupe_by_website(self):
        a = _make_lead(site="https://acme.com")
        b = _make_lead(site="https://acme.com")
        assert len(dedupe_leads([a, b])) == 1

    def test_case_insensitive(self):
        a = _make_lead(site="https://acme.com")
        b = _make_lead(site="https://ACME.COM/")
        assert len(dedupe_leads([a, b])) == 1


class TestRoundTrip:
    def test_csv_round_trip(self, tmp_path):
        out = tmp_path / "leads.csv"
        lead = _make_lead(emails=["info@acme.com", "sales@acme.com"], wa=["15551234567"])
        export_leads([lead], str(out), merge=False)
        loaded = load_leads(str(out))
        assert len(loaded) == 1
        row = loaded[0]
        assert row.emails == ["info@acme.com", "sales@acme.com"]
        assert row.whatsapp_numbers == ["15551234567"]
        assert row.email_origin == "scraped"

    def test_json_round_trip(self, tmp_path):
        out = tmp_path / "leads.json"
        lead = _make_lead(emails=["info@acme.com"], ig=["acme"])
        export_leads([lead], str(out), merge=False)
        loaded = load_leads(str(out))
        assert len(loaded) == 1
        assert loaded[0].instagram_handles == ["acme"]
        assert loaded[0].quality_label == "low"

    def test_merge_into_existing_file(self, tmp_path):
        out = tmp_path / "leads.csv"
        export_leads([_make_lead(site="https://acme.com", emails=["info@acme.com"])],
                     str(out), merge=False)
        export_leads([_make_lead(site="https://new.com", emails=["new@new.com"]),
                      _make_lead(site="https://acme.com", emails=["info@acme.com", "sales@acme.com"])],
                     str(out), merge=True)
        loaded = load_leads(str(out))
        by_site = {l.website: l for l in loaded}
        assert "https://new.com" in by_site
        assert by_site["https://acme.com"].emails == ["info@acme.com", "sales@acme.com"]

    def test_no_merge_overwrites(self, tmp_path):
        out = tmp_path / "leads.csv"
        export_leads([_make_lead(site="https://old.com")], str(out), merge=False)
        export_leads([_make_lead(site="https://new.com")], str(out), merge=False)
        loaded = load_leads(str(out))
        assert [l.website for l in loaded] == ["https://new.com"]

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_leads(str(tmp_path / "nope.csv")) == []

    def test_json_payload_structure(self, tmp_path):
        out = tmp_path / "leads.json"
        export_leads([_make_lead(emails=["a@acme.com"])], str(out), merge=False)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["lead_count"] == 1
        assert payload["leads"][0]["emails"] == ["a@acme.com"]

    def test_corrupt_json_returns_empty(self, tmp_path):
        out = tmp_path / "leads.json"
        out.write_text("{ definitely not json", encoding="utf-8")
        assert load_leads(str(out)) == []

    def test_malformed_csv_does_not_raise(self, tmp_path):
        out = tmp_path / "leads.csv"
        out.write_text("not,valid,csv\nno-closing-quote\n", encoding="utf-8")
        loaded = load_leads(str(out))
        assert isinstance(loaded, list)


class TestScrapedAtPreserved:
    def test_scraped_at_round_trip(self, tmp_path):
        lead = _make_lead()
        lead.scraped_at = "2026-01-02T03:04:05+00:00"
        out = tmp_path / "leads.csv"
        export_leads([lead], str(out), merge=False)
        assert load_leads(str(out))[0].scraped_at == "2026-01-02T03:04:05+00:00"