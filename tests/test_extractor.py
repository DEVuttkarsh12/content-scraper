"""Tests for core.extractor: email/phone/WhatsApp/Instagram/LinkedIn parsing."""

from core.extractor import (
    decode_cloudflare_email,
    extract_all,
    extract_cloudflare_emails,
    extract_emails,
    extract_encoded_emails,
    extract_from_html,
    extract_instagram_handles,
    extract_linkedin_urls,
    extract_phones,
    extract_whatsapp_numbers,
)


def _cf_email(email: str, key: int = 0x42) -> str:
    return f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in email)


class TestEmails:
    def test_plain_emails_extracted(self):
        assert extract_emails("reach sales@acme.com or info@acme.co.uk today") == [
            "info@acme.co.uk",
            "sales@acme.com",
        ]

    def test_dedupe_and_sort(self):
        assert extract_emails("a@x.com b@x.com a@x.com") == ["a@x.com", "b@x.com"]

    def test_noise_domains_dropped(self):
        assert extract_emails("use your@example.com or name@domain.com") == []

    def test_gov_and_mil_dropped(self):
        assert extract_emails("write mayor@city.gov.in or admin@army.mil") == []

    def test_obfuscated_at_dot(self):
        assert extract_emails("Contact john [at] agency [dot] com") == ["john@agency.com"]

    def test_obfuscated_variants(self):
        assert extract_emails("a (at) b (dot) net") == ["a@b.net"]

    def test_trailing_punctuation_stripped(self):
        assert extract_emails("Email us at sales@acme.com.") == ["sales@acme.com"]

    def test_embedded_valid_pattern_still_extracted(self):
        assert extract_emails("bad@nope@x.com") == ["nope@x.com"]

    def test_mailto_in_extract_all(self):
        info = extract_all(text="", links=["mailto:sales@acme.com?subject=Hello"])
        assert info.emails == ["sales@acme.com"]


class TestWhatsapp:
    def test_wa_me_link(self):
        assert extract_whatsapp_numbers(links=["https://wa.me/919876543210"]) == [
            "919876543210"
        ]

    def test_api_whatsapp_link(self):
        assert extract_whatsapp_numbers(
            links=['https://api.whatsapp.com/send?phone=15551234567']
        ) == ["15551234567"]

    def test_too_short_number_rejected(self):
        assert extract_whatsapp_numbers(links=["https://wa.me/12345"]) == []

    def test_from_text(self):
        assert extract_whatsapp_numbers(text="WhatsApp us: https://wa.me/15551234567") == [
            "15551234567"
        ]


class TestPhones:
    def test_us_number(self):
        assert extract_phones("Call (555) 123-4567 today") == ["5551234567"]

    def test_international_with_country_code(self):
        assert extract_phones("Reach us at +44 20 7946 0958") == ["442079460958"]

    def test_garbage_variants_rejected(self):
        assert extract_phones("see 2008 or call 0000000000 or 11111111111") == []

    def test_local_dropped_when_international_present(self):
        got = extract_phones("both +1 (555) 123-4567 and 555-123-4567")
        assert "5551234567" not in got
        assert "15551234567" in got


class TestInstagram:
    def test_link_handle(self):
        assert extract_instagram_handles(
            links=["https://www.instagram.com/acme_realty/"]
        ) == ["acme_realty"]

    def test_at_mention(self):
        assert extract_instagram_handles(text="Follow us @acme_realty") == ["acme_realty"]

    def test_photo_path_skipped(self):
        assert extract_instagram_handles(
            links=["https://www.instagram.com/p/AbCdEf/"]
        ) == []

    def test_junk_asset_name_rejected(self):
        assert extract_instagram_handles(
            links=["https://www.instagram.com/main.js/"]
        ) == []

    def test_platform_handle_noise_skipped(self):
        assert extract_instagram_handles(text="tag @instagram") == []


class TestLinkedIn:
    def test_company_url(self):
        assert extract_linkedin_urls(
            links=["https://www.linkedin.com/company/acme/"]
        ) == ["https://linkedin.com/company/acme"]

    def test_normalises_http_and_slash(self):
        assert extract_linkedin_urls(
            links=["http://linkedin.com/company/acme"]
        ) == ["https://linkedin.com/company/acme"]

    def test_both_variants_collapse(self):
        got = extract_linkedin_urls(
            links=["http://www.linkedin.com/company/acme", "https://linkedin.com/company/acme/"]
        )
        assert got == ["https://linkedin.com/company/acme"]

    def test_trailing_punctuation_stripped(self):
        assert extract_linkedin_urls(
            text="see https://www.linkedin.com/company/acme."
        ) == ["https://linkedin.com/company/acme"]


class TestCloudflare:
    def test_decode_returns_original(self):
        assert decode_cloudflare_email(_cf_email("sales@example.com")) == "sales@example.com"

    def test_decode_rejects_bad_hex(self):
        assert decode_cloudflare_email("zznothex") is None

    def test_decode_rejects_odd_length(self):
        assert decode_cloudflare_email("abc") is None

    def test_extract_from_html(self):
        html = f'<a href="/cdn-cgi/l/email-protection" data-cfemail="{_cf_email("info@acme.com")}">x</a>'
        assert extract_cloudflare_emails(html) == ["info@acme.com"]

    def test_encoded_emails(self):
        html = 'mailto:info%40acme%2Ecom and john%40acme%2Ecom'
        assert extract_encoded_emails(html) == ["info@acme.com", "john@acme.com"]

    def test_extract_from_html_combines(self):
        html = (
            f'<a data-cfemail="{_cf_email("a@acme.com")}"></a>'
            ' and b%40acme%2Ecom'
        )
        assert extract_from_html(html).emails == ["a@acme.com", "b@acme.com"]

    def test_extract_from_html_empty(self):
        assert extract_from_html("").emails == []