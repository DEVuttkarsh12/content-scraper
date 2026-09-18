"""Tests for dashboard/server.py read-side helpers (no server, no network)."""

import json

import pytest

import dashboard.server as server


class TestQuality:
    def test_email_weight(self):
        assert server.quality_score(["a@x.com"], [], [], [], []) == 17
        assert server.quality_score(["a@x.com"] * 5, [], [], [], []) == 65

    def test_label_bands(self):
        assert server.quality_label(60) == "high"
        assert server.quality_label(59) == "medium"
        assert server.quality_label(30) == "medium"
        assert server.quality_label(29) == "low"


class TestSplitAndNorm:
    def test_split_pipe(self):
        assert server._split(" a | b | c ") == ["a", "b", "c"]

    def test_split_empty(self):
        assert server._split("") == []
        assert server._split(None) == []

    def test_norm_list_string_with_pipes(self):
        assert server._norm_list("a@x.com | b@x.com") == ["a@x.com", "b@x.com"]

    def test_norm_list_single_string(self):
        assert server._norm_list("a@x.com") == ["a@x.com"]

    def test_norm_list_json_list(self):
        assert server._norm_list(["a@x.com", " b@x.com "]) == ["a@x.com", "b@x.com"]

    def test_norm_list_none(self):
        assert server._norm_list(None) == []


class TestLeadFromAny:
    def test_csv_style_row(self):
        item = {
            "business_name": "Acme",
            "niche": "real_estate",
            "website": "https://acme.com",
            "emails": "a@acme.com | b@acme.com",
            "quality_score": "74",
            "quality_label": "high",
            "email_origin": "inferred",
        }
        lead = server._lead_from_any(item)
        assert lead["emails"] == ["a@acme.com", "b@acme.com"]
        assert lead["quality_score"] == 74
        assert lead["quality_label"] == "high"
        assert lead["email_origin"] == "inferred"

    def test_missing_score_recomputed(self):
        lead = server._lead_from_any({
            "business_name": "Acme", "website": "https://acme.com",
            "emails": ["a@acme.com"],
        })
        assert lead["quality_score"] == 17
        assert lead["quality_label"] == "low"

    def test_missing_email_origin_defaults(self):
        lead = server._lead_from_any({"emails": []})
        assert lead["email_origin"] == "scraped"

    def test_bad_quality_values(self):
        lead = server._lead_from_any({"quality_score": "not-a-number"})
        assert lead["quality_score"] == 0
        assert lead["quality_label"] == "low"


class TestHostKey:
    def test_normalises(self):
        assert (
            server._host_key("https://www.Acme.com/path/")
            == "acme.com"
        )

    def test_different_paths_same_host(self):
        assert server._host_key("https://acme.com/x") == server._host_key("https://acme.com/y")

    def test_empty(self):
        assert server._host_key("") == ""


class TestParseLog:
    def test_parses_metric_lines(self):
        lines = [
            "2026-09-18 | Searching: '\"real estate\" brokerage \"contact us\"'",
            "2026-09-18 | Probing https://acme.com",
            "2026-09-18 | Probing https://other.com",
            "2026-09-18 | collected 3 qualified leads for real_estate",
        ]
        stats = server.parse_log(lines)
        assert stats["searches"] == 1
        assert stats["candidates_probed"] == 2
        assert stats["leads_collected"] == 3
        assert stats["per_niche"] == {"real_estate": 3}
        assert stats["current_query"] == '"real estate" brokerage "contact us"'
        assert stats["current_url"] == "https://other.com"

    def test_multiple_niches_summed(self):
        lines = [
            "collected 2 qualified leads for real_estate",
            "collected 4 qualified leads for saas",
        ]
        stats = server.parse_log(lines)
        assert stats["leads_collected"] == 6
        assert stats["per_niche"] == {"real_estate": 2, "saas": 4}

    def test_query_dedupe_and_tracking(self):
        lines = [
            'Searching: \'q1\'',
            'Searching: \'q2\'',
            'Searching: \'q1\'',
        ]
        stats = server.parse_log(lines)
        assert stats["queries_seen"] == ["q1", "q2"]


class TestLoadLeads:
    def test_merges_files_richest_wins(self, tmp_path, monkeypatch):
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        f1.write_text(json.dumps({"leads": [
            {"business_name": "Acme", "website": "https://acme.com",
             "emails": ["info@acme.com"], "quality_score": 17},
        ]}), encoding="utf-8")
        f2.write_text(json.dumps({"leads": [
            {"business_name": "Acme", "website": "https://www.acme.com/",
             "emails": ["info@acme.com", "sales@acme.com"], "quality_score": 29},
        ]}), encoding="utf-8")
        monkeypatch.setattr(server, "candidate_files", lambda: [f1, f2])
        leads, src = server.load_leads()
        assert len(leads) == 1
        assert leads[0]["emails"] == ["info@acme.com", "sales@acme.com"]

    def test_empty_when_no_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(server, "candidate_files", lambda: [])
        leads, src = server.load_leads()
        assert leads == []
        assert src is None

    def test_skips_corrupt_file(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.csv"
        bad.write_text("garbage,,,", encoding="utf-8")
        monkeypatch.setattr(server, "candidate_files", lambda: [bad])
        leads, _ = server.load_leads()
        assert leads == []